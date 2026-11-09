#!/usr/bin/env python3
"""Detecta bancos de dados no código de um projeto.

Python 3 stdlib apenas. API:
  detect(project_dir: str) -> list[dict]
CLI:
  python3 dbdetect.py <pasta>   (imprime o JSON de detect)
"""
from __future__ import annotations

import json
import os
import re
import sys

IGNORE_DIRS = {
    "node_modules", ".git", "xtool", "dist", "build", ".gradle",
    "Pods", ".next", "coverage", ".build", ".swiftpm", "DerivedData", ".venv", "venv", "__pycache__",
}  # "android/app/build" já é coberto pelo nome "build"

CODE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".dart", ".kt", ".swift")
MAX_CODE_FILES = 400
MAX_FILE_BYTES = 300 * 1024
MAX_EVIDENCE = 5

PROD_DIRS = {"prod", "production", "release", "live"}
DEV_DIRS = {"dev", "development", "debug", "staging", "stage", "test"}
ENV_DIRS = PROD_DIRS | DEV_DIRS
ROLE_ORDER = {"prod": 0, "dev": 1, "other": 2}

PROD_BUILDS = ["build:client:prod", "build:prod", "build:production", "build:release"]
DEV_BUILDS = ["build:client:dev", "build:dev", "build:development", "build:client", "build"]

DEFAULT_PLIST_DEST = "ios/App/App/GoogleService-Info.plist"
ANDROID_DEST = "android/app/google-services.json"
FIREBASE_SERVICES = ("rtdb", "firestore")
SQLITE_DEPS = ("better-sqlite3", "sqlite3", "sql.js")
SQLITE_EXTS = (".sqlite", ".sqlite3", ".db")
ENV_KEYS = {"SUPABASE_URL", "DATABASE_URL", "MONGODB_URI", "MONGO_URL"}

RTDB_RE = re.compile(
    r"https://([a-z0-9-]+?)(?:-default-rtdb)?\.(?:firebaseio\.com|[a-z0-9-]+\.firebasedatabase\.app)"
)
PROJECT_ID_RE = re.compile(r"projectId\s*[:=]\s*['\"]([\w-]+)['\"]")
SUPABASE_RE = re.compile(r"https://([a-z0-9]{20})\.supabase\.co")
# URL inteira; a separação user/senha/host é feita depois, pelo ÚLTIMO "@" (a senha pode conter "@").
DB_RE = re.compile(r"\b(mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://([^\s'\"`)\],;]+)")
PLIST_PID_RE = re.compile(r"<key>PROJECT_ID</key>\s*<string>([^<]+)</string>")
ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")

DB_LABELS = {"mongodb": "MongoDB", "postgres": "PostgreSQL", "mysql": "MySQL"}


def _read_text(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _inside(path, root_real):
    """True se o realpath de `path` está dentro de `root_real`."""
    try:
        real = os.path.realpath(path)
        return os.path.commonpath([real, root_real]) == root_real
    except (OSError, ValueError):
        return False


def _walk(root):
    """Lista (rel_posix, abs_path, nome) de todos os arquivos, ignorando pastas proibidas.

    Symlinks (arquivos e pastas) são pulados; qualquer caminho cujo realpath
    fique fora da raiz do projeto também é pulado. Só estes caminhos são lidos depois.
    """
    out = []
    root_real = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        kept = []
        for d in sorted(dirnames):
            dp = os.path.join(dirpath, d)
            if d in IGNORE_DIRS or os.path.islink(dp) or not _inside(dp, root_real):
                continue
            kept.append(d)
        dirnames[:] = kept
        for fn in sorted(filenames):
            ap = os.path.join(dirpath, fn)
            if os.path.islink(ap) or not _inside(ap, root_real):
                continue
            rel = os.path.relpath(ap, root).replace(os.sep, "/")
            out.append((rel, ap, fn))
    return out


def _split_db_url(tail):
    """Recebe o texto após 'scheme://' e devolve (user, rest) ou None.

    A senha é tudo entre o primeiro ':' e o ÚLTIMO '@'; rest é o que vem depois do último '@'.
    """
    if "@" not in tail:
        return None
    creds, rest = tail.rsplit("@", 1)
    if ":" not in creds or not rest:
        return None
    user = creds.split(":", 1)[0]
    return user, rest


def _is_code(name):
    low = name.lower()
    return name.startswith(".env") or low.endswith(CODE_EXTS)


def _env_key_ok(key):
    return key.startswith("FIREBASE_") or key in ENV_KEYS


def _in_env_dir(rel):
    return any(seg.lower() in ENV_DIRS for seg in rel.split("/")[:-1])


def _google_services_pid(path):
    text = _read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    info = data.get("project_info") if isinstance(data, dict) else None
    pid = info.get("project_id") if isinstance(info, dict) else None
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return None


def _pkg_has_sqlite(path):
    text = _read_text(path)
    if text is None:
        return False
    try:
        data = json.loads(text)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    deps = {}
    for key in ("dependencies", "devDependencies"):
        val = data.get(key)
        if isinstance(val, dict):
            deps.update(val)
    return any(d in deps for d in SQLITE_DEPS)


def _read_scripts(root):
    text = _read_text(os.path.join(root, "package.json"))
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return scripts if isinstance(scripts, dict) else {}


class _Store:
    def __init__(self):
        self.items = {}    # (provider, identifier) -> dict
        self.native = {}   # project_id -> {"android": rel, "ios": rel}

    def add(self, provider, identifier, name, evidence, services=()):
        key = (provider, identifier)
        it = self.items.get(key)
        if it is None:
            it = {"provider": provider, "identifier": identifier, "name": name,
                  "services": set(), "evidence": []}
            self.items[key] = it
        it["services"].update(services)
        if evidence and evidence not in it["evidence"]:
            it["evidence"].append(evidence)

    def add_firebase(self, pid, evidence, services=()):
        self.add("firebase", pid, f"Firebase {pid}", evidence, services)


def _scan_text(text, rel, store):
    for m in RTDB_RE.finditer(text):
        store.add_firebase(m.group(1), rel, ("rtdb",))

    pids = PROJECT_ID_RE.findall(text)
    if pids:
        has_firestore = "getFirestore" in text or "firebase/firestore" in text
        if has_firestore or "firebase" in text.lower():
            for pid in dict.fromkeys(pids):
                store.add_firebase(pid, rel, ("firestore",) if has_firestore else ())

    for m in SUPABASE_RE.finditer(text):
        ref = m.group(1)
        store.add("supabase", ref, f"Supabase {ref}", rel)

    for m in DB_RE.finditer(text):
        scheme, tail = m.group(1), m.group(2)
        parts = _split_db_url(tail)
        if parts is None:
            continue
        user, rest = parts
        if scheme.startswith("mongodb"):
            provider = "mongodb"
        elif scheme.startswith("postgres"):
            provider = "postgres"
        else:
            provider = "mysql"
        identifier = f"{scheme}://{user}:***@{rest}"
        host = re.split(r"[/?]", rest, maxsplit=1)[0]
        store.add(provider, identifier, f"{DB_LABELS[provider]} {host}", rel)


def _role(identifier, evidence):
    dirs = set()
    for p in evidence:
        for seg in p.split("/")[:-1]:
            dirs.add(seg.lower())
    if dirs & PROD_DIRS:
        return "prod"
    if dirs & DEV_DIRS:
        return "dev"
    low = identifier.lower()
    if low.endswith("-prod"):
        return "prod"
    if low.endswith(("-dev", "-staging")):
        return "dev"
    return "other"


def _first_script(scripts, names):
    for n in names:
        if n in scripts:
            return f"npm run {n}"
    return ""


def _pre_build(role, scripts):
    pre = ""
    if role == "prod":
        pre = _first_script(scripts, PROD_BUILDS)
    elif role == "dev":
        pre = _first_script(scripts, DEV_BUILDS)
    native_env = role in ("prod", "dev") and "native:env" in scripts
    if native_env:
        extra = f"npm run native:env -- {role}"
        pre = f"{pre} && {extra}" if pre else extra
    return pre, native_env


def _copy_files(native, plists):
    copies = []
    android_src = native.get("android")
    if android_src and android_src != ANDROID_DEST:
        copies.append({"from": android_src, "to": ANDROID_DEST})
    ios_src = native.get("ios")
    if ios_src:
        dest = next((p for p in plists if not _in_env_dir(p)), DEFAULT_PLIST_DEST)
        if ios_src != dest:
            copies.append({"from": ios_src, "to": dest})
    return copies


def _detect(project_dir):
    root = os.path.abspath(project_dir)
    files = _walk(root)
    store = _Store()

    # 1. Firebase nativo
    plists = []
    for rel, ap, name in files:
        try:
            if name == "google-services.json":
                pid = _google_services_pid(ap)
                if pid:
                    store.add_firebase(pid, rel)
                    store.native.setdefault(pid, {}).setdefault("android", rel)
            elif name == "GoogleService-Info.plist":
                plists.append(rel)
                text = _read_text(ap)
                m = PLIST_PID_RE.search(text) if text else None
                if m and m.group(1).strip():
                    pid = m.group(1).strip()
                    store.add_firebase(pid, rel)
                    store.native.setdefault(pid, {}).setdefault("ios", rel)
        except Exception:
            continue

    # 2. Varredura de código (limite de 400 arquivos, cada um <= 300 KB)
    code_files = [f for f in files if _is_code(f[2])][:MAX_CODE_FILES]
    for rel, ap, name in code_files:
        try:
            if os.path.getsize(ap) > MAX_FILE_BYTES:
                continue
            text = _read_text(ap)
            if text is None:
                continue
            if name.startswith(".env"):
                for line in text.splitlines():
                    m = ENV_LINE_RE.match(line)
                    if m and _env_key_ok(m.group(1)):
                        _scan_text(m.group(2), rel, store)
            else:
                _scan_text(text, rel, store)
        except Exception:
            continue

    # SQLite: arquivos e dependências em package.json
    sqlite_pkgs = []
    for rel, ap, name in files:
        try:
            low = name.lower()
            if low.endswith(SQLITE_EXTS):
                store.add("sqlite", rel, f"SQLite {rel}", rel)
            if low == "package.json" and _pkg_has_sqlite(ap):
                sqlite_pkgs.append(rel)
        except Exception:
            continue
    if sqlite_pkgs and not any(k[0] == "sqlite" for k in store.items):
        for rel in sqlite_pkgs:
            store.add("sqlite", "sqlite", "SQLite (dependência)", rel)

    # Saída
    scripts = _read_scripts(root)
    result = []
    for it in store.items.values():
        provider = it["provider"]
        identifier = it["identifier"]
        role = _role(identifier, it["evidence"])
        pre, native_env = _pre_build(role, scripts)
        copies = []
        if provider == "firebase" and not native_env:
            copies = _copy_files(store.native.get(identifier, {}), plists)
        services = [s for s in FIREBASE_SERVICES if s in it["services"]] if provider == "firebase" else []
        result.append({
            "provider": provider,
            "identifier": identifier,
            "name": it["name"],
            "services": services,
            "suggestedRole": role,
            "evidence": it["evidence"][:MAX_EVIDENCE],
            "recipe": {"preBuild": pre, "copyFiles": copies, "env": {}},
        })

    result.sort(key=lambda c: (ROLE_ORDER[c["suggestedRole"]], c["identifier"]))
    return result


def detect(project_dir: str) -> list:
    """Retorna a lista de candidatos de banco de dados do projeto. Nunca lança exceção."""
    try:
        return _detect(str(project_dir))
    except Exception:
        return []


def main(argv):
    if len(argv) < 2:
        print("uso: python3 dbdetect.py <pasta>", file=sys.stderr)
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(detect(argv[1]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
