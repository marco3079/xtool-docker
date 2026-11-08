"""GitHub accounts and repositories through the gh CLI (supports several accounts)."""
import json
import os
import re
import subprocess

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _run(args, token=None, cwd=None, timeout=60):
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env,
                       stdin=subprocess.DEVNULL)
    return p.returncode, ANSI.sub("", (p.stdout or "") + (p.stderr or ""))


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
            "behind": int(a[1]) if len(a) == 2 and a[1].isdigit() else 0}


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
