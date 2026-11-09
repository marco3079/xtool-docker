#!/usr/bin/env python3
"""PC: empacota um projeto web/Capacitor como app de PC (Electron) para Windows, Linux e macOS,
e gera o zip de cada plataforma. Roda como job do painel.

usage: pc.py <args.json>
args: project, version ("" = resolver), appName ("" = resolver), platforms (lista, padrão ["win32"]),
      preBuild ("" = padrão detectado, "-" = pular), webDir ("" = detectado),
      electronVersion ("" = padrão), zip (bool), dryRun (bool: faz tudo menos o empacotador e o zip),
      icon (caminho relativo ao projeto de um .png/.ico; "" = procurar sozinho),
      company (texto para o CompanyName do .exe; "" = usar o appName),
      projectType (um de PROJECT_TYPES; "" = o tipo salvo em meta["pc"]["projectType"] ou "auto").
      O tipo define o pré-build, a pasta do site e as verificações (ver profile()). Só "auto" usa o
      comportamento antigo; "puro" copia a pasta do site sem build e "custom" usa só o que foi informado.

O app abre o site pelo protocolo app:// (não por arquivo), então /assets/... funciona sem mudar o projeto.
Ícone e metadados do .exe (win32) precisam do Wine na imagem; o ícone .ico é gerado com ImageMagick
(convert ou magick) a partir do PNG.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402
import versions  # noqa: E402

WORK = os.environ.get("XTOOL_WORK", "/work")
PLATFORMS = ("win32", "linux", "darwin")
ARCH = "x64"
DEFAULT_ELECTRON = "33.4.11"
PRE_SCRIPTS = ["build:client:prod", "build:prod", "build:client", "build"]
CAP_FILES = ("capacitor.config.ts", "capacitor.config.js", "capacitor.config.json")
VERSION_RE = re.compile(r"\d+(\.\d+){0,3}")
ELECTRON_RE = re.compile(r"\d+\.\d+\.\d+")
NEXT_EXPORT_RE = re.compile(r"output\s*:\s*['\"]export['\"]")
FRAMEWORK_DEPS = (("next", "next"), ("nuxt", "nuxt"), ("nuxt3", "nuxt"), ("@sveltejs/kit", "sveltekit"), ("astro", "astro"))
PROJECT_TYPES = ("auto", "ts", "js", "puro", "capacitor", "framework", "custom")
TYPE_LABELS = {
    "auto": "Automático (detecta pelo projeto)",
    "ts": "TypeScript (tsc / Vite / Webpack)",
    "js": "JavaScript com build (Vite / Webpack / Parcel)",
    "puro": "JavaScript / HTML puro (sem build)",
    "capacitor": "Capacitor (web + cap sync)",
    "framework": "Next.js / Nuxt / SvelteKit (exporta estático)",
    "custom": "Personalizado (eu digito o comando e a pasta)",
}

ICON_PROJECT_PATHS = ("resources/icon.png", "resources/icon.ico", "public/icon.png",
                      "public/icons/icon-512x512.png", "public/icons/icon-512.png", "assets/icon.png", "icon.png")
ICON_WEB_PATHS = ("icon.png", "icons/icon-512x512.png", "icons/icon-512.png", "favicon.png", "apple-touch-icon.png")

MAIN_JS = """const { app, BrowserWindow, Menu, protocol, net } = require('electron');
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');
const WWW = path.join(__dirname, 'www');
protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } }]);
function createWindow() {
  const iconFile = path.join(__dirname, 'icon.png');
  const win = new BrowserWindow({ width: 1280, height: 800, autoHideMenuBar: true, backgroundColor: '#000000',
    ...(fs.existsSync(iconFile) ? { icon: iconFile } : {}),
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true } });
  Menu.setApplicationMenu(null);
  win.loadURL('app://game/index.html');
}
app.whenReady().then(() => {
  protocol.handle('app', async (req) => {
    let rel;
    try {
      rel = decodeURIComponent(new URL(req.url).pathname);
    } catch (e) {
      return new Response('bad request', { status: 400 });
    }
    if (rel === '/' || rel === '') rel = '/index.html';
    let file = path.normalize(path.join(WWW, rel));
    if (file !== WWW && !file.startsWith(WWW + path.sep)) return new Response('forbidden', { status: 403 });
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      if (path.extname(rel)) return new Response('not found', { status: 404 });
      file = path.join(WWW, 'index.html'); // rotas do app (SPA)
    }
    try {
      return await net.fetch(pathToFileURL(file).toString(), { headers: req.headers, bypassCustomProtocolHandlers: true });
    } catch (e) {
      return new Response('error', { status: 500 });
    }
  });
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
"""


def log(msg=""):
    print(msg, flush=True)


def step(title):
    log(f"\n\033[1;36m▶ {title}\033[0m")


def run(cmd, cwd=None, env=None, shell=False):
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    log(f"\033[2m$ {shown}\033[0m")
    # sem capturar: a saída vai direto para o terminal do job (progresso do npm/electron)
    rc = subprocess.run(cmd, cwd=cwd, env=env, shell=shell).returncode
    if rc != 0:
        raise SystemExit(f"comando falhou (código {rc})")


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def detect(project_dir):
    def has(*parts):
        return os.path.exists(os.path.join(project_dir, *parts))

    if not has("package.json"):
        return None
    try:
        pj = json.loads(read_text(os.path.join(project_dir, "package.json")))
    except (ValueError, OSError):
        pj = {}
    if not isinstance(pj, dict):
        pj = {}

    name = str(pj.get("name") or os.path.basename(os.path.normpath(project_dir)))
    version = str(pj.get("version") or "")
    scripts = pj.get("scripts") if isinstance(pj.get("scripts"), dict) else {}
    deps = pj.get("dependencies") if isinstance(pj.get("dependencies"), dict) else {}
    dev = pj.get("devDependencies") if isinstance(pj.get("devDependencies"), dict) else {}

    capfile = next((f for f in CAP_FILES if has(f)), None)
    cap_app = cap_web = ""
    if capfile:
        txt = read_text(os.path.join(project_dir, capfile))
        if capfile.endswith(".json"):
            try:
                cfg = json.loads(txt)
            except ValueError:
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}
            cap_app = str(cfg.get("appName") or "")
            cap_web = str(cfg.get("webDir") or "")
        else:
            m = re.search(r"appName\s*:\s*[\"']([^\"']+)[\"']", txt)
            if m:
                cap_app = m.group(1)
            m = re.search(r"webDir\s*:\s*[\"']([^\"']+)[\"']", txt)
            if m:
                cap_web = m.group(1)

    app_name = cap_app or str(pj.get("productName") or "") or name
    web_dir = cap_web or next((d for d in ("dist", "build", "www", "out") if has(d, "index.html")), "dist")

    install = "npm ci" if has("package-lock.json") else "npm install"
    s = next((x for x in PRE_SCRIPTS if x in scripts), None)
    default_pre = install + (f" && npm run {s}" if s else "")

    all_deps = {**deps, **dev}
    framework = next((fw for dep, fw in FRAMEWORK_DEPS if dep in all_deps), "")
    typescript = has("tsconfig.json") or "typescript" in all_deps
    build_script = s or ""
    if capfile:
        suggested = "capacitor"
    elif framework:
        suggested = "framework"
    elif typescript:
        suggested = "ts"
    elif build_script:
        suggested = "js"
    elif any(has(d, "index.html") for d in (".", "public", "www")):
        suggested = "puro"
    else:
        suggested = "auto"

    return {"packageJson": True, "name": name, "appName": app_name, "version": version,
            "capacitor": bool(capfile), "webDir": web_dir, "webDirExists": has(web_dir, "index.html"),
            "hasElectron": "electron" in deps or "electron" in dev, "defaultPreBuild": default_pre,
            "suggestedType": suggested, "framework": framework, "typescript": typescript,
            "buildScript": build_script}


def _read_pkg(pdir):
    try:
        pj = json.loads(read_text(os.path.join(pdir, "package.json")))
    except (ValueError, OSError):
        return {}
    return pj if isinstance(pj, dict) else {}


def _next_export(pdir):
    for n in ("next.config.js", "next.config.mjs", "next.config.cjs", "next.config.ts"):
        p = os.path.join(pdir, n)
        if os.path.isfile(p) and NEXT_EXPORT_RE.search(read_text(p)):
            return True
    return False


def profile(pdir, info, ptype):
    """Função pura (só lê arquivos): devolve o pré-build, a pasta do site e os avisos/erros do tipo de projeto."""
    def has(*parts):
        return os.path.exists(os.path.join(pdir, *parts))

    pj = _read_pkg(pdir)
    scripts = pj.get("scripts") if isinstance(pj.get("scripts"), dict) else {}
    deps = {}
    for k in ("dependencies", "devDependencies"):
        if isinstance(pj.get(k), dict):
            deps.update(pj[k])
    install = "npm ci" if has("package-lock.json") else "npm install"
    bs = info.get("buildScript") or ""
    run_bs = f" && npm run {bs}" if bs else ""
    out = {"type": ptype, "preBuild": "", "webDir": info["webDir"], "warnings": [], "errors": []}
    warnings, errors = out["warnings"], out["errors"]

    if ptype == "auto":
        out["preBuild"] = info["defaultPreBuild"]
    elif ptype == "ts":
        if bs:
            out["preBuild"] = install + run_bs
        elif has("tsconfig.json"):
            out["preBuild"] = install + " && npx tsc -p ."
        else:
            out["preBuild"] = install
            errors.append("não há script de build nem tsconfig.json: o TypeScript não seria compilado")
        if not has("tsconfig.json"):
            warnings.append("não achei tsconfig.json: o projeto é TypeScript?")
        if "typescript" not in deps:
            warnings.append("typescript não está nas dependências")
    elif ptype == "js":
        out["preBuild"] = install + run_bs
        if not has("package.json") or not bs:
            errors.append("o package.json não tem script de build (build, build:prod...): "
                          "use o tipo JavaScript / HTML puro")
    elif ptype == "puro":
        out["preBuild"] = "-"
        found = next((d for d in (".", "public", "www", "src", "dist") if has(d, "index.html")), None)
        if found is None:
            out["webDir"] = "."
            errors.append("não achei index.html na raiz nem em public, www, src ou dist")
        else:
            out["webDir"] = found
        if out["webDir"] == ".":
            warnings.append("o site é a raiz do projeto: node_modules, .git, xtool, android e ios ficam de fora da cópia")
    elif ptype == "capacitor":
        if not info.get("capacitor"):
            errors.append("não achei capacitor.config no projeto")
        out["preBuild"] = install + run_bs
        if not bs:
            warnings.append("sem script de build: usando a pasta do site como está")
    elif ptype == "framework":
        fw = info.get("framework") or ""
        if fw == "next":
            out["preBuild"] = install + " && npm run build"
            out["webDir"] = "out"
            if not _next_export(pdir):
                errors.append("Next.js precisa de output: 'export' no next.config para gerar o site estático")
        elif fw == "nuxt":
            out["preBuild"] = install + (" && npm run generate" if "generate" in scripts else " && npx nuxi generate")
            out["webDir"] = ".output/public"
        elif fw == "sveltekit":
            out["preBuild"] = install + " && npm run build"
            out["webDir"] = "build"
            warnings.append("SvelteKit precisa do @sveltejs/adapter-static")
        elif fw == "astro":
            out["preBuild"] = install + " && npm run build"
            out["webDir"] = "dist"
        else:
            out["preBuild"] = install
            errors.append("não detectei Next.js, Nuxt, SvelteKit nem Astro nas dependências")
    elif ptype == "custom":
        out["preBuild"] = "-"
    else:
        errors.append(f"tipo desconhecido: {ptype}")
    return out


def safe_name(app_name):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", app_name).strip("-") or "app"


def merge_meta(project, patch):
    cur = dict(store.project_meta(project).get("pc", {}))
    cur.update(patch)
    store.project_meta_update(project, {"pc": cur})


def dir_size(path):
    total = 0
    for f in glob.glob(os.path.join(path, "**", "*"), recursive=True):
        if os.path.isfile(f):
            try:
                total += os.path.getsize(f)
            except OSError:
                pass
    return total


def find_icon(pdir, info, webdir, wanted):
    """Devolve o caminho de um .png/.ico do projeto, ou None. 'wanted' (relativo ao projeto) tem prioridade."""
    if wanted:
        p = os.path.join(pdir, wanted)
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in (".png", ".ico"):
            return p
        log(f"\033[33m⚠ ícone '{wanted}' não encontrado (ou não é .png/.ico): procurando um automaticamente\033[0m")
    webdir = webdir or info.get("webDir") or "dist"
    candidates = [os.path.join(pdir, c) for c in ICON_PROJECT_PATHS]
    candidates += [os.path.join(pdir, webdir, c) for c in ICON_WEB_PATHS]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def imagemagick():
    if shutil.which("convert"):
        return "convert"
    if shutil.which("magick"):
        return "magick"
    return None


def make_ico(png, ico):
    tool = imagemagick()
    cmd = [tool, png, "-define", "icon:auto-resize=256,128,64,48,32,16", ico]
    log(f"\033[2m$ {' '.join(cmd)}\033[0m")
    try:
        return subprocess.run(cmd).returncode == 0
    except OSError:
        return False


def one_line(s):
    return re.sub(r"[\r\n\t]+", " ", str(s)).strip()


def build(a):
    project = (a.get("project") or "").strip()
    if not project:
        raise SystemExit("projeto não informado")

    step("1/4 Conferindo o projeto")
    pdir = os.path.join(WORK, project)
    info = detect(pdir)
    if not info:
        raise SystemExit("o projeto não tem package.json")

    platforms = []
    for p in (a.get("platforms") or ["win32"]):
        if p not in PLATFORMS:
            raise SystemExit(f"plataforma desconhecida: {p}")
        if p not in platforms:
            platforms.append(p)

    pm = store.project_meta(project)
    meta = pm.get("pc") or {}

    v = (a.get("version") or "").strip()
    if not v:
        src = pm.get("versionSource") or "auto"
        if src not in ("auto", "manual"):
            try:
                v = versions.resolve(pdir, src) or ""
            except Exception:
                v = ""
        v = v or meta.get("lastVersionName") or info["version"] or "1.0.0"
    if not VERSION_RE.fullmatch(v):
        raise SystemExit("versão inválida (ex: 1.2.0)")

    app_name = (a.get("appName") or "").strip() or meta.get("appName") or info["appName"]
    safe = safe_name(app_name)

    ev = (a.get("electronVersion") or "").strip() or DEFAULT_ELECTRON
    if not ELECTRON_RE.fullmatch(ev):
        raise SystemExit("versão do Electron inválida (ex: 33.4.11)")

    ptype = str(a.get("projectType") or meta.get("projectType") or "auto").strip() or "auto"
    if ptype not in PROJECT_TYPES:
        raise SystemExit(f"tipo de projeto desconhecido: {ptype}")
    prof = profile(pdir, info, ptype)
    own_pre = (a.get("preBuild") or "").strip()
    if prof["errors"] and not own_pre:
        raise SystemExit("; ".join(prof["errors"]))
    web_dir = (a.get("webDir") or "").strip() or meta.get("webDir") or prof["webDir"]

    log(f"App: {app_name} (pasta {safe})")
    log(f"Versão {v}")
    log(f"Plataformas: {', '.join(platforms)}")
    log(f"Electron {ev}")
    log(f"Tipo: {TYPE_LABELS[ptype]}")
    for w in prof["warnings"]:
        log(f"\033[33m⚠ {w}\033[0m")
    for e in prof["errors"]:
        log(f"\033[33m⚠ {e}\033[0m")

    step("2/4 Preparando o projeto web")
    pre = own_pre or prof["preBuild"]
    if pre == "-":
        log("Pré-build pulado (tipo sem build ou pulado por escolha).")
    else:
        cmd = pre or info["defaultPreBuild"]
        if cmd:
            run(["bash", "-lc", cmd], cwd=pdir, env=dict(os.environ, CI="true"))
        else:
            log("Não há pré-build para este projeto.")

    step("3/4 Montando o app Electron")
    src = os.path.join(pdir, web_dir)
    if not os.path.isfile(os.path.join(src, "index.html")):
        raise SystemExit(f"não achei {web_dir}/index.html: rode o build do projeto web (pré-build) ou ajuste a pasta do site")
    appdir = os.path.join(pdir, "xtool", "pc", "app")
    shutil.rmtree(appdir, ignore_errors=True)
    if os.path.abspath(src) == os.path.abspath(pdir):
        # o site é a raiz do projeto: não copia dependências, git, a própria saída (xtool) nem pastas nativas
        ignore = shutil.ignore_patterns(".git", "node_modules", "xtool", "android", "ios", ".github",
                                        ".vscode", ".idea", "coverage")
        shutil.copytree(src, os.path.join(appdir, "www"), ignore=ignore)
    else:
        shutil.copytree(src, os.path.join(appdir, "www"))
    pkg = {"name": safe.lower(), "productName": app_name, "version": v, "main": "main.js",
           "description": app_name, "author": "xtool-painel", "license": "UNLICENSED"}
    with open(os.path.join(appdir, "package.json"), "w", encoding="utf-8") as f:
        json.dump(pkg, f, indent=2, ensure_ascii=False)
    with open(os.path.join(appdir, "main.js"), "w", encoding="utf-8") as f:
        f.write(MAIN_JS)
    icon_src = find_icon(pdir, info, web_dir, (a.get("icon") or "").strip())
    if icon_src:
        if os.path.splitext(icon_src)[1].lower() == ".ico":
            shutil.copyfile(icon_src, os.path.join(appdir, "icon.ico"))
        else:
            shutil.copyfile(icon_src, os.path.join(appdir, "icon.png"))
        log(f"Ícone: {icon_src}")
    log(f"App montado em {appdir}")
    index_txt = read_text(os.path.join(appdir, "www", "index.html"))
    if re.search(r"(?:src|href)=[\"']/[^/]", index_txt):
        log("O site usa caminhos absolutos (/assets/...): tudo bem, o app abre o site por app://.")

    step("4/4 Empacotando")
    outRoot = os.path.join(pdir, "xtool", "pc", "out")
    os.makedirs(outRoot, exist_ok=True)
    folders, zips = {}, {}
    dry = bool(a.get("dryRun"))
    company = (a.get("company") or "").strip() or app_name
    wine = shutil.which("wine") or shutil.which("wine64")
    ico_path = None
    if "win32" in platforms and wine and icon_src:
        if icon_src.lower().endswith(".ico"):
            ico_path = os.path.join(appdir, "icon.ico")
        elif imagemagick():
            ico_path = os.path.join(appdir, "icon.ico")
            if not make_ico(icon_src, ico_path):
                log("\033[33m⚠ não consegui gerar o .ico a partir do PNG: o ícone do .exe não será aplicado\033[0m")
                ico_path = None
        else:
            log("\033[33m⚠ ícone do .exe não aplicado: o ImageMagick (convert/magick) não está instalado\033[0m")
    for plat in platforms:
        folder = f"{safe}-{plat}-{ARCH}"
        folders[plat] = folder
        target = os.path.join(outRoot, folder)
        shutil.rmtree(target, ignore_errors=True)
        extra = []
        if plat == "win32":
            if not wine:
                msg = ("⚠ o ícone e os metadados do .exe não foram aplicados: o Wine não está instalado. "
                       "Para aplicar, reconstrua a imagem com: INSTALL_WINE=1 docker compose up -d --build")
                if icon_src and not icon_src.lower().endswith(".ico"):
                    msg += "; o ícone da janela já foi aplicado"
                log(f"\033[33m{msg}\033[0m")
            else:
                extra += [f"--win32metadata.ProductName={one_line(app_name)}",
                          f"--win32metadata.FileDescription={one_line(app_name)}",
                          f"--win32metadata.CompanyName={one_line(company)}",
                          f"--win32metadata.OriginalFilename={safe}.exe"]
                if ico_path:
                    extra.append(f"--icon={ico_path}")
                elif not icon_src:
                    log("\033[33m⚠ ícone do .exe não aplicado: coloque um PNG em resources/icon.png "
                        "(ou passe o caminho em 'ícone')\033[0m")
        if plat == "darwin":
            log("\033[33m⚠ app do macOS sem assinatura nem notarização: o Gatekeeper pede para liberar manualmente\033[0m")
        cmd = ["npx", "--yes", "@electron/packager", appdir, safe, f"--platform={plat}", f"--arch={ARCH}",
               f"--out={outRoot}", "--overwrite", f"--electron-version={ev}", f"--app-version={v}", "--prune=false"]
        cmd += extra
        if dry:
            log(f"(dry-run) $ {' '.join(cmd)}")
            os.makedirs(target)
            with open(os.path.join(target, "DRY-RUN.txt"), "w", encoding="utf-8") as f:
                f.write("simulação: o empacotador não foi chamado\n")
        else:
            run(cmd, cwd=pdir, env=dict(os.environ, CI="true"))
        if not os.path.isdir(target):
            raise SystemExit(f"o empacotador não gerou {folder}")
        log(f"{folder}: {dir_size(target) / 1e6:.1f} MB")
        if a.get("zip"):
            zipfile = os.path.join(pdir, "xtool", "pc", f"{safe}-{v}-{plat}-{ARCH}.zip")
            os.makedirs(os.path.dirname(zipfile), exist_ok=True)
            if os.path.exists(zipfile):
                os.remove(zipfile)
            zips[plat] = zipfile
            if dry:
                log(f"zip simulado: {zipfile}")
            else:
                run(["zip", "-qry", zipfile, folder], cwd=outRoot)

    result = {"version": v, "appName": app_name, "safeName": safe, "outRoot": outRoot,
              "folders": folders, "zips": zips,
              "exe": {"win32": f"{safe}.exe", "linux": safe, "darwin": f"{safe}.app"}}
    merge_meta(project, {"lastVersionName": v, "appName": app_name,
                         "lastBuild": {"versionName": v, "outRoot": outRoot, "folders": folders,
                                       "zips": zips, "at": time.time()}})
    log(f"\n\033[1;32m✔ Pronto: {app_name} {v} em {', '.join(platforms)}\033[0m")
    return result


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        a = json.load(f)
    build(a)


if __name__ == "__main__":
    try:
        main()
    except (SystemExit, Exception) as e:  # noqa
        if isinstance(e, SystemExit) and e.code in (0, None):
            raise
        log(f"\n\033[1;31m✖ {e}\033[0m")
        sys.exit(1)
