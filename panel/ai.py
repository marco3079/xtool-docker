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


LANG_NAMES = {"pt-BR": "português do Brasil", "en-US": "inglês (EUA)", "es-ES": "espanhol",
              "es-MX": "espanhol (México)", "fr-FR": "francês", "de-DE": "alemão", "it": "italiano",
              "ja": "japonês", "zh-Hans": "chinês simplificado"}


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
