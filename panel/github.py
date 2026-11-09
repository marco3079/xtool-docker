"""GitHub accounts and repositories through the gh CLI (supports several accounts)."""
import json
import os
import re
import signal
import subprocess
import tempfile
import time

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


_PROG_RE = re.compile(
    r"(Enumerating objects|Counting objects|Compressing objects|Receiving objects|Resolving deltas)"
    r"[: ]+(?:(\d+)%\s*)?\((\d+)/(\d+)\)(?:,\s*([\d.]+\s*\w+)\s*(?:\|\s*([\d.]+\s*\w+/s))?)?", re.I)
_PROG_DONE_RE = re.compile(r"(Enumerating objects|Counting objects)[: ]+(\d+),\s*done", re.I)
_PHASES = (("enumerat", "Preparando"), ("counting", "Preparando"), ("compress", "Compactando no servidor"),
           ("receiving", "Baixando"), ("resolving", "Montando"))


def _phase(name):
    for key, label in _PHASES:
        if key in name.lower():
            return label
    return name


def parse_progress(text):
    """Última linha de progresso do git fetch --progress (as atualizações vêm separadas por \\r)."""
    for line in reversed(re.split(r"[\r\n]", text or "")):
        m = _PROG_RE.search(line)
        if m:
            return {"phase": _phase(m.group(1)), "percent": int(m.group(2)) if m.group(2) is not None else None,
                    "received": m.group(5) or "", "speed": m.group(6) or "",
                    "objects": f"{m.group(3)}/{m.group(4)}"}
        m = _PROG_DONE_RE.search(line)
        if m:
            return {"phase": _phase(m.group(1)), "percent": None, "received": "", "speed": "",
                    "objects": m.group(2)}
    return None


def _tail(f, n=8192):
    """Final do arquivo sem mexer no deslocamento usado pelo processo filho."""
    size = os.fstat(f.fileno()).st_size
    return os.pread(f.fileno(), min(n, size), max(0, size - n)).decode("utf-8", "replace")


def _run(args, token=None, cwd=None, timeout=60, on_progress=None):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # nunca pergunta usuário/senha no meio do painel
    if token:
        env["GH_TOKEN"] = token
    # Saída em arquivo, e não em pipe: um filho em segundo plano (ex.: gc do git) que herda
    # o pipe faria o communicate() esperar para sempre. Só o processo direto é aguardado.
    with tempfile.TemporaryFile() as out:
        # sessão própria: no timeout mata-se o GRUPO (git + index-pack + filhos), não só o pai
        p = subprocess.Popen(args, stdout=out, stderr=subprocess.STDOUT, cwd=cwd, env=env,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        waited, last = 0.0, None
        while True:
            try:
                rc = p.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                waited += 1
                if on_progress:  # só avisa quando o progresso muda
                    prog = parse_progress(_tail(out))
                    if prog is not None and prog != last:
                        last = prog
                        try:
                            on_progress(prog)
                        except Exception:  # noqa — quem mostra o progresso não derruba o download
                            pass
                if waited >= timeout:
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    p.kill()
                    p.wait()
                    raise subprocess.TimeoutExpired(args, timeout)
        if on_progress:  # leitura final: o processo pode ter terminado entre duas leituras
            prog = parse_progress(_tail(out))
            if prog is not None and prog != last:
                try:
                    on_progress(prog)
                except Exception:  # noqa
                    pass
        out.seek(0)
        text = out.read().decode("utf-8", "replace")
    return rc, ANSI.sub("", text)


def accounts():
    code, out = _run(["gh", "auth", "status", "--hostname", "github.com"])
    res, cur = [], None
    for line in out.splitlines():
        m = re.search(r"Logged in to github\.com account (\S+)", line)
        if m:
            cur = {"user": m.group(1), "active": False}
            res.append(cur)
        elif cur and "Active account: true" in line:
            cur["active"] = True
        elif cur and re.search(r"Token scopes:\s*(.*)", line):
            cur["scopes"] = re.search(r"Token scopes:\s*(.*)", line).group(1).replace("'", "")
    for a in res:
        _, info = _run(["gh", "api", "user", "--jq", "{name,login,avatar_url,email}"], token=token(a["user"]))
        try:
            a.update(json.loads(info))
        except ValueError:
            pass
    return res


def token(user):
    code, out = _run(["gh", "auth", "token", "--hostname", "github.com", "--user", user])
    if code != 0:
        raise ValueError(f"conta GitHub {user} não está logada")
    return out.strip().splitlines()[-1]


def repos(user, query=""):
    code, out = _run(["gh", "repo", "list", "--limit", "300", "--json",
                      "nameWithOwner,isPrivate,updatedAt,description,url,defaultBranchRef"],
                     token=token(user), timeout=90)
    if code != 0:
        raise ValueError(out.strip()[:500])
    data = json.loads(out or "[]")
    # also repos from organizations the user belongs to
    c2, orgs = _run(["gh", "api", "user/orgs", "--jq", ".[].login"], token=token(user))
    for org in (orgs.split() if c2 == 0 else []):
        c3, o = _run(["gh", "repo", "list", org, "--limit", "200", "--json",
                      "nameWithOwner,isPrivate,updatedAt,description,url,defaultBranchRef"], token=token(user), timeout=90)
        if c3 == 0:
            data += json.loads(o or "[]")
    q = query.lower()
    return sorted([r for r in data if q in r["nameWithOwner"].lower()], key=lambda r: r["updatedAt"], reverse=True)


def identity(user):
    _, out = _run(["gh", "api", "user", "--jq", "{login,name,id}"], token=token(user))
    u = json.loads(out)
    return u.get("name") or u["login"], f"{u['id']}+{u['login']}@users.noreply.github.com"


def git_status(path):
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    _, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    _, remote = _run(["git", "remote", "get-url", "origin"], cwd=path)
    _, changes = _run(["git", "status", "--porcelain"], cwd=path)
    _, ahead = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=path)
    a = ahead.split()
    return {"branch": branch.strip(), "remote": remote.strip() if "fatal" not in remote else "",
            "changes": len([l for l in changes.splitlines() if l.strip()]),
            "ahead": int(a[0]) if len(a) == 2 and a[0].isdigit() else 0,
            "behind": int(a[1]) if len(a) == 2 and a[1].isdigit() else 0,
            "commit": _commit_info(path)}


def _commit_info(path):
    """Último commit: hash curto (7), completo, número sequencial, assunto e data (None sem commits)."""
    code, full = _run(["git", "rev-parse", "HEAD"], cwd=path)
    full = full.strip()
    if code != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", full):
        return None
    _, cnt = _run(["git", "rev-list", "--count", "HEAD"], cwd=path)
    _, subj = _run(["git", "log", "-1", "--pretty=%s"], cwd=path)
    _, at = _run(["git", "log", "-1", "--pretty=%ct"], cwd=path)
    return {"hash": full[:7], "full": full,
            "count": int(cnt.strip()) if cnt.strip().isdigit() else 0,
            "subject": subj.strip(),
            "at": int(at.strip()) if at.strip().isdigit() else 0}


def _short(out):
    lines = [l.strip() for l in (out or "").splitlines() if l.strip()]
    return (lines[-1] if lines else "erro desconhecido")[:200]


def _drop_partial_packs(path, since):
    """Apaga os tmp_pack_* deixados pela tentativa que estourou o tempo (criados desde 'since')."""
    d = os.path.join(path, ".git", "objects", "pack")
    try:
        names = os.listdir(d)
    except OSError:
        return
    for n in names:
        fp = os.path.join(d, n)
        if n.startswith("tmp_pack_"):
            try:
                if os.path.getmtime(fp) >= since:
                    os.remove(fp)
            except OSError:
                pass


def auto_pull(path, token=None, on_progress=None):
    """Atualiza o projeto só por fast-forward e com árvore limpa. Nunca pull/rebase/reset/stash."""
    def res(state, message, pulled=0):
        return {"state": state, "pulled": pulled, "message": message}

    if not os.path.isdir(os.path.join(path, ".git")):
        return res("noremote", "não é um repositório git")
    code, _ = _run(["git", "remote", "get-url", "origin"], cwd=path)
    if code != 0:
        return res("noremote", "o repositório não tem remote origin")
    started = time.time()
    try:
        code, out = _run(["git", "-c", "gc.auto=0", "fetch", "--progress", "origin"],
                         token=token, cwd=path, timeout=900, on_progress=on_progress)
    except subprocess.TimeoutExpired:
        _drop_partial_packs(path, started)
        return res("error", "o download passou de 15 minutos; tente de novo")
    if code != 0:
        return res("error", "falha ao buscar do GitHub: " + _short(out))
    code, _ = _run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=path)
    if code != 0:
        return res("noremote", "a branch não tem upstream")
    code, counts = _run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"], cwd=path)
    parts = counts.split()
    if code != 0 or len(parts) != 2 or not all(p.isdigit() for p in parts):
        return res("error", "não consegui comparar com o remoto")
    ahead, behind = int(parts[0]), int(parts[1])
    if behind == 0:
        return res("uptodate", "já está atualizado")
    if ahead > 0:
        return res("diverged", "há commits locais e remotos: faça o pull à mão")
    _, st = _run(["git", "status", "--porcelain"], cwd=path)
    if st.strip():
        return res("dirty", "há alterações locais: o pull automático esperou")
    code, out = _run(["git", "merge", "--ff-only", "@{u}"], cwd=path)
    if code != 0:
        return res("error", "não consegui atualizar (fast-forward): " + _short(out))
    return res("pulled", f"{behind} commit(s) baixado(s) do GitHub", behind)


def changes_since(path, since_commit=None, limit=80):
    """Commit messages (and a file summary) since the last release, for the AI."""
    if not os.path.isdir(os.path.join(path, ".git")):
        return ""
    rng = []
    if since_commit:
        rng = [f"{since_commit}..HEAD"]
    else:
        code, tag = _run(["git", "describe", "--tags", "--abbrev=0"], cwd=path)
        if code == 0 and tag.strip():
            rng = [f"{tag.strip()}..HEAD"]
    _, log = _run(["git", "log", "--no-merges", f"-{limit}", "--pretty=format:- %s%n%b", *rng], cwd=path)
    empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # diff against nothing = whole history
    code, stat = _run(["git", "diff", "--stat", rng[0].split("..")[0] if rng else empty_tree, "HEAD"], cwd=path)
    if code != 0:
        stat = ""
    log = "\n".join(l for l in log.splitlines() if l.strip())
    return (log.strip() + ("\n\nArquivos alterados:\n" + stat.strip()[-3000:] if stat.strip() else "")).strip()
