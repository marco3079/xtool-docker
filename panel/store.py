"""Small JSON stores shared by the server and the release job.

Everything lives in ~/.config/xtool-panel (the xtool-home volume). Secrets (API keys)
go to secrets.json with mode 600 and are never sent back to the browser in full.
"""
import json
import os
import re
import threading
import time
import uuid

PANEL_DIR = os.path.expanduser("~/.config/xtool-panel")
ACC_FILE = os.path.join(PANEL_DIR, "accounts.json")
SECRETS = os.path.join(PANEL_DIR, "secrets.json")
PROJECTS = os.path.join(PANEL_DIR, "projects.json")
APPS = os.path.join(PANEL_DIR, "apps.json")
PLAY_APPS = os.path.join(PANEL_DIR, "play_apps.json")
ANDROID_KEYS_DIR = os.path.join(PANEL_DIR, "android-keys")
STEAM_ACCOUNTS = os.path.join(PANEL_DIR, "steam_accounts.json")
STEAM_APPS = os.path.join(PANEL_DIR, "steam_apps.json")
STEAM_PLATFORMS = ("win32", "linux", "darwin")
DEFAULTS = os.path.join(PANEL_DIR, "defaults.json")
_lock = threading.RLock()


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def mask(s):
    s = s or ""
    return (s[:4] + "…" + s[-4:]) if len(s) > 12 else ("•••" if s else "")


# ---- Apple accounts (structure owned by server.py) ----
def account(acc_id):
    st = load(ACC_FILE, {"accounts": []})
    for a in st["accounts"]:
        if a["id"] == acc_id:
            return a
    raise SystemExit("conta Apple não encontrada")


def signing_dir(acc_id):
    return os.path.join(PANEL_DIR, "signing", acc_id)


# ---- secrets ----
def secrets():
    return load(SECRETS, {"asc": {}, "ai": {}})


def asc_key(acc_id):
    return secrets().get("asc", {}).get(acc_id, {})


def asc_key_set(acc_id, issuer, key_id, p8):
    with _lock:
        s = secrets()
        cur = s.setdefault("asc", {}).get(acc_id, {})
        s["asc"][acc_id] = {"issuerId": issuer.strip(), "keyId": key_id.strip(),
                            "p8": p8.strip() if p8 and p8.strip() else cur.get("p8", "")}
        save(SECRETS, s, private=True)


def asc_key_remove(acc_id):
    with _lock:
        s = secrets()
        s.get("asc", {}).pop(acc_id, None)
        save(SECRETS, s, private=True)


def asc_key_public(acc_id):
    k = asc_key(acc_id)
    return {"configured": bool(k.get("p8")), "issuerId": k.get("issuerId", ""), "keyId": k.get("keyId", "")}


def ai_config():
    return secrets().get("ai", {"providers": {}, "default": None})


def ai_public():
    c = ai_config()
    return {"default": c.get("default"),
            "providers": {k: {**{x: y for x, y in v.items() if x != "apiKey"}, "apiKey": mask(v.get("apiKey"))}
                          for k, v in c.get("providers", {}).items()}}


def ai_save(provider, conf, make_default=False):
    with _lock:
        s = secrets()
        ai = s.setdefault("ai", {})
        ai.setdefault("providers", {})
        cur = ai["providers"].get(provider, {})
        new = {**cur, **{k: v for k, v in conf.items() if k != "apiKey"}}
        if conf.get("apiKey") and "…" not in conf["apiKey"] and conf["apiKey"] != "•••":
            new["apiKey"] = conf["apiKey"].strip()
        ai["providers"][provider] = new
        if make_default or not ai.get("default"):
            ai["default"] = provider
        save(SECRETS, s, private=True)


def ai_remove(provider):
    with _lock:
        s = secrets()
        ai = s.get("ai", {})
        ai.get("providers", {}).pop(provider, None)
        if ai.get("default") == provider:
            ai["default"] = next(iter(ai.get("providers", {})), None)
        save(SECRETS, s, private=True)


def ai_provider(provider=None):
    c = ai_config()
    p = provider or c.get("default")
    if not p or p not in c.get("providers", {}):
        raise ValueError("configure uma IA em Configurações de IA primeiro")
    return {"provider": p, **c["providers"][p]}


# ---- per-project links (GitHub repo, Apple account, App Store app) ----
def projects():
    return load(PROJECTS, {})


def project_meta(name):
    return projects().get(name, {})


def project_meta_update(name, patch):
    with _lock:
        p = projects()
        p.setdefault(name, {}).update(patch)
        save(PROJECTS, p)
        return p[name]


# ---- registry of every app seen on each Apple account ----
def apps_registry():
    return load(APPS, {})


def apps_record(acc_id, items):
    """Merge apps found on an account. Each item: bundleId plus any of name/ascId/versions/source."""
    with _lock:
        reg = apps_registry()
        cur = reg.setdefault(acc_id, {})
        now = int(time.time())
        for it in items:
            b = (it.get("bundleId") or "").strip()
            if not b:
                continue
            e = cur.setdefault(b, {"bundleId": b, "added": now})
            for k, v in it.items():
                if k == "sources":
                    e["sources"] = sorted(set(e.get("sources", [])) | set(v))
                elif v not in (None, "", []):
                    e[k] = v
            e["updated"] = now
        save(APPS, reg)
        return cur


def apps_forget(acc_id, bundle=None):
    with _lock:
        reg = apps_registry()
        if bundle is None:
            reg.pop(acc_id, None)
        else:
            reg.get(acc_id, {}).pop(bundle, None)
        save(APPS, reg)


# ---- Google Play accounts (service account JSON lives in secrets.json) ----
def _play_public(a):
    return {k: a.get(k) for k in ("id", "label", "email", "projectId", "added")}


def play_accounts():
    accs = [_play_public(a) for a in secrets().get("play", {}).values()]
    return sorted(accs, key=lambda x: (x.get("label") or "").lower())


def play_account(acc_id):
    a = secrets().get("play", {}).get(acc_id)
    if not a:
        raise ValueError("conta da Play Store não encontrada")
    return a


def play_account_add(label, json_text):
    try:
        sa = json_text if isinstance(json_text, dict) else json.loads(json_text or "")
    except ValueError:
        sa = None
    if not isinstance(sa, dict) or sa.get("type") != "service_account" \
            or not sa.get("client_email") or not sa.get("private_key"):
        raise ValueError("arquivo JSON não é uma chave de conta de serviço do Google")
    acc = {"id": uuid.uuid4().hex[:8], "label": (label or "").strip() or sa["client_email"],
           "email": sa["client_email"], "projectId": sa.get("project_id", ""),
           "added": int(time.time()), "json": sa}
    with _lock:
        s = secrets()
        s.setdefault("play", {})[acc["id"]] = acc
        save(SECRETS, s, private=True)
    return _play_public(acc)


def play_account_rename(acc_id, label):
    with _lock:
        s = secrets()
        a = s.setdefault("play", {}).get(acc_id)
        if not a:
            raise ValueError("conta da Play Store não encontrada")
        a["label"] = (label or "").strip() or a.get("label", "")
        save(SECRETS, s, private=True)


def play_account_remove(acc_id):
    with _lock:
        s = secrets()
        s.setdefault("play", {}).pop(acc_id, None)
        save(SECRETS, s, private=True)
        play_apps_forget(acc_id)
        _defaults_forget("playAccountId", acc_id)


# ---- Google Play apps seen on each account (packageName -> name, tracks) ----
def play_apps_registry():
    return load(PLAY_APPS, {})


def play_apps_record(acc_id, items):
    """Merge apps found on a Play account. Each item: packageName plus any of name/tracks."""
    with _lock:
        reg = play_apps_registry()
        cur = reg.setdefault(acc_id, {})
        now = int(time.time())
        for it in items:
            p = (it.get("packageName") or "").strip()
            if not p:
                continue
            e = cur.setdefault(p, {"packageName": p, "added": now})
            for k, v in it.items():
                if k == "tracks":
                    e["tracks"] = v or []
                elif v not in (None, "", []):
                    e[k] = v
            e["updated"] = now
        save(PLAY_APPS, reg)
        return cur


def play_apps_forget(acc_id, package=None):
    with _lock:
        reg = play_apps_registry()
        if package is None:
            reg.pop(acc_id, None)
        else:
            reg.get(acc_id, {}).pop(package, None)
        save(PLAY_APPS, reg)


# ---- Android signing keys (keystore file in ANDROID_KEYS_DIR, passwords in secrets.json) ----
def android_key(package):
    return secrets().get("androidKeys", {}).get(package, {})


def android_key_public(package):
    k = android_key(package)
    return {"configured": bool(k), "keyAlias": k.get("keyAlias", ""), "sha1": k.get("sha1", ""),
            "sha256": k.get("sha256", ""), "created": k.get("created"),
            "file": os.path.basename(k["file"]) if k.get("file") else ""}


def android_key_set(package, data):
    with _lock:
        s = secrets()
        s.setdefault("androidKeys", {})[package] = dict(data)
        save(SECRETS, s, private=True)


def android_key_remove(package):
    with _lock:
        s = secrets()
        k = s.setdefault("androidKeys", {}).pop(package, None)
        save(SECRETS, s, private=True)
    if k and k.get("file"):
        try:
            os.remove(k["file"])
        except OSError:
            pass


# ---- Steam (contas e apps; a senha nunca é gravada) ----
# A senha fica só no login do steamcmd (/root/Steam); aqui vão apenas usuário e apps.
_STEAM_USER_RE = r"[A-Za-z0-9_.-]{2,64}"
_STEAM_BRANCH_RE = r"[A-Za-z0-9_.-]{1,64}"
_STEAM_ID_RE = r"[0-9]{1,10}"


def _steam_public(a):
    return {k: a.get(k) for k in ("id", "label", "username", "added")}


def _steam_accounts():
    return load(STEAM_ACCOUNTS, {})


def steam_accounts():
    accs = [_steam_public(a) for a in _steam_accounts().values()]
    return sorted(accs, key=lambda x: (x.get("label") or "").lower())


def steam_account(acc_id):
    a = _steam_accounts().get(acc_id)
    if not a:
        raise ValueError("conta Steam não encontrada")
    return _steam_public(a)


def steam_account_add(label, username):
    username = (username or "").strip()
    if not re.fullmatch(_STEAM_USER_RE, username):
        raise ValueError("usuário da Steam inválido (letras, números, _ . -)")
    with _lock:
        accs = _steam_accounts()
        if any((a.get("username") or "").lower() == username.lower() for a in accs.values()):
            raise ValueError("essa conta Steam já está cadastrada")
        acc = {"id": uuid.uuid4().hex[:8], "label": (label or "").strip() or username,
               "username": username, "added": int(time.time())}
        accs[acc["id"]] = acc
        save(STEAM_ACCOUNTS, accs)
    return _steam_public(acc)


def steam_account_rename(acc_id, label):
    with _lock:
        accs = _steam_accounts()
        a = accs.get(acc_id)
        if not a:
            raise ValueError("conta Steam não encontrada")
        a["label"] = (label or "").strip() or a.get("label", "")
        save(STEAM_ACCOUNTS, accs)


def steam_account_remove(acc_id):
    with _lock:
        accs = _steam_accounts()
        accs.pop(acc_id, None)
        save(STEAM_ACCOUNTS, accs)
        steam_apps_forget(acc_id)
        _defaults_forget("steamAccountId", acc_id)


# registro de apps Steam: {accId: {appId: entrada}}
def steam_apps_registry():
    return load(STEAM_APPS, {})


def steam_app_set(acc_id, app_id, name="", depots=None, branch=""):
    steam_account(acc_id)  # propaga ValueError se a conta não existir
    app_id = str(app_id).strip()
    if not re.fullmatch(_STEAM_ID_RE, app_id):
        raise ValueError("App ID da Steam inválido (só números)")
    clean = {}
    for k, v in (depots or {}).items():
        if k not in STEAM_PLATFORMS:
            raise ValueError(f"plataforma desconhecida: {k}")
        v = ("" if v is None else str(v)).strip()
        if not v:
            continue
        if not re.fullmatch(_STEAM_ID_RE, v):
            raise ValueError(f"Depot ID inválido para {k} (só números)")
        clean[k] = v
    if not clean:
        raise ValueError("informe o Depot ID de pelo menos uma plataforma")
    branch = (branch or "").strip()
    if branch == "default":
        raise ValueError("a branch default não pode ser liberada automaticamente pelo steamcmd; use outra branch ou libere no site do Steamworks")
    if branch and not re.fullmatch(_STEAM_BRANCH_RE, branch):
        raise ValueError("nome de branch inválido")
    with _lock:
        reg = steam_apps_registry()
        cur = reg.setdefault(acc_id, {})
        old = cur.get(app_id, {})
        now = int(time.time())
        entry = {"appId": app_id, "name": (name or "").strip() or old.get("name") or f"App {app_id}",
                 "depots": clean, "branch": branch,
                 "added": old.get("added", now), "updated": now}
        cur[app_id] = entry
        save(STEAM_APPS, reg)
    return entry


def steam_app(acc_id, app_id):
    e = steam_apps_registry().get(acc_id, {}).get(str(app_id).strip())
    if not e:
        raise ValueError("app Steam não cadastrado")
    return e


def steam_apps_list():
    accs = _steam_accounts()
    out = []
    for acc_id, apps in steam_apps_registry().items():
        acc = accs.get(acc_id)
        if not acc:
            continue  # conta removida: ignora os apps dela
        for e in apps.values():
            out.append({"accountId": acc_id, "accountLabel": acc.get("label", ""), **e})
    return sorted(out, key=lambda x: (x.get("name") or x.get("appId") or "").lower())


def steam_apps_forget(acc_id, app_id=None):
    with _lock:
        reg = steam_apps_registry()
        if app_id is None:
            reg.pop(acc_id, None)
        else:
            reg.get(acc_id, {}).pop(str(app_id).strip(), None)
        save(STEAM_APPS, reg)


# ---- defaults da barra do topo (conta Steam e conta Play principais; só ids) ----
_DEFAULT_KEYS = ("steamAccountId", "playAccountId")


def defaults_get():
    d = load(DEFAULTS, {})
    if not isinstance(d, dict):
        d = {}
    return {k: (d[k] if isinstance(d.get(k), str) else "") for k in _DEFAULT_KEYS}


def defaults_set(patch):
    patch = patch or {}
    for k, v in patch.items():
        if k not in _DEFAULT_KEYS:
            raise ValueError(f"opção desconhecida: {k}")
        if not isinstance(v, str):
            raise ValueError(f"valor inválido para {k} (texto esperado)")
    with _lock:
        new = defaults_get()
        for k, v in patch.items():
            if v == "":
                new[k] = ""
            elif k == "steamAccountId":
                if v not in {a["id"] for a in steam_accounts()}:
                    raise ValueError("conta Steam não encontrada")
                new[k] = v
            else:
                if v not in {a["id"] for a in play_accounts()}:
                    raise ValueError("conta da Play Store não encontrada")
                new[k] = v
        save(DEFAULTS, new)
    return defaults_get()


def _defaults_forget(key, acc_id):
    with _lock:
        d = load(DEFAULTS, {})
        if isinstance(d, dict) and d.get(key) == acc_id:
            d.pop(key, None)
            save(DEFAULTS, d)
