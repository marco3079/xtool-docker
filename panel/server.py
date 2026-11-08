#!/usr/bin/env python3
"""xtool web panel: runs xtool commands in a PTY and exposes them over HTTP.

Every command becomes a "job" with its own pseudo-terminal, so interactive
prompts (login mode, Apple ID, 2FA code, Xcode.xip path) work from the browser:
the page polls the job output and posts lines back as input.
"""
import json
import os
import pty
import re
import select
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

PORT = int(os.environ.get("PANEL_PORT", "8080"))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WORK = os.environ.get("XTOOL_WORK", "/work")
ROOTS = {"work": WORK, "downloads": "/downloads"}
MAX_OUT = 2_000_000  # keep the last ~2 MB of output per job

JOBS = {}
LOCK = threading.Lock()


class Job:
    def __init__(self, argv, cwd, title):
        self.id = uuid.uuid4().hex[:10]
        self.argv = argv
        self.cwd = cwd
        self.title = title
        self.started = time.time()
        self.ended = None
        self.code = None
        self.buf = bytearray()
        self.trimmed = 0  # bytes dropped from the front of buf
        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                os.chdir(cwd)
                env = dict(os.environ, TERM="xterm-256color", COLUMNS="120", LINES="40")
                os.execvpe(argv[0], argv, env)
            except Exception as e:  # noqa
                os.write(2, f"falha ao iniciar: {e}\n".encode())
                os._exit(127)
        self.pid, self.fd = pid, fd
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while True:
            try:
                r, _, _ = select.select([self.fd], [], [], 0.5)
                if r:
                    data = os.read(self.fd, 65536)
                    if not data:
                        break
                    with LOCK:
                        self.buf += data
                        if len(self.buf) > MAX_OUT:
                            cut = len(self.buf) - MAX_OUT
                            del self.buf[:cut]
                            self.trimmed += cut
            except OSError:
                break
        _, status = os.waitpid(self.pid, 0)
        self.code = os.waitstatus_to_exitcode(status)
        self.ended = time.time()
        try:
            os.close(self.fd)
        except OSError:
            pass

    def write(self, text):
        if self.ended is None:
            os.write(self.fd, text.encode())

    def stop(self):
        if self.ended is None:
            try:
                pg = os.getpgid(self.pid)
                for sig in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM, signal.SIGKILL):
                    os.killpg(pg, sig)
                    time.sleep(0.7)
                    if self.ended is not None:
                        break
            except ProcessLookupError:
                pass

    def info(self):
        return {
            "id": self.id, "title": self.title, "argv": self.argv, "cwd": self.cwd,
            "started": self.started, "ended": self.ended, "code": self.code,
            "running": self.ended is None,
        }


def safe_path(root_key, rel=""):
    base = os.path.realpath(ROOTS.get(root_key, WORK))
    p = os.path.realpath(os.path.join(base, rel.lstrip("/")))
    if p != base and not p.startswith(base + os.sep):
        raise ValueError("caminho fora da pasta permitida")
    return p


def quick(argv, timeout=20, cwd=None):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, cwd=cwd)
        return (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa
        return f"erro: {e}"


def usbmux_ok():
    addr = os.environ.get("USBMUXD_SOCKET_ADDRESS")
    if not addr:
        return os.path.exists("/var/run/usbmuxd")
    import socket
    host, _, port = addr.rpartition(":")
    try:
        socket.create_connection((host, int(port)), timeout=2).close()
        return True
    except OSError:
        return False


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def status():
    xt = quick(["xtool", "--version"])
    sw = quick(["swift", "--version"]).splitlines()
    auth = ANSI.sub("", quick(["xtool", "auth", "status"]))
    sdk = ANSI.sub("", quick(["xtool", "sdk", "status"]))
    du = shutil.disk_usage(WORK)
    return {
        "xtool": xt, "swift": sw[0] if sw else "",
        "auth": auth, "sdk": sdk,
        "disk": {"free": du.free, "total": du.total},
        "usbmuxd": usbmux_ok(),
        "usbmuxdVia": os.environ.get("USBMUXD_SOCKET_ADDRESS") or "/var/run/usbmuxd",
        "downloads": os.path.isdir("/downloads"),
    }


def list_dir(root_key, rel):
    p = safe_path(root_key, rel)
    out = []
    for name in sorted(os.listdir(p), key=str.lower):
        if name.startswith("."):
            continue
        fp = os.path.join(p, name)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        out.append({"name": name, "dir": os.path.isdir(fp), "size": st.st_size, "mtime": st.st_mtime})
    return out


def projects():
    res = []
    if not os.path.isdir(WORK):
        return res
    for name in sorted(os.listdir(WORK), key=str.lower):
        d = os.path.join(WORK, name)
        if os.path.isfile(os.path.join(d, "Package.swift")):
            arts = []
            xd = os.path.join(d, "xtool")
            if os.path.isdir(xd):
                for a in os.listdir(xd):
                    if a.endswith((".ipa", ".app")):
                        arts.append(f"{name}/xtool/{a}")
            res.append({
                "name": name,
                "hasToml": os.path.isfile(os.path.join(d, "xtool.yml")),
                "artifacts": sorted(arts),
                "mtime": os.stat(d).st_mtime,
            })
    return res


# Commands the page may ask for. Each maps a name to a function returning argv.
def build_cmd(action, a):
    q = lambda k, d="": str(a.get(k, d)).strip()  # noqa
    dev_sel = []
    if q("udid"):
        dev_sel += ["--udid", q("udid")]
    conn = q("conn", "all")
    if conn in ("usb", "network", "all"):
        dev_sel += [f"--{conn}"]
    cmds = {
        "setup": lambda: ["xtool", "setup"],
        "auth.login": lambda: ["xtool", "auth", "login"] + (["--mode", q("mode")] if q("mode") in ("key", "password") else [])
                              + (["--username", q("username")] if q("username") else []),
        "auth.logout": lambda: ["xtool", "auth", "logout"] + (["--reset-2fa"] if a.get("reset2fa") else []),
        "auth.status": lambda: ["xtool", "auth", "status"],
        "sdk.install": lambda: ["xtool", "sdk", "install", q("path")] + (["--slim"] if a.get("slim") else []),
        "sdk.update": lambda: ["xtool", "sdk", "update"],
        "sdk.remove": lambda: ["xtool", "sdk", "remove"],
        "sdk.status": lambda: ["xtool", "sdk", "status"],
        "sdk.build": lambda: ["xtool", "sdk", "build", q("path"), q("out", "/work/sdk-out")],
        "new": lambda: ["xtool", "new", q("name")] + (["--skip-setup"] if a.get("skipSetup", True) else []),
        "dev.build": lambda: ["xtool", "dev", "build", "-c", q("config", "debug")]
                             + (["--sign"] if a.get("sign") else []) + (["--ipa"] if a.get("ipa") else []),
        "dev.run": lambda: ["xtool", "dev", "run", "-c", q("config", "debug")] + dev_sel,
        "dev.xcode": lambda: ["xtool", "dev", "generate-xcode-project"],
        "devices": lambda: ["xtool", "devices", f"--{conn}", "--no-wait"],
        "install": lambda: ["xtool", "install"] + dev_sel + [q("path")],
        "uninstall": lambda: ["xtool", "uninstall"] + dev_sel + [q("bundle")],
        "launch": lambda: ["xtool", "launch"] + dev_sel + [q("bundle")] + shlex.split(q("args")),
        "ds": lambda: ["xtool", "ds", q("sub")] + shlex.split(q("args")),
        "shell": lambda: ["bash", "-lc", q("cmd")],
        "help": lambda: ["xtool"] + shlex.split(q("sub")) + ["--help"],
    }
    if action not in cmds:
        raise ValueError(f"ação desconhecida: {action}")
    argv = cmds[action]()
    if any(x == "" for x in argv):
        raise ValueError("preencha os campos obrigatórios")
    return argv


class H(BaseHTTPRequestHandler):
    server_version = "xtool-panel"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, path, ctype=None, download=False):
        if not os.path.isfile(path):
            return self._json({"error": "não encontrado"}, 404)
        self.send_response(200)
        if not ctype:
            ext = path.rsplit(".", 1)[-1].lower()
            ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css",
                     "svg": "image/svg+xml", "png": "image/png"}.get(ext, "application/octet-stream")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(path)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._file(os.path.join(STATIC, "index.html"))
            if u.path.startswith("/static/"):
                return self._file(os.path.join(STATIC, os.path.basename(u.path)))
            if u.path == "/api/status":
                return self._json(status())
            if u.path == "/api/projects":
                return self._json(projects())
            if u.path == "/api/files":
                return self._json(list_dir(qs.get("root", "work"), qs.get("path", "")))
            if u.path == "/api/download":
                return self._file(safe_path(qs.get("root", "work"), qs.get("path", "")), download=True)
            if u.path == "/api/jobs":
                with LOCK:
                    return self._json(sorted([j.info() for j in JOBS.values()], key=lambda x: -x["started"]))
            m = re.fullmatch(r"/api/jobs/(\w+)", u.path)
            if m:
                j = JOBS.get(m.group(1))
                if not j:
                    return self._json({"error": "job não existe"}, 404)
                off = int(qs.get("offset", 0))
                with LOCK:
                    start = max(0, off - j.trimmed)
                    chunk = bytes(j.buf[start:])
                    nxt = j.trimmed + len(j.buf)
                return self._json({**j.info(), "out": chunk.decode("utf-8", "replace"), "offset": nxt})
            return self._json({"error": "rota não existe"}, 404)
        except Exception as e:  # noqa
            return self._json({"error": str(e)}, 400)

    def do_POST(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/run":
                b = self._body()
                argv = build_cmd(b.get("action", ""), b.get("args", {}))
                cwd = safe_path("work", b.get("project", "")) if b.get("project") else WORK
                j = Job(argv, cwd, b.get("title") or " ".join(argv))
                JOBS[j.id] = j
                return self._json(j.info())
            m = re.fullmatch(r"/api/jobs/(\w+)/(input|stop)", u.path)
            if m:
                j = JOBS.get(m.group(1))
                if not j:
                    return self._json({"error": "job não existe"}, 404)
                if m.group(2) == "input":
                    j.write(self._body().get("text", ""))
                else:
                    threading.Thread(target=j.stop, daemon=True).start()
                return self._json({"ok": True})
            if u.path == "/api/jobs/clear":
                for k in [k for k, j in JOBS.items() if j.ended]:
                    del JOBS[k]
                return self._json({"ok": True})
            if u.path == "/api/upload":
                # raw body upload: /api/upload?root=work&path=uploads/app.ipa
                dest = safe_path(qs.get("root", "work"), unquote(qs.get("path", "")))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                left = int(self.headers.get("Content-Length") or 0)
                with open(dest, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                return self._json({"ok": True, "path": dest})
            if u.path == "/api/delete":
                b = self._body()
                p = safe_path(b.get("root", "work"), b.get("path", ""))
                if p == os.path.realpath(ROOTS.get(b.get("root", "work"), WORK)):
                    raise ValueError("não dá para apagar a pasta raiz")
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                return self._json({"ok": True})
            return self._json({"error": "rota não existe"}, 404)
        except Exception as e:  # noqa
            return self._json({"error": str(e)}, 400)


if __name__ == "__main__":
    os.makedirs(WORK, exist_ok=True)
    print(f"xtool panel em http://0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
