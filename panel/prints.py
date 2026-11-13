"""Prints automáticos de projetos web (com build estático, ex.: Capacitor/SPA).

O Chromium (Playwright) é baixado sob demanda para o volume /root, então nada
muda na imagem Docker. A captura roda como job do painel (shots/shoot.mjs), e o
resultado vai para /work/<projeto>/xtool/prints/<runId>/. Daí o painel envia as
imagens para a App Store e para o Google Play pelo lojas_io.

Funções usadas pelo server: get_config, save_config, detect_web_dir, install_cmd,
status, run_cmd, runs, run_files, upload.
"""
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import time

import lojas
import lojas_io
import store

PANEL_PY = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("XTOOL_WORK", "/work")
TOOLS = "/root/.xtool-panel/shots"
BROWSERS = "/root/.cache/ms-playwright"
PLAYWRIGHT = "1.49.1"
RUNS_KEEP = 10
IOS_MAX = 10  # App Store: até 10 imagens por tipo e idioma
PLAY_MAX = 8  # Google Play: até 8 imagens por tipo e idioma
RUN_RE = re.compile(r"^\d{8}-\d{6}$")
STYLES = ("plain", "caption")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
FONT_RE = re.compile(r"^[A-Za-z0-9 ,._\-]{1,80}$")
BUILD_RE = re.compile(r"^[A-Za-z0-9:_.\-]{1,60}$")
ACTION_TYPES = ("click", "type", "wait", "eval")
MAX_SCREENS = 10
MAX_ACTIONS = 20
DEFAULT_WAIT = 1500

SIZES = {
    "iphone69": {"label": "iPhone 6,9\"", "w": 1320, "h": 2868, "dpr": 3, "store": "ios", "kind": "APP_IPHONE_67"},
    "iphone65": {"label": "iPhone 6,5\"", "w": 1284, "h": 2778, "dpr": 3, "store": "ios", "kind": "APP_IPHONE_65"},
    "ipad13": {"label": "iPad 13\"", "w": 2064, "h": 2752, "dpr": 2, "store": "ios", "kind": "APP_IPAD_PRO_3GEN_129"},
    "playPhone": {"label": "Celular (Play)", "w": 1080, "h": 1920, "dpr": 3, "store": "android", "kind": "phoneScreenshots"},
    "playTab7": {"label": "Tablet 7\" (Play)", "w": 1200, "h": 1920, "dpr": 2, "store": "android", "kind": "sevenInchScreenshots"},
    "playTab10": {"label": "Tablet 10\" (Play)", "w": 1600, "h": 2560, "dpr": 2, "store": "android", "kind": "tenInchScreenshots"},
}


# ---------------- validações (mensagens em português) ----------------
def _txt(v, msg, maxlen, empty_ok=False):
    if not isinstance(v, str):
        raise ValueError(msg)
    v = v.strip()
    if not v and not empty_ok:
        raise ValueError(msg)
    if len(v) > maxlen:
        raise ValueError(f"{msg} (no máximo {maxlen} caracteres)")
    return v


def _int(v, msg, lo, hi):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(msg)
    return v


def _codes():
    return {c["code"] for c in lojas.catalog()}


def _clean_locales(lst):
    if not isinstance(lst, list):
        raise ValueError("idiomas inválidos")
    validos = _codes()
    out = []
    for c in lst:
        if c not in validos:
            raise ValueError(f"idioma desconhecido: {c}")
        if c not in out:
            out.append(c)
    return out


def _norm_rel(p):
    """Caminho relativo à pasta do projeto, ou "" se for inválido (absoluto ou saindo da pasta)."""
    p = str(p or "").strip().replace("\\", "/")
    if not p:
        return ""
    n = posixpath.normpath(p)
    if n.startswith("/") or n == ".." or n.startswith("../"):
        return ""
    return n


def _clean_action(a, where):
    if not isinstance(a, dict):
        raise ValueError(f"{where}: ação inválida")
    t = a.get("type")
    if t == "click":
        return {"type": "click", "selector": _txt(a.get("selector"), f"{where}: informe o seletor do clique", 300)}
    if t == "type":
        return {"type": "type",
                "selector": _txt(a.get("selector"), f"{where}: informe o seletor do campo", 300),
                "text": _txt(a.get("text", ""), f"{where}: informe o texto a digitar", 500, empty_ok=True)}
    if t == "wait":
        return {"type": "wait", "ms": _int(a.get("ms"), f"{where}: espera inválida (0 a 30000 ms)", 0, 30000)}
    if t == "eval":
        return {"type": "eval", "js": _txt(a.get("js"), f"{where}: informe o JavaScript", 5000)}
    raise ValueError(f"{where}: ação desconhecida: {t}")


def _clean_screen(s, i, validos):
    where = f"tela {i}"
    if not isinstance(s, dict):
        raise ValueError(f"{where}: dados inválidos")
    name = _txt(s.get("name"), f"{where}: informe o nome", 60)
    path = _txt(s.get("path"), f"{where}: informe a rota (começando por / ou #)", 200)
    if path[0] not in "/#":
        raise ValueError(f"{where}: a rota precisa começar por / ou #")
    wait = s.get("wait")
    wait = DEFAULT_WAIT if wait is None else _int(wait, f"{where}: espera inválida (0 a 30000 ms)", 0, 30000)
    acts = s.get("actions") or []
    if not isinstance(acts, list) or len(acts) > MAX_ACTIONS:
        raise ValueError(f"{where}: no máximo {MAX_ACTIONS} ações")
    caps = s.get("captions") or {}
    if not isinstance(caps, dict):
        raise ValueError(f"{where}: legendas inválidas")
    legendas = {}
    for code, txt in caps.items():
        if code not in validos:
            raise ValueError(f"{where}: idioma desconhecido nas legendas: {code}")
        txt = _txt(txt, f"{where}: legenda vazia em {code}", 120, empty_ok=True)
        if txt:
            legendas[code] = txt
    return {"name": name, "path": path, "wait": wait,
            "actions": [_clean_action(a, where) for a in acts],
            "captions": legendas}


def _defaults():
    return {"webDir": "", "build": "", "style": "plain", "background": "#1e1e2e",
            "textColor": "#ffffff", "font": "system-ui", "sizes": list(SIZES),
            "screens": [], "locales": [], "setLocale": ""}


def _clean(cfg):
    """Valida a configuração inteira e devolve a forma gravada em projects.json."""
    if not isinstance(cfg, dict):
        raise ValueError("configuração inválida")
    d = _defaults()

    web = str(cfg.get("webDir") or "").strip()
    if web and not _norm_rel(web):
        raise ValueError("a pasta do site precisa estar dentro do projeto (sem / inicial nem ..)")
    build = str(cfg.get("build") or "").strip()
    if build and not BUILD_RE.match(build):
        raise ValueError("nome de script inválido (use letras, números, : . _ -)")

    style = cfg.get("style") or d["style"]
    if style not in STYLES:
        raise ValueError("estilo inválido: use plain ou caption")
    bg = cfg.get("background") or d["background"]
    if not isinstance(bg, str) or not HEX_RE.match(bg):
        raise ValueError("cor de fundo inválida (use #rrggbb)")
    tc = cfg.get("textColor") or d["textColor"]
    if not isinstance(tc, str) or not HEX_RE.match(tc):
        raise ValueError("cor da legenda inválida (use #rrggbb)")
    font = str(cfg.get("font") or d["font"]).strip()
    if not FONT_RE.match(font):
        raise ValueError("fonte inválida (use letras, números, espaço ou , . _ -)")

    sizes = cfg.get("sizes", d["sizes"])
    if not isinstance(sizes, list):
        raise ValueError("tamanhos inválidos")
    lim = []
    for s in sizes:
        if s not in SIZES:
            raise ValueError(f"tamanho desconhecido: {s}")
        if s not in lim:
            lim.append(s)
    if not lim:
        raise ValueError("escolha pelo menos um tamanho")

    screens = cfg.get("screens", [])
    if not isinstance(screens, list):
        raise ValueError("telas inválidas")
    if not screens:
        raise ValueError("cadastre de 1 a 10 telas")
    if len(screens) > MAX_SCREENS:
        raise ValueError(f"no máximo {MAX_SCREENS} telas")
    validos = _codes()
    telas = [_clean_screen(s, i, validos) for i, s in enumerate(screens, 1)]

    set_locale = cfg.get("setLocale") or ""
    set_locale = _txt(set_locale, "JavaScript de idioma inválido", 2000, empty_ok=True)

    return {"webDir": _norm_rel(web) if web else "", "build": build, "style": style,
            "background": bg, "textColor": tc, "font": font, "sizes": lim,
            "screens": telas, "locales": _clean_locales(cfg.get("locales") or []),
            "setLocale": set_locale}


# ---------------- projeto ----------------
def _project_dir(project):
    name = str(project or "")
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("projeto inválido")
    p = os.path.join(WORK, name)
    if not os.path.isdir(p):
        raise ValueError("projeto não encontrado")
    return p


def _prints_dir(project):
    return os.path.join(_project_dir(project), "xtool", "prints")


def _run_dir(project, run_id):
    if not RUN_RE.match(str(run_id or "")):
        raise ValueError("identificador do lote inválido")
    return os.path.join(_prints_dir(project), run_id)


# ---------------- configuração ----------------
def get_config(project):
    _project_dir(project)
    cfg = _defaults()
    saved = store.project_meta(project).get("prints")
    if isinstance(saved, dict):
        for k in cfg:
            if k in saved and saved[k] is not None:
                cfg[k] = saved[k]
    cfg["detectedWebDir"] = detect_web_dir(_project_dir(project))
    return cfg


def save_config(project, cfg):
    _project_dir(project)
    clean = _clean(cfg)
    store.project_meta_update(project, {"prints": clean})
    return get_config(project)


_WEBDIR_RE = re.compile(r"""webDir['"]?\s*[:=]\s*['"]([^'"]+)['"]""")


def detect_web_dir(project_dir):
    """Pasta do site: webDir do capacitor.config; senão a primeira de dist/build/www/out/public com index.html."""
    for f in ("capacitor.config.json", "capacitor.config.ts", "capacitor.config.js"):
        p = os.path.join(project_dir, f)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except OSError:
            continue
        m = _WEBDIR_RE.search(txt)
        if m:
            rel = _norm_rel(m.group(1))
            if rel:
                return rel
    for d in ("dist", "build", "www", "out", "public"):
        if os.path.isfile(os.path.join(project_dir, d, "index.html")):
            return d
    return ""


# ---------------- Chromium sob demanda ----------------
def _installed():
    if not os.path.isfile(os.path.join(TOOLS, "node_modules", "playwright-core", "package.json")):
        return False
    try:
        names = os.listdir(BROWSERS)
    except OSError:
        return False
    return any(n.startswith("chromium-") and os.path.isdir(os.path.join(BROWSERS, n)) for n in names)


def _pw_version():
    try:
        with open(os.path.join(TOOLS, "node_modules", "playwright-core", "package.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "")
    except (OSError, ValueError):
        return ""


def _env():
    return dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=BROWSERS, NODE_PATH=os.path.join(TOOLS, "node_modules"))


def _libs_ok():
    js = ("const {chromium}=require('playwright-core');"
          "chromium.launch().then(b=>b.close()).then(()=>process.exit(0),"
          "e=>{console.error(String((e&&e.message)||e));process.exit(1)});")
    try:
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL, env=_env())
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def status():
    inst = _installed()
    if not inst:
        return {"installed": False, "libsOk": False, "version": ""}
    return {"installed": True, "libsOk": _libs_ok(), "version": _pw_version()}


_LIBS = ("libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libxkbcommon0 libxcomposite1 "
         "libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 "
         "fonts-noto-color-emoji fonts-liberation")


def install_cmd():
    script = f"""set -e
echo '▶ Preparando a pasta das ferramentas de print'
mkdir -p {shlex.quote(TOOLS)}
cd {shlex.quote(TOOLS)}
if [ ! -f package.json ]; then npm init -y >/dev/null; fi
echo '▶ Instalando playwright-core {PLAYWRIGHT}'
npm install --no-audit --no-fund playwright-core@{PLAYWRIGHT} playwright@{PLAYWRIGHT}
echo '▶ Baixando o Chromium (uma vez; fica no volume)'
npx playwright install chromium
echo '▶ Instalando as bibliotecas do sistema'
{{ npx playwright install-deps chromium || {{ apt-get update && apt-get install -y {_LIBS}; }}; }}
echo '✔ Chromium pronto para os prints'
"""
    return ["sh", "-c", script], {"PLAYWRIGHT_BROWSERS_PATH": BROWSERS}


# ---------------- lotes (runs) ----------------
def _run_ids(project):
    base = _prints_dir(project)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    return sorted((n for n in names if RUN_RE.match(n) and os.path.isdir(os.path.join(base, n))), reverse=True)


def _manifest(run_dir):
    try:
        with open(os.path.join(run_dir, "manifest.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [i for i in data if isinstance(i, dict) and i.get("file")] if isinstance(data, list) else []


def runs(project):
    _project_dir(project)
    out = []
    for rid in _run_ids(project)[:RUNS_KEEP]:
        d = os.path.join(_prints_dir(project), rid)
        out.append({"id": rid, "at": int(os.path.getmtime(d)), "count": len(_manifest(d))})
    return out


def _prune(project):
    for old in _run_ids(project)[RUNS_KEEP:]:
        shutil.rmtree(os.path.join(_prints_dir(project), old), ignore_errors=True)


def _lote(project, run_id):
    """Itens do manifest com caminho relativo a /work (file), e o absoluto (abs)."""
    d = _run_dir(project, run_id)
    if not os.path.isdir(d):
        raise ValueError("lote não encontrado")
    itens = []
    for it in _manifest(d):
        rel = str(it["file"]).replace("\\", "/")
        if posixpath.normpath(rel).startswith(("/", "..")):
            continue
        itens.append({"file": f"{project}/xtool/prints/{run_id}/{rel}",
                      "abs": os.path.join(d, rel),
                      "locale": it.get("locale"), "size": it.get("size"), "store": it.get("store"),
                      "kind": it.get("kind"), "screen": it.get("screen"), "index": it.get("index")})
    return itens


def run_files(project, run_id):
    return [{k: i[k] for k in ("file", "locale", "size", "store", "kind", "screen", "index")}
            for i in _lote(project, run_id)]


def run_cmd(project):
    """Monta o job de captura: (argv, env, run_dir). Erros de configuração viram ValueError antes do Job."""
    proj = _project_dir(project)
    cfg = get_config(project)
    if not _installed():
        raise ValueError("o Chromium dos prints ainda não foi instalado (botão Instalar)")
    if not cfg["screens"]:
        raise ValueError("cadastre pelo menos uma tela")
    web = cfg["webDir"] or cfg["detectedWebDir"]
    if not web:
        raise ValueError("não achei a pasta do site: informe a pasta em webDir")
    web_abs = os.path.realpath(os.path.join(proj, web))
    if web_abs != os.path.realpath(proj) and not web_abs.startswith(os.path.realpath(proj) + os.sep):
        raise ValueError("a pasta do site precisa estar dentro do projeto")
    if not cfg["build"] and not os.path.isfile(os.path.join(web_abs, "index.html")):
        raise ValueError(f"não achei index.html em {web}: rode o build ou ajuste webDir")

    _prints_dir(project)  # garante que o projeto existe
    base = _prints_dir(project)
    os.makedirs(base, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    while os.path.exists(os.path.join(base, run_id)):
        time.sleep(1)
        run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(base, run_id)
    os.makedirs(run_dir)
    _prune(project)

    args = {
        "webDir": web_abs, "outDir": run_dir,
        "sizes": {sid: SIZES[sid] for sid in cfg["sizes"]},
        "screens": cfg["screens"],
        "locales": cfg["locales"] or lojas.project_locales(project),
        "setLocale": cfg["setLocale"], "style": cfg["style"], "background": cfg["background"],
        "textColor": cfg["textColor"], "font": cfg["font"],
    }
    args_path = os.path.join(run_dir, "args.json")
    with open(args_path, "w", encoding="utf-8") as f:
        json.dump(args, f, ensure_ascii=False)

    shoot = os.path.join(PANEL_PY, "shots", "shoot.mjs")
    steps = ["set -e", f"cd {shlex.quote(proj)}"]
    if cfg["build"]:
        steps.append(f"echo {shlex.quote('▶ Gerando o site (npm run ' + cfg['build'] + ')')}")
        steps.append(f"npm run {shlex.quote(cfg['build'])}")
    steps.append("echo '▶ Capturando as telas'")
    steps.append(f"node {shlex.quote(shoot)} {shlex.quote(args_path)}")
    return ["sh", "-c", "\n".join(steps)], _env(), run_dir


# ---------------- envio para as lojas ----------------
def upload(project, run_id, version, items, replace=False):
    _project_dir(project)
    if not str(version or "").strip():
        raise ValueError("escolha a versão")
    if not isinstance(items, list) or not items:
        raise ValueError("escolha pelo menos uma imagem")
    lote = {i["file"]: i for i in _lote(project, run_id)}
    errors = []
    pedidos, vistos = [], set()
    for rel in items:
        if not isinstance(rel, str):
            errors.append("arquivo inválido")
            continue
        if rel in vistos:
            continue
        vistos.add(rel)
        if rel not in lote:
            errors.append(f"{rel}: não faz parte deste lote")
            continue
        pedidos.append(lote[rel])
    if not pedidos:
        return {"uploaded": 0, "errors": errors}

    imagens = {}
    for loja in sorted({p["store"] for p in pedidos}):
        imagens[loja] = lojas_io.load_fields(project, loja, version)["images"]

    grupos = {}
    for p in pedidos:
        grupos.setdefault((p["store"], p["locale"], p["kind"]), []).append(p)

    enviadas = 0
    for (loja, locale, kind), itens in grupos.items():
        rotulo = f"{locale} ({kind})"
        lim = IOS_MAX if loja == "ios" else PLAY_MAX
        atuais = list(((imagens[loja].get(locale) or {}).get(kind)) or [])
        if replace:
            try:
                for img in atuais:
                    lojas_io.delete_image(project, loja, version, locale, kind, img["id"])
            except (ValueError, lojas.LojasError) as e:
                errors.append(f"{rotulo}: não consegui apagar as imagens antigas ({e})")
                continue
            atuais = []
        livres = lim - len(atuais)
        if livres <= 0:
            errors.append(f"{rotulo}: já tem {lim} imagens (limite da loja)")
            continue
        if len(itens) > livres:
            errors.append(f"{rotulo}: limite de {lim} por tipo; {len(itens) - livres} ficou(aram) de fora")
            itens = itens[:livres]
        for p in itens:
            if not os.path.isfile(p["abs"]):
                errors.append(f"{p['file']}: arquivo não encontrado")
                continue
            try:
                lojas_io.upload_image(project, loja, version, locale, kind, p["abs"])
                enviadas += 1
            except (ValueError, lojas.LojasError) as e:
                errors.append(f"{p['file']}: {e}")
    return {"uploaded": enviadas, "errors": errors}
