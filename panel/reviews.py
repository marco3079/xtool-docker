"""Avaliações das lojas (App Store e Google Play): busca, guarda, responde e avisa.

Cada projeto tem um arquivo em <PANEL_DIR>/reviews/<projeto>.json com as avaliações de cada loja,
a data da última busca, o erro da última busca (se houver) e os rascunhos de resposta.
A rede fica fora do lock; o lock protege só a leitura e a gravação do arquivo.

O Google Play devolve só as avaliações dos últimos 7 dias, então nada que já foi guardado é
apagado. O único corte é o excesso acima de 2000 itens por loja (sai sempre o mais antigo).
"""
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone

import ai
import lojas
import store

STORE_KEYS = ("ios", "android")
STORE_NAMES = {"ios": "App Store", "android": "Google Play"}
REPLY_MAX = {"ios": 5970, "android": 350}
REPLY_NOTE = {
    "ios": "App Store: a resposta tem no máximo 5970 caracteres. Responder de novo substitui a resposta anterior.",
    "android": "Google Play: a resposta tem no máximo 350 caracteres.",
}
MAX_ITEMS = 2000
POLL_FIRST = 120       # segundos depois de iniciar o painel
POLL_EVERY = 3600      # 60 min entre as buscas

SYSTEM = (
    "Você responde avaliações de um app na loja em nome do desenvolvedor. "
    "Responda no MESMO idioma da avaliação. Seja educado e específico ao que a pessoa disse, "
    "sem prometer datas nem recursos e sem inventar fatos. Agradeça os elogios. "
    "Em reclamação, reconheça o problema e diga o próximo passo (por exemplo, uma atualização "
    "ou o contato pelo suporte, se as orientações extras informarem um). "
    "Evite emojis em excesso. Escreva no máximo {limite} caracteres. "
    "Devolva SÓ o texto da resposta, sem aspas, título ou explicação."
)

_lock = threading.RLock()
_start_lock = threading.Lock()
_started = False


# ---- arquivo ----
def _check_store(store_key):
    if store_key not in STORE_KEYS:
        raise ValueError("loja desconhecida: use ios ou android")


def _file(project):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(project))
    return os.path.join(store.PANEL_DIR, "reviews", f"{safe}.json")


def _load(project):
    with _lock:
        d = store.load(_file(project), None)
    if not isinstance(d, dict):
        d = {}
    out = {"drafts": d["drafts"] if isinstance(d.get("drafts"), dict) else {}}
    for k in STORE_KEYS:
        s = d.get(k) if isinstance(d.get(k), dict) else {}
        out[k] = {"items": s["items"] if isinstance(s.get("items"), dict) else {},
                  "fetchedAt": s.get("fetchedAt") or 0,
                  "error": str(s.get("error") or "")}
    return out


def _save(project, data):
    with _lock:
        store.save(_file(project), data)


# ---- valores ----
def _iso(v):
    """Data para texto ISO 8601 (aceita epoch em segundos, texto ou vazio)."""
    if v is None or v == "" or isinstance(v, bool):
        return ""
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(v)


def _ts(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _rating(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return min(5, max(0, n))


def _resp(v):
    if not isinstance(v, dict) or not str(v.get("body") or "").strip():
        return None
    out = {"body": str(v.get("body")), "updatedAt": _iso(v.get("updatedAt"))}
    if v.get("id"):
        out["id"] = str(v["id"])
    if v.get("state"):
        out["state"] = str(v["state"])
    return out


LOCAL_KEEP = 600  # segundos: a resposta enviada pelo painel é mantida só por 10 min se a loja não a devolver


def _keep_local(resp, now):
    """Resposta enviada pelo painel (com localAt) ainda válida para não ser apagada pela busca; senão None."""
    if isinstance(resp, dict) and resp.get("localAt") and now - float(resp["localAt"]) < LOCAL_KEEP:
        return resp
    return None


def _norm(r, store_key, now, old):
    """Avaliação no formato guardado.

    Mantém seenAt. Se a loja devolver resposta, ela vence. Se não devolver, mantém a resposta
    enviada pelo painel só enquanto tiver localAt com menos de 10 min (a loja pode demorar a
    refletir o envio); depois disso vale o que a loja disser (sem resposta).
    """
    old = old or {}
    return {
        "id": str(r.get("id") or ""),
        "rating": _rating(r.get("rating")),
        "title": str(r.get("title") or ""),
        "body": str(r.get("body") or ""),
        "author": str(r.get("author") or ""),
        "territory": str(r.get("territory") or ""),
        "language": str(r.get("language") or ""),
        "appVersion": str(r.get("appVersion") or ""),
        "device": str(r.get("device") or ""),
        "createdAt": _iso(r.get("createdAt")),
        "response": _resp(r.get("response")) or _keep_local(old.get("response"), now),
        "store": store_key,
        "seenAt": old.get("seenAt") or now,
    }


def _avg(items):
    vals = [r.get("rating") or 0 for r in items]
    vals = [v for v in vals if 1 <= v <= 5]
    return round(sum(vals) / len(vals), 2) if vals else None


def _counts(items):
    by = {str(n): 0 for n in range(1, 6)}
    for r in items:
        rt = r.get("rating") or 0
        if 1 <= rt <= 5:
            by[str(rt)] += 1
    return {"total": len(items),
            "unanswered": sum(1 for r in items if not r.get("response")),
            "avg": _avg(items), "byStar": by}


def _trim(items):
    if len(items) <= MAX_ITEMS:
        return items
    keep = sorted(items.values(), key=lambda r: _ts(r.get("createdAt")), reverse=True)[:MAX_ITEMS]
    return {r["id"]: r for r in keep}


def _prune_drafts(d):
    live = {f"{k}:{rid}" for k in STORE_KEYS for rid in d[k]["items"]}
    d["drafts"] = {k: v for k, v in d["drafts"].items() if k in live}


def _stars_set(stars):
    if stars is None or stars == "":
        return set()
    vals = stars if isinstance(stars, (list, tuple, set)) else [stars]
    out = set()
    for v in vals:
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("estrelas devem ser de 1 a 5")
        if not 1 <= n <= 5:
            raise ValueError("estrelas devem ser de 1 a 5")
        out.add(n)
    return out


def _cut(text, limit):
    """Corta no limite sem quebrar palavra."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    sp = head.rfind(" ")
    if sp > limit // 2:
        head = head[:sp]
    return head.rstrip(" ,;:-")


# ---- busca ----
def _fetch(project, store_key):
    """Busca na loja e mescla no arquivo. Devolve contagens e as avaliações que chegaram agora."""
    _check_store(store_key)
    link = lojas.link(project, store_key)  # LojasError se a loja não está vinculada
    if store_key == "ios":
        api = lojas.asc_client(link["accountId"])
    else:
        play = lojas.play_client(link["accountId"])
    try:
        if store_key == "ios":
            app = api.app_by_bundle(link["bundleId"])
            if not app or not app.get("id"):
                raise lojas.LojasError("app não encontrado na App Store Connect")
            raw = api.customer_reviews(app["id"])
        else:
            raw = play.reviews(link["packageName"])
    except Exception as e:  # noqa — grava o erro da API e relança
        with _lock:
            d = _load(project)
            d[store_key]["error"] = str(e) or type(e).__name__
            _save(project, d)
        raise

    now = time.time()
    with _lock:
        d = _load(project)
        s = d[store_key]
        cur = s["items"]
        first = not s["fetchedAt"]
        new_items = []
        for r in raw or []:
            rid = str(r.get("id") or "")
            if not rid:
                continue
            old = cur.get(rid)
            item = _norm(r, store_key, now, old)
            if old is None:
                new_items.append(item)
            cur[rid] = item
        s["items"] = _trim(cur)
        s["fetchedAt"] = now
        s["error"] = ""
        _prune_drafts(d)
        _save(project, d)
    return {"new": len(new_items), "total": len(s["items"]), "newItems": new_items, "first": first}


def fetch(project, store_key):
    info = _fetch(project, store_key)
    return {"new": info["new"], "total": info["total"]}


# ---- leitura ----
def listing(project, store_key, only_unanswered=False, stars=None):
    _check_store(store_key)
    wanted = _stars_set(stars)
    d = _load(project)
    s = d[store_key]
    allitems = list(s["items"].values())
    rows = []
    for r in allitems:
        if only_unanswered and r.get("response"):
            continue
        if wanted and r.get("rating") not in wanted:
            continue
        row = dict(r)
        dr = d["drafts"].get(f"{store_key}:{r.get('id')}")
        if dr:
            row["draft"] = dr
        rows.append(row)
    rows.sort(key=lambda r: _ts(r.get("createdAt")), reverse=True)
    return {"items": rows, "fetchedAt": s["fetchedAt"], "error": s["error"],
            "counts": _counts(allitems),
            "limits": {"replyMax": REPLY_MAX[store_key], "note": REPLY_NOTE[store_key]}}


def summary(project):
    """Selo do card: sem rede. None = loja NÃO vinculada; vinculada sempre devolve um dict."""
    d = _load(project)
    out = {}
    for k in STORE_KEYS:
        try:
            lojas.link(project, k)  # só confere o vínculo (sem rede)
        except lojas.LojasError:
            out[k] = None
            continue
        s = d[k]
        items = list(s["items"].values())
        out[k] = {"unanswered": sum(1 for r in items if not r.get("response")),
                  "avg": _avg(items), "fetchedAt": s["fetchedAt"]}
    return out


# ---- rascunhos e resposta ----
def save_draft(project, store_key, review_id, text):
    _check_store(store_key)
    rid = str(review_id or "")
    text = (text or "").strip()
    key = f"{store_key}:{rid}"
    with _lock:
        d = _load(project)
        if rid not in d[store_key]["items"]:
            raise ValueError("avaliação não encontrada: atualize a lista")
        if text:
            d["drafts"][key] = text
        else:
            d["drafts"].pop(key, None)
        _save(project, d)
    return {"draft": text}


def _user_msg(project, store_key, item, extra):
    if store_key == "android":
        lang_line = f"Idioma: {item.get('language') or 'não informado'}"
    else:
        lang_line = f"Território: {item.get('territory') or 'não informado'}"
    lines = [
        f"App: {project}",
        f"Loja: {STORE_NAMES[store_key]}",
        f"Nota: {item.get('rating') or 0} de 5",
        f"Título: {item.get('title') or '(sem título)'}",
        f"Texto: {item.get('body') or '(sem texto)'}",
        lang_line,
        f"Versão do app: {item.get('appVersion') or 'não informada'}",
    ]
    if extra and str(extra).strip():
        lines.append(f"Orientações extras: {str(extra).strip()}")
    return "\n".join(lines)


def draft_ai(cfg, project, store_key, review_id, extra=""):
    _check_store(store_key)
    rid = str(review_id or "")
    with _lock:
        item = _load(project)[store_key]["items"].get(rid)
    if not item:
        raise ValueError("avaliação não encontrada: atualize a lista")
    limit = REPLY_MAX[store_key]
    system = SYSTEM.format(limite=limit)
    user = _user_msg(project, store_key, item, extra)
    raw = ai.chat(cfg, system, user, max_tokens=600 if store_key == "android" else 1500)
    text = _cut(str(raw or ""), limit)
    if not text:
        raise ValueError("a IA devolveu uma resposta vazia")
    save_draft(project, store_key, rid, text)
    return {"text": text}


def reply(project, store_key, review_id, text):
    _check_store(store_key)
    rid = str(review_id or "")
    text = (text or "").strip()
    limit = REPLY_MAX[store_key]
    if not text:
        raise ValueError("escreva a resposta antes de enviar")
    if len(text) > limit:
        raise ValueError(f"a resposta no {STORE_NAMES[store_key]} tem no máximo {limit} caracteres")
    with _lock:
        item = _load(project)[store_key]["items"].get(rid)
    if not item:
        raise ValueError("avaliação não encontrada: atualize a lista")

    link = lojas.link(project, store_key)
    now = time.time()
    if store_key == "ios":
        api = lojas.asc_client(link["accountId"])
        res = api.reply_review(rid, text) or {}
        resp = {"id": str(res.get("id") or ""), "body": str(res.get("body") or text),
                "state": str(res.get("state") or ""), "updatedAt": _iso(now), "localAt": now}
    else:
        play = lojas.play_client(link["accountId"])
        res = play.reply_review(link["packageName"], rid, text) or {}
        resp = {"body": str(res.get("body") or text),
                "updatedAt": _iso(res.get("updatedAt")) or _iso(now), "localAt": now}

    with _lock:
        d = _load(project)
        cur = d[store_key]["items"].get(rid) or item
        cur = {**cur, "response": resp}
        d[store_key]["items"][rid] = cur
        d["drafts"].pop(f"{store_key}:{rid}", None)
        _save(project, d)
    return cur


# ---- aviso e loop ----
def _notify(project, store_key, r):
    try:
        import notify  # tardio: falha do notify não pode travar a busca
    except Exception:
        return
    try:
        rating = _rating(r.get("rating"))
        icon = "🍎" if store_key == "ios" else "▶"
        stars = "★" * rating + "☆" * (5 - rating)
        body = str(r.get("body") or "").strip()[:120]
        notify.emit("review_new", "Avaliações", f"{icon} {project}: {stars} — {body}")
    except Exception:
        pass


def poll_all():
    """Busca as avaliações de todos os projetos com loja vinculada e avisa as que são novas."""
    out = {"projects": 0, "new": 0}
    for name in list(store.projects().keys()):
        for k in STORE_KEYS:
            try:
                info = _fetch(name, k)
            except lojas.LojasError:
                continue  # loja não vinculada ou sem chave: pula
            except Exception as e:  # noqa — um projeto não para os outros
                sys.stderr.write(f"reviews: {name} {k}: {e}\n")
                continue
            out["new"] += info["new"]
            if not info["first"]:  # primeira carga da loja não avisa
                for r in info["newItems"]:
                    _notify(name, k, r)
        out["projects"] += 1
    return out


def _loop():
    time.sleep(POLL_FIRST)
    while True:
        try:
            poll_all()
        except Exception as e:  # noqa — o loop nunca morre
            sys.stderr.write(f"reviews: {e}\n")
        time.sleep(POLL_EVERY)


def start():
    """Inicia UMA thread daemon de avaliações (chamadas repetidas não fazem nada)."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="reviews", daemon=True).start()
