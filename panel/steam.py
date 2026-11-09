#!/usr/bin/env python3
"""Steam: compila o app de PC (se pedido), gera os arquivos VDF do SteamPipe e envia
o build com steamcmd. Roda como job do painel.

usage: steam.py <args.json>
args: project, accountId, appId, branch ("" = sem liberar; "default" não é aceito),
      platforms (lista de "win32"|"linux"|"darwin", padrão ["win32"]),
      build (padrão true: compila antes; false: usa o último build de PC),
      version, appName, projectType (tipo de código do projeto para o build de PC;
      "" = automático), preBuild, webDir, electronVersion, zip, description,
      upload (padrão true: envia para a Steam; false: só gera os arquivos),
      fromZips (opcional, {plataforma: caminho absoluto de .zip}): usa zips já prontos
      do build de PC (cada zip com uma pasta de topo, ex. feito com `zip -qry`) em vez
      de compilar; quando presente, não compila e ignora build/pc.lastBuild
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

WORK = os.environ.get("XTOOL_WORK", "/work")
PLATFORMS = ("win32", "linux", "darwin")
DESC_MAX = 200


def log(msg=""):
    print(msg, flush=True)


def step(title):
    log(f"\n\033[1;36m▶ {title}\033[0m")


def run(cmd, cwd=None, env=None, shell=False):
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    log(f"\033[2m$ {shown}\033[0m")
    # sem capturar: a saída vai direto para o terminal do job (progresso do steamcmd)
    rc = subprocess.run(cmd, cwd=cwd, env=env, shell=shell).returncode
    if rc != 0:
        raise SystemExit(f"comando falhou (código {rc})")


def vdf_quote(s):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def depot_vdf(depot_id, folder):
    return (
        '"DepotBuildConfig"\n'
        "{\n"
        f"\t\"DepotID\" {vdf_quote(depot_id)}\n"
        "\t\"FileMapping\"\n"
        "\t{\n"
        f"\t\t\"LocalPath\" {vdf_quote(f'{folder}/*')}\n"
        "\t\t\"DepotPath\" \".\"\n"
        "\t\t\"recursive\" \"1\"\n"
        "\t}\n"
        "}\n"
    )


def _with_slash(p):
    p = str(p)
    return p if p.endswith("/") else p + "/"


def app_vdf(app_id, desc, build_output, content_root, depot_files, branch=""):
    lines = [
        '"AppBuild"',
        "{",
        f"\t\"AppID\" {vdf_quote(app_id)}",
        f"\t\"Desc\" {vdf_quote(desc)}",
        "\t\"Preview\" \"0\"",
        f"\t\"ContentRoot\" {vdf_quote(_with_slash(content_root))}",
        f"\t\"BuildOutput\" {vdf_quote(_with_slash(build_output))}",
    ]
    if branch:
        lines.append(f"\t\"SetLive\" {vdf_quote(branch)}")
    lines.append("\t\"Depots\"")
    lines.append("\t{")
    for depot_id, path in depot_files.items():
        lines.append(f"\t\t{vdf_quote(depot_id)} {vdf_quote(path)}")
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def merge_meta(project, patch):
    cur = dict(store.project_meta(project).get("steam", {}))
    cur.update(patch)
    store.project_meta_update(project, {"steam": cur})


def _extract(zp, dest):
    """Descompacta preservando permissões (unzip); sem unzip, usa o zipfile."""
    if shutil.which("unzip"):
        r = subprocess.run(["unzip", "-oq", zp, "-d", dest])
        if r.returncode != 0:
            raise SystemExit(f"não consegui descompactar {zp} (código {r.returncode})")
    else:
        with zipfile.ZipFile(zp) as z:
            z.extractall(dest)


def unpack_zips(project, platforms, zips, a):
    """Descompacta os zips de cada plataforma em <WORK>/<projeto>/xtool/steam/content/.
    Devolve o mesmo formato de pc.build: version, appName, outRoot, folders."""
    version = str(a.get("version") or "").strip()
    if not version:
        raise SystemExit("informe a versão do build (obrigatória ao usar zips prontos)")
    content = os.path.join(WORK, project, "xtool", "steam", "content")
    shutil.rmtree(content, ignore_errors=True)
    os.makedirs(content, exist_ok=True)
    folders = {}
    pc_dir = os.path.realpath(os.path.join(WORK, project, "xtool", "pc"))
    for plat in platforms:
        zp = str(zips.get(plat) or "")
        if zp and not os.path.realpath(zp).startswith(pc_dir + os.sep):
            raise SystemExit("o .zip precisa estar na pasta xtool/pc do projeto")
        if not zp or not os.path.isfile(zp) or not zp.lower().endswith(".zip"):
            raise SystemExit(f"zip do build de {plat} não encontrado: {zp or '(vazio)'}")
        with zipfile.ZipFile(zp) as z:
            tops, root_files = set(), False
            for name in z.namelist():
                parts = [p for p in name.split("/") if p]
                if ".." in parts or name.startswith("/"):
                    raise SystemExit(f"zip de {plat} com caminho inválido: {name}")
                if not parts:
                    continue
                if len(parts) > 1:
                    tops.add(parts[0])
                elif not name.endswith("/"):
                    root_files = True
        if root_files or len(tops) != 1:
            raise SystemExit(f"o zip de {plat} precisa ter uma única pasta de topo (ex.: <app>/...)")
        _extract(zp, content)
        folders[plat] = tops.pop()
        log(f"{plat}: zip {zp} -> {folders[plat]}/")
    meta_pc = store.project_meta(project).get("pc", {})
    return {
        "version": version,
        "appName": a.get("appName") or meta_pc.get("appName") or project,
        "outRoot": content,
        "folders": folders,
    }


def release(a):
    # 1/5 conta, app e branch
    step("1/5 Conferindo a conta e o app")
    project = a["project"]
    pdir = os.path.join(WORK, project)

    platforms = []
    for p in (a.get("platforms") or ["win32"]):
        if p not in PLATFORMS:
            raise SystemExit(f"plataforma inválida: {p}")
        if p not in platforms:
            platforms.append(p)

    appId = str(a.get("appId", "")).strip()
    if not re.fullmatch(r"\d+", appId):
        raise SystemExit("App ID da Steam inválido")

    accountId = str(a.get("accountId", "") or "").strip()
    try:
        acc = store.steam_account(accountId)
        app = store.steam_app(accountId, appId)
    except ValueError as e:
        raise SystemExit(str(e))

    branch = (a.get("branch") or "").strip()
    if branch == "default":
        raise SystemExit("a branch default não pode ser liberada pelo steamcmd; "
                         "escolha outra (ex.: beta) ou deixe em branco e libere no site do Steamworks")
    if branch and not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", branch):
        raise SystemExit("nome de branch inválido")

    depots = {}
    for plat in platforms:
        depot = app["depots"].get(plat)
        if not depot:
            raise SystemExit(f"o app {appId} não tem Depot ID para {plat}: cadastre em Apps da conta → Steam")
        depots[plat] = str(depot)

    upload = bool(a.get("upload", True))
    if upload and not shutil.which("steamcmd"):
        raise SystemExit("o steamcmd não está instalado (reconstrua a imagem: docker compose up -d --build)")

    log(f"Conta: {acc.get('label', '')} (usuário {acc.get('username', '')})")
    log(f"App: {app.get('name', '')} (appId {appId})")
    log("Plataformas -> depots: " + ", ".join(f"{p} -> {depots[p]}" for p in platforms))
    log(f"Branch: {branch or '(sem liberar)'}")

    # 2/5 compilar, reaproveitar o último build de PC ou usar os zips enviados
    from_zips = a.get("fromZips") or {}
    if from_zips:
        step("2/5 Usando os zips do build de PC")
        for plat in platforms:
            if not from_zips.get(plat):
                raise SystemExit(f"falta o zip do build de {plat} (fromZips)")
        res = unpack_zips(project, platforms, from_zips, a)
    elif a.get("build", True):
        step("2/5 Compilando para PC")
        import pc  # noqa: E402
        res = pc.build({
            "project": project,
            "platforms": platforms,
            "version": a.get("version", ""),
            "appName": a.get("appName", ""),
            "projectType": a.get("projectType", ""),
            "preBuild": a.get("preBuild", ""),
            "webDir": a.get("webDir", ""),
            "electronVersion": a.get("electronVersion", ""),
            "zip": bool(a.get("zip")),
        })
    else:
        pc_meta = store.project_meta(project).get("pc", {})
        lb = pc_meta.get("lastBuild")
        msg = "não há build de PC anterior: marque 'Compilar antes de enviar'"
        if not lb:
            raise SystemExit(msg)
        folders = lb.get("folders") or {}
        for plat in platforms:
            if not folders.get(plat):
                raise SystemExit(msg)
        res = {
            "version": lb.get("versionName", ""),
            "appName": pc_meta.get("appName") or project,
            "outRoot": lb.get("outRoot", ""),
            "folders": folders,
        }
        log(f"Usando o último build de PC (versão {res['version']}).")

    for plat in platforms:
        folder = (res.get("folders") or {}).get(plat)
        path = os.path.join(res.get("outRoot", ""), folder or "")
        if not folder or not os.path.isdir(path):
            raise SystemExit(f"pasta do build de {plat} não encontrada: {path}. "
                             "Compile de novo (marque 'Compilar antes de enviar')")
        log(f"{plat}: {path}")

    # 3/5 arquivos VDF
    step("3/5 Gerando os arquivos da Steam")
    sdir = os.path.join(pdir, "xtool", "steam")
    out_dir = os.path.join(sdir, "output")
    os.makedirs(out_dir, exist_ok=True)

    desc = str(a.get("description") or f"{res['appName']} v{res['version']}")
    desc = re.sub(r"[\r\n]+", " ", desc).strip()
    if len(desc) > DESC_MAX:
        log(f"\033[33m⚠ a descrição tem {len(desc)} caracteres; a Steam aceita {DESC_MAX} e o texto será cortado\033[0m")
        desc = desc[:DESC_MAX]

    depot_files = {}
    for plat in platforms:
        depot = depots[plat]
        folder = res["folders"][plat]
        dpath = os.path.abspath(os.path.join(sdir, f"depot_build_{depot}.vdf"))
        with open(dpath, "w", encoding="utf-8") as f:
            f.write(depot_vdf(depot, folder))
        depot_files[depot] = dpath
        log(f"Depot {depot} ({plat}): {dpath}")

    app_path = os.path.abspath(os.path.join(sdir, f"app_build_{appId}.vdf"))
    with open(app_path, "w", encoding="utf-8") as f:
        f.write(app_vdf(appId, desc, out_dir, res["outRoot"], depot_files, branch))
    log(f"App: {app_path}")

    if not upload:
        log(f"Parado aqui (envio para a Steam desligado). Arquivos em {sdir}")
        return

    # 4/5 envio
    step("4/5 Enviando para a Steam")
    log("Na primeira vez o steamcmd pede a senha e o código do Steam Guard: digite aqui no console. "
        "O login fica salvo e não pergunta de novo.")
    cmd = ["steamcmd", "+@ShutdownOnFailedCommand", "1", "+login", acc["username"],
           "+run_app_build", app_path, "+quit"]
    run(cmd)

    # 5/5 registro
    step("5/5 Registrando")
    head = ""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=pdir,
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    merge_meta(project, {"accountId": accountId, "appId": appId, "branch": branch,
                         "lastRelease": {"versionName": res["version"], "branch": branch,
                                         "commit": head, "at": time.time()}})
    log(f"\n\033[1;32m✔ Build enviado para a Steam (app {appId}, versão {res['version']}, "
        f"branch {branch or '(sem liberar)'}).\033[0m")
    log(f"Confira em https://partner.steamgames.com/apps/builds/{appId}")
    if not branch:
        log("\033[33m⚠ Falta liberar o build numa branch no site do Steamworks (Builds do app).\033[0m")


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        a = json.load(f)
    release(a)


if __name__ == "__main__":
    try:
        main()
    except (SystemExit, Exception) as e:  # noqa
        if isinstance(e, SystemExit) and e.code in (0, None):
            raise
        log(f"\n\033[1;31m✖ {e}\033[0m")
        sys.exit(1)
