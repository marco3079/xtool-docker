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
import github
import store
from asc import ASC, AscError
from play import Play, PlayError

PANEL_PY = os.path.dirname(os.path.abspath(__file__))

VERSION = "1.1.0"
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


def xtool_latest(force=False):
    if force or time.time() - _latest["at"] > 3600:
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
        "xtoolLatest": xtool_latest(),
        "xtoolUpdate": bool(xtool_latest()) and _vtuple(xtool_latest()) > _vtuple(xt),
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
        if not ios and not andr:
            continue
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
        res.append({
            "name": name,
            "hasToml": bool(yml),
            "bundleId": yml.get("bundleID", ""),
            "artifacts": sorted(arts),
            "mtime": os.stat(d).st_mtime,
            "meta": store.project_meta(name),
            "git": gs,
            "platforms": [p for p, ok in (("ios", ios), ("android", andr)) if ok],
            "android": andr,
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
              for i in out["identifiers"] or []]
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
        for e in apps.values():
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


def android_info(project):
    d = safe_path("work", project)
    meta = store.project_meta(project).get("android", {})
    det = android.detect(d)
    pkg = meta.get("packageName") or (det or {}).get("packageName") or ""
    play, play_err = None, None
    if meta.get("playAccountId") and pkg:
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
            "play": play, "playError": play_err, "changes": changes}


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
        "adb.pair": lambda: ["adb", "pair", q("addr"), q("code")],
        "adb.connect": lambda: ["adb", "connect", q("addr")],
        "adb.disconnect": lambda: ["adb", "disconnect"],
        "adb.devices": lambda: ["adb", "devices", "-l"],
        "adb.install": lambda: ["adb"] + s + ["install", "-r", q("path")],
        "adb.launch": lambda: ["adb"] + s + ["shell", "monkey", "-p", q("package"),
                                             "-c", "android.intent.category.LAUNCHER", "1"],
        "xtool.update": lambda: ["bash", "-c", XTOOL_UPDATE],
    }
    if action not in cmds:
        raise ValueError(f"ação desconhecida: {action}")
    argv = cmds[action]()
    if any(x == "" for x in argv):
        raise ValueError("preencha os campos obrigatórios")
    env = {}
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
            if u.path == "/api/android/info":
                return self._json(android_info(qs.get("project", "")))
            if u.path == "/api/android/key":
                return self._json(store.android_key_public(qs.get("package", "")))
            if u.path == "/api/android/key/download":
                k = store.android_key(qs.get("package", ""))
                if not k.get("file"):
                    raise ValueError("chave não encontrada")
                return self._file(k["file"], download=True)
            if u.path == "/api/adb/devices":
                return self._json(adb_devices())
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
    print(f"xtool panel em http://0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
