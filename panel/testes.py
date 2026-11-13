"""Aba Testes do painel: TestFlight (iOS) e faixas de teste do Google Play (Android).

Usa os métodos de asc.ASC (grupos, testadores, builds, revisão beta) e de play.Play (faixas de
teste e Google Groups). Erros da API seguem como asc.AscError / play.PlayError / lojas.LojasError;
erros de validação são ValueError com mensagem em português (o servidor responde 400).

Nada aqui publica o app: a promoção entre faixas fica em lojas (/api/lojas/promote).
"""
import re
from concurrent.futures import ThreadPoolExecutor

import ai
import asc
import lojas
import play

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WHAT_TO_TEST_MAX = 4000   # "O que testar" por idioma (App Store Connect)
AI_TEXT_MAX = 600         # limite pedido à IA por idioma
OVERVIEW_WORKERS = 6
# campos da ficha de revisão beta que o painel envia (o id não é enviado)
DETAIL_FIELDS = ("contactFirstName", "contactLastName", "contactPhone", "contactEmail",
                 "demoAccountRequired", "demoAccountName", "demoAccountPassword", "notes")
CONTACT_REQUIRED = (("contactFirstName", "nome de contato"), ("contactLastName", "sobrenome de contato"),
                    ("contactPhone", "telefone de contato"), ("contactEmail", "e-mail de contato"))

SYSTEM_WTT = (
    "Você escreve o texto \"O que testar\" de builds de teste do TestFlight. "
    "Os testadores leem o texto: diga, de forma curta e direta, o que mudou nesta versão e o que vale testar. "
    "Escreva para o usuário final, não para programadores: nada de nomes de arquivos, commits ou detalhes "
    "técnicos internos. Não invente funcionalidades: use somente o que estiver nas mudanças e nas observações. "
    "Escreva cada texto no idioma indicado para a sua chave. "
    "Cada texto tem no máximo 600 caracteres. "
    "Responda SOMENTE com um objeto JSON, sem cercas de código e sem comentários, com uma chave por idioma "
    "e o texto como valor."
)


# ---- helpers ----
def _id(valor, nome):
    s = str(valor or "").strip()
    if not s:
        raise ValueError(f"informe {nome}")
    return s


def _itens(valor):
    """Textos separados por vírgula, ponto e vírgula ou quebra de linha (ou uma lista). Sem repetidos."""
    if valor is None:
        return []
    if isinstance(valor, str):
        brutos = [valor]
    elif isinstance(valor, (list, tuple)):
        brutos = [str(x) for x in valor if x is not None]
    else:
        raise ValueError("lista inválida")
    out, vistos = [], set()
    for bruto in brutos:
        for parte in re.split(r"[,;\r\n]+", bruto):
            p = parte.strip()
            if p and p.lower() not in vistos:
                vistos.add(p.lower())
                out.append(p)
    return out


def _corta(texto, limite):
    """Corta o texto no limite, preferindo a última palavra inteira."""
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    espaco = corte.rfind(" ")
    if espaco > 0:
        corte = corte[:espaco]
    return corte.rstrip()


def _ios_api(project):
    """(cliente App Store Connect, vínculo iOS) do projeto."""
    link = lojas.link(project, "ios")
    return lojas.asc_client(link["accountId"]), link


def _ios(project):
    """(cliente App Store Connect, id do app na Apple) do projeto."""
    api, link = _ios_api(project)
    return api, api.app_by_bundle(link["bundleId"])["id"]


def _grupo(api, app_id, gid):
    for g in api.beta_groups(app_id):
        if g.get("id") == gid:
            return g
    raise ValueError("grupo de testadores não encontrado neste app")


def _recusa_grupo(interno, detalhe):
    if not interno:
        return detalhe
    return ("o grupo interno só aceita quem já é usuário da equipe no App Store Connect "
            "(para outras pessoas, use um grupo externo). Detalhe da Apple: " + detalhe)


# ---- iOS: TestFlight ----
def _seguro(fn, vazio, contexto):
    """Roda fn; se falhar, devolve o valor vazio e o aviso em português."""
    try:
        return fn(), None
    except Exception as e:  # noqa — falha parcial: a tela continua
        return vazio, f"{contexto}: {e}"


def ios_overview(project):
    """Grupos (com testadores), builds (com "O que testar" e revisão beta), ficha de revisão e informações beta.

    Falha numa chamada auxiliar (testadores de um grupo, "O que testar" ou revisão de um build) não derruba
    a tela: vira vazio e a mensagem entra em "warnings". Falha em beta_groups/beta_builds continua lançando.
    """
    api, app_id = _ios(project)
    locales = lojas.project_locales(project)
    loc0 = locales[0]
    grupos = api.beta_groups(app_id)
    builds = api.beta_builds(app_id, limit=15)

    def testers_de(g):
        return _seguro(lambda: api.beta_testers(g["id"]), [],
                       f"testadores do grupo {g.get('name') or g.get('id')}")

    def extras_de(b):
        nome = b.get("version") or b["id"]
        wtt, a1 = _seguro(lambda: api.what_to_test(b["id"]), {}, f"\"O que testar\" do build {nome}")
        rev, a2 = _seguro(lambda: api.beta_review_status(b["id"]), {"state": "", "id": None},
                          f"revisão beta do build {nome}")
        return wtt, rev, [a for a in (a1, a2) if a]

    with ThreadPoolExecutor(OVERVIEW_WORKERS) as ex:
        testers = list(ex.map(testers_de, grupos))
        extras = list(ex.map(extras_de, builds))
    warnings = []
    for g, (t, aviso) in zip(grupos, testers):
        g["testers"] = t
        if aviso:
            warnings.append(aviso)
    labels = asc.BETA_REVIEW_LABELS
    for b, (wtt, rev, avisos) in zip(builds, extras):
        b["whatToTest"] = str(((wtt or {}).get(loc0) or {}).get("text") or "")
        b["review"] = rev or {"state": "", "id": None}
        estado = b["review"].get("state") or ""
        b["reviewLabel"] = labels.get(estado, estado)
        warnings.extend(avisos)
    return {"groups": grupos, "builds": builds,
            "reviewDetails": api.beta_review_details(app_id),
            "betaInfo": api.beta_app_info(app_id),
            "locales": locales, "warnings": warnings}


def ios_create_group(project, name, internal):
    nome = str(name or "").strip()
    if not nome:
        raise ValueError("informe o nome do grupo")
    api, app_id = _ios(project)
    return api.create_beta_group(app_id, nome, internal=bool(internal))


def ios_public_link(project, group_id, enabled, limit=None):
    gid = _id(group_id, "o grupo")
    lim = None
    if limit not in (None, ""):
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            raise ValueError("o limite do link precisa ser um número inteiro") from None
        if lim < 1:
            raise ValueError("o limite do link precisa ser maior que zero")
    api, _ = _ios_api(project)
    return api.set_public_link(gid, bool(enabled), limit=lim)


def ios_add_testers(project, group_id, emails):
    """Adiciona testadores por e-mail. Devolve {"added": [e-mails], "errors": [{"email","error"}]}."""
    gid = _id(group_id, "o grupo")
    lista = _itens(emails)
    if not lista:
        raise ValueError("informe ao menos um e-mail")
    api, app_id = _ios(project)
    interno = bool(_grupo(api, app_id, gid).get("internal"))
    added, errors = [], []
    for email in lista:
        if not EMAIL_RE.match(email):
            errors.append({"email": email, "error": "e-mail inválido"})
            continue
        try:
            api.add_beta_tester(gid, email)
        except asc.AscError as e:
            errors.append({"email": email, "error": _recusa_grupo(interno, str(e))})
            continue
        added.append(email)
    return {"added": added, "errors": errors}


def ios_remove_tester(project, group_id, tester_id):
    gid = _id(group_id, "o grupo")
    tid = _id(tester_id, "o testador")
    api, _ = _ios_api(project)
    api.remove_beta_tester(gid, tid)
    return {"ok": True}


def ios_add_build(project, group_id, build_id):
    gid = _id(group_id, "o grupo")
    bid = _id(build_id, "o build")
    api, _ = _ios_api(project)
    api.add_build_to_group(gid, bid)
    return {"ok": True}


def ios_set_what_to_test(project, build_id, texts):
    """Grava o "O que testar" por idioma. Idiomas com texto vazio não são alterados."""
    bid = _id(build_id, "o build")
    if not isinstance(texts, dict):
        raise ValueError("textos do \"O que testar\" inválidos")
    limpos = {}
    for loc, txt in texts.items():
        cod = str(loc or "").strip()
        t = str(txt or "").strip()
        if not cod:
            continue
        if len(t) > WHAT_TO_TEST_MAX:
            raise ValueError(f"o texto \"O que testar\" em {cod} passa de {WHAT_TO_TEST_MAX} caracteres")
        if t:
            limpos[cod] = t
    if not limpos:
        raise ValueError("escreva o texto \"O que testar\" em ao menos um idioma")
    api, _ = _ios_api(project)
    for cod, t in limpos.items():
        api.set_what_to_test(bid, cod, t)
    return {"saved": list(limpos)}


def ios_what_to_test_ai(cfg, project, version, locales, changes, extra=""):
    """Rascunho do "O que testar" por idioma, pela IA. Não grava: a interface mostra e o usuário salva."""
    mudancas = str(changes or "").strip()
    obs = str(extra or "").strip()
    if not mudancas and not obs:
        raise ValueError("sem mudanças nem observações para escrever o texto")
    codigos = _itens(locales) or lojas.project_locales(project)
    if not codigos:
        raise ValueError("escolha ao menos um idioma")
    lista = "\n".join(f"- {c}: {ai.LANG_NAMES.get(c, c)}" for c in codigos)
    user = (f"App: {project}\nVersão: {version or ''}\n"
            f"Chaves do JSON (um texto por chave), com o idioma de cada uma:\n{lista}\n")
    if obs:
        user += f"\nObservações do desenvolvedor: {obs}\n"
    if mudancas:
        user += f"\nMudanças desde a última versão:\n{mudancas[:12000]}\n"
    texto = ai.chat(cfg, SYSTEM_WTT, user, max_tokens=2000)
    dados = ai._extract_json(texto)
    out = {}
    for c in codigos:
        v = dados.get(c)
        if v is None:
            v = next((val for k, val in dados.items() if str(k).lower() == c.lower()), None)
        if isinstance(v, str) and v.strip():
            out[c] = _corta(v.strip(), AI_TEXT_MAX)
    if not out:
        raise ValueError("a IA não devolveu o texto \"O que testar\" em nenhum idioma")
    return out


def ios_submit_beta_review(project, build_id, details=None, info=None):
    """Salva a ficha de revisão beta e as informações por idioma (se vierem) e envia o build à revisão.

    Confere antes de gravar: contato (nome, sobrenome, telefone, e-mail) e, em ao menos um idioma,
    descrição e e-mail de feedback.
    """
    bid = _id(build_id, "o build")
    if details is not None and not isinstance(details, dict):
        raise ValueError("dados de contato da revisão beta inválidos")
    if info is not None and not isinstance(info, dict):
        raise ValueError("informações do app para a revisão beta inválidas")
    api, app_id = _ios(project)

    atual = api.beta_review_details(app_id) or {}
    mudar = {}
    for k in DETAIL_FIELDS:
        if details and k in details:
            v = details[k]
            mudar[k] = v.strip() if isinstance(v, str) else v
    final = {**atual, **mudar}

    problemas = [rot for k, rot in CONTACT_REQUIRED if not str(final.get(k) or "").strip()]
    mail_contato = str(final.get("contactEmail") or "").strip()
    if mail_contato and not EMAIL_RE.match(mail_contato):
        problemas.append("e-mail de contato inválido")

    atual_info = api.beta_app_info(app_id) or {}
    novo = {}
    for loc, campos in (info or {}).items():
        if not isinstance(campos, dict):
            raise ValueError("informações do app para a revisão beta inválidas")
        cod = str(loc or "").strip()
        if not cod:
            continue
        base = atual_info.get(cod) if isinstance(atual_info.get(cod), dict) else {}
        novo[cod] = {
            "description": str(campos.get("description", base.get("description", "")) or "").strip(),
            "feedbackEmail": str(campos.get("feedbackEmail", base.get("feedbackEmail", "")) or "").strip(),
        }
    todos = {**atual_info, **novo}
    for cod, v in novo.items():
        if v["feedbackEmail"] and not EMAIL_RE.match(v["feedbackEmail"]):
            problemas.append(f"e-mail de feedback inválido em {cod}")
    completos = [c for c, v in todos.items() if isinstance(v, dict)
                 and str(v.get("description") or "").strip()
                 and EMAIL_RE.match(str(v.get("feedbackEmail") or "").strip())]
    if not completos:
        problemas.append("descrição e e-mail de feedback em ao menos um idioma")
    if problemas:
        raise ValueError("Antes de enviar à revisão beta, falta ou está errado: " + "; ".join(problemas))

    if mudar:
        did = str(atual.get("id") or "")
        if not did:
            raise ValueError("a Apple ainda não tem a ficha de revisão beta deste app: "
                             "preencha-a no App Store Connect e tente de novo")
        api.set_beta_review_details(did, mudar)
    for cod, v in novo.items():
        api.set_beta_app_info(app_id, cod, v["description"], v["feedbackEmail"])
    return api.submit_beta_review(bid)


# ---- Android: Google Play ----
def android_overview(project):
    """Faixas de teste (sem produção), com os Google Groups de cada uma, e o link para o testador entrar."""
    link = lojas.link(project, "android")
    pkg = link["packageName"]
    cli = lojas.play_client(link["accountId"])
    faixas = cli.test_tracks(pkg)
    for f in faixas:
        f["testers"] = cli.testers(pkg, f["track"])["googleGroups"]
    return {"tracks": faixas, "optInUrl": play.opt_in_url(pkg), "packageName": pkg}


def android_set_testers(project, track, groups):
    """Troca os Google Groups de testadores da faixa. Aceita texto com vírgulas ou linhas."""
    faixa = _id(track, "a faixa")
    lista = _itens(groups)
    link = lojas.link(project, "android")
    cli = lojas.play_client(link["accountId"])
    return cli.set_testers(link["packageName"], faixa, lista)
