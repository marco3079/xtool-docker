"""Atualização do painel pelo último commit de marco3079/xtool-docker (branch main).

Só a pasta panel/ é trocada. Mudanças fora dela (Dockerfile, base/, docker-compose.yml)
pedem rebuild da imagem: aqui só são listadas para o aviso.
"""
import hashlib
import json
import os
import py_compile
import re
import shutil
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request

REPO = "marco3079/xtool-docker"
BRANCH = "main"
PANEL_DIR = os.path.dirname(os.path.abspath(__file__))
COMMIT_FILE = os.path.join(PANEL_DIR, ".commit")
BACKUP_DIR = "/root/.xtool-panel-backup"
BACKUP_KEEP = 3
CHECK_TTL = 6 * 3600
ERROR_TTL = 600
UA = "xtool-painel"

_cache = {"at": 0.0, "res": None}
_lock = threading.Lock()        # protege o cache do check
_apply_lock = threading.Lock()  # uma atualização por vez


class UpdateError(Exception):
    pass


def installed_commit():
    """Commit do painel instalado (gravado pelo apply) ou None."""
    try:
        with open(COMMIT_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _http(url, accept=None, timeout=20, what="consultar o GitHub"):
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        extra = " (limite da API)" if e.code in (403, 429) else ""
        raise UpdateError(f"Não foi possível {what}: HTTP {e.code}{extra}")
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"Não foi possível {what}: {getattr(e, 'reason', e)}")


def _get_json(url):
    try:
        return json.loads(_http(url, accept="application/vnd.github+json"))
    except ValueError:
        raise UpdateError("Não foi possível consultar o GitHub: resposta inválida")


def _blob_sha(data):
    """SHA-1 do objeto blob do git (o mesmo que o GitHub informa na árvore)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _tree(base):
    """Arquivos e pastas de uma pasta do painel. Ignora __pycache__ e *.pyc.
    Devolve ({caminho com '/': caminho no disco}, {pastas com '/'})."""
    files, dirs = {}, set()
    for root, ds, fs in os.walk(base):
        ds[:] = [d for d in ds if d != "__pycache__"]
        for d in ds:
            dirs.add(os.path.relpath(os.path.join(root, d), base).replace(os.sep, "/"))
        for f in fs:
            if f.endswith(".pyc"):
                continue
            p = os.path.join(root, f)
            files[os.path.relpath(p, base).replace(os.sep, "/")] = p
    return files, dirs


def _build(version):
    """Consulta o GitHub e monta o resultado do check. Nunca lança: erro vai em 'error'."""
    installed = installed_commit()
    res = {"repo": REPO, "branch": BRANCH,
           "installed": {"version": version, "commit": installed},
           "latest": None, "changes": [], "imageChanges": None,
           "upToDate": False, "checkedAt": int(time.time()), "error": ""}
    try:
        info = _get_json(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}")
        sha = info["sha"]
        commit = info["commit"]

        tree = _get_json(f"https://api.github.com/repos/{REPO}/git/trees/{sha}?recursive=1")
        remote = {}
        for e in tree.get("tree") or []:
            if e.get("type") == "blob" and e.get("path", "").startswith("panel/"):
                remote[e["path"][len("panel/"):]] = e["sha"]

        local, _ = _tree(PANEL_DIR)
        local.pop(".commit", None)
        changes = []
        for rel in sorted(set(remote) | set(local)):
            if rel not in local:
                changes.append({"path": rel, "status": "added"})
            elif rel not in remote:
                changes.append({"path": rel, "status": "removed"})
            else:
                with open(local[rel], "rb") as f:
                    if _blob_sha(f.read()) != remote[rel]:
                        changes.append({"path": rel, "status": "modified"})

        try:
            txt = _http(f"https://raw.githubusercontent.com/{REPO}/{sha}/panel/server.py").decode("utf-8", "replace")
            m = re.search(r'^VERSION\s*=\s*"([^"]+)"', txt, re.M)
            remote_version = m.group(1) if m else None
        except UpdateError:
            remote_version = None

        image_changes = None  # desconhecido
        if installed and installed != sha:
            try:
                cmp = _get_json(f"https://api.github.com/repos/{REPO}/compare/{installed}...{sha}")
                image_changes = [f.get("filename", "") for f in cmp.get("files") or []
                                 if not f.get("filename", "").startswith("panel/")]
            except Exception:  # noqa — compare falhou: fica desconhecido
                image_changes = None
        elif installed:
            image_changes = []

        res.update(
            latest={"sha": sha, "short": sha[:7],
                    "message": commit["message"].split("\n")[0].strip(),
                    "date": commit["committer"]["date"], "url": info["html_url"],
                    "version": remote_version},
            changes=changes, imageChanges=image_changes, upToDate=not changes)
    except UpdateError as e:
        res["error"] = str(e)
    except Exception:  # noqa — resposta fora do formato esperado
        res["error"] = "Não foi possível consultar o GitHub: resposta inesperada"
    return res


def check(version, force=False):
    """Compara o painel instalado com o último commit de main. Usa cache (6 h; 10 min após erro)."""
    with _lock:
        c = _cache
        if not force and c["res"] is not None:
            ttl = ERROR_TTL if c["res"].get("error") else CHECK_TTL
            if time.time() - c["at"] < ttl:
                return c["res"]
        res = _build(version)
        _cache["at"], _cache["res"] = time.time(), res
        return res


def _extract(archive, dest):
    """Extrai o .tar.gz do GitHub. Recusa caminhos absolutos e '..'; links são ignorados."""
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            if m.name.startswith("/") or "\\" in m.name:
                raise UpdateError("O pacote do commit tem caminho inválido")
            parts = [p for p in m.name.split("/") if p not in ("", ".")]
            if ".." in parts:
                raise UpdateError("O pacote do commit tem caminho inválido")
            if not parts:
                continue
            target = os.path.join(dest, *parts)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tf.extractfile(m)
                with src, open(target, "wb") as f:
                    shutil.copyfileobj(src, f)


def _compile_check(panel, tmp, short):
    """Compila todos os .py novos (o .pyc vai para o tempdir, não para o pacote)."""
    for root, _, files in os.walk(panel):
        for f in files:
            if not f.endswith(".py"):
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, panel)
            cfile = os.path.join(tmp, "pyc", rel.replace(os.sep, "_") + "c")
            os.makedirs(os.path.dirname(cfile), exist_ok=True)
            try:
                py_compile.compile(src, cfile=cfile, doraise=True)
            except py_compile.PyCompileError as e:
                lines = str(e).strip().splitlines()
                detail = lines[-1] if lines else "erro de sintaxe"
                raise UpdateError(f"O commit {short} não compila: {rel}: {detail}")


def _backup(old_short):
    """Copia o painel atual para BACKUP_DIR/<data>-<commit antigo> e mantém só os mais novos."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"{stamp}-{old_short}")
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(BACKUP_DIR, f"{stamp}-{old_short}-{n}")
        n += 1
    shutil.copytree(PANEL_DIR, dest, ignore=shutil.ignore_patterns("__pycache__"))
    olds = sorted(d for d in os.listdir(BACKUP_DIR) if os.path.isdir(os.path.join(BACKUP_DIR, d)))
    for d in olds[:-BACKUP_KEEP]:
        shutil.rmtree(os.path.join(BACKUP_DIR, d), ignore_errors=True)
    return dest


def _swap(new_panel, sha):
    """Apaga o que não existe no painel novo, copia o novo por cima e grava o commit."""
    new_files, new_dirs = _tree(new_panel)

    def prune(d, rel):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            r = f"{rel}/{name}" if rel else name
            if r == ".commit":
                continue
            if os.path.isdir(p) and not os.path.islink(p):
                if r in new_dirs:
                    prune(p, r)
                else:
                    shutil.rmtree(p)
            elif r not in new_files:
                os.remove(p)

    prune(PANEL_DIR, "")
    for rel in sorted(new_dirs):
        os.makedirs(os.path.join(PANEL_DIR, *rel.split("/")), exist_ok=True)
    for rel, src in new_files.items():
        dst = os.path.join(PANEL_DIR, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    for root, ds, _ in os.walk(PANEL_DIR):
        for d in [d for d in ds if d == "__pycache__"]:
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            ds.remove(d)
    with open(COMMIT_FILE, "w") as f:
        f.write(sha)


def restart():
    """Troca o processo do servidor por uma nova execução (o container continua no ar)."""
    os.execv(sys.executable, [sys.executable, "-u", os.path.join(PANEL_DIR, "server.py")])


def _apply(sha, short):
    tmp = tempfile.mkdtemp(prefix="xtool-update-")
    try:
        arch = os.path.join(tmp, "src.tar.gz")
        data = _http(f"https://codeload.github.com/{REPO}/tar.gz/{sha}", timeout=120,
                     what=f"baixar o commit {short}")
        with open(arch, "wb") as f:
            f.write(data)
        del data
        ext = os.path.join(tmp, "src")
        os.makedirs(ext)
        _extract(arch, ext)
        roots = [d for d in sorted(os.listdir(ext)) if os.path.isdir(os.path.join(ext, d, "panel"))]
        if not roots:
            raise UpdateError(f"O commit {short} não tem a pasta panel/")
        new_panel = os.path.join(ext, roots[0], "panel")
        if not os.path.isfile(os.path.join(new_panel, "server.py")):
            raise UpdateError(f"O commit {short} não tem panel/server.py")
        _compile_check(new_panel, tmp, short)
        backup = _backup((installed_commit() or "")[:7] or "desconhecido")
        _swap(new_panel, sha)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with _lock:
        _cache.update(at=0.0, res=None)
    threading.Timer(1.5, restart).start()
    return {"ok": True, "sha": sha, "short": sha[:7], "restarting": True, "backup": backup}


def apply(sha):
    """Aplica o commit 'sha', que tem de ser o último commit do check bem-sucedido mais recente."""
    sha = str(sha or "")
    with _lock:
        last = _cache["res"]
    latest = (last or {}).get("latest")
    if not latest or latest.get("sha") != sha or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise UpdateError("Verifique de novo: o commit mudou")
    with _apply_lock:
        return _apply(sha, latest["short"])
