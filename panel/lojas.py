"""Lojas publicadas de um projeto (App Store, Google Play, Steam): visão geral e vínculos.

Só leitura: nada é gravado aqui. Campos e imagens ficam em lojas_io.py.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import asc
import builds
import store
from asc import ASC, AscError
from play import Play


class LojasError(Exception):
    pass


STORES = ("ios", "android", "pc")
STORE_LABELS = {"ios": "App Store", "android": "Google Play", "pc": "Steam"}

LOCALES = [
    ("pt-BR", "Português (Brasil)"), ("pt-PT", "Português (Portugal)"), ("en-US", "English (US)"),
    ("en-GB", "English (UK)"), ("es-ES", "Español (España)"), ("es-MX", "Español (México)"),
    ("fr-FR", "Français"), ("de-DE", "Deutsch"), ("it", "Italiano"), ("ja", "日本語"), ("ko", "한국어"),
    ("zh-Hans", "中文 (简体)"), ("zh-Hant", "中文 (繁體)"), ("ru", "Русский"), ("nl-NL", "Nederlands"),
    ("tr", "Türkçe"), ("ar-SA", "العربية"), ("hi", "हिन्दी"), ("id", "Bahasa Indonesia"),
    ("pl", "Polski"), ("sv", "Svenska"), ("th", "ไทย"), ("vi", "Tiếng Việt"),
]
_KNOWN = {code for code, _ in LOCALES}

PLAY_LANG = {
    "pt-BR": "pt-BR", "pt-PT": "pt-PT", "en-US": "en-US", "en-GB": "en-GB", "es-ES": "es-ES",
    "es-MX": "es-419", "fr-FR": "fr-FR", "de-DE": "de-DE", "it": "it-IT", "ja": "ja-JP", "ko": "ko-KR",
    "zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "ru": "ru-RU", "nl-NL": "nl-NL", "tr": "tr-TR",
    "ar-SA": "ar", "hi": "hi-IN", "id": "id", "pl": "pl-PL", "sv": "sv-SE", "th": "th", "vi": "vi",
}
_FROM_PLAY = {v: k for k, v in PLAY_LANG.items()}

ACTION_LABELS = {"accounts": "Ir para Contas", "configure": "Configurar",
                 "build": "Gerar build", "deliver": "Enviar para a loja"}
NO_ACCOUNT_STEPS = ["Cadastre a conta em Contas", "Vincule a conta e o app em ⚙ Configurar"]
NOT_PUBLISHED_STEPS = ["Gere um build Release em 🔨 Build",
                       "Envie para a loja em 📤 Enviar para a loja",
                       "Depois de aprovada, volte aqui para gerenciar a ficha"]
ACC_ACTIONS = ("accounts", "configure")
# versões que NÃO são "pendentes": à venda ou encerradas (terminais)
_NOT_PENDING = set(asc.LIVE_STATES) | {"REPLACED_WITH_NEW_VERSION", "REMOVED_FROM_SALE",
                                       "DEVELOPER_REMOVED_FROM_SALE"}
PENDING_REVIEW_LABEL = " — falta enviar para a revisão"


def play_lang(code):
    return PLAY_LANG.get(code, code)


def from_play_lang(lang):
    return _FROM_PLAY.get(lang, lang)


def catalog():
    return [{"code": c, "label": l} for c, l in LOCALES]


def _dedupe(seq):
    out = []
    for x in seq:
        if x in _KNOWN and x not in out:
            out.append(x)
    return out


def project_locales(project, extra=()):
    """Idiomas efetivos: meta["locales"]; senão extra; senão pt-BR. Só códigos do catálogo."""
    meta_list = store.project_meta(project).get("locales")
    codes = _dedupe(meta_list if isinstance(meta_list, list) else [])
    if codes:
        return codes
    codes = _dedupe(list(extra or ()))
    return codes or ["pt-BR"]


# ---- vínculos ----
def _project_dir(project):
    return os.path.join(os.environ.get("XTOOL_WORK", "/work"), project)


def _d(v):
    return v if isinstance(v, dict) else {}


def _ctx(project):
    meta = store.project_meta(project)
    return meta, builds.detect_platforms(_project_dir(project), meta, project)


def _raw(plat, meta, plats):
    """Vínculos da loja como estão no projeto (sem validar contas)."""
    if plat == "ios":
        return {"accountId": meta.get("accountId") or "",
                "bundleId": meta.get("bundleId") or plats["ios"].get("bundleId") or ""}
    if plat == "android":
        am = _d(meta.get("android"))
        return {"accountId": am.get("playAccountId") or "",
                "packageName": am.get("packageName") or plats["android"].get("packageName") or ""}
    sm = _d(meta.get("steam"))
    return {"accountId": sm.get("accountId") or "", "appId": str(sm.get("appId") or ""),
            "branch": sm.get("branch") or ""}


def _missing(plat, raw):
    """Mensagem do que falta configurar ('' se o vínculo está completo)."""
    if plat == "ios":
        if not raw["accountId"]:
            return "Nenhuma conta da Apple vinculada a este projeto: vincule em ⚙ Configurar"
        if not raw["bundleId"]:
            return "Projeto sem bundle ID iOS: defina em ⚙ Configurar"
    elif plat == "android":
        if not raw["accountId"]:
            return "Nenhuma conta da Google Play vinculada a este projeto: vincule em ⚙ Configurar"
        if not raw["packageName"]:
            return "Projeto sem nome de pacote Android: defina em ⚙ Configurar"
    else:
        if not raw["accountId"]:
            return "Nenhuma conta Steam vinculada a este projeto: vincule em ⚙ Configurar"
        if not raw["appId"]:
            return "Nenhum app Steam vinculado: escolha em ⚙ Configurar"
    return ""


def link(project, store):
    """Vínculo da loja: ios {accountId,bundleId}; android {accountId,packageName}; pc {accountId,appId,branch}."""
    if store not in STORES:
        raise LojasError(f"loja desconhecida: {store}")
    meta, plats = _ctx(project)
    raw = _raw(store, meta, plats)
    msg = _missing(store, raw)
    if msg:
        raise LojasError(msg)
    return raw


def asc_client(account_id):
    k = store.asc_key(account_id)
    if not k.get("p8"):
        raise LojasError("a conta Apple não tem a chave da API do App Store Connect (cadastre em Contas)")
    return ASC(k.get("issuerId"), k.get("keyId"), k.get("p8"))


def play_client(account_id):
    try:
        acc = store.play_account(account_id)
    except ValueError:
        raise LojasError("conta da Google Play não encontrada: cadastre em Contas")
    sa = acc.get("json")
    if not isinstance(sa, dict) or not sa:
        raise LojasError("a conta da Google Play não tem a chave de serviço (cadastre em Contas)")
    return Play(sa)


def _apple_account(acc_id):
    for a in store.load(store.ACC_FILE, {"accounts": []}).get("accounts", []):
        if a.get("id") == acc_id:
            return {"id": acc_id, "label": a.get("label") or acc_id}
    return None


def _play_account(acc_id):
    for a in store.play_accounts():
        if a.get("id") == acc_id:
            return {"id": acc_id, "label": a.get("label") or a.get("email") or acc_id}
    return None


def _steam_account(acc_id):
    try:
        a = store.steam_account(acc_id)
    except ValueError:
        return None
    return {"id": acc_id, "label": a.get("label") or a.get("username") or acc_id}


# ---- versões ----
def _vkey(v):
    """Tupla de inteiros da versão; zeros finais removidos (1.0 == 1)."""
    nums = [int(x) for x in re.findall(r"\d+", str(v or ""))]
    while nums and nums[-1] == 0:
        nums.pop()
    return tuple(nums)


def _has_num(v):
    return bool(re.search(r"\d", str(v or "")))


def _same(a, b):
    return _has_num(a) and _has_num(b) and _vkey(a) == _vkey(b)


def _newer(a, b):
    return _has_num(a) and _has_num(b) and _vkey(a) > _vkey(b)


def _candidates(blist, plat):
    """Builds release da plataforma (pc: só zip), do mais novo para o mais antigo."""
    out = []
    for b in blist:
        if b.get("platform") != plat or not b.get("release"):
            continue
        if plat == "pc" and b.get("kind") != "zip":
            continue
        out.append(b)
    return out


def _local(blist, plat):
    """(versions, latest): uma linha por versão (o build mais novo), e a maior versão enviável."""
    cands = _candidates(blist, plat)
    rows, seen = [], set()
    for b in cands:
        v = b.get("version") or ""
        if v in seen:
            continue
        seen.add(v)
        rows.append({"version": v, "build": str(b.get("build") or ""), "file": b.get("file", ""),
                     "at": b.get("at") or 0, "deliverable": bool(b.get("deliverable")),
                     "reason": str(b.get("deliverReason") or "")})
    rows.sort(key=lambda r: (_vkey(r["version"]), r["at"]), reverse=True)

    best = None
    for b in cands:
        if not b.get("deliverable"):
            continue
        k = (_vkey(b.get("version")), b.get("at") or 0)
        if best is None or k > best[0]:
            best = (k, b)
    latest = None
    if best:
        b = best[1]
        db = b.get("database")
        latest = {"version": b.get("version", ""), "build": str(b.get("build") or ""),
                  "file": b.get("file", ""), "at": b.get("at") or 0,
                  "database": {"name": db.get("name", ""), "role": db.get("role", "")} if db else None}
    return rows, latest


def _version_for_build(blist, plat, build):
    for b in blist:
        if b.get("platform") == plat and str(b.get("build") or "") == build and b.get("version"):
            return b.get("version", "")
    return ""


# ---- estado por loja ----
def _new(key, enabled):
    return {"key": key, "label": STORE_LABELS[key], "enabled": bool(enabled), "state": "error",
            "problem": "", "steps": [], "actions": [], "account": None, "appRef": "", "store": None,
            "latest": None, "versions": [], "pending": None,
            "upToDate": False, "newer": False}


def _set(s, state, problem="", steps=(), actions=()):
    s["state"] = state
    s["problem"] = problem or ""
    if state == "ok":
        s["steps"], s["actions"] = [], []
        return
    s["steps"] = list(steps)
    acts = []
    for a in actions:
        label = ACTION_LABELS[a]
        if a == "deliver" and s["key"] == "pc":
            label = "Enviar para a Steam"
        acts.append({"id": a, "label": label})
    s["actions"] = acts


def _epoch(iso):
    """Data ISO 8601 da Apple -> segundos (0 se não der para ler)."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _apple_rows(items):
    """Builds VALID e não expirados do App Store Connect: uma linha por versão (o maior build)."""
    best = {}
    for b in items or []:
        mv = str(b.get("marketingVersion") or "")
        if not mv or b.get("processingState") != "VALID" or b.get("expired"):
            continue
        n = int(b["version"]) if str(b.get("version") or "").isdigit() else 0
        if mv not in best or n > best[mv][0]:
            best[mv] = (n, b)
    return [{"version": mv, "build": str(b.get("version") or ""), "file": "", "at": _epoch(b.get("uploadedDate")),
             "deliverable": True, "reason": "", "source": "apple"} for mv, (n, b) in best.items()]


def _merge_apple(s, rows, latest):
    """iOS: junta as versões já no App Store Connect às locais (a local vence quando a versão é a mesma)."""
    apple = s.pop("_apple", None) or []
    have = {r["version"] for r in rows}
    rows = rows + [r for r in apple if r["version"] not in have]
    rows.sort(key=lambda r: (_vkey(r["version"]), r["at"]), reverse=True)
    top = max(apple, key=lambda r: (_vkey(r["version"]), r["at"]), default=None)
    if top and (latest is None or _vkey(top["version"]) > _vkey(latest["version"])):
        latest = {"version": top["version"], "build": top["build"], "file": "", "at": top["at"],
                  "database": None, "source": "apple"}
    return rows, latest


def _finish(s, local):
    rows, latest = local
    if s["key"] == "ios":
        rows, latest = _merge_apple(s, rows, latest)
    s.pop("_apple", None)
    s["versions"] = rows
    s["latest"] = latest
    st = s["store"]
    if st and s["key"] == "android" and not st.get("version"):
        # Play sem nome de release: usa a versão do build local de mesmo versionCode
        for r in rows:
            if r["build"] and r["build"] == str(st.get("build") or ""):
                st["version"] = r["version"]
                break
    sv = st.get("version", "") if st else ""
    lv = latest["version"] if latest else ""
    if latest and st and s["key"] == "android" and _isint(latest["build"]) and _isint(st.get("build")):
        # Android: o nome da release é texto livre; compara pelo versionCode
        lb, sb = int(latest["build"]), int(st["build"])
        s["upToDate"] = lb == sb
        s["newer"] = lb > sb
        return
    s["upToDate"] = bool(latest and st and _same(lv, sv))
    s["newer"] = bool(latest and st and _newer(lv, sv))


def _isint(v):
    return str(v or "").isdigit()


def _is_editable(state):
    editable = getattr(asc, "EDITABLE", None) or ASC.EDITABLE
    return state in editable


def _ios_pending(api, app_id, live, apple_rows):
    """Versão criada na App Store que ainda não está à venda (e é mais nova que a ao vivo), ou None."""
    try:
        versions = api.app_versions(app_id)
    except Exception:  # noqa — o cartão pendente é extra: erro aqui não derruba a loja
        return None
    live_vs = (live or {}).get("versionString") or ""
    best = None
    for v in versions or []:
        vs = v.get("versionString") or ""
        if v.get("state") in _NOT_PENDING:
            continue
        if live and not _newer(vs, live_vs):
            continue
        if best is None or _vkey(vs) > _vkey(best.get("versionString")):
            best = v
    if best is None:
        return None
    vs, state = best.get("versionString") or "", best.get("state") or ""
    build = next((r["build"] for r in apple_rows or [] if r["version"] == vs), "")
    can = _is_editable(state)
    label = asc.state_label(state) + (PENDING_REVIEW_LABEL if can else "")
    return {"version": vs, "build": build, "state": state, "label": label, "canSubmit": can,
            "canPromote": False, "track": "", "id": best.get("id") or ""}


def _android_pending(prod, others):
    """Release mais nova fora da produção (que falta promover), ou None.

    Sem produção: a release mais nova das outras faixas (é a que a ficha mostra).
    Com produção: só se alguma outra faixa tiver versionCode maior que o da produção.
    """
    usable = [o for o in others or [] if str(o.get("status") or "") not in ("draft", "halted")]
    if not usable:
        return None
    top = max(usable, key=lambda o: int(o.get("versionCode") or 0))
    if prod and int(top.get("versionCode") or 0) <= int(prod.get("versionCode") or 0):
        return None
    track = top.get("track") or ""
    where = f"Na faixa {track}" if prod else f"Está na faixa {track}"
    return {"version": top.get("name") or "", "build": str(top.get("versionCode") or ""),
            "state": top.get("status") or "", "label": f"{where}: falta promover para produção",
            "canSubmit": False, "canPromote": True, "track": track, "id": ""}


def _ios_body(s, meta, plats, blist):
    raw = _raw("ios", meta, plats)
    s["appRef"] = raw["bundleId"]
    if not raw["accountId"]:
        return _set(s, "no_account", _missing("ios", raw), NO_ACCOUNT_STEPS, ACC_ACTIONS)
    s["account"] = _apple_account(raw["accountId"])
    if not s["account"]:
        return _set(s, "no_account", "A conta da Apple vinculada não existe mais: vincule outra em ⚙ Configurar",
                    NO_ACCOUNT_STEPS, ACC_ACTIONS)
    if not raw["bundleId"]:
        return _set(s, "no_account", _missing("ios", raw), ["Vincule o app em ⚙ Configurar"], ("configure",))
    try:
        api = asc_client(raw["accountId"])
    except LojasError as e:
        return _set(s, "no_account", str(e), NO_ACCOUNT_STEPS, ACC_ACTIONS)
    try:
        app = api.app_by_bundle(raw["bundleId"])
    except AscError as e:
        if "não existe app" not in str(e):
            raise
        return _set(s, "no_app", str(e),
                    ["Crie o app no App Store Connect com este bundle ID", "Depois confira o vínculo em ⚙ Configurar"],
                    ("configure",))
    try:  # builds já enviados e processados na Apple (TestFlight): versões prontas para publicar
        s["_apple"] = _apple_rows(api.builds(app["id"], limit=50))
    except AscError:
        s["_apple"] = []
    live = api.live_version(app["id"])
    s["pending"] = _ios_pending(api, app["id"], live, s.get("_apple"))
    if not live:
        return _set(s, "not_published", "Nenhuma versão deste app está publicada na App Store",
                    NOT_PUBLISHED_STEPS, ("build", "deliver"))
    s["store"] = {"version": live.get("versionString") or "", "build": "", "state": live.get("state") or "",
                  "track": "", "date": live.get("createdDate") or "",
                  "url": f"https://apps.apple.com/app/id{app['id']}"}
    _set(s, "ok")


def _android_body(s, meta, plats, blist):
    raw = _raw("android", meta, plats)
    s["appRef"] = raw["packageName"]
    if not raw["accountId"]:
        return _set(s, "no_account", _missing("android", raw), NO_ACCOUNT_STEPS, ACC_ACTIONS)
    s["account"] = _play_account(raw["accountId"])
    if not s["account"]:
        return _set(s, "no_account", "A conta da Google Play vinculada não existe mais: vincule outra em ⚙ Configurar",
                    NO_ACCOUNT_STEPS, ACC_ACTIONS)
    if not raw["packageName"]:
        return _set(s, "no_account", _missing("android", raw), ["Vincule o app em ⚙ Configurar"], ("configure",))
    try:
        cli = play_client(raw["accountId"])
    except LojasError as e:
        return _set(s, "no_account", str(e), NO_ACCOUNT_STEPS, ACC_ACTIONS)
    summary = cli.release_summary(raw["packageName"])
    prod = summary.get("live")
    live = prod
    others = summary.get("others") or []
    s["pending"] = _android_pending(prod, others)
    if not live:
        # sem produção: vale a release mais nova das outras faixas (teste fechado/aberto/interno), exceto rascunhos
        cand = [o for o in others if str(o.get("status") or "") not in ("draft", "halted")]
        live = max(cand, key=lambda o: int(o.get("versionCode") or 0), default=None)
    if not live:
        tracks = []
        for o in others:
            t = o.get("track") or ""
            if t and t not in tracks:
                tracks.append(t)
        problem = "Nenhuma versão está publicada na faixa de produção do Google Play"
        if tracks:
            problem += f" (só há versões na faixa {', '.join(tracks)})"
        return _set(s, "not_published", problem, NOT_PUBLISHED_STEPS, ("build", "deliver"))
    vc = str(live.get("versionCode") or "")
    s["store"] = {"version": live.get("name") or "", "build": vc, "state": live.get("status") or "",
                  "track": live.get("track") or "", "date": "",
                  "url": f"https://play.google.com/store/apps/details?id={raw['packageName']}"}
    _set(s, "ok")


def _pc_body(s, meta, plats, blist):
    raw = _raw("pc", meta, plats)
    s["appRef"] = raw["appId"]
    if not raw["accountId"]:
        return _set(s, "no_account", _missing("pc", raw), NO_ACCOUNT_STEPS, ACC_ACTIONS)
    s["account"] = _steam_account(raw["accountId"])
    if not s["account"]:
        return _set(s, "no_account", "A conta Steam vinculada não existe mais: vincule outra em ⚙ Configurar",
                    NO_ACCOUNT_STEPS, ACC_ACTIONS)
    if not raw["appId"]:
        return _set(s, "no_app", _missing("pc", raw), ["Vincule o app da Steam em ⚙ Configurar"],
                    ("configure",))
    try:
        app = store.steam_app(raw["accountId"], raw["appId"])
    except ValueError:
        return _set(s, "no_app", "O app Steam vinculado não está cadastrado: escolha outro em ⚙ Configurar",
                    ["Vincule um app Steam em ⚙ Configurar"], ("configure",))
    s["appRef"] = app.get("name") or raw["appId"]
    last = _d(meta.get("steam")).get("lastRelease")
    if not isinstance(last, dict) or not last:
        return _set(s, "not_published", "Nenhum build foi enviado para a Steam ainda",
                    NOT_PUBLISHED_STEPS, ("build", "deliver"))
    s["store"] = {"version": last.get("versionName") or "", "build": "", "state": "",
                  "track": last.get("branch") or "", "date": last.get("at") or "",
                  "url": f"https://store.steampowered.com/app/{raw['appId']}"}
    _set(s, "ok")


def _run(key, enabled, body, meta, plats, blist):
    s = _new(key, enabled)
    local = ([], None)
    try:
        local = _local(blist, key)
        body(s, meta, plats, blist)
    except Exception as e:  # noqa — uma loja nunca derruba as outras
        _set(s, "error", str(e) or type(e).__name__)
    _finish(s, local)
    return s


def overview(project):
    d = _project_dir(project)
    meta = store.project_meta(project)
    plats = builds.detect_platforms(d, meta, project)
    blist = builds.list_builds(project, d)
    bodies = {"ios": _ios_body, "android": _android_body, "pc": _pc_body}
    out = {}
    with ThreadPoolExecutor(3) as ex:
        futs = {k: ex.submit(_run, k, plats[k]["enabled"], bodies[k], meta, plats, blist) for k in STORES}
        for k in STORES:
            try:
                out[k] = futs[k].result()
            except Exception as e:  # noqa
                s = _new(k, plats[k]["enabled"])
                _set(s, "error", str(e) or type(e).__name__)
                out[k] = s
    return {"project": project, "locales": project_locales(project), "catalog": catalog(), "stores": out}
