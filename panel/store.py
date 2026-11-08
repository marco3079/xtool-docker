"""Small JSON stores shared by the server and the release job.

Everything lives in ~/.config/xtool-panel (the xtool-home volume). Secrets (API keys)
go to secrets.json with mode 600 and are never sent back to the browser in full.
"""
import json
import os
import threading

PANEL_DIR = os.path.expanduser("~/.config/xtool-panel")
ACC_FILE = os.path.join(PANEL_DIR, "accounts.json")
SECRETS = os.path.join(PANEL_DIR, "secrets.json")
PROJECTS = os.path.join(PANEL_DIR, "projects.json")
APPS = os.path.join(PANEL_DIR, "apps.json")
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
        ai = s.setdefault("ai", {"providers": {}, "default": None})
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
    import time
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
