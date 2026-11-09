"""AI providers for writing App Store "What's New" text.

Two wire formats cover every provider:
  * OpenAI-compatible /chat/completions (OpenAI, Gemini, Mistral, Groq, DeepSeek,
    xAI, OpenRouter, Together, Ollama, LM Studio, any custom endpoint)
  * Anthropic /v1/messages
"""
import json
import urllib.error
import urllib.request

# kind: "openai" or "anthropic". local: runs on the user's PC (reached via host.docker.internal)
PROVIDERS = {
    "openai":     {"label": "OpenAI (ChatGPT)",   "kind": "openai",    "base": "https://api.openai.com/v1"},
    "anthropic":  {"label": "Anthropic (Claude)", "kind": "anthropic", "base": "https://api.anthropic.com/v1"},
    "gemini":     {"label": "Google Gemini",      "kind": "openai",    "base": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "mistral":    {"label": "Mistral",            "kind": "openai",    "base": "https://api.mistral.ai/v1"},
    "groq":       {"label": "Groq",               "kind": "openai",    "base": "https://api.groq.com/openai/v1"},
    "deepseek":   {"label": "DeepSeek",           "kind": "openai",    "base": "https://api.deepseek.com/v1"},
    "xai":        {"label": "xAI (Grok)",         "kind": "openai",    "base": "https://api.x.ai/v1"},
    "openrouter": {"label": "OpenRouter",         "kind": "openai",    "base": "https://openrouter.ai/api/v1"},
    "together":   {"label": "Together AI",        "kind": "openai",    "base": "https://api.together.xyz/v1"},
    "ollama":     {"label": "Ollama (local)",     "kind": "openai",    "base": "http://host.docker.internal:11434/v1", "local": True},
    "lmstudio":   {"label": "LM Studio (local)",  "kind": "openai",    "base": "http://host.docker.internal:1234/v1", "local": True},
    "custom":     {"label": "Outro (compatível com OpenAI)", "kind": "openai", "base": ""},
}


def _req(url, body=None, headers=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:600]
        raise ValueError(f"{e.code} da API: {msg}")
    except urllib.error.URLError as e:
        if "host.docker.internal" in url:
            raise ValueError(f"a IA local não respondeu em {url.rsplit('/', 1)[0]}. Ela está aberta no seu PC?")
        raise ValueError(f"não foi possível conectar em {url}: {e.reason}")


def _conf(cfg):
    p = PROVIDERS.get(cfg.get("provider"), PROVIDERS["custom"])
    base = (cfg.get("baseUrl") or p["base"]).rstrip("/")
    if not base:
        raise ValueError("informe a URL da API")
    return p, base


def _headers(p, cfg):
    key = cfg.get("apiKey", "")
    if p["kind"] == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    h = {"Authorization": f"Bearer {key}"} if key else {}
    if cfg.get("provider") == "openrouter":
        h.update({"X-Title": "xtool painel"})
    return h


def list_models(cfg):
    p, base = _conf(cfg)
    r = _req(base + "/models", headers=_headers(p, cfg), timeout=20)
    items = r.get("data") or r.get("models") or []
    ids = []
    for m in items:
        mid = m.get("id") or m.get("name") or ""
        if mid.startswith("models/"):
            mid = mid[7:]
        if mid:
            ids.append(mid)
    return sorted(set(ids))


def chat(cfg, system, user, max_tokens=1500):
    p, base = _conf(cfg)
    model = cfg.get("model")
    if not model:
        raise ValueError("escolha um modelo")
    if p["kind"] == "anthropic":
        r = _req(base + "/messages", {
            "model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}],
        }, _headers(p, cfg))
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text").strip()
    r = _req(base + "/chat/completions", {
        "model": model, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }, _headers(p, cfg))
    return (r.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()


LANG_NAMES = {"pt-BR": "português do Brasil", "pt-PT": "português de Portugal",
              "en-US": "inglês (EUA)", "en-GB": "inglês (Reino Unido)", "es-ES": "espanhol",
              "es-MX": "espanhol (México)", "fr-FR": "francês", "de-DE": "alemão", "it": "italiano",
              "ja": "japonês", "ko": "coreano", "zh-Hans": "chinês simplificado",
              "zh-Hant": "chinês tradicional", "ru": "russo", "nl-NL": "holandês", "tr": "turco",
              "ar-SA": "árabe", "hi": "hindi", "id": "indonésio", "pl": "polonês", "sv": "sueco",
              "th": "tailandês", "vi": "vietnamita"}


def whats_new(cfg, app_name, version, changes, locale="pt-BR", tone="", extra=""):
    lang = LANG_NAMES.get(locale, locale)
    system = (
        "Você escreve o texto \"O que há de novo\" (What's New) de atualizações na App Store. "
        "Escreva para o usuário final, não para programadores: nada de nomes de arquivos, commits, "
        "refatorações ou detalhes técnicos internos. Seja claro, curto e positivo. Use no máximo "
        "6 itens com marcadores \"•\". Não invente funcionalidades que não estão nas mudanças. "
        "Responda somente com o texto final, sem título e sem comentários. Máximo de 3500 caracteres."
    )
    user = (f"App: {app_name}\nVersão: {version}\nIdioma da resposta: {lang}\n"
            + (f"Tom: {tone}\n" if tone else "")
            + (f"Observações do desenvolvedor: {extra}\n" if extra else "")
            + f"\nMudanças desde a última versão:\n{changes[:12000]}")
    return chat(cfg, system, user)[:4000]


# Limites de caracteres por loja e campo (contrato "Campos"; a App Store e o Google Play cortam acima disso).
LIMITS = {
    "ios": {"whatsNew": 4000, "promotionalText": 170, "description": 4000, "keywords": 100, "subtitle": 30},
    "android": {"whatsNew": 500, "shortDescription": 80, "fullDescription": 4000},
}

_FIELD_HINTS = {
    "whatsNew": "o que há de novo nesta versão, em itens com \"•\", a partir de changes e extra",
    "promotionalText": "texto promocional curto e chamativo, sem promessas que o app não cumpre",
    "description": "descrição da ficha da App Store, em parágrafos curtos",
    "keywords": "palavras-chave separadas por vírgula, sem espaço depois da vírgula, sem repetir o nome do app",
    "subtitle": "subtítulo curto da ficha da App Store",
    "shortDescription": "descrição curta da ficha do Google Play, uma frase",
    "fullDescription": "descrição completa da ficha do Google Play, em parágrafos curtos",
}

_SYSTEM_BASE = (
    "Você escreve textos de ficha de app para lojas (App Store e Google Play). "
    "Escreva para o público final, não para programadores: nada de nomes de arquivos, commits, "
    "refatorações ou detalhes técnicos internos. Use tom claro, direto e positivo. "
    "Não invente funcionalidades: use somente o que estiver em changes, extra e nos textos atuais. "
    "Quando houver textos atuais, mantenha a identidade (nome, termos e tom) e mude só o necessário. "
    "Respeite o limite de caracteres de cada campo. "
    "Escreva a resposta no idioma indicado pelo usuário. "
    "Responda SOMENTE com um objeto JSON, sem cercas de código e sem comentários, "
    "com exatamente as chaves pedidas, no formato {\"campo\": \"texto\", ...}."
)


def _extract_json(texto):
    """Extrai o primeiro objeto JSON da resposta, tolerando cercas ```json e texto em volta."""
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("a IA devolveu uma resposta vazia")
    partes = texto.split("```")
    # Conteúdo entre cercas (posições ímpares) vem antes do texto inteiro.
    candidatos = [partes[i] for i in range(1, len(partes), 2)] + [texto]
    decoder = json.JSONDecoder(strict=False)
    for trecho in candidatos:
        pos = trecho.find("{")
        if pos == -1:
            continue
        try:
            obj, _ = decoder.raw_decode(trecho, pos)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("a IA não devolveu um JSON válido")


def _fit(field, text, limit):
    """Ajusta o texto ao limite do campo sem deixar espaços sobrando."""
    texto = str(text or "").strip()
    if field == "keywords":
        partes = [p.strip() for p in texto.split(",")]
        texto = ",".join(p for p in partes if p)
        if len(texto) <= limit:
            return texto
        corte = texto[:limit]
        virgula = corte.rfind(",")
        if virgula > 0:
            corte = corte[:virgula]
        return corte.rstrip(" ,")
    if len(texto) <= limit:
        return texto
    if texto[limit].isspace():
        return texto[:limit].rstrip()
    corte = texto[:limit]
    espaco = max(corte.rfind(" "), corte.rfind("\n"))
    if espaco > 0:
        corte = corte[:espaco]
    return corte.rstrip()


def generate_listing(cfg, store, app_name, version, locales, fields, current, changes="", extra=""):
    """Gera textos de ficha por idioma. Devolve {"results": {locale: {field: text}}, "errors": {locale: msg}}.

    Uma chamada de chat por idioma. Erro num idioma vai para errors e os outros continuam;
    se todos falharem, levanta ValueError com a primeira mensagem.
    """
    if store not in LIMITS:
        raise ValueError(f"loja desconhecida: {store}")
    limites = LIMITS[store]
    campos = []
    for f in fields or []:
        if f in limites and f not in campos:
            campos.append(f)
    if not campos:
        raise ValueError("nenhum campo válido para gerar nesta loja")
    idiomas = []
    for loc in locales or []:
        if loc and loc not in idiomas:
            idiomas.append(loc)
    if not idiomas:
        raise ValueError("escolha ao menos um idioma")
    if not isinstance(current, dict):
        current = {}

    loja = "App Store" if store == "ios" else "Google Play"
    regras = "\n".join(f"- {f}: até {limites[f]} caracteres. {_FIELD_HINTS[f]}" for f in campos)
    resultados, erros = {}, {}
    for loc in idiomas:
        try:
            lang = LANG_NAMES.get(loc, loc)
            atual_loc = current.get(loc) if isinstance(current.get(loc), dict) else {}
            atual = {f: atual_loc[f] for f in campos
                     if isinstance(atual_loc.get(f), str) and atual_loc[f].strip()}
            user = (f"App: {app_name}\nVersão: {version}\nLoja: {loja}\n"
                    f"Idioma da resposta: {lang} (locale {loc})\n"
                    f"Campos a gerar (JSON com exatamente estas chaves):\n{regras}\n")
            if atual:
                user += ("\nTextos atuais na loja neste idioma:\n"
                         + json.dumps(atual, ensure_ascii=False, indent=1) + "\n")
            if extra:
                user += f"\nObservações do desenvolvedor: {extra}\n"
            if changes:
                user += f"\nMudanças desde a última versão:\n{changes[:12000]}\n"
            texto = chat(cfg, _SYSTEM_BASE, user, max_tokens=2500)
            dados = _extract_json(texto)
            out, faltam = {}, []
            for f in campos:
                v = dados.get(f)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    v = str(v)
                t = _fit(f, v, limites[f]) if isinstance(v, str) else ""
                if t:
                    out[f] = t
                else:
                    faltam.append(f)
            if not out:
                raise ValueError("a IA não devolveu nenhum dos campos pedidos")
            resultados[loc] = out
            if faltam:
                erros[loc] = "a IA não devolveu: " + ", ".join(faltam)
        except Exception as e:
            erros[loc] = str(e) or e.__class__.__name__
    if not resultados:
        raise ValueError(next(iter(erros.values()), "a IA não gerou nenhum texto"))
    return {"results": resultados, "errors": erros}
