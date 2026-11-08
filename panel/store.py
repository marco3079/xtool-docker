"""Small JSON stores shared by the server and the release job.

Everything lives in ~/.config/xtool-panel (the xtool-home volume). Secrets (API keys)
go to secrets.json with mode 600 and are never sent back to the browser in full.
"""
import json
import os
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
