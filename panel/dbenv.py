#!/usr/bin/env python3
"""Bancos de dados por projeto: cadastro, receita antes do build, registro de qual banco
gerou cada build e regra de envio para a loja (só o banco prod vai para a loja).

Dados ficam em meta["databases"] (lista) e meta["buildDb"] (registro por arquivo) do projects.json.

usage:
  dbenv.py apply <project> <dbid>            copia os arquivos da receita do banco
  dbenv.py record <project> <dbid> <epoch>   registra o banco nos builds feitos desde <epoch>
"""
import os
import re
import shutil
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

WORK = os.environ.get("XTOOL_WORK", "/work")
PROVIDERS = ("firebase", "supabase", "mongodb", "postgres", "mysql", "sqlite", "custom")
ROLES = ("prod", "dev", "other")
SOURCES = ("detected", "manual")
SERVICES = ("rtdb", "firestore")
MAX_DBS = 12
MAX_COPY = 10
MAX_ENV = 20
PRE_BUILD_ACTIONS = ("android.release", "pc.build", "steam.release")
ID_RE = re.compile(r"[a-z0-9-]{1,32}")
ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---- validação ----
def _text(v, field, lo, hi):
    if not isinstance(v, str):
        raise ValueError(f"{field}: texto esperado")
    s = v.strip()
    if len(s) < lo or len(s) > hi:
        raise ValueError(f"{field}: deve ter entre {lo} e {hi} caracteres")
    return s


def _clean_path(v, what):
    p = _text(v, what, 1, 500)
    parts = re.split(r"[\\/]+", p)
    if os.path.isabs(p) or p.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", p) or ".." in parts:
        raise ValueError(f"{what} inválido (use caminho relativo à pasta do projeto, sem '..'): {p}")
    return p


def _clean_recipe(r):
    if r is None:
        r = {}
    if not isinstance(r, dict):
        raise ValueError("receita inválida (objeto esperado)")
    pre = _text(r.get("preBuild") or "", "comando pré-build", 0, 500)
    copies_in = r.get("copyFiles") or []
    if not isinstance(copies_in, list):
        raise ValueError("copyFiles deve ser uma lista")
    if len(copies_in) > MAX_COPY:
        raise ValueError(f"no máximo {MAX_COPY} arquivos para copiar na receita")
    copies = []
    for c in copies_in:
        if not isinstance(c, dict):
            raise ValueError("cada cópia da receita precisa de 'from' e 'to'")
        copies.append({"from": _clean_path(c.get("from"), "origem da cópia"),
                       "to": _clean_path(c.get("to"), "destino da cópia")})
    env_in = r.get("env") or {}
    if not isinstance(env_in, dict):
        raise ValueError("env da receita deve ser um objeto CHAVE: valor")
    if len(env_in) > MAX_ENV:
        raise ValueError(f"no máximo {MAX_ENV} variáveis de ambiente na receita")
    env = {}
    for k, v in env_in.items():
        if not isinstance(k, str) or not ENV_KEY_RE.fullmatch(k):
            raise ValueError(f"nome de variável inválido: {k}")
        if not isinstance(v, str):
            raise ValueError(f"valor de {k} deve ser texto")
        if len(v) > 500 or "\n" in v or "\r" in v:
            raise ValueError(f"valor de {k} inválido (até 500 caracteres, sem quebra de linha)")
        env[k] = v
    return {"preBuild": pre, "copyFiles": copies, "env": env}


def _clean(db):
    did = db.get("id")
    if not isinstance(did, str) or not ID_RE.fullmatch(did):
        raise ValueError("id do banco inválido (use a-z, 0-9 e hífen, até 32 caracteres)")
    name = _text(db.get("name"), "nome do banco", 1, 60)
    provider = db.get("provider")
    if provider not in PROVIDERS:
        raise ValueError("provedor inválido: use " + ", ".join(PROVIDERS))
    identifier = _text(db.get("identifier") or "", "identificador do banco", 0, 300)
    services_in = db.get("services") or []
    if not isinstance(services_in, list):
        raise ValueError("serviços devem ser uma lista")
    services = []
    for s in services_in:
        if s not in SERVICES:
            raise ValueError("serviço inválido: use " + " ou ".join(SERVICES))
        if s not in services:
            services.append(s)
    role = db.get("role") or "other"
    if role not in ROLES:
        raise ValueError("papel inválido: use prod, dev ou other")
    source = db.get("source") or "manual"
    if source not in SOURCES:
        raise ValueError("origem inválida: use detected ou manual")
    return {"id": did, "name": name, "provider": provider, "identifier": identifier,
            "services": services, "role": role, "source": source,
            "recipe": _clean_recipe(db.get("recipe"))}


def _slug(name, taken):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:32].strip("-") or "banco"
    cand, n = s, 2
    while cand in taken:
        suf = f"-{n}"
        cand = s[:32 - len(suf)].rstrip("-") + suf
        n += 1
    return cand


# ---- leitura ----
def databases(project):
    return [dict(d) for d in (store.project_meta(project).get("databases") or [])]


def has_databases(project):
    return bool(databases(project))


def get(project, dbid):
    for d in databases(project):
        if d.get("id") == dbid:
            return d
    return None


def prod_id(project):
    for d in databases(project):
        if d.get("role") == "prod":
            return d.get("id", "")
    return ""


def registry(project):
    return dict(store.project_meta(project).get("buildDb") or {})


def build_db(project, file_rel):
    e = registry(project).get(file_rel)
    if not e:
        return None
    cur = get(project, e.get("id"))
    return {**e, "role": cur["role"] if cur else ""}


def deliverable(project, file_rel):
    if not has_databases(project):
        return True, ""
    e = build_db(project, file_rel)
    if e is None:
        return False, "build sem banco registrado: gere de novo escolhendo o banco prod"
    if e.get("role") != "prod":
        label = e.get("role") or "removido"
        return False, f"feito com o banco {e.get('name')} ({label}): só o banco prod vai para a loja"
    return True, ""


# ---- escrita ----
def save_database(project, db):
    if not isinstance(db, dict):
        raise ValueError("banco inválido")
    with store._lock:
        dbs = databases(project)
        raw_id = (db.get("id") or "").strip() if isinstance(db.get("id"), str) else db.get("id")
        current = next((d for d in dbs if raw_id and d.get("id") == raw_id), None)
        if current is None:
            if len(dbs) >= MAX_DBS:
                raise ValueError(f"máximo de {MAX_DBS} bancos por projeto")
            merged = dict(db)
            if not raw_id:
                name = _text(db.get("name"), "nome do banco", 1, 60)
                merged["id"] = _slug(name, {d.get("id") for d in dbs})
        else:
            merged = {**current, **{k: v for k, v in db.items() if k != "id"}, "id": current["id"]}
        clean = _clean(merged)
        for d in dbs:
            if d.get("id") != clean["id"] and clean["role"] in ("prod", "dev") and d.get("role") == clean["role"]:
                raise ValueError(f"já existe um banco {clean['role']} neste projeto: {d.get('name')}")
        if current is None:
            new_dbs = dbs + [clean]
        else:
            new_dbs = [clean if d.get("id") == clean["id"] else d for d in dbs]
        store.project_meta_update(project, {"databases": new_dbs})
    return dict(clean)


def delete_database(project, dbid):
    with store._lock:
        meta = store.project_meta(project)
        dbs = list(meta.get("databases") or [])
        if not any(d.get("id") == dbid for d in dbs):
            raise ValueError("banco não encontrado")
        new_dbs = [d for d in dbs if d.get("id") != dbid]
        reg = {k: v for k, v in (meta.get("buildDb") or {}).items() if v.get("id") != dbid}
        store.project_meta_update(project, {"databases": new_dbs, "buildDb": reg})


def step_plan(project, action, args):
    args = args or {}
    dbid = args.get("database")
    if not dbid:
        return args, {}
    db = get(project, dbid)
    if db is None:
        raise ValueError("banco não encontrado")
    args2 = dict(args)
    rec = db.get("recipe") or {}
    pre = rec.get("preBuild") or ""
    if pre and action in PRE_BUILD_ACTIONS:
        args2["preBuild"] = pre
    env = dict(rec.get("env") or {})
    env["XTOOL_DB_ID"] = db["id"]
    env["XTOOL_DB_ROLE"] = db["role"]
    return args2, env


def _is_store_upload(action, args):
    if action == "android.release":
        return bool(args.get("upload"))
    if action == "release":
        return bool(args.get("ipaFile")) or bool((args.get("steps") or {}).get("upload"))
    if action == "steam.release":
        return bool(args.get("upload", True))
    return False


def _is_existing_file_mode(action, args):
    if action == "android.release":
        return bool(args.get("existing"))
    if action == "release":
        return bool(args.get("ipaFile"))
    if action == "steam.release":
        return isinstance(args.get("fromZips"), dict) or args.get("build") is False
    return False


def check_store_step(project, action, args, file_rels=None):
    args = args or {}
    if not _is_store_upload(action, args) or not has_databases(project):
        return
    if _is_existing_file_mode(action, args):
        rels = list(file_rels or [])
        if not rels:
            raise ValueError("nenhum arquivo informado para conferir o banco do build")
        for rel in rels:
            ok, reason = deliverable(project, rel)
            if not ok:
                raise ValueError(reason)
        return
    dbid = args.get("database")
    db = get(project, dbid) if dbid else None
    if db is None or db.get("role") != "prod":
        raise ValueError("só dá para enviar para a loja com o banco prod")


def abs_to_rel(abs_path):
    ap = os.path.normpath(os.path.abspath(abs_path))
    base = os.path.normpath(os.path.abspath(WORK))
    try:
        if os.path.commonpath([ap, base]) == base:
            return os.path.relpath(ap, base).replace(os.sep, "/")
    except ValueError:
        pass
    return os.path.normpath(abs_path).replace(os.sep, "/")


# ---- receita e registro (CLI) ----
def _safe_rel(p, what):
    if not isinstance(p, str) or not p.strip():
        raise SystemExit(f"{what} vazio na receita")
    p = p.strip()
    parts = re.split(r"[\\/]+", p)
    if os.path.isabs(p) or p.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", p) or ".." in parts:
        raise SystemExit(f"{what} inválido na receita (use caminho relativo à pasta do projeto, sem '..'): {p}")
    return p


def apply_recipe(project, dbid):
    db = get(project, dbid)
    if db is None:
        raise SystemExit("banco não encontrado")
    copies = (db.get("recipe") or {}).get("copyFiles") or []
    if not copies:
        print(f"Receita do banco {db['name']}: nada a copiar")
        return
    base = os.path.join(WORK, project)
    plan = []
    for c in copies:
        src_rel = _safe_rel(c.get("from"), "origem")
        dst_rel = _safe_rel(c.get("to"), "destino")
        src = os.path.join(base, src_rel)
        if not os.path.isfile(src):
            raise SystemExit(f"arquivo de origem não encontrado: {src_rel}")
        plan.append((src_rel, src, dst_rel, os.path.join(base, dst_rel)))
    for src_rel, src, dst_rel, dst in plan:
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"Receita do banco {db['name']}: copiado {src_rel} -> {dst_rel}")


def record_builds(project, dbid, since_epoch):
    import builds  # lazy: builds importa dbenv, evita ciclo no import
    rows = builds.list_builds(project, os.path.join(WORK, project))
    mine = [b for b in rows if (b.get("at") or 0) >= float(since_epoch) - 1]
    now = time.time()
    with store._lock:
        db = get(project, dbid)
        if db is None:
            raise ValueError("banco não encontrado")
        reg = registry(project)
        for b in mine:
            reg[b["file"]] = {"id": db["id"], "name": db["name"], "role": db["role"], "at": now}
        store.project_meta_update(project, {"buildDb": reg})
    print(f"Banco {db['name']} registrado em {len(mine)} build(s)")
    return len(mine)


def main(argv):
    try:
        if len(argv) == 4 and argv[1] == "apply":
            apply_recipe(argv[2], argv[3])
            return 0
        if len(argv) == 5 and argv[1] == "record":
            try:
                since = float(argv[4])
            except ValueError:
                print("epoch inválido", file=sys.stderr)
                return 1
            record_builds(argv[2], argv[3], since)
            return 0
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("uso: dbenv.py apply <projeto> <banco> | record <projeto> <banco> <epoch>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
