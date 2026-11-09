#!/usr/bin/env python3
"""xtool web panel: runs xtool commands in a PTY and exposes them over HTTP.

Every command becomes a "job" with its own pseudo-terminal, so interactive
prompts (login mode, Apple ID, 2FA code, Xcode.xip path) work from the browser:
the page polls the job output and posts lines back as input.
"""
import base64
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

import ai
import android
import builds
import dbdetect
import dbenv
import github
import lojas
import lojas_io
import pc
import steam
import store
import versions
from asc import ASC, AscError
from play import Play, PlayError

PANEL_PY = os.path.dirname(os.path.abspath(__file__))

VERSION = "1.5.0"
PORT = int(os.environ.get("PANEL_PORT", "8080"))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WORK = os.environ.get("XTOOL_WORK", "/work")
ANDROID_HOME = os.environ.get("ANDROID_HOME", "/opt/android-sdk")
ROOTS = {"work": WORK, "downloads": "/downloads"}
MAX_OUT = 2_000_000  # keep the last ~2 MB of output per job

JOBS = {}
LOCK = threading.Lock()


class Job:
    def __init__(self, argv, cwd, title, env=None):
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
                env = dict(os.environ, TERM="xterm-256color", COLUMNS="120", LINES="40", **(env or {}))
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
        try:  # a login/logout may have changed the active account's data
            accounts_sync()
        except Exception:  # noqa
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


# ---------------------------------------------------------------------------
# Saved state: Apple accounts and devices
#
# xtool keeps one login in ~/.config/xtool/data. Each account gets its own copy
# of that folder under ~/.config/xtool-panel/accounts/<id>; switching accounts
# saves the live folder into the current profile and restores the chosen one.
# The iOS SDK lives elsewhere (~/.swiftpm) and is shared by all accounts.
# ---------------------------------------------------------------------------
XDATA = os.path.expanduser("~/.config/xtool/data")
PANEL_DIR = os.path.expanduser("~/.config/xtool-panel")
ACC_DIR = os.path.join(PANEL_DIR, "accounts")
ACC_FILE = os.path.join(PANEL_DIR, "accounts.json")
DEV_FILE = os.path.join(PANEL_DIR, "devices.json")
STATE_LOCK = threading.RLock()


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _copy_dir(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        os.makedirs(dst, exist_ok=True)


def parse_auth(text):
    text = ANSI.sub("", text)
    logged = text.lower().startswith("logged in")
    m_id = re.search(r"Apple ID:\s*(\S+)", text)
    m_team = re.search(r"Team ID:\s*(\S+)", text)
    m_exp = re.search(r"Token expiry:\s*(.+)", text)
    return {
        "loggedIn": logged,
        "appleId": m_id.group(1) if m_id else "",
        "teamId": m_team.group(1) if m_team else "",
        "expiry": m_exp.group(1).strip() if m_exp else "",
    }


def accounts_state():
    st = _load(ACC_FILE, None)
    if st is None:  # first run: adopt whatever login already exists
        st = {"active": None, "accounts": []}
        info = parse_auth(quick(["xtool", "auth", "status"]))
        if info["loggedIn"]:
            acc = {"id": uuid.uuid4().hex[:8], "label": "Conta principal", **info}
            st = {"active": acc["id"], "accounts": [acc]}
            _copy_dir(XDATA, os.path.join(ACC_DIR, acc["id"]))
        _save(ACC_FILE, st)
    return st


def accounts_sync():
    """Copy the live xtool login into the active profile and refresh its info."""
    with STATE_LOCK:
        st = accounts_state()
        acc = next((a for a in st["accounts"] if a["id"] == st["active"]), None)
        if not acc:
            # logged in with no account selected (e.g. plain "xtool setup"): save it
            info = parse_auth(quick(["xtool", "auth", "status"]))
            if not info["loggedIn"]:
                return st
            acc = {"id": uuid.uuid4().hex[:8], "label": info["appleId"] or "Conta", **info}
            st["accounts"].append(acc)
            st["active"] = acc["id"]
        _copy_dir(XDATA, os.path.join(ACC_DIR, acc["id"]))
        acc.update(parse_auth(quick(["xtool", "auth", "status"])))
        _save(ACC_FILE, st)
        return st


def any_running():
    return any(j.ended is None for j in JOBS.values())


def accounts_switch(acc_id):
    with STATE_LOCK:
        if any_running():
            raise ValueError("espere as tarefas em andamento terminarem antes de trocar de conta")
        st = accounts_sync()
        if not any(a["id"] == acc_id for a in st["accounts"]):
            raise ValueError("conta não existe")
        src = os.path.join(ACC_DIR, acc_id)
        _copy_dir(src, XDATA)
        st["active"] = acc_id
        _save(ACC_FILE, st)
        return accounts_sync()


def accounts_add(label):
    with STATE_LOCK:
        if any_running():
            raise ValueError("espere as tarefas em andamento terminarem")
        st = accounts_sync()
        acc = {"id": uuid.uuid4().hex[:8], "label": label or "Nova conta",
               "loggedIn": False, "appleId": "", "teamId": "", "expiry": ""}
        os.makedirs(os.path.join(ACC_DIR, acc["id"]), exist_ok=True)  # empty = logged out
        st["accounts"].append(acc)
        _save(ACC_FILE, st)
        return accounts_switch(acc["id"])


def accounts_remove(acc_id):
    with STATE_LOCK:
        if any_running():
            raise ValueError("espere as tarefas em andamento terminarem")
        st = accounts_sync()
        st["accounts"] = [a for a in st["accounts"] if a["id"] != acc_id]
        shutil.rmtree(os.path.join(ACC_DIR, acc_id), ignore_errors=True)
        store.asc_key_remove(acc_id)
        store.apps_forget(acc_id)
        if st["active"] == acc_id:  # removed the one in use: log the live folder out
            shutil.rmtree(XDATA, ignore_errors=True)
            st["active"] = None
            _save(ACC_FILE, st)
            if st["accounts"]:
                return accounts_switch(st["accounts"][0]["id"])
        _save(ACC_FILE, st)
        return st


def accounts_rename(acc_id, label):
    with STATE_LOCK:
        st = accounts_state()
        for a in st["accounts"]:
            if a["id"] == acc_id:
                a["label"] = label
        _save(ACC_FILE, st)
        return st


def devices_list():
    return _load(DEV_FILE, [])


# Background watcher: which devices are reachable right now (udid -> "usb"/"network").
ONLINE = {"devices": {}, "service": False, "checked": 0}


def _watch_devices():
    while True:
        try:
            service = usbmux_ok()
            found = {}
            if service:
                for f in devices_detect()["found"]:
                    # a device can show up on both; prefer the cable
                    if found.get(f["udid"].lower()) != "usb":
                        found[f["udid"].lower()] = f["conn"]
            ONLINE.update(devices=found, service=service, checked=time.time())
        except Exception:  # noqa
            pass
        time.sleep(5)


def devices_with_status():
    out = []
    for d in devices_list():
        out.append({**d, "conn": ONLINE["devices"].get(d["udid"].lower())})
    return {"devices": out, "service": ONLINE["service"], "checked": ONLINE["checked"]}


def devices_save(d):
    with STATE_LOCK:
        devs = devices_list()
        udid = str(d.get("udid", "")).strip()
        name = str(d.get("name", "")).strip() or udid
        if not re.fullmatch(r"[0-9A-Fa-f-]{20,50}", udid):
            raise ValueError("UDID inválido")
        cur = next((x for x in devs if x["id"] == d.get("id")), None) \
            or next((x for x in devs if x["udid"].lower() == udid.lower()), None)
        if cur is None:
            cur = {"id": uuid.uuid4().hex[:8]}
            devs.append(cur)
        cur.update({"name": name, "udid": udid, "notes": str(d.get("notes", "")).strip()})
        if d.get("default") or len(devs) == 1:
            for x in devs:
                x["default"] = x is cur
        _save(DEV_FILE, devs)
        return devs


def devices_remove(dev_id):
    with STATE_LOCK:
        devs = [x for x in devices_list() if x["id"] != dev_id]
        if devs and not any(x.get("default") for x in devs):
            devs[0]["default"] = True
        _save(DEV_FILE, devs)
        return devs


def devices_detect():
    out = ANSI.sub("", quick(["xtool", "devices", "--all", "--no-wait"], timeout=15))
    saved = {x["udid"].lower(): x for x in devices_list()}
    found = []
    for line in out.splitlines():
        m = re.match(r"(.+?)\s*\[(\w+)\]:\s*([0-9A-Fa-f-]{20,50})\s*$", line.strip())
        if m:
            udid = m.group(3)
            found.append({"name": m.group(1), "conn": m.group(2), "udid": udid,
                          "savedAs": saved.get(udid.lower(), {}).get("name")})
    return {"found": found, "raw": out}


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


# ---- xtool updates: newer versions are installed into the volume (/root/.xtool/<ver>)
XTOOL_HOME = os.path.expanduser("~/.xtool")
_latest = {"at": 0, "tag": None}


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def xtool_installed():
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", quick(["xtool", "--version"]))
    return m.group(1) if m else ""


BASE_XTOOL = "/opt/xtool"  # baked into the image from base/ in the repository
_base_ver = {}


def xtool_source(path):
    """"base" = the xtool shipped in the repository; "xtool-org" = downloaded from GitHub by the panel."""
    if not path:
        return ""
    return "base" if os.path.realpath(path).startswith(BASE_XTOOL + os.sep) else "xtool-org"


def xtool_versions():
    """Every xtool available: the base one plus updates kept in the volume (~/.xtool/<version>)."""
    if "v" not in _base_ver:
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", quick([os.path.join(BASE_XTOOL, "AppRun"), "--version"]))
        _base_ver["v"] = m.group(1) if m else ""
    active = os.path.realpath(shutil.which("xtool") or "")
    out = [{"version": _base_ver["v"], "source": "base",
            "active": active.startswith(BASE_XTOOL + os.sep)}]
    try:
        for d in sorted(os.listdir(XTOOL_HOME), key=_vtuple):
            p = os.path.join(XTOOL_HOME, d)
            if d != "current" and not d.endswith(".tmp") and os.path.isdir(p) and not os.path.islink(p):
                out.append({"version": d, "source": "xtool-org", "active": active.startswith(p + os.sep)})
    except OSError:
        pass
    return out


def xtool_latest(force=False, wait=True):
    """Newest xtool on GitHub — optional: the panel works without it (offline it stays None).
    With wait=False a stale value is refreshed in the background instead of blocking."""
    if not (force or time.time() - _latest["at"] > 3600):
        return _latest["tag"]
    if not wait:
        if not _latest.get("busy"):
            _latest["busy"] = True
            threading.Thread(target=lambda: (xtool_latest(force=True), _latest.update(busy=False)),
                             daemon=True).start()
        return _latest["tag"]
    try:
        import urllib.request
        req = urllib.request.Request("https://api.github.com/repos/xtool-org/xtool/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "xtool-painel"})
        with urllib.request.urlopen(req, timeout=10) as r:
            _latest["tag"] = json.load(r).get("tag_name", "").lstrip("v")
        _latest["at"] = time.time()
    except Exception:  # noqa — offline or rate-limited: try again in 10 min
        _latest["at"] = time.time() - 3000
    return _latest["tag"]


def xtool_activate_saved():
    """On start, prefer an xtool updated from the panel over the one baked into the image."""
    cur = os.path.join(XTOOL_HOME, "current", "AppRun")
    if os.path.exists(cur):
        img = os.path.realpath("/usr/local/bin/xtool")
        base = quick(["/opt/xtool/AppRun", "--version"])
        saved = quick([cur, "--version"])
        if _vtuple(saved) > _vtuple(base) and img != os.path.realpath(cur):
            subprocess.run(["ln", "-sf", cur, "/usr/local/bin/xtool"])


XTOOL_UPDATE = r'''set -e
V="$VER"; D="$HOME/.xtool/$V"
echo "Baixando xtool $V…"
rm -rf "$D.tmp"; mkdir -p "$D.tmp"; cd "$D.tmp"
curl -fL --progress-bar "https://github.com/xtool-org/xtool/releases/download/$V/xtool-$(uname -m).AppImage" -o xtool.AppImage
chmod +x xtool.AppImage
./xtool.AppImage --appimage-extract >/dev/null
rm -rf "$D"; mv squashfs-root "$D"; cd ..; rm -rf "$D.tmp"
ln -sfn "$D" "$HOME/.xtool/current"
ln -sf "$HOME/.xtool/current/AppRun" /usr/local/bin/xtool
echo; xtool --version
echo "✔ xtool atualizado. A versão nova fica salva no volume e continua valendo após reiniciar."'''


def status():
    xt = quick(["xtool", "--version"])
    sw = quick(["swift", "--version"]).splitlines()
    auth = ANSI.sub("", quick(["xtool", "auth", "status"]))
    sdk = ANSI.sub("", quick(["xtool", "sdk", "status"]))
    du = shutil.disk_usage(WORK)
    jv = quick(["java", "-version"]) if shutil.which("java") else ""
    return {
        "xtool": xt, "swift": sw[0] if sw else "",
        "xtoolSource": xtool_source(os.path.realpath(shutil.which("xtool") or "")),
        "xtoolVersions": xtool_versions(),
        "xtoolLatest": xtool_latest(wait=False),
        "xtoolUpdate": bool(xtool_latest(wait=False)) and _vtuple(xtool_latest(wait=False)) > _vtuple(xt),
        "auth": auth, "sdk": sdk,
        "disk": {"free": du.free, "total": du.total},
        "usbmuxd": usbmux_ok(),
        "usbmuxdVia": os.environ.get("USBMUXD_SOCKET_ADDRESS") or "/var/run/usbmuxd",
        "downloads": os.path.isdir("/downloads"),
        "android": {
            "sdk": os.path.isdir(ANDROID_HOME),
            "java": jv.splitlines()[0] if jv else "",
            "node": quick(["node", "--version"]) if shutil.which("node") else "",
            "adb": shutil.which("adb") is not None,
        },
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


PULL_STATE = {}  # projeto -> último resultado do pull automático {"state","pulled","message","at"}
PULL_LOCK = threading.Lock()


FETCH_MAX_AGE = 1200  # s: um "fetching" mais antigo que isso é tratado como travado


def _project_dir(name):
    """Pasta do projeto dentro de WORK ('' se o nome sai da pasta de trabalho)."""
    base = os.path.realpath(WORK)
    d = os.path.realpath(os.path.join(WORK, name)) if name else ""
    return d if d and d.startswith(base + os.sep) else ""


def _pull_prepare(name):
    """Confere se o pull do projeto pode começar. Se pode, marca o estado 'fetching' (sob o lock).
    Devolve (motivo ou None, pasta, usuário do GitHub)."""
    d = _project_dir(name)
    if not d:
        return "projeto não encontrado", d, None
    if not os.path.isdir(os.path.join(d, ".git")):
        return "o projeto não tem repositório git", d, None
    user = store.project_meta(name).get("ghUser")
    if not user:
        return "o projeto não tem conta do GitHub vinculada", d, None
    with LOCK:
        busy = any(j.ended is None and j.cwd and os.path.realpath(j.cwd) == os.path.realpath(d)
                   for j in JOBS.values())
    if busy:  # uma tarefa mexe nesta pasta agora
        return "há uma tarefa rodando neste projeto", d, user
    with PULL_LOCK:  # um fetch por projeto
        cur = PULL_STATE.get(name) or {}
        if cur.get("state") == "fetching" and time.time() - cur.get("at", 0) < FETCH_MAX_AGE:
            return "já está baixando atualizações", d, user
        PULL_STATE[name] = {"state": "fetching", "pulled": 0, "progress": None,
                            "message": "baixando atualizações…", "at": time.time()}
    return None, d, user


def _pull_fetch(name, d, user):
    """Roda o fetch/fast-forward e grava o resultado final (substitui o 'fetching')."""
    try:
        try:
            tok = github.token(user)
        except ValueError as e:
            res = {"state": "error", "pulled": 0, "message": str(e)}
        else:
            def on_progress(prog):
                with PULL_LOCK:
                    cur = PULL_STATE.get(name)
                    if cur and cur.get("state") == "fetching":
                        PULL_STATE[name] = {**cur, "progress": prog}
            res = github.auto_pull(d, tok, on_progress=on_progress)
        with PULL_LOCK:  # o resultado final zera o progresso
            PULL_STATE[name] = {**res, "progress": None, "at": time.time()}
    except Exception as e:  # noqa
        with PULL_LOCK:
            PULL_STATE[name] = {"state": "error", "pulled": 0, "progress": None,
                                "message": str(e), "at": time.time()}


def auto_pull_one(name, force=False):
    """Pull automático de um projeto (síncrono). 'force' é reservado: hoje não muda as regras."""
    reason, d, user = _pull_prepare(name)
    if reason:
        return {"started": False, "reason": reason}
    _pull_fetch(name, d, user)
    return {"started": True, "reason": ""}


def auto_pull_all():
    """Atualiza do GitHub, só por fast-forward, os projetos com .git e conta GitHub. Um erro não derruba os outros."""
    if not os.path.isdir(WORK):
        return
    for name in sorted(os.listdir(WORK), key=str.lower):
        try:
            auto_pull_one(name)
        except Exception as e:  # noqa
            with PULL_LOCK:
                PULL_STATE[name] = {"state": "error", "pulled": 0, "progress": None,
                                    "message": str(e), "at": time.time()}


def project_pull(b):
    """Botão 'verificar agora': dispara o pull do projeto numa thread e responde na hora."""
    name = str(b.get("project", "") or "")
    d = _project_dir(name)
    if not d or not os.path.isdir(d):
        raise ValueError("projeto não encontrado")
    if not os.path.isdir(os.path.join(d, ".git")) or not store.project_meta(name).get("ghUser"):
        raise ValueError("o projeto não tem repositório do GitHub vinculado")
    reason, d, user = _pull_prepare(name)
    if reason:
        return {"started": False, "reason": reason}
    threading.Thread(target=_pull_fetch, args=(name, d, user), daemon=True).start()
    return {"started": True, "reason": ""}


def _auto_pull_loop():
    time.sleep(20)
    while True:
        try:
            auto_pull_all()
        except Exception:  # noqa
            pass
        time.sleep(120)


def projects():
    res = []
    if not os.path.isdir(WORK):
        return res
    for name in sorted(os.listdir(WORK), key=str.lower):
        d = os.path.join(WORK, name)
        ios = os.path.isfile(os.path.join(d, "Package.swift"))
        try:
            andr = android.detect(d)
        except Exception:  # noqa
            andr = None
        try:
            pcd = pc.detect(d)
        except Exception:  # noqa
            pcd = None
        targets = store.project_meta(name).get("targets")
        targets = targets if isinstance(targets, dict) else {}
        if not ios and not andr and not pcd and not any(v is True for v in targets.values()):
            continue
        detected = [p for p, ok in (("ios", ios), ("android", andr), ("pc", pcd)) if ok]
        try:
            eff_platforms = builds.effective_platforms(d, store.project_meta(name))
        except Exception:  # noqa
            eff_platforms = detected
        arts = []
        xd = os.path.join(d, "xtool")
        if os.path.isdir(xd):
            for a in os.listdir(xd):
                if a.endswith((".ipa", ".app")):
                    arts.append(f"{name}/xtool/{a}")
        ad = os.path.join(xd, "android")
        if os.path.isdir(ad):
            for a in os.listdir(ad):
                if a.endswith((".apk", ".aab")):
                    arts.append(f"{name}/xtool/android/{a}")
        pd = os.path.join(xd, "pc")
        if os.path.isdir(pd):
            for a in os.listdir(pd):
                if a.endswith(".zip"):
                    arts.append(f"{name}/xtool/pc/{a}")
        yml = {}
        try:
            for line in open(os.path.join(d, "xtool.yml")):
                if ":" in line and not line.startswith(" "):
                    k, v = line.split(":", 1)
                    yml[k.strip()] = v.strip().strip("'\"")
        except OSError:
            pass
        try:
            gs = github.git_status(d)
        except Exception:  # noqa
            gs = None
        if gs is not None:
            gs = {**gs, "autoPull": PULL_STATE.get(name)}
        try:
            conf = builds.configured_flags(d, store.project_meta(name))
        except Exception:  # noqa
            conf = {"ios": False, "android": False, "pc": False}
        try:
            rel_count = builds.release_count(name, d)
        except Exception:  # noqa
            rel_count = 0
        try:
            db_count = len(dbenv.databases(name))
        except Exception:  # noqa
            db_count = 0
        res.append({
            "configured": conf, "releaseCount": rel_count, "dbCount": db_count,
            "name": name,
            "hasToml": bool(yml),
            "bundleId": yml.get("bundleID", ""),
            "artifacts": sorted(arts),
            "mtime": os.stat(d).st_mtime,
            "meta": store.project_meta(name),
            "git": gs,
            "platforms": eff_platforms, "detected": detected,
            "android": andr,
            "pc": pcd,
        })
    return res


def release_info(project):
    d = safe_path("work", project)
    meta = store.project_meta(project)
    p = next((x for x in projects() if x["name"] == project), None)
    if not p:
        raise ValueError("projeto não encontrado")
    acc_id = meta.get("accountId") or accounts_state().get("active")
    info = {"project": project, "bundleId": meta.get("bundleId") or p["bundleId"], "accountId": acc_id,
            "meta": meta, "app": None, "versions": [], "builds": [], "ascError": None}
    since = (meta.get("lastRelease") or {}).get("commit")
    info["changes"] = github.changes_since(d, since)
    info["versionSources"] = versions.sources(d)
    info["versionSource"] = meta.get("versionSource") or "auto"
    try:
        k = store.asc_key(acc_id)
        api = ASC(k.get("issuerId"), k.get("keyId"), k.get("p8"))
        app = api.app_by_bundle(info["bundleId"])
        info["app"] = {"id": app["id"], **app["attributes"]}
        info["versions"] = [{"id": v["id"], **v["attributes"]} for v in api.get(
            f"/v1/apps/{app['id']}/appStoreVersions", limit=5)["data"]]
        info["builds"] = api.builds(app["id"], 5)
    except (AscError, ValueError) as e:
        info["ascError"] = str(e)
    return info


# ---- store page preview: public App Store data + local project + App Store Connect draft
_lookup_cache = {}


def _itunes_lookup(bundle, country):
    import urllib.request
    key = (bundle, country)
    hit = _lookup_cache.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    res = None
    try:
        url = f"https://itunes.apple.com/lookup?bundleId={bundle}&country={country}&entity=software"
        with urllib.request.urlopen(url, timeout=10) as r:
            items = json.load(r).get("results") or []
        res = items[0] if items else None
    except Exception:  # noqa
        return None
    _lookup_cache[key] = (time.time(), res)
    return res


def _hires(url):
    """mzstatic serves any size: ask for a sharp version instead of the 320px thumbnail."""
    return re.sub(r"/\d+x\d+bb\.(jpg|png)$", "/1000x1000bb.jpg", url or "")


def _strip_team(bundle):
    """xtool registers free-provisioning IDs as <bundle>.<TEAMID>; compare both forms."""
    return re.sub(r"\.[A-Z0-9]{10}$", "", bundle or "")


def _local_project_for(bundle):
    for p in projects():
        pb = p["meta"].get("bundleId") or p["bundleId"]
        if pb and (pb == bundle or _strip_team(pb) == _strip_team(bundle)):
            return p
    return None


def _local_icon(project):
    d = safe_path("work", project)
    cands = []
    try:
        for line in open(os.path.join(d, "xtool.yml")):
            m = re.match(r"iconPath:\s*['\"]?([^'\"\n]+)", line)
            if m:
                cands.append(m.group(1).strip())
    except OSError:
        pass
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in (".build", "xtool", ".git", ".swiftpm")]
        if root.endswith(".appiconset"):
            pngs = [f for f in files if f.lower().endswith(".png")]
            pngs.sort(key=lambda f: os.path.getsize(os.path.join(root, f)), reverse=True)
            cands += [os.path.relpath(os.path.join(root, f), d) for f in pngs[:1]]
    for c in cands:
        if os.path.isfile(os.path.join(d, c)):
            return f"/api/download?root=work&path={project}/{c}&inline=1"
    return None


def _asc_draft(acc_id, bundle):
    """Texts and screenshots of the version being prepared (needs the account's API key)."""
    k = store.asc_key(acc_id)
    if not k.get("p8"):
        return None
    api = ASC(k["issuerId"], k["keyId"], k["p8"])
    try:
        app = api.app_by_bundle(bundle)
    except AscError:
        try:
            app = api.app_by_bundle(_strip_team(bundle))
        except AscError:
            return None
    out = {"name": app["attributes"].get("name"), "locale": app["attributes"].get("primaryLocale")}
    infos = api.get(f"/v1/apps/{app['id']}/appInfos", limit=5).get("data") or []
    if infos:
        locs = api.get(f"/v1/appInfos/{infos[0]['id']}/appInfoLocalizations", limit=50).get("data") or []
        loc = next((l for l in locs if l["attributes"]["locale"] == out["locale"]), locs[0] if locs else None)
        if loc:
            out.update(name=loc["attributes"].get("name") or out["name"], subtitle=loc["attributes"].get("subtitle"))
    vers = api.get(f"/v1/apps/{app['id']}/appStoreVersions", limit=1).get("data") or []
    if vers:
        v = vers[0]
        out.update(version=v["attributes"]["versionString"], state=v["attributes"]["appStoreState"])
        locs = api.get(f"/v1/appStoreVersions/{v['id']}/appStoreVersionLocalizations", limit=50).get("data") or []
        loc = next((l for l in locs if l["attributes"]["locale"] == out["locale"]), locs[0] if locs else None)
        if loc:
            a = loc["attributes"]
            out.update(description=a.get("description"), releaseNotes=a.get("whatsNew"),
                       promotionalText=a.get("promotionalText"))
            shots = {"iphone": [], "ipad": []}
            r = api.get(f"/v1/appStoreVersionLocalizations/{loc['id']}/appScreenshotSets",
                        limit=50, include="appScreenshots")
            kind_of = {}  # screenshot id -> iphone/ipad, from the set's display type (APP_IPHONE_67, APP_IPAD_PRO_129…)
            for st in r.get("data") or []:
                kind = "ipad" if "IPAD" in (st["attributes"].get("screenshotDisplayType") or "") else "iphone"
                for x in ((st.get("relationships") or {}).get("appScreenshots") or {}).get("data") or []:
                    kind_of[x["id"]] = kind
            for s in r.get("included") or []:
                ia = (s.get("attributes") or {}).get("imageAsset") or {}
                if ia.get("templateUrl") and s["id"] in kind_of:
                    w = 700
                    url = ia["templateUrl"].replace("{w}", str(w)).replace("{h}", str(int(w * ia["height"] / ia["width"]))).replace("{f}", "jpg")
                    shots[kind_of[s["id"]]].append(url)
            if shots["iphone"] or shots["ipad"]:
                out["screenshots"] = shots
    return out


def store_page(bundle, acc_id=None, country="br", light=False):
    page = {"bundleId": bundle, "sources": []}
    live = None
    for b in dict.fromkeys([bundle, _strip_team(bundle)]):
        for c in dict.fromkeys([country, "us"]):
            live = _itunes_lookup(b, c)
            if live:
                break
        if live:
            break
    if live:
        page["sources"].append("loja")
        page.update({
            "name": live.get("trackName"), "seller": live.get("sellerName") or live.get("artistName"),
            "icon": live.get("artworkUrl512") or live.get("artworkUrl100"),
            "version": live.get("version"), "releaseNotes": live.get("releaseNotes"),
            "releaseDate": live.get("currentVersionReleaseDate"), "description": live.get("description"),
            "genre": live.get("primaryGenreName"), "age": live.get("contentAdvisoryRating") or live.get("trackContentRating"),
            "rating": live.get("averageUserRating") or 0, "ratingCount": live.get("userRatingCount") or 0,
            "price": live.get("formattedPrice"), "size": live.get("fileSizeBytes"),
            "minOS": live.get("minimumOsVersion"), "languages": live.get("languageCodesISO2A") or [],
            "url": live.get("trackViewUrl"), "screenshots": {"iphone": [_hires(u) for u in live.get("screenshotUrls") or []],
                                                           "ipad": [_hires(u) for u in live.get("ipadScreenshotUrls") or []]},
        })
    proj = _local_project_for(bundle)
    if proj:
        page["project"] = proj["name"]
        if not page.get("icon"):
            page["icon"] = _local_icon(proj["name"])
        page.setdefault("name", proj["name"])
        page["sources"].append("projeto")
    if light and page.get("icon"):  # list icons only need the picture
        return page
    try:
        draft = _asc_draft(acc_id or accounts_state().get("active"), bundle)
    except Exception:  # noqa
        draft = None
    if draft:
        page["draft"] = draft
        page["sources"].append("app store connect")
    return page


def _xtool_dev_id(bundle):
    """App IDs xtool registers just to sign development builds (XTL-<team>.<bundle>.<team>): not store apps."""
    return (bundle or "").startswith("XTL-")


def apple_apps(acc_id):
    """Apps of an Apple account: App Store Connect apps (needs API key) + registered bundle IDs."""
    st = accounts_state()
    out = {"accountId": acc_id, "apps": None, "ascError": None, "identifiers": None, "idError": None}
    k = store.asc_key(acc_id)
    if k.get("p8"):
        try:
            out["apps"] = ASC(k["issuerId"], k["keyId"], k["p8"]).apps()
        except AscError as e:
            out["ascError"] = str(e)
    else:
        out["ascError"] = "sem chave da API do App Store Connect"
    if st.get("active") == acc_id:
        txt = ANSI.sub("", quick(["xtool", "ds", "identifiers", "list"], timeout=60))
        ids, cur = [], None
        for line in txt.splitlines():
            m = re.match(r"\s*-?\s*(\w+):\s*(.*)", line)
            if not m:
                continue
            if line.lstrip().startswith("- "):
                cur = {}
                ids.append(cur)
            if cur is not None:
                cur[m.group(1)] = m.group(2).strip()
        out["identifiers"] = ids
        if not ids and txt.strip():
            out["idError"] = txt.strip()[:400]
    else:
        out["idError"] = "troque para esta conta para listar os bundle IDs"
    # remember everything we saw, so the app stays listed even when it can't be fetched now
    found = [{"bundleId": a.get("bundleId"), "name": a.get("name"), "ascId": a.get("id"),
              "versions": a.get("versions", [])[:3], "sources": ["asc"]} for a in out["apps"] or []]
    found += [{"bundleId": i.get("identifier"), "name": i.get("name"), "sources": ["bundle"]}
              for i in out["identifiers"] or [] if not _xtool_dev_id(i.get("identifier"))]
    if found:
        store.apps_record(acc_id, found)
    return out


def apps_registry():
    """Every app ever seen, with its Apple account and whether that account has an API key."""
    st = accounts_state()
    accs = {a["id"]: a for a in st["accounts"]}
    out = []
    for acc_id, apps in store.apps_registry().items():
        a = accs.get(acc_id)
        if not a:
            continue
        api = store.asc_key_public(acc_id)["configured"]
        for e in list(apps.values()):
            if _xtool_dev_id(e.get("bundleId")):  # saved before this filter existed: clean it up
                store.apps_forget(acc_id, e["bundleId"])
                continue
            out.append({**e, "accountId": acc_id, "accountLabel": a.get("label", ""),
                        "appleId": a.get("appleId", ""), "teamId": a.get("teamId", ""), "hasApi": api})
    out.sort(key=lambda x: ((x.get("name") or x["bundleId"]).lower(), x["accountLabel"]))
    return out


# ---- Google Play apps and Android projects ----
def play_apps_list():
    accs = {a["id"]: a for a in store.play_accounts()}
    out = []
    for acc_id, apps in store.play_apps_registry().items():
        a = accs.get(acc_id)
        if not a:
            continue
        for e in apps.values():
            out.append({"packageName": e.get("packageName", ""), "name": e.get("name", ""),
                        "accountId": acc_id, "accountLabel": a.get("label", ""), "email": a.get("email", ""),
                        "updated": e.get("updated"), "tracks": e.get("tracks", [])})
    out.sort(key=lambda x: ((x.get("name") or x["packageName"]).lower(), x["accountLabel"]))
    return out


def play_app(acc_id, pkg):
    info = Play(store.play_account(acc_id)["json"]).app_info(pkg)
    store.play_apps_record(acc_id, [{"packageName": pkg, "name": info.get("title") or pkg,
                                     "tracks": info.get("tracks", [])}])
    return info


def _android_project_for(pkg):
    for p in projects():
        if "android" not in (p.get("platforms") or []):
            continue
        d = safe_path("work", p["name"])
        mp = (store.project_meta(p["name"]).get("android") or {}).get("packageName")
        if (mp or (android.detect(d) or {}).get("packageName")) == pkg:
            return p["name"], d
    return None, None


def _android_icon(project, d):
    """Launcher icon of the Android project (largest density first)."""
    det = android.detect(d) or {}
    res = os.path.join(d, det.get("gradleDir", "android"), "app", "src", "main", "res")
    for dens in ("xxxhdpi", "xxhdpi", "xhdpi", "hdpi", "mdpi"):
        for f in ("ic_launcher.png", "ic_launcher_round.png", "ic_launcher.webp"):
            p = os.path.join(res, "mipmap-" + dens, f)
            if os.path.isfile(p):
                return f"/api/download?root=work&path={project}/{os.path.relpath(p, d)}&inline=1"
    return None


_play_page_cache = {}


def play_store_page(acc_id, pkg, light=False):
    """Preview of the Google Play page: Play Console listing + local Android project as fallback."""
    project, d = _android_project_for(pkg)
    local_icon = _android_icon(project, d) if project else None
    key = (acc_id, pkg)
    hit = _play_page_cache.get(key)
    if light and hit:
        return {"packageName": pkg, "icon": hit[1].get("icon") or local_icon}
    if light and local_icon:
        return {"packageName": pkg, "icon": local_icon}
    if hit and time.time() - hit[0] < 300 and not light:
        return hit[1]
    page = {"packageName": pkg, "project": project, "sources": [], "url":
            f"https://play.google.com/store/apps/details?id={pkg}"}
    acc = next((a for a in store.play_accounts() if a["id"] == acc_id), None)
    if acc:
        page["developer"] = acc.get("label", "")
        try:
            L = Play(store.play_account(acc_id)["json"]).listing(pkg)
            page["sources"].append("play console")
            imgs = L.pop("images", {})
            page.update(L)
            page["icon"] = (imgs.get("icon") or [None])[0]
            page["featureGraphic"] = (imgs.get("featureGraphic") or [None])[0]
            page["screenshots"] = {"phone": imgs.get("phoneScreenshots", []),
                                   "tablet": imgs.get("tenInchScreenshots", []) or imgs.get("sevenInchScreenshots", [])}
        except (PlayError, ValueError, KeyError) as e:
            page["playError"] = str(e)
    if not page.get("icon") and local_icon:
        page["icon"] = local_icon
    if project:
        page["sources"].append("projeto")
        if not page.get("title"):
            page["title"] = project
    # newest release per track, for "Novidades"
    rels = []
    for t in page.get("tracks") or []:
        for r in t.get("releases") or []:
            vcs = [int(v) for v in r.get("versionCodes") or [] if str(v).isdigit()]
            rels.append({"track": t.get("track"), "name": r.get("name", ""), "status": r.get("status", ""),
                         "versionCode": max(vcs) if vcs else 0, "notes": r.get("releaseNotes") or []})
    rels.sort(key=lambda r: r["versionCode"], reverse=True)
    page["releases"] = rels
    if "play console" in page["sources"]:
        _play_page_cache[key] = (time.time(), page)
    if light:
        return {"packageName": pkg, "icon": page.get("icon")}
    return page


def android_info(project, with_play=True):
    d = safe_path("work", project)
    meta = store.project_meta(project).get("android", {})
    det = android.detect(d)
    pkg = meta.get("packageName") or (det or {}).get("packageName") or ""
    play, play_err = None, None
    if with_play and meta.get("playAccountId") and pkg:
        try:
            play = play_app(meta["playAccountId"], pkg)
        except (PlayError, ValueError) as e:
            play_err = str(e)
    try:
        changes = github.changes_since(d, (meta.get("lastRelease") or {}).get("commit"))
    except Exception:  # noqa
        changes = ""
    return {"project": project, "detect": det, "meta": meta, "packageName": pkg,
            "key": store.android_key_public(pkg), "playAccounts": store.play_accounts(),
            "play": play, "playError": play_err, "changes": changes,
            "versionSources": versions.sources(d),
            "versionSource": store.project_meta(project).get("versionSource") or "auto"}


def pc_info(project):
    d = safe_path("work", project)
    meta = store.project_meta(project)
    since = ((meta.get("steam", {}).get("lastRelease")) or {}).get("commit")
    try:
        changes = github.changes_since(d, since)
    except Exception:  # noqa
        changes = ""
    return {"project": project, "detect": pc.detect(d), "meta": meta.get("pc", {}),
            "steam": meta.get("steam", {}), "steamAccounts": store.steam_accounts(),
            "steamApps": store.steam_apps_list(), "steamcmd": bool(shutil.which("steamcmd")),
            "changes": changes, "versionSources": versions.sources(d),
            "versionSource": meta.get("versionSource") or "auto",
            "types": [{"id": t, "label": pc.TYPE_LABELS[t]} for t in pc.PROJECT_TYPES]}


def pc_profile(project, ptype):
    """Passos de build do tipo de código escolhido (ou detectado, com "auto")."""
    d = safe_path("work", project)
    info = pc.detect(d)
    if info is None:
        raise ValueError("o projeto não tem package.json")
    ptype = ptype or "auto"
    if ptype != "auto" and ptype not in pc.PROJECT_TYPES:
        raise ValueError(f"tipo de projeto desconhecido: {ptype}")
    return pc.profile(d, info, ptype)


def _last_commit(meta):
    """Commit do lançamento mais recente entre iOS, Android e PC (None se nenhum)."""
    cands = []
    for rel in (meta.get("lastRelease") or {}, (meta.get("android") or {}).get("lastRelease") or {},
                (meta.get("steam") or {}).get("lastRelease") or {}):
        if rel.get("commit"):
            cands.append(rel)
    if not cands:
        return None
    return max(cands, key=lambda r: r.get("at") or 0)["commit"]


def project_overview(project):
    """Tudo que a tela de configuração/build de um projeto precisa, numa chamada só."""
    d = safe_path("work", project)
    meta = store.project_meta(project)
    plats = builds.detect_platforms(d, meta, project)
    st = accounts_state()
    and_meta = meta.get("android") or {}
    pc_meta = meta.get("pc") or {}
    steam_meta = meta.get("steam") or {}
    ios_p = plats.get("ios") or {}
    and_p = plats.get("android") or {}
    try:
        changes = github.changes_since(d, _last_commit(meta))
    except Exception:  # noqa
        changes = ""
    return {
        "project": project, "platforms": plats, "builds": builds.list_builds(project, d),
        "version": {
            "source": meta.get("versionSource") or "auto", "sources": versions.sources(d),
            "last": {
                "ios": (meta.get("lastRelease") or {}).get("version")
                       or (meta.get("lastUpload") or {}).get("version") or "",
                "android": and_meta.get("lastVersionName") or "",
                "pc": pc_meta.get("lastVersionName") or "",
            },
        },
        "settings": {
            "targets": meta.get("targets", {}),
            "ios": {"accountId": meta.get("accountId") or st.get("active") or "",
                    "bundleId": meta.get("bundleId") or ios_p.get("bundleId") or "",
                    "submit": bool(meta.get("iosSubmit"))},
            "android": {"playAccountId": and_meta.get("playAccountId") or "",
                        "track": and_meta.get("track") or "internal",
                        "status": and_meta.get("status") or "completed",
                        "packageName": and_meta.get("packageName") or and_p.get("packageName") or "",
                        "preBuild": and_meta.get("preBuild") or ""},
            "pc": {"steamAccountId": steam_meta.get("accountId") or "",
                   "steamAppId": steam_meta.get("appId") or "",
                   "branch": steam_meta.get("branch") or "",
                   "preBuild": pc_meta.get("preBuild") or "",
                   "webDir": pc_meta.get("webDir") or "",
                   "electronVersion": pc_meta.get("electronVersion") or "",
                   "projectType": pc_meta.get("projectType") or "",
                   "appName": pc_meta.get("appName") or "",
                   "platforms": pc_meta.get("platforms") or ["win32"],
                   "zip": bool(pc_meta.get("zip", True))},
        },
        "accounts": {
            "apple": [{"id": a["id"], "label": a.get("label", ""), "appleId": a.get("appleId", ""),
                       "hasApi": store.asc_key_public(a["id"])["configured"]} for a in st["accounts"]],
            "play": [{"id": a.get("id"), "label": a.get("label", "")} for a in store.play_accounts()],
            "steam": [{"id": a.get("id"), "label": a.get("label", ""), "username": a.get("username", "")}
                      for a in store.steam_accounts()],
        },
        "steamApps": store.steam_apps_list(),
        "changes": changes,
        "databases": dbenv.databases(project),
        "locales": {"selected": meta.get("locales") or [], "catalog": lojas.catalog()},
    }


def project_settings(b):
    """Grava uma configuração de plataforma. Sempre mescla: sub-chaves nunca são sobrescritas."""
    project = str(b.get("project", "") or "")
    plat = b.get("platform")
    patch = b.get("patch")
    if not project or not isinstance(patch, dict):
        raise ValueError("configuração inválida")
    if not os.path.isdir(safe_path("work", project)):
        raise ValueError("projeto não encontrado")
    if plat == "ios":
        if set(patch) - {"accountId", "bundleId", "iosSubmit"}:
            raise ValueError("configuração inválida")
        store.project_meta_update(project, dict(patch))
    elif plat == "version":
        if set(patch) != {"versionSource"}:
            raise ValueError("configuração inválida")
        store.project_meta_update(project, {"versionSource": patch["versionSource"]})
    elif plat == "targets":
        if not set(patch) <= {"ios", "android", "pc"} or not all(isinstance(v, bool) for v in patch.values()):
            raise ValueError("configuração inválida")
        cur = dict(store.project_meta(project).get("targets") or {})
        cur.update(patch)
        store.project_meta_update(project, {"targets": cur})
    elif plat == "locales":
        lista = patch.get("locales")
        known = {c["code"] for c in lojas.catalog()}
        if set(patch) != {"locales"} or not isinstance(lista, list):
            raise ValueError("configuração inválida")
        # all() antes de set(): itens não-texto (dict, lista) não chegam ao set()
        if (not all(isinstance(c, str) and c in known for c in lista)
                or len(lista) > 30 or len(set(lista)) != len(lista)):
            raise ValueError("configuração inválida")
        store.project_meta_update(project, {"locales": list(lista)})
    elif plat in ("android", "pc", "steam"):
        cur = dict(store.project_meta(project).get(plat) or {})
        cur.update(patch)
        store.project_meta_update(project, {plat: cur})
    else:
        raise ValueError("configuração inválida")
    return {"ok": True}


def project_databases_get(qs):
    """Bancos cadastrados do projeto e os candidatos achados na pasta (dbdetect)."""
    project = str(qs.get("project", "") or "")
    if not project:
        raise ValueError("projeto não encontrado")
    d = safe_path("work", project)
    if not os.path.isdir(d):
        raise ValueError("projeto não encontrado")
    return {"databases": dbenv.databases(project), "found": dbdetect.detect(d)}


def project_databases_save(b):
    """Grava (save) ou apaga (delete) um banco de dados do projeto."""
    project = str(b.get("project", "") or "")
    if not project:
        raise ValueError("projeto não encontrado")
    if not os.path.isdir(safe_path("work", project)):
        raise ValueError("projeto não encontrado")
    action = b.get("action")
    if action == "save":
        db = b.get("database")
        if not isinstance(db, dict):
            raise ValueError("banco inválido")
        saved = dbenv.save_database(project, db)
        return {"databases": dbenv.databases(project), "saved": saved}
    if action == "delete":
        dbid = b.get("id")
        if not isinstance(dbid, str) or not dbid:
            raise ValueError("banco inválido")
        dbenv.delete_database(project, dbid)
        return {"databases": dbenv.databases(project)}
    raise ValueError("ação inválida")


def steam_status():
    p = shutil.which("steamcmd")
    return {"steamcmd": bool(p), "path": p or ""}


STEAM_CHECK = {}  # id da conta -> último resultado de steam_check (só em memória)
STEAM_LOCK = threading.Lock()  # um login de checagem do steamcmd por vez


def _steam_parse(out):
    """Lê a saída de `steamcmd +login <conta> +quit` -> (state, message, steamId). Função pura."""
    txt = ANSI.sub("", out or "")
    m = re.search(r"Logging in user '[^']*' \[(U:\d+:\d+)\] to Steam Public\.*\s*OK", txt)
    if m and "FAILED" not in txt:
        return "ok", f"Conectada ({m.group(1)})", m.group(1)
    if "rate limit" in txt.lower():
        return "error", "A Steam limitou as tentativas: aguarde alguns minutos", ""
    if any(k in txt for k in ("FAILED", "Login Failure", "No cached credentials",
                              "Cached credentials not found", "Invalid Password", "Two-factor")):
        return "nologin", "Sem login salvo: clique em Login", ""
    lines = [x.strip() for x in txt.splitlines() if x.strip()]
    return "error", lines[-1] if lines else "resposta inesperada do steamcmd", ""


def steam_busy():
    """Há alguma tarefa do steamcmd (login, release da Steam) rodando agora?"""
    with LOCK:
        return any(j.ended is None and any(("steamcmd" in x or "steam.py" in x) for x in j.argv)
                   for j in JOBS.values())


def steam_check(acc_id, force=False):
    acc = store.steam_account(acc_id)  # conta inexistente: ValueError sobe
    hit = STEAM_CHECK.get(acc_id)
    if not force and hit and time.time() - hit["checked"] < 30 and hit["state"] in ("ok", "nologin"):
        return hit

    def res(state, message, steam_id=""):
        return {"id": acc_id, "state": state, "connected": state == "ok", "message": message,
                "steamId": steam_id, "checked": time.time()}

    if steam_busy():
        return res("busy", "Ocupado: há uma tarefa do steamcmd em andamento")  # não vai para o cache
    with STEAM_LOCK:
        try:
            r = subprocess.run(["steamcmd", "+@ShutdownOnFailedCommand", "1", "+@NoPromptForPassword", "1",
                                "+login", acc["username"], "+quit"],
                               capture_output=True, text=True, timeout=90, errors="replace")
            out = res(*_steam_parse((r.stdout or "") + (r.stderr or "")))
        except subprocess.TimeoutExpired:
            out = res("error", "O steamcmd demorou demais (90 s)")
        except FileNotFoundError:
            out = res("error", "steamcmd não instalado")
        except Exception as e:  # noqa
            out = res("error", str(e))
    STEAM_CHECK[acc_id] = out
    return out


def _steam_flags(accs):
    """id da conta -> True (conectada), False (sem login), None (desconhecido), só pelo cache."""
    now = time.time()
    flags = {}
    for a in accs:
        hit = STEAM_CHECK.get(a.get("id"))
        st = hit["state"] if hit and now - hit["checked"] < 600 else None
        flags[a.get("id")] = True if st == "ok" else False if st == "nologin" else None
    return flags


def topbar():
    """Barra do topo: contas principais (Steam e Google Play), Android e PC conectados."""
    def safe(fn, default):
        try:
            return fn()
        except Exception:  # noqa
            return default

    def resolve(saved, accs):
        ids = [a.get("id") for a in accs]
        if saved in ids:
            return saved
        return ids[0] if ids else ""

    steam_accs = safe(store.steam_accounts, [])
    play_accs = safe(store.play_accounts, [])
    d = safe(store.defaults_get, {})
    try:
        import socket
        socket.gethostbyname("host.docker.internal")
        pc_connected = True
    except OSError:
        pc_connected = False
    return {
        "defaults": {
            "steamAccountId": resolve(d.get("steamAccountId", ""), steam_accs),
            "playAccountId": resolve(d.get("playAccountId", ""), play_accs),
        },
        "steamAccounts": steam_accs,
        "steamStatus": safe(lambda: _steam_flags(steam_accs), {}),
        "playAccounts": play_accs,
        "android": safe(adb_devices, []),
        "pc": {"connected": bool(pc_connected), "host": "host.docker.internal",
               "appleService": bool(ONLINE["service"])},
    }


def pc_status():
    """Estado do PC (host Windows) e das ferramentas de build; nunca levanta exceção."""
    import socket

    def electron_bytes():
        total = 0
        try:
            for root, _, files in os.walk(os.path.expanduser("~/.cache/electron")):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except Exception:  # noqa
            return 0
        return total

    try:
        host_ip = socket.gethostbyname("host.docker.internal")
        connected = True
    except Exception:  # noqa
        host_ip, connected = "", False
    try:
        node = quick(["node", "--version"], timeout=5).strip()
        if node.startswith("erro"):  # quick() devolve "erro: ..." em vez de levantar exceção
            node = ""
    except Exception:  # noqa
        node = ""
    try:
        steamcmd_path = shutil.which("steamcmd") or ""
    except Exception:  # noqa
        steamcmd_path = ""
    return {
        "connected": bool(connected), "host": "host.docker.internal", "hostIp": host_ip,
        "appleService": bool(ONLINE["service"]),
        "usbmuxdVia": os.environ.get("USBMUXD_SOCKET_ADDRESS") or "/var/run/usbmuxd",
        "steamcmd": bool(steamcmd_path), "steamcmdPath": steamcmd_path,
        "node": node, "npx": bool(shutil.which("npx")),
        "electronCacheBytes": electron_bytes(),
    }


def adb_devices():
    if not shutil.which("adb"):
        return []
    out = []
    for line in quick(["adb", "devices", "-l"], timeout=15).splitlines():
        line = line.strip()
        if not line or line.startswith(("*", "List of devices", "erro")):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        rest = parts[2] if len(parts) > 2 else ""
        m_model = re.search(r"model:(\S+)", rest)
        m_dev = re.search(r"device:(\S+)", rest)
        out.append({"serial": parts[0], "state": parts[1],
                    "model": m_model.group(1) if m_model else "",
                    "device": m_dev.group(1) if m_dev else ""})
    return out


def play_test(b):
    try:
        return Play(store.play_account(str(b.get("id", "")))["json"]).test()
    except (PlayError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def android_key_import(b):
    data = base64.b64decode(b.get("data", "") or "")
    return android.key_import(b["package"], data, b.get("storePassword", ""), b.get("keyAlias", ""),
                              b.get("keyPassword", ""), ext=b.get("ext", "p12"))


NEW_SCRIPT = r'''set -e
cd /work
if [ -e "$NAME" ]; then printf '\033[1;31m✖ já existe uma pasta %s\033[0m\n' "$NAME"; exit 1; fi
if gh repo view "$REPO" >/dev/null 2>&1; then printf '\033[1;31m✖ o repositório %s já existe no GitHub\033[0m\n' "$REPO"; exit 1; fi
printf '\033[1;36m▶ Criando o projeto %s\033[0m\n' "$NAME"
xtool new "$NAME" $SKIP
cd "/work/$NAME"
git config --global --add safe.directory "$PWD" >/dev/null 2>&1 || true
[ -f .gitignore ] || printf '.build/\nxtool/\n.swiftpm/\n' > .gitignore
[ -d .git ] || git init -q
git config user.name "$GN"; git config user.email "$GE"
git add -A; git diff --cached --quiet || git commit -qm "Primeiro commit"
git branch -M main
printf '\033[1;36m▶ Criando o repositório %s\033[0m\n' "$REPO"
gh repo create "$REPO" $PRIVATE --source . --remote origin --push
python3 -c "import os,sys; sys.path.insert(0,'/opt/panel'); import store; store.project_meta_update(os.environ['NAME'], {'repo': os.environ['REPO'], 'ghUser': os.environ['GHUSER']})"
printf '\033[1;32m✔ projeto criado e vinculado a https://github.com/%s\033[0m\n' "$REPO"'''


def new_project_env(a):
    """Valida o novo projeto (antes de executar nada) e devolve o ambiente do NEW_SCRIPT."""
    name = str(a.get("name", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        raise ValueError("nome inválido: comece com letra e use só letras, números, _ ou -")
    if os.path.exists(os.path.join(WORK, name)):
        raise ValueError("já existe um projeto com esse nome")
    user = str(a.get("ghUser", "") or "").strip()
    if not user:
        raise ValueError("todo projeto novo precisa de um repositório do GitHub: escolha uma conta cadastrada")
    if user not in {x.get("user") for x in github.accounts()}:
        raise ValueError("essa conta do GitHub não está cadastrada")
    repo_name = str(a.get("repoName") or name).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", repo_name):
        raise ValueError("nome do repositório inválido")
    gn, ge = github.identity(user)
    return {"GH_TOKEN": github.token(user), "GN": gn, "GE": ge, "REPO": f"{user}/{repo_name}",
            "PRIVATE": "--private" if a.get("private", True) else "--public", "NAME": name,
            "SKIP": "--skip-setup" if a.get("skipSetup", True) else "", "GHUSER": user}


MULTI_OK = ("dev.build", "dev.run", "release", "android.release", "pc.build", "steam.release")


def _store_file_rels(project, act, args):
    """Arquivos (relativos ao projeto) que a etapa usa, para o gate do dbenv. None = não se aplica."""
    if act == "android.release":
        return [dbenv.abs_to_rel(args["existing"])] if args.get("existing") else None
    if act == "release":
        return [dbenv.abs_to_rel(args["ipaFile"])] if args.get("ipaFile") else None
    if act == "steam.release":
        from_zips = args.get("fromZips") or {}
        if from_zips:
            return [dbenv.abs_to_rel(v) for v in from_zips.values()]
        if args.get("build") is False:
            plats = args.get("platforms") or ["win32"]
            return [b["file"] for b in builds.list_builds(project, safe_path("work", project))
                    if b.get("platform") == "pc" and b.get("kind") == "folder" and b.get("target") in plats]
    return None


def multi_script(a):
    """Script bash que roda, em sequência, até 8 ações da whitelist MULTI_OK; para na primeira que falhar."""
    steps = a.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("nenhuma etapa")
    if len(steps) > 8:
        raise ValueError("no máximo 8 etapas")
    project = str(a.get("project", ""))
    n = len(steps)
    dbenv_py = os.path.join(PANEL_PY, "dbenv.py")
    lines = ["set -u"]
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            raise ValueError("etapa inválida")
        act = st.get("action", "")
        if act not in MULTI_OK:
            raise ValueError(f"ação não permitida em sequência: {act}")
        args = dict(st.get("args") or {})
        args["project"] = project
        if isinstance(args.get("database"), dict):  # normaliza para o id (string) antes do dbenv
            args["database"] = str(args["database"].get("id") or "")
        dbenv.check_store_step(project, act, args, _store_file_rels(project, act, args))
        args2, dbenv_env = dbenv.step_plan(project, act, args)
        argv, env = build_cmd(act, args2)
        env = {**(env or {}), **(dbenv_env or {})}
        title = re.sub(r"['\"`$\\\n\r]", "", str(st.get("title") or act)).strip() or act
        t = shlex.quote(title)
        pre = (["env"] + [f"{k}={v}" for k, v in env.items()]) if env else []
        cmd = shlex.join(pre + argv)
        dbid = args.get("database")  # id do banco (string), como em dbenv.step_plan
        if dbid:
            if not isinstance(dbid, str):
                raise ValueError("banco inválido")
            db = dbenv.get(project, dbid)
            if not db:
                raise ValueError("banco não encontrado")
        lines.append("printf '\\n\\033[1;36m━━ %s/%s %s ━━\\033[0m\\n' " + f"{i} {n} {t}")
        if dbid:
            bname = str(db.get("name") or dbid)
            brole = str(db.get("role") or "")
            lines.append("printf '\\033[1;36mBanco: %s (%s)\\033[0m\\n' "
                         + f"{shlex.quote(bname)} {shlex.quote(brole)}")
            lines.append(f"T{i}=$(date +%s)")
            apply_cmd = shlex.join(["python3", "-u", dbenv_py, "apply", project, dbid])
            lines.append(f"{apply_cmd} || {{ printf '\\033[1;31m✖ falha ao preparar o banco: %s\\033[0m\\n' "
                         f"{shlex.quote(bname)}; exit 1; }}")
        lines.append(f"{cmd} || {{ printf '\\033[1;31m✖ etapa falhou: %s\\033[0m\\n' {t}; exit 1; }}")
        if dbid:
            record_cmd = shlex.join(["python3", "-u", dbenv_py, "record", project, dbid])
            lines.append(f'{record_cmd} "$T{i}" || true')
    lines.append("printf '\\033[1;32m✔ Todas as etapas terminaram\\033[0m\\n'")
    return "\n".join(lines)


# Commands the page may ask for. Each maps a name to a function returning argv.
def build_cmd(action, a):
    q = lambda k, d="": str(a.get(k, d)).strip()  # noqa
    dev_sel = []
    if q("udid"):
        dev_sel += ["--udid", q("udid")]
    conn = q("conn", "all")
    if conn in ("usb", "network", "all"):
        dev_sel += [f"--{conn}"]
    s = ["-s", q("serial")] if q("serial") else []  # adb: serial opcional
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
        "new": lambda: ["bash", "-c", NEW_SCRIPT],
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
        # GitHub (gh prints the device code; BROWSER=echo just shows the link)
        "gh.login": lambda: ["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https",
                             "--web", "--scopes", "repo,read:org,workflow"],
        "gh.token": lambda: ["bash", "-c", "gh auth login --hostname github.com --git-protocol https --with-token <<< \"$TOKEN\" "
                             "&& gh auth status"],
        "gh.switch": lambda: ["gh", "auth", "switch", "--hostname", "github.com", "--user", q("user")],
        "gh.logout": lambda: ["gh", "auth", "logout", "--hostname", "github.com", "--user", q("user")],
        "gh.clone": lambda: ["bash", "-c", 'set -e; git clone "https://github.com/$REPO.git" "/work/$NAME"; '
                             'cd "/work/$NAME"; git config user.name "$GN"; git config user.email "$GE"; '
                             'ls; [ -f Package.swift ] || echo "⚠ o repositório não tem Package.swift na raiz"'],
        "gh.link": lambda: ["bash", "-c", LINK_SCRIPT],
        "gh.create": lambda: ["bash", "-c", CREATE_SCRIPT],
        "git.pull": lambda: ["bash", "-c", "set -e; git pull --no-rebase; git log --oneline -5"],
        "git.push": lambda: ["bash", "-c", 'set -e; git config user.name "$GN"; git config user.email "$GE"; '
                             'git add -A; git diff --cached --quiet || git commit -m "$MSG"; '
                             'git push -u origin HEAD; git log --oneline -3'],
        "release": lambda: ["python3", "-u", os.path.join(PANEL_PY, "release.py"), write_args(a)],
        "android.release": lambda: ["python3", "-u", os.path.join(PANEL_PY, "android.py"), write_args(a)],
        "pc.build": lambda: ["python3", "-u", os.path.join(PANEL_PY, "pc.py"), write_args(a)],
        "steam.release": lambda: ["python3", "-u", os.path.join(PANEL_PY, "steam.py"), write_args(a)],
        "steam.login": lambda: ["steamcmd", "+login", q("username"), "+quit"],
        "adb.pair": lambda: ["adb", "pair", q("addr"), q("code")],
        "adb.connect": lambda: ["adb", "connect", q("addr")],
        "adb.disconnect": lambda: ["adb", "disconnect"],
        "adb.devices": lambda: ["adb", "devices", "-l"],
        "adb.install": lambda: ["adb"] + s + ["install", "-r", q("path")],
        "adb.launch": lambda: ["adb"] + s + ["shell", "monkey", "-p", q("package"),
                                             "-c", "android.intent.category.LAUNCHER", "1"],
        "xtool.update": lambda: ["bash", "-c", XTOOL_UPDATE],
        "init.android": lambda: ["bash", "-lc", builds.init_script(safe_path("work", q("project")))],
        "multi": lambda: ["bash", "-lc", multi_script(a)],
    }
    if action not in cmds:
        raise ValueError(f"ação desconhecida: {action}")
    argv = cmds[action]()
    if any(x == "" for x in argv):
        raise ValueError("preencha os campos obrigatórios")
    env = {}
    if action == "new":
        env.update(new_project_env(a))
    if action == "gh.login":
        env["BROWSER"] = "echo"
    if action == "xtool.update":
        ver = q("version") or xtool_latest(force=True) or ""
        if not re.fullmatch(r"\d+\.\d+(\.\d+)?", ver):
            raise ValueError("não consegui descobrir a versão mais nova do xtool")
        env["VER"] = ver
    if action == "gh.token":
        env["TOKEN"] = q("token")
    if action.startswith(("gh.clone", "gh.link", "gh.create", "git.")):
        user = q("user") or store.project_meta(q("project")).get("ghUser", "")
        if not user:
            raise ValueError("escolha a conta do GitHub")
        env["GH_TOKEN"] = github.token(user)
        env["GN"], env["GE"] = github.identity(user)
        env.update(REPO=q("repo"), NAME=q("name") or q("repo").split("/")[-1], MSG=q("message") or "Atualização",
                   PRIVATE="--private" if a.get("private", True) else "--public")
    return argv, env


LINK_SCRIPT = r'''set -e
git config --global --add safe.directory "$PWD" >/dev/null 2>&1 || true
[ -d .git ] || git init -q
git config user.name "$GN"; git config user.email "$GE"
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$REPO.git"
git fetch origin
BR=$(git remote show origin | sed -n 's/.*HEAD branch: //p')
if [ -z "$(git rev-parse --verify HEAD 2>/dev/null)" ]; then
  if [ -n "$BR" ] && [ "$BR" != "(unknown)" ]; then
    git add -A; git commit -qm "Projeto local" || true
    git branch -M "$BR"
    git pull --no-rebase --allow-unrelated-histories --no-edit origin "$BR" || echo "⚠ conflitos: resolva no Terminal"
  fi
fi
git branch --set-upstream-to="origin/${BR:-main}" 2>/dev/null || true
echo "✔ vinculado a $REPO"; git status -sb | head -5'''

CREATE_SCRIPT = r'''set -e
[ -f .gitignore ] || printf '.build/\nxtool/\n.swiftpm/\n' > .gitignore
[ -d .git ] || git init -q
git config user.name "$GN"; git config user.email "$GE"
git add -A; git diff --cached --quiet || git commit -qm "Primeiro commit"
git branch -M main
gh repo create "$REPO" $PRIVATE --source . --remote origin --push
echo "✔ repositório criado: https://github.com/$REPO"'''


def asc_test(acc_id):
    k = store.asc_key(acc_id)
    try:
        apps = ASC(k.get("issuerId"), k.get("keyId"), k.get("p8")).get("/v1/apps", limit=200)["data"]
        return {"ok": True, "apps": len(apps)}
    except Exception as e:  # noqa
        return {"ok": False, "error": str(e)}


def ai_conf_for(b):
    """Saved provider config, overridden by unsaved fields typed in the form."""
    try:
        conf = store.ai_provider(b.get("provider"))
    except ValueError:
        conf = {"provider": b.get("provider")}
    over = {k: v for k, v in (b.get("conf") or {}).items() if v and "…" not in str(v) and v != "•••"}
    return {**conf, **over, "provider": b.get("provider") or conf.get("provider")}


def ai_whats_new(b):
    conf = ai_conf_for(b)
    project = b.get("project", "")
    changes = b.get("changes") or github.changes_since(
        safe_path("work", project), (store.project_meta(project).get("lastRelease") or {}).get("commit"))
    if not changes.strip():
        raise ValueError("não há mudanças registradas no git; escreva um resumo no campo de observações")
    out = {}
    for loc in b.get("locales") or ["pt-BR"]:
        out[loc] = ai.whats_new(conf, b.get("appName") or project, b.get("version", ""), changes, loc,
                                b.get("tone", ""), b.get("extra", ""))
    return out


# ---------------------------------------------------------------------------
# Gerenciar lojas publicadas (App Store, Google Play): rotas /api/lojas/*
# ---------------------------------------------------------------------------
LOJAS_IMG_SUBDIR = "xtool/lojas-img"  # dentro da pasta do projeto
LOJAS_IMG_EXT = (".png", ".jpg", ".jpeg")
LOJAS_IMG_MAX = 10 * 1024 * 1024  # 10 MB


def _txt(b, key):
    v = b.get(key)
    return "" if v is None else str(v).strip()


def _lojas_project(b):
    project = _txt(b, "project")
    if not project or not os.path.isdir(safe_path("work", project)):
        raise ValueError("projeto não encontrado")
    return project


def _lojas_store(b):
    st = _txt(b, "store")
    if st == "pc":
        raise ValueError("a Steam não tem página editável pelo painel")
    if st not in ("ios", "android"):
        raise ValueError("loja inválida")
    return st


def lojas_overview(qs):
    return lojas.overview(_lojas_project(qs))


def lojas_fields(qs):
    project = _lojas_project(qs)
    return lojas_io.load_fields(project, _lojas_store(qs), _txt(qs, "version"), _txt(qs, "build"))


def lojas_save(b):
    data = b.get("data")
    if not isinstance(data, dict):
        raise ValueError("dados inválidos")
    project = _lojas_project(b)
    return lojas_io.save_fields(project, _lojas_store(b), _txt(b, "version"), _txt(b, "build"),
                                data, _txt(b, "track"))


def lojas_changes(project, store_key):
    """Mudanças no git desde o último lançamento: da loja, se houver; senão a geral (como ai_whats_new)."""
    meta = store.project_meta(project)
    rel = {}
    if store_key == "android":
        rel = (meta.get("android") or {}).get("lastRelease") or {}
    if not rel.get("commit"):
        rel = meta.get("lastRelease") or {}
    return github.changes_since(safe_path("work", project), rel.get("commit"))


def lojas_generate(b):
    project = _lojas_project(b)
    store_key = _lojas_store(b)
    fields = b.get("fields") or []
    locales = b.get("locales") or lojas.project_locales(project)
    current = b.get("current") or {}
    if not isinstance(fields, list) or not isinstance(locales, list) or not isinstance(current, dict):
        raise ValueError("dados inválidos")
    extra = _txt(b, "extra")
    changes = lojas_changes(project, store_key)
    if "whatsNew" in fields and not changes.strip() and not extra:
        raise ValueError("não há mudanças registradas no git; escreva um resumo no campo de observações")
    return ai.generate_listing(ai_conf_for(b), store_key, _txt(b, "appName") or project, _txt(b, "version"),
                               locales, fields, current, changes, extra)


def _lojas_img_file(project, rel):
    """Caminho absoluto do upload; ValueError se não estiver dentro de <project>/xtool/lojas-img/."""
    if not rel:
        raise ValueError("arquivo não informado")
    p = safe_path("work", rel)
    base = safe_path("work", project + "/" + LOJAS_IMG_SUBDIR)
    if not p.startswith(base + os.sep):
        raise ValueError("arquivo fora da pasta de imagens do projeto")
    return p


def _lojas_remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


def lojas_image_upload(b):
    absp = ""  # só recebe valor depois de validado: nunca apagamos nada fora de lojas-img
    try:
        project = _lojas_project(b)
        store_key = _lojas_store(b)
        absp = _lojas_img_file(project, _txt(b, "path"))
        if os.path.splitext(absp)[1].lower() not in LOJAS_IMG_EXT:
            raise ValueError("formato inválido: envie PNG ou JPG")
        if not os.path.isfile(absp):
            raise ValueError("arquivo não encontrado: envie de novo")
        if os.path.getsize(absp) > LOJAS_IMG_MAX:
            raise ValueError("imagem maior que 10 MB")
        return lojas_io.upload_image(project, store_key, _txt(b, "version"), _txt(b, "locale"),
                                     _txt(b, "kind"), absp)
    finally:
        if absp:
            _lojas_remove(absp)


def lojas_image_delete(b):
    project = _lojas_project(b)
    store_key = _lojas_store(b)
    image_id = _txt(b, "id")
    if not image_id:
        raise ValueError("imagem inválida")
    return lojas_io.delete_image(project, store_key, _txt(b, "version"), _txt(b, "locale"),
                                 _txt(b, "kind"), image_id)


def _lojas_version(b):
    v = _txt(b, "version")
    if not re.fullmatch(r"\d+(\.\d+){0,3}", v):
        raise ValueError("versão inválida")
    return v


def _lojas_store_is(b, want):
    st = _lojas_store(b)
    if st != want:
        raise ValueError("esta ação só existe para " + ("App Store" if want == "ios" else "Google Play"))
    return st


def lojas_submit(b):
    """Envia a versão do App Store Connect para a revisão da Apple (só iOS)."""
    project = _lojas_project(b)
    _lojas_store_is(b, "ios")
    return lojas_io.submit_review(project, "ios", _lojas_version(b), _txt(b, "build"))


def lojas_promote(b):
    """Copia a release do Google Play de uma faixa para outra (só Android)."""
    project = _lojas_project(b)
    _lojas_store_is(b, "android")
    version = _lojas_version(b)
    fraction = b.get("fraction")
    if fraction is not None and str(fraction).strip() != "":
        try:
            fraction = float(fraction)
        except (TypeError, ValueError):
            raise ValueError("fração inválida")
    else:
        fraction = None
    return lojas_io.promote(project, "android", version, _txt(b, "build"),
                            to_track=_txt(b, "to_track") or "production",
                            status=_txt(b, "status") or "completed",
                            fraction=fraction,
                            from_track=_txt(b, "from_track"))


def write_args(a):
    os.makedirs("/tmp/panel-args", exist_ok=True)
    p = f"/tmp/panel-args/{uuid.uuid4().hex}.json"
    with open(p, "w") as f:
        json.dump(a, f)
    return p


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
                     "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "application/octet-stream")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(path)))
        if not download and (ctype.startswith("text/") or ctype == "image/svg+xml"):
            self.send_header("Cache-Control", "no-cache")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/favicon.ico":
                return self._file(os.path.join(STATIC, "logo.svg"), "image/svg+xml")
            if u.path == "/api/version":
                return self._json({"panel": VERSION, "author": "marco3079"})
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
                return self._file(safe_path(qs.get("root", "work"), qs.get("path", "")), download=not qs.get("inline"))
            if u.path == "/api/accounts":
                st = accounts_state()
                return self._json({**st, "accounts": [{**a, "hasApi": store.asc_key_public(a["id"])["configured"]}
                                                      for a in st["accounts"]]})
            if u.path == "/api/apps/registry":
                return self._json(apps_registry())
            if u.path == "/api/devices":
                return self._json(devices_list())
            if u.path == "/api/asc/key":
                return self._json(store.asc_key_public(qs.get("account", "")))
            if u.path == "/api/apps":
                return self._json(apple_apps(qs.get("account") or accounts_state().get("active")))
            if u.path == "/api/ai":
                return self._json({**store.ai_public(), "catalog": ai.PROVIDERS})
            if u.path == "/api/gh/accounts":
                return self._json(github.accounts())
            if u.path == "/api/gh/repos":
                return self._json(github.repos(qs.get("user", ""), qs.get("q", "")))
            if u.path == "/api/storepage":
                return self._json(store_page(qs.get("bundle", ""), qs.get("account"), qs.get("country", "br"),
                                             bool(qs.get("light"))))
            if u.path == "/api/release/info":
                return self._json(release_info(qs.get("project", "")))
            if u.path == "/api/devices/status":
                return self._json(devices_with_status())
            if u.path == "/api/devices/detect":
                return self._json(devices_detect())
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
            if u.path == "/api/play/accounts":
                return self._json(store.play_accounts())
            if u.path == "/api/play/apps":
                return self._json(play_apps_list())
            if u.path == "/api/play/app":
                return self._json(play_app(qs.get("account", ""), qs.get("package", "")))
            if u.path == "/api/play/storepage":
                return self._json(play_store_page(qs.get("account", ""), qs.get("package", ""),
                                                  qs.get("light") == "1"))
            if u.path == "/api/android/info":
                return self._json(android_info(qs.get("project", ""), qs.get("play") != "0"))
            if u.path == "/api/android/key":
                return self._json(store.android_key_public(qs.get("package", "")))
            if u.path == "/api/android/key/download":
                k = store.android_key(qs.get("package", ""))
                if not k.get("file"):
                    raise ValueError("chave não encontrada")
                return self._file(k["file"], download=True)
            if u.path == "/api/adb/devices":
                return self._json(adb_devices())
            if u.path == "/api/steam/accounts":
                return self._json(store.steam_accounts())
            if u.path == "/api/steam/apps":
                return self._json(store.steam_apps_list())
            if u.path == "/api/steam/status":
                return self._json(steam_status())
            if u.path == "/api/pc/info":
                return self._json(pc_info(qs.get("project", "")))
            if u.path == "/api/topbar":
                return self._json(topbar())
            if u.path == "/api/pc/status":
                return self._json(pc_status())
            if u.path == "/api/steam/check":
                return self._json(steam_check(qs.get("id", ""), qs.get("force") == "1"))
            if u.path == "/api/pc/profile":
                return self._json(pc_profile(qs.get("project", ""), qs.get("type", "")))
            if u.path == "/api/project/overview":
                return self._json(project_overview(qs.get("project", "")))
            if u.path == "/api/project/databases":
                return self._json(project_databases_get(qs))
            if u.path == "/api/lojas/overview":
                return self._json(lojas_overview(qs))
            if u.path == "/api/lojas/fields":
                return self._json(lojas_fields(qs))
            if u.path == "/api/pull/state":  # leve: só lê o dicionário, não roda git
                with PULL_LOCK:
                    return self._json({k: dict(v) for k, v in PULL_STATE.items()})
            return self._json({"error": "rota não existe"}, 404)
        except Exception as e:  # noqa
            return self._json({"error": str(e)}, 400)

    def do_POST(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/run":
                b = self._body()
                argv, env = build_cmd(b.get("action", ""), {**b.get("args", {}), "project": b.get("project", "")})
                cwd = safe_path("work", b.get("project", "")) if b.get("project") else WORK
                j = Job(argv, cwd, b.get("title") or " ".join(argv), env)
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
            acc_routes = {
                "/api/accounts/add": lambda b: accounts_add(str(b.get("label", "")).strip()),
                "/api/accounts/switch": lambda b: accounts_switch(b.get("id")),
                "/api/accounts/remove": lambda b: accounts_remove(b.get("id")),
                "/api/accounts/rename": lambda b: accounts_rename(b.get("id"), str(b.get("label", "")).strip()),
                "/api/accounts/refresh": lambda b: accounts_sync(),
                "/api/devices/save": devices_save,
                "/api/devices/remove": lambda b: devices_remove(b.get("id")),
                "/api/asc/key": lambda b: (store.asc_key_set(b["accountId"], b.get("issuerId", ""), b.get("keyId", ""),
                                                             b.get("p8", "")), store.asc_key_public(b["accountId"]))[1],
                "/api/apps/forget": lambda b: (store.apps_forget(b["accountId"], b["bundleId"]), {"ok": True})[1],
                "/api/asc/key/remove": lambda b: (store.asc_key_remove(b["accountId"]), {"ok": True})[1],
                "/api/asc/test": lambda b: asc_test(b["accountId"]),
                "/api/ai/save": lambda b: (store.ai_save(b["provider"], b.get("conf", {}), b.get("default")),
                                           store.ai_public())[1],
                "/api/ai/remove": lambda b: (store.ai_remove(b["provider"]), store.ai_public())[1],
                "/api/ai/models": lambda b: ai.list_models(ai_conf_for(b)),
                "/api/ai/whatsnew": ai_whats_new,
                "/api/projects/meta": lambda b: store.project_meta_update(b["project"], b.get("patch", {})),
                "/api/play/accounts/add": lambda b: (store.play_account_add(str(b.get("label", "")), b.get("json", "")),
                                                     store.play_accounts())[1],
                "/api/play/accounts/remove": lambda b: (store.play_account_remove(b.get("id", "")),
                                                        store.play_accounts())[1],
                "/api/play/accounts/rename": lambda b: (store.play_account_rename(b.get("id", ""), str(b.get("label", ""))),
                                                        store.play_accounts())[1],
                "/api/play/test": play_test,
                "/api/play/apps/add": lambda b: (play_app(b["accountId"], b["packageName"]), play_apps_list())[1],
                "/api/play/apps/forget": lambda b: (store.play_apps_forget(b["accountId"], b["packageName"]),
                                                    play_apps_list())[1],
                "/api/android/key/generate": lambda b: android.keygen(b["package"], b.get("cn", ""), b.get("org", "")),
                "/api/android/key/import": android_key_import,
                "/api/android/key/remove": lambda b: (store.android_key_remove(b["package"]), {"ok": True})[1],
                "/api/steam/accounts/add": lambda b: (store.steam_account_add(str(b.get("label", "")).strip(),
                                                                              str(b.get("username", "")).strip()),
                                                      store.steam_accounts())[1],
                "/api/steam/accounts/rename": lambda b: (store.steam_account_rename(b["id"],
                                                                                    str(b.get("label", "")).strip()),
                                                         store.steam_accounts())[1],
                "/api/steam/accounts/remove": lambda b: (STEAM_CHECK.pop(b.get("id"), None),
                                                         store.steam_account_remove(b["id"]), store.steam_accounts())[2],
                "/api/steam/apps/set": lambda b: (store.steam_app_set(b["accountId"], b["appId"], str(b.get("name", "")),
                                                                      b.get("depots") or {},
                                                                      str(b.get("branch", ""))),
                                                  store.steam_apps_list())[1],
                "/api/steam/apps/forget": lambda b: (store.steam_apps_forget(b["accountId"], b["appId"]),
                                                     store.steam_apps_list())[1],
                "/api/defaults/set": lambda b: (store.defaults_set(b), topbar())[1],
                "/api/project/settings": project_settings,
                "/api/project/databases": project_databases_save,
                "/api/lojas/save": lojas_save,
                "/api/lojas/generate": lojas_generate,
                "/api/lojas/image/upload": lojas_image_upload,
                "/api/lojas/image/delete": lojas_image_delete,
                "/api/lojas/submit": lojas_submit,
                "/api/lojas/promote": lojas_promote,
                "/api/projects/pull": project_pull,
            }
            if u.path in acc_routes:
                return self._json(acc_routes[u.path](self._body()))
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
    xtool_activate_saved()
    accounts_state()  # adopt an existing login on first run
    threading.Thread(target=_watch_devices, daemon=True).start()
    threading.Thread(target=_auto_pull_loop, daemon=True).start()
    print(f"xtool panel em http://0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
