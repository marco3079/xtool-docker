"""Plataformas de cada projeto (iOS, Android, PC) e lista de builds gerados.

Funções puras: só leem arquivos e o store (JSON). Nada é executado aqui.
Usado pelo server.py (cards da aba Projetos) e pelo front.
"""
import os
import re
import shlex

import android
import dbenv
import pc
import store

WORK = os.environ.get("XTOOL_WORK", "/work")
CAP_FILES = ("capacitor.config.ts", "capacitor.config.js", "capacitor.config.json")

IOS_RE = re.compile(r"^(?P<n>.+)-(?P<v>\d+(?:\.\d+){0,3})-(?P<b>\d+)\.ipa$")
ANDROID_RE = re.compile(r"^(?P<n>.+)-(?P<v>\d+(?:\.\d+){0,3})-(?P<c>\d+)(?P<d>-debug)?\.(aab|apk)$")
PC_RE = re.compile(r"^(?P<n>.+)-(?P<v>\d+(?:\.\d+){0,3})-(?P<t>win32|linux|darwin)-x64\.zip$")

IOS_REASON = ("O iOS compila com xtool (SwiftPM) e este projeto não tem Package.swift nem xtool.yml. "
              "Projetos web/Capacitor não viram iOS aqui: o Capacitor iOS precisa de Xcode num Mac.")
ANDROID_REASON_INIT = ("Capacitor detectado, mas falta a pasta android/: clique em Configurar para adicionar "
                       "o Android (npx cap add android).")
ANDROID_REASON_NONE = ("Não há pasta android/ nem Capacitor neste projeto. Instale o Capacitor "
                       "(npm i @capacitor/core @capacitor/cli @capacitor/android e npx cap init) e volte aqui.")
PC_REASON_NO_PKG = ("Sem package.json: o app de PC precisa de um projeto web "
                    "(Vite, Webpack, Capacitor ou HTML com package.json).")
PC_REASON_UNKNOWN = ("Não consegui detectar como compilar este projeto para PC: escolha o tipo de código em Configurar.")


def _has(project_dir, *parts):
    return os.path.exists(os.path.join(project_dir, *parts))


def _meta_dict(meta, key):
    v = (meta or {}).get(key)
    return v if isinstance(v, dict) else {}


def _safe_detect(fn, project_dir):
    try:
        return fn(project_dir)
    except Exception:  # noqa — tolerante: erro de leitura conta como "não detectado"
        return None


def _read_yml(project_dir):
    """Mesma leitura do server.projects(): linhas 'chave: valor' sem indentação."""
    yml = {}
    try:
        with open(os.path.join(project_dir, "xtool.yml"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if ":" in line and not line.startswith(" "):
                    k, v = line.split(":", 1)
                    yml[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return yml


# ---- regras por plataforma (usadas por detect_platforms e configured_flags) ----
def _ios(project_dir):
    configured = _has(project_dir, "Package.swift")
    bundle = _read_yml(project_dir).get("bundleID", "") or ""
    detail = "Projeto xtool (SwiftPM)" + (f" · {bundle}" if bundle else "")
    return {"configured": configured, "detail": detail,
            "reason": "" if configured else IOS_REASON, "bundleId": bundle, "detected": configured}


def _android(project_dir):
    det = _safe_detect(android.detect, project_dir)
    configured = bool(det)
    capacitor = any(_has(project_dir, f) for f in CAP_FILES)
    package = (det or {}).get("packageName", "") if det else ""
    detail = ""
    if det:
        detail = f"Gradle em {det['gradleDir']}" + (" · Capacitor" if capacitor else "") + \
            (f" · {package}" if package else "")
    can_init = (not configured) and capacitor and _has(project_dir, "package.json")
    if configured:
        reason = ""
    elif can_init:
        reason = ANDROID_REASON_INIT
    else:
        reason = ANDROID_REASON_NONE
    return {"configured": configured, "detail": detail, "reason": reason, "capacitor": capacitor,
            "canInit": can_init, "packageName": package, "detected": configured or capacitor}


def _pc(project_dir, meta):
    det = _safe_detect(pc.detect, project_dir)
    types = [{"id": t, "label": pc.TYPE_LABELS[t]} for t in pc.PROJECT_TYPES]
    if det is None:
        return {"configured": False, "detail": "", "reason": PC_REASON_NO_PKG, "projectType": "",
                "suggestedType": "", "types": types, "detected": False}
    suggested = det["suggestedType"]
    saved = _meta_dict(meta, "pc").get("projectType", "")
    if saved not in pc.PROJECT_TYPES:  # valor salvo inválido: trata como não salvo
        saved = ""
    project_type = saved or suggested
    configured = bool(saved) or suggested != "auto"
    detail = f"Tipo: {pc.TYPE_LABELS[project_type]}" + ("" if saved else " · detectado")
    return {"configured": configured, "detail": detail,
            "reason": "" if configured else PC_REASON_UNKNOWN, "projectType": project_type,
            "suggestedType": suggested, "types": types, "detected": True}


DISABLED_DETAIL = "Desativado neste projeto"
PLATFORM_KEYS = ("ios", "android", "pc")


def _targets(meta):
    t = (meta or {}).get("targets")
    return t if isinstance(t, dict) else {}


def _platforms(project_dir, meta):
    """Estado completo das três plataformas. Ponto único de regra para detect_platforms,
    configured_flags e effective_platforms.

    enabled = meta["targets"][k] se a chave existe; senão, a detecção (detected).
    configured continua sendo a prontidão técnica, mesmo quando desativada.
    Desativada: detail = "Desativado neste projeto". reason segue a prontidão: fica preenchida
    sempre que configured é False (mesmo desativada) e vazia quando configured é True.
    """
    meta = meta or {}
    out = {"ios": _ios(project_dir), "android": _android(project_dir), "pc": _pc(project_dir, meta)}
    t = _targets(meta)
    for k in PLATFORM_KEYS:
        info = out[k]
        info["enabled"] = bool(t[k]) if k in t else bool(info["detected"])
        if not info["enabled"]:
            info["detail"] = DISABLED_DETAIL
    return out


def detect_platforms(project_dir, meta, project):
    """Estado de iOS, Android e PC do projeto. 'project' fica na assinatura do contrato."""
    p = _platforms(project_dir, meta or {})
    ios, andr, pcp = p["ios"], p["android"], p["pc"]
    return {
        "ios": {"configured": ios["configured"], "detail": ios["detail"], "reason": ios["reason"],
                "bundleId": ios["bundleId"], "enabled": ios["enabled"], "detected": ios["detected"]},
        "android": {"configured": andr["configured"], "detail": andr["detail"],
                    "reason": andr["reason"], "capacitor": andr["capacitor"],
                    "canInit": andr["canInit"], "packageName": andr["packageName"],
                    "enabled": andr["enabled"], "detected": andr["detected"]},
        "pc": {"configured": pcp["configured"], "detail": pcp["detail"], "reason": pcp["reason"],
               "projectType": pcp["projectType"], "suggestedType": pcp["suggestedType"],
               "types": pcp["types"], "enabled": pcp["enabled"], "detected": pcp["detected"]},
    }


def configured_flags(project_dir, meta):
    """configured AND enabled por plataforma: é o que o card usa para 🔨/📤."""
    p = _platforms(project_dir, meta or {})
    return {k: bool(p[k]["configured"] and p[k]["enabled"]) for k in PLATFORM_KEYS}


def effective_platforms(project_dir, meta):
    """Plataformas ativadas do projeto, na ordem ios, android, pc (configuradas ou não)."""
    p = _platforms(project_dir, meta or {})
    return [k for k in PLATFORM_KEYS if p[k]["enabled"]]


# ---- lista de builds ----
def _rel(project, project_dir, path):
    """Caminho relativo a WORK, ex.: 'Proj/xtool/android/x.aab'."""
    rel = os.path.relpath(path, project_dir)
    if rel.startswith(".."):
        return os.path.relpath(path, WORK).replace(os.sep, "/")
    return (project + "/" + rel).replace(os.sep, "/")


def _build(platform, kind, target, name, file_rel, abs_path, version, build, release, at, size):
    return {"id": f"{platform}:{file_rel}", "platform": platform, "kind": kind, "target": target,
            "name": name, "file": file_rel, "abs": abs_path, "version": version, "build": build,
            "release": release, "at": at, "size": size}


def _files(dirpath, exts):
    try:
        names = os.listdir(dirpath)
    except OSError:
        return []
    out = []
    for n in sorted(names):
        p = os.path.join(dirpath, n)
        if os.path.isfile(p) and n.lower().endswith(exts):
            out.append((n, p))
    return out


def _stat(p):
    try:
        st = os.stat(p)
        return st.st_mtime, st.st_size
    except OSError:
        return 0.0, 0


def list_builds(project, project_dir):
    """Todos os builds do projeto (iOS, Android, PC), mais novo primeiro."""
    out = []

    # iOS: xtool/*.ipa (só essa pasta)
    for n, p in _files(os.path.join(project_dir, "xtool"), (".ipa",)):
        at, size = _stat(p)
        m = IOS_RE.match(n)
        if m:
            out.append(_build("ios", "ipa", "", m.group("n"), _rel(project, project_dir, p), p,
                              m.group("v"), m.group("b"), True, at, size))
        else:
            out.append(_build("ios", "ipa", "", n[:-4], _rel(project, project_dir, p), p,
                              "", "", False, at, size))

    # Android: xtool/android/*.aab e *.apk
    for n, p in _files(os.path.join(project_dir, "xtool", "android"), (".aab", ".apk")):
        at, size = _stat(p)
        kind = "aab" if n.lower().endswith(".aab") else "apk"
        m = ANDROID_RE.match(n)
        if m:
            out.append(_build("android", kind, "", m.group("n"), _rel(project, project_dir, p), p,
                              m.group("v"), m.group("c"), not m.group("d"), at, size))
        else:
            out.append(_build("android", kind, "", n.rsplit(".", 1)[0], _rel(project, project_dir, p), p,
                              "", "", False, at, size))

    # PC: xtool/pc/*.zip
    for n, p in _files(os.path.join(project_dir, "xtool", "pc"), (".zip",)):
        at, size = _stat(p)
        m = PC_RE.match(n)
        if m:
            out.append(_build("pc", "zip", m.group("t"), m.group("n"), _rel(project, project_dir, p), p,
                              m.group("v"), "", True, at, size))
        else:
            out.append(_build("pc", "zip", "", n[:-4], _rel(project, project_dir, p), p,
                              "", "", False, at, size))

    # PC: última pasta montada pelo pc.py (meta pc.lastBuild)
    last = _meta_dict(store.project_meta(project), "pc").get("lastBuild")
    if isinstance(last, dict):
        out_root = last.get("outRoot") or ""
        folders = last.get("folders") if isinstance(last.get("folders"), dict) else {}
        for plat, folder in folders.items():
            if not folder or not out_root:
                continue
            p = os.path.join(out_root, folder)
            if not os.path.isdir(p):
                continue
            at, _ = _stat(p)
            out.append(_build("pc", "folder", plat, folder, _rel(project, project_dir, p), p,
                              str(last.get("versionName") or ""), "", True, at, 0))

    # Regra estrita de banco: cada build recebe o banco que usou (ou None), e se pode ser
    # entregue (deliverable). Sem bancos no projeto, tudo é entregável.
    for b in out:
        db = dbenv.build_db(project, b["file"])
        b["database"] = ({"id": db.get("id"), "name": db.get("name"), "role": db.get("role")}
                         if db else None)
        ok, reason = dbenv.deliverable(project, b["file"])
        b["deliverable"] = bool(ok)
        b["deliverReason"] = str(reason or "")

    out.sort(key=lambda b: b["at"], reverse=True)
    return out


def release_count(project, project_dir):
    """Builds release só das plataformas configuradas e entregáveis.

    Regra estrita: um build só conta se b["deliverable"] for True (ver dbenv.deliverable).
    Projeto sem bancos mantém o critério anterior do diálogo Enviar.
    """
    flags = configured_flags(project_dir, store.project_meta(project))
    return sum(1 for b in list_builds(project, project_dir)
               if b["release"] and b["deliverable"] and flags.get(b["platform"]))


# ---- script de adição do Android ao Capacitor ----
_CYAN = r"\033[1;36m"
_GREEN = r"\033[1;32m"
_RESET = r"\033[0m"
_NODE_CHECK = ("const p=require('./package.json');process.exit((p.dependencies&&p.dependencies['@capacitor/android'])"
               "||(p.devDependencies&&p.devDependencies['@capacitor/android'])?0:1)")


def init_script(project_dir):
    """Script bash que adiciona o Android ao Capacitor (npx cap add android)."""
    if android.detect(project_dir):
        raise ValueError("o projeto já tem a pasta android/")
    if not any(_has(project_dir, f) for f in CAP_FILES):
        raise ValueError("o projeto não tem capacitor.config")
    if not _has(project_dir, "package.json"):
        raise ValueError("o projeto não tem package.json")
    d = shlex.quote(os.path.abspath(project_dir))
    lines = [
        "set -e",
        f"cd {d}",
        f"printf '{_CYAN}▶ Instalando as dependências (se faltarem){_RESET}\\n'",
        "if [ ! -d node_modules ]; then if [ -f package-lock.json ]; then npm ci; else npm install; fi; fi",
        f"printf '{_CYAN}▶ Conferindo o pacote @capacitor/android{_RESET}\\n'",
        f'node -e "{_NODE_CHECK}" || npm install @capacitor/android',
        f"printf '{_CYAN}▶ Adicionando o Android ao Capacitor{_RESET}\\n'",
        "npx cap add android",
        f"printf '{_GREEN}✔ Android adicionado: a pasta android/ foi criada{_RESET}\\n'",
    ]
    return "\n".join(lines) + "\n"
