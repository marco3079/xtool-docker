"""Notificações do painel: navegador, Telegram, Discord e e-mail.

Configuração não secreta em notify.json; segredos em secrets.json (chave "notify"),
gravados com modo 600 e nunca devolvidos inteiros ao navegador.
"""
import json
import os
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from email.message import EmailMessage

import store

NOTIFY = os.path.join(store.PANEL_DIR, "notify.json")
TIMEOUT = 15
CHANNELS = ("browser", "telegram", "discord", "email")
EXTERNAL = ("telegram", "discord", "email")
SECRET_KEYS = ("telegramToken", "discordWebhook", "smtpPassword")
SECURITY = ("starttls", "ssl", "none")
DISCORD_PREFIXES = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
EVENT_LABELS = {
    "job_ok": "Build/envio concluído",
    "job_fail": "Build/envio com erro",
    "store_change": "Mudança de estado na loja",
    "store_rejected": "App rejeitado",
    "panel_update": "Atualização do painel disponível",
    "review_new": "Nova avaliação na loja",
}
_EMAIL_RE = re.compile(r"[^@\s,]+@[^@\s,]+")

_lock = threading.RLock()
EVENTS = deque(maxlen=200)
_seq = 0
_last_errors = {c: "" for c in CHANNELS}


# ---- configuração ----
def _defaults():
    return {"channels": {"browser": {"enabled": True},
                         "telegram": {"enabled": False, "chatId": ""},
                         "discord": {"enabled": False},
                         "email": {"enabled": False, "host": "", "port": 587, "security": "starttls",
                                   "user": "", "from": "", "to": ""}},
            "events": {k: True for k in EVENT_LABELS}}


def _config():
    cfg = _defaults()
    raw = store.load(NOTIFY, {})
    raw = raw if isinstance(raw, dict) else {}
    rch = raw.get("channels") if isinstance(raw.get("channels"), dict) else {}
    for name, fields in cfg["channels"].items():
        src = rch.get(name) if isinstance(rch.get(name), dict) else {}
        for k in fields:
            if k in src:
                fields[k] = src[k]
    rev = raw.get("events") if isinstance(raw.get("events"), dict) else {}
    for k in cfg["events"]:
        if k in rev:
            cfg["events"][k] = bool(rev[k])
    return cfg


def _secrets():
    s = store.secrets()
    n = s.get("notify") if isinstance(s.get("notify"), dict) else {}
    return {k: str(n.get(k) or "") for k in SECRET_KEYS}


def config_public():
    with _lock:
        cfg = _config()
        sec = _secrets()
        ch = cfg["channels"]
        channels = {
            "browser": dict(ch["browser"]),
            "telegram": {**ch["telegram"], "token": store.mask(sec["telegramToken"])},
            "discord": {**ch["discord"], "webhook": store.mask(sec["discordWebhook"])},
            "email": {**ch["email"], "password": store.mask(sec["smtpPassword"])},
        }
        return {"channels": channels,
                "events": dict(cfg["events"]),
                "eventLabels": dict(EVENT_LABELS),
                "lastErrors": dict(_last_errors)}


def _port(v):
    try:
        p = int(v)
    except (TypeError, ValueError):
        raise ValueError("porta inválida (use um número de 1 a 65535)")
    if not 1 <= p <= 65535:
        raise ValueError("porta inválida (use um número de 1 a 65535)")
    return p


def _clean_field(key, v):
    if key == "enabled":
        return bool(v)
    if key == "port":
        return _port(v)
    if key == "security":
        if v not in SECURITY:
            raise ValueError("segurança do e-mail inválida (use STARTTLS, SSL ou nenhuma)")
        return v
    if key == "from":
        s = "" if v is None else str(v).strip()
        if s and not _EMAIL_RE.fullmatch(s):
            raise ValueError("remetente inválido: informe um e-mail válido")
        return s
    if key == "to":
        s = "" if v is None else str(v).strip()
        parts = [p.strip() for p in s.split(",") if p.strip()]
        for p in parts:
            if not _EMAIL_RE.fullmatch(p):
                raise ValueError(f"destinatário inválido: {p}")
        return ", ".join(parts)
    return "" if v is None else str(v).strip()


def config_save(body):
    if not isinstance(body, dict):
        raise ValueError("dados inválidos")
    with _lock:
        cfg = _config()
        sec = _secrets()
        channels = body.get("channels")
        if channels is not None:
            if not isinstance(channels, dict):
                raise ValueError("configuração de canais inválida")
            for name, vals in channels.items():
                if name not in CHANNELS or not isinstance(vals, dict):
                    continue
                dst = cfg["channels"][name]
                for k, v in vals.items():
                    if k in dst:
                        dst[k] = _clean_field(k, v)
        events = body.get("events")
        if events is not None:
            if not isinstance(events, dict):
                raise ValueError("configuração de eventos inválida")
            for k, v in events.items():
                if k in cfg["events"]:
                    cfg["events"][k] = bool(v)
        secrets_in = body.get("secrets")
        if secrets_in is not None:
            if not isinstance(secrets_in, dict):
                raise ValueError("segredos inválidos")
            for k in SECRET_KEYS:
                if k not in secrets_in or secrets_in[k] == "":
                    continue  # ausente ou vazio: mantém o que já está salvo
                if secrets_in[k] is None:
                    sec[k] = ""  # null: apaga
                    continue
                if not isinstance(secrets_in[k], str):
                    raise ValueError("segredo inválido (texto esperado)")
                v = secrets_in[k].strip()
                if not v:
                    continue
                if k == "discordWebhook" and not v.startswith(DISCORD_PREFIXES):
                    raise ValueError("URL do webhook do Discord inválida "
                                     "(deve começar com https://discord.com/api/webhooks/)")
                sec[k] = v
        store.save(NOTIFY, cfg)
        s = store.secrets()
        s["notify"] = sec
        store.save(store.SECRETS, s, private=True)


# ---- envio ----
def _ready(ch, cfg, sec, need_enabled):
    c = cfg["channels"][ch]
    if need_enabled and not c.get("enabled"):
        return False
    if ch == "telegram":
        return bool(sec["telegramToken"] and c["chatId"])
    if ch == "discord":
        return bool(sec["discordWebhook"])
    if ch == "email":
        return bool(c["host"] and c["to"] and (c["from"] or c["user"]))
    return False


def _json_or_empty(raw):
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _send_telegram(c, sec, title, text, url):
    msg = f"{title}\n{text}" + (f"\n{url}" if url else "")
    body = json.dumps({"chat_id": c["chatId"], "text": msg,
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{sec['telegramToken']}/sendMessage",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = _json_or_empty(r.read())
    if data.get("ok") is False:
        raise RuntimeError(f"Telegram recusou: {data.get('description') or 'erro desconhecido'}")


def _send_discord(c, sec, title, text, url):
    content = f"**{title}**\n{text}"[:1900] + (f"\n{url}" if url else "")
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(sec["discordWebhook"], data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": "xtool-painel"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        r.read()


def _send_email(c, sec, title, text, url):
    msg = EmailMessage()
    msg["Subject"] = f"[xtool Painel] {title}"
    msg["From"] = c["from"] or c["user"]
    msg["To"] = c["to"]
    msg.set_content(text + (f"\n\n{url}" if url else ""))
    ctx = ssl.create_default_context()
    port = int(c["port"])
    if c["security"] == "ssl":
        smtp = smtplib.SMTP_SSL(c["host"], port, timeout=TIMEOUT, context=ctx)
    else:
        smtp = smtplib.SMTP(c["host"], port, timeout=TIMEOUT)
    with smtp as s:
        if c["security"] == "starttls":
            s.starttls(context=ctx)
        if c["user"]:
            s.login(c["user"], sec["smtpPassword"])
        s.send_message(msg)


def _send(ch, cfg, sec, title, text, url):
    c = cfg["channels"][ch]
    if ch == "telegram":
        _send_telegram(c, sec, title, text, url)
    elif ch == "discord":
        _send_discord(c, sec, title, text, url)
    elif ch == "email":
        _send_email(c, sec, title, text, url)


def _friendly(e, sec):
    if isinstance(e, urllib.error.HTTPError):
        detail = ""
        try:
            d = _json_or_empty(e.read())
            detail = d.get("description") or d.get("message") or ""
        except Exception:
            pass
        msg = f"HTTP {e.code}" + (f": {detail}" if detail else "")
    elif isinstance(e, urllib.error.URLError):
        msg = f"não foi possível conectar ({e.reason})"
    elif isinstance(e, smtplib.SMTPAuthenticationError):
        msg = "login recusado pelo servidor (no Gmail use uma senha de app)"
    elif isinstance(e, TimeoutError):
        msg = f"tempo esgotado ({TIMEOUT} s)"
    elif isinstance(e, smtplib.SMTPException):
        msg = f"servidor SMTP: {e}"
    elif isinstance(e, OSError):
        msg = f"falha de rede: {e}"
    else:
        msg = str(e) or type(e).__name__
    # nunca deixar segredo aparecer em mensagem de erro
    for v in sec.values():
        if v and len(v) >= 6:
            msg = msg.replace(v, "•••")
    return msg[:240]


def _set_error(ch, msg):
    with _lock:
        _last_errors[ch] = msg


def _deliver(ch, cfg, sec, title, text, url):
    try:
        _send(ch, cfg, sec, title, text, url)
        _set_error(ch, "")
    except Exception as e:
        _set_error(ch, _friendly(e, sec))


def _push(event, label, title, text, url):
    global _seq
    with _lock:
        _seq += 1
        EVENTS.append({"id": _seq, "at": int(time.time()), "event": event, "label": label,
                       "title": title, "text": text, "url": url})


def emit(event, title, text, url=None):
    with _lock:
        cfg = _config()
        if not cfg["events"].get(event):
            return
        sec = _secrets()
        if cfg["channels"]["browser"]["enabled"]:
            _push(event, EVENT_LABELS.get(event, event), title, text, url)
    for ch in EXTERNAL:
        if _ready(ch, cfg, sec, need_enabled=True):
            threading.Thread(target=_deliver, args=(ch, cfg, sec, title, text, url), daemon=True).start()


def test(channel):
    if channel not in CHANNELS:
        return {"ok": False, "error": "canal desconhecido"}
    with _lock:
        cfg = _config()
        sec = _secrets()
        if channel == "browser":
            _push("test", "Teste", "Teste", "Teste do xtool Painel", None)
            return {"ok": True, "error": ""}
        if not _ready(channel, cfg, sec, need_enabled=False):
            return {"ok": False, "error": "Configure o canal antes de testar"}
    try:
        _send(channel, cfg, sec, "Teste", "Teste do xtool Painel", None)
    except Exception as e:
        err = _friendly(e, sec)
        _set_error(channel, err)
        return {"ok": False, "error": err}
    _set_error(channel, "")
    return {"ok": True, "error": ""}


def events_since(since_id):
    try:
        since = int(since_id)
    except (TypeError, ValueError):
        since = 0
    with _lock:
        return {"last": _seq, "events": [dict(e) for e in EVENTS if e["id"] > since]}
