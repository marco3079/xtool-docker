"""Acompanhamento das lojas em segundo plano (App Store e Google Play).

Consulta as lojas dos projetos com versão pendente ou em revisão (e por 24 h depois de qualquer
mudança), guarda o último retrato de cada loja em watch.json, registra o histórico e avisa pelo
notify.py. Uma thread daemon (start) faz as consultas; a varredura completa roda a cada 6 h e
também pode ser disparada na hora (run_once).

Limites: a Apple não informa o motivo da rejeição pela API (o aviso manda abrir o App Store
Connect), e o Google Play não informa se a release está "em análise" (só faixa e estado).
"""
import os
import sys
import threading
import time

import asc
import lojas
import selfupdate
import store

WATCH = os.path.join(store.PANEL_DIR, "watch.json")
DAY = 24 * 3600
SWEEP_EVERY = 6 * 3600
UPDATE_EVERY = 6 * 3600
TICK = 30            # segundos entre as verificações do loop
FIRST_SWEEP = 60     # primeira varredura completa, depois de iniciar o painel
DEFAULT_INTERVAL = 15
MIN_INTERVAL, MAX_INTERVAL = 5, 240
HISTORY_MAX = 30

REJECTED_STATES = {"REJECTED", "METADATA_REJECTED", "INVALID_BINARY"}
OK_STATES = {"READY_FOR_SALE", "completed"}
ANDROID_LABELS = {"draft": "rascunho", "inProgress": "em andamento", "halted": "pausada",
                  "completed": "concluída"}
ICON = {"ios": "🍎", "android": "▶"}

_file_lock = threading.RLock()   # leitura/gravação de watch.json (curta)
_run_lock = threading.Lock()     # uma consulta de cada vez
_start_lock = threading.Lock()
_started = False


# ---- arquivo ----
def _default():
    return {"intervalMin": DEFAULT_INTERVAL, "lastRun": 0, "lastSweep": 0,
            "notifiedPanelSha": "", "projects": {}}


def _read():
    d = store.load(WATCH, _default())
    if not isinstance(d, dict):
        d = _default()
    base = _default()
    base.update(d)
    if not isinstance(base.get("projects"), dict):
        base["projects"] = {}
    return base


def _write(data):
    store.save(WATCH, data)


def _set_field(field, value):
    with _file_lock:
        d = _read()
        d[field] = value
        _write(d)


def _pinfo(data, name):
    p = data["projects"].setdefault(name, {"activeUntil": 0, "stores": {}, "history": []})
    p.setdefault("activeUntil", 0)
    p.setdefault("stores", {})
    p.setdefault("history", [])
    return p


# ---- configuração ----
def config():
    with _file_lock:
        return {"intervalMin": int(_read().get("intervalMin") or DEFAULT_INTERVAL)}


def set_interval(minutes):
    msg = f"intervalo entre {MIN_INTERVAL} e {MAX_INTERVAL} minutos"
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        raise ValueError(msg)
    if not MIN_INTERVAL <= m <= MAX_INTERVAL:
        raise ValueError(msg)
    with _file_lock:
        d = _read()
        d["intervalMin"] = m
        _write(d)
    return {"intervalMin": m}


def touch(project):
    """Marca o projeto como acompanhado por 24 h (chamado depois de enviar ou promover)."""
    with _file_lock:
        d = _read()
        _pinfo(d, project)["activeUntil"] = time.time() + DAY
        _write(d)


# ---- retratos e diferenças ----
def _pick_live(s):
    return {"version": str(s.get("version") or ""), "build": str(s.get("build") or ""),
            "state": str(s.get("state") or ""), "track": str(s.get("track") or "")}


def _pick_pending(p):
    return {"version": str(p.get("version") or ""), "build": str(p.get("build") or ""),
            "state": str(p.get("state") or ""), "label": str(p.get("label") or ""),
            "track": str(p.get("track") or "")}


def snapshot(project):
    """Retrato das lojas iOS e Android.

    Entra a loja vinculada e consultada ('ok'); também entra a loja ainda não publicada
    ('not_published') quando há versão pendente (a 1ª versão em revisão precisa ser acompanhada).
    """
    ov = lojas.overview(project)
    now = time.time()
    out = {}
    for key in ("ios", "android"):
        s = (ov.get("stores") or {}).get(key)
        if not s:
            continue
        st = s.get("state")
        pend = s.get("pending")
        if st != "ok" and not (st == "not_published" and pend):
            continue
        live = s.get("store")
        out[key] = {"live": _pick_live(live) if live else None,
                    "pending": _pick_pending(pend) if pend else None,
                    "updatedAt": now}
    return out


def _ev(store_key, text, rejected=False):
    return {"at": time.time(), "store": store_key, "text": text, "rejected": bool(rejected)}


def _ios_diff(old, new, project):
    evs = []
    op, np_ = old.get("pending"), new.get("pending")
    nl = new.get("live") or {}
    if op and np_ and op["version"] == np_["version"]:
        if op["state"] != np_["state"]:
            rej = np_["state"] in REJECTED_STATES
            text = (f"🍎 {project} {np_['version']}: {asc.state_label(op['state'])} → "
                    f"{asc.state_label(np_['state'])}")
            if rej:
                text += " — veja o motivo no App Store Connect"
            evs.append(_ev("ios", text, rej))
    elif op and (np_ is None or np_["version"] != op["version"]):
        if nl.get("version") and nl["version"] == op["version"]:
            evs.append(_ev("ios", f"🍎 {project} {op['version']} está à venda"))
    if np_ and (op is None or op["version"] != np_["version"]):
        rej = np_["state"] in REJECTED_STATES
        text = f"🍎 {project} {np_['version']}: {asc.state_label(np_['state'])}"
        if rej:
            text += " — veja o motivo no App Store Connect"
        evs.append(_ev("ios", text, rej))
    return evs


def _android_state(p):
    st = p.get("state") or ""
    return ANDROID_LABELS.get(st, st)


def _android_diff(old, new, project):
    evs = []
    for part in ("live", "pending"):
        o, n = old.get(part), new.get(part)
        if not n:
            continue
        ver = n["version"] or (f"build {n['build']}" if n["build"] else "")
        track = f" ({n['track']})" if n["track"] else ""
        head = f"▶ {project} {ver}{track}"
        if not o:
            evs.append(_ev("android", f"{head}: {_android_state(n)}"))
        elif o["version"] == n["version"] and o["build"] == n["build"]:
            if o["state"] != n["state"] or o["track"] != n["track"]:
                evs.append(_ev("android", f"{head}: {_android_state(o)} → {_android_state(n)}"))
        else:
            # outra release nesta posição: diz o estado da nova
            evs.append(_ev("android", f"{head}: {_android_state(n)}"))
    return evs


def diff(old, new, store_key, project):
    """Eventos entre dois retratos de uma loja. Primeira vez (old None) não gera evento."""
    if not old or not new:
        return []
    if store_key == "ios":
        return _ios_diff(old, new, project)
    if store_key == "android":
        return _android_diff(old, new, project)
    return []


def is_active(pinfo, now=None):
    now = time.time() if now is None else now
    if not pinfo:
        return False
    if float(pinfo.get("activeUntil") or 0) > now:
        return True
    return any((s or {}).get("pending") for s in (pinfo.get("stores") or {}).values())


# ---- notificação ----
def _emit(event, title, text):
    try:
        import notify  # tardio: o notify pode falhar sem bloquear a consulta
    except Exception:
        return
    try:
        notify.emit(event, title, text)
    except Exception:
        pass


def _emit_event(ev):
    _emit("store_rejected" if ev["rejected"] else "store_change", "Lojas", ev["text"])


# ---- consulta ----
def run_once(force_project=None, sweep=False):
    """Consulta lojas: um projeto (force_project), todos (sweep) ou só os acompanhados."""
    with _run_lock:
        names_all = list(store.projects().keys())
        if force_project:
            names = [force_project] if force_project in names_all else []
        elif sweep:
            names = names_all
        else:
            with _file_lock:
                d = _read()
            now = time.time()
            names = [n for n in names_all if is_active(d["projects"].get(n), now)]

        checked, total = [], 0
        for name in names:
            checked.append(name)
            try:
                new = snapshot(name)
                evs = []
                with _file_lock:
                    d = _read()
                    p = _pinfo(d, name)
                    for key in ("ios", "android"):
                        if key not in new:
                            continue  # loja não consultada agora: mantém o retrato anterior
                        evs += diff(p["stores"].get(key), new[key], key, name)
                        p["stores"][key] = new[key]
                    if evs:
                        p["history"] = (list(reversed(evs)) + p["history"])[:HISTORY_MAX]
                        p["activeUntil"] = time.time() + DAY
                    _write(d)
                for ev in evs:
                    _emit_event(ev)
                total += len(evs)
            except Exception as e:  # noqa — um projeto não derruba os outros
                sys.stderr.write(f"watch: {name}: {e}\n")
        return {"checked": checked, "events": total}


# ---- selos e painel ----
def _tone(state, rejected):
    if rejected or state in REJECTED_STATES:
        return "bad"
    if state in OK_STATES:
        return "ok"
    return "warn"


def _label(store_key, state):
    if store_key == "android":
        return ANDROID_LABELS.get(state, state or "")
    return asc.state_label(state)


def _badges(pinfo, now):
    out = []
    for key in ("ios", "android"):
        snap = (pinfo.get("stores") or {}).get(key)
        if not snap:
            continue
        recent = [e for e in pinfo.get("history") or []
                  if e.get("store") == key and now - float(e.get("at") or 0) < DAY]
        rejected = any(e.get("rejected") for e in recent)
        pend, live = snap.get("pending"), snap.get("live")
        if pend:
            ver = pend.get("version") or (f"build {pend['build']}" if pend.get("build") else "")
            state = pend.get("state") or ""
        elif recent and live:
            ver = live.get("version") or ""
            state = live.get("state") or ""
        else:
            continue
        text = f"{ICON[key]} {ver} · {_label(key, state)}"
        out.append({"store": key, "text": text, "tone": _tone(state, rejected)})
    return out


def badge(project):
    """Selos do card do projeto (por loja com versão pendente ou mudança nas últimas 24 h)."""
    with _file_lock:
        pinfo = _read()["projects"].get(project) or {}
    return _badges(pinfo, time.time())


def public():
    now = time.time()
    with _file_lock:
        d = _read()
    names = set(store.projects().keys())
    projects = {}
    for name, pinfo in d["projects"].items():
        if name not in names:
            continue
        projects[name] = {"active": is_active(pinfo, now), "badges": _badges(pinfo, now),
                          "history": list(pinfo.get("history") or [])}
    return {"intervalMin": int(d.get("intervalMin") or DEFAULT_INTERVAL),
            "lastRun": d.get("lastRun", 0), "lastSweep": d.get("lastSweep", 0), "projects": projects}


# ---- loop em segundo plano ----
def _check_update(version):
    res = selfupdate.check(version)
    latest = res.get("latest")
    if res.get("upToDate") or res.get("error") or not latest:
        return
    sha = latest.get("sha") or ""
    with _file_lock:
        if sha == _read().get("notifiedPanelSha"):
            return
    _emit("panel_update", "Painel",
          f"Atualização do painel disponível: v{latest.get('version') or '?'} ({latest.get('short')}) — "
          f"{latest.get('message')}")
    _set_field("notifiedPanelSha", sha)


def _loop(version):
    started = time.time()
    first_sweep_done = False
    next_update = started + FIRST_SWEEP
    while True:
        try:
            now = time.time()
            d = _read()
            if now - float(d.get("lastRun") or 0) >= int(d.get("intervalMin") or DEFAULT_INTERVAL) * 60:
                run_once()
                _set_field("lastRun", time.time())
            d = _read()
            due = now - float(d.get("lastSweep") or 0) >= SWEEP_EVERY
            if not first_sweep_done and now - started >= FIRST_SWEEP:
                due = True
            if due:
                run_once(sweep=True)
                first_sweep_done = True
                _set_field("lastSweep", time.time())
            if now >= next_update:
                next_update = now + UPDATE_EVERY
                _check_update(version)
        except Exception as e:  # noqa — o loop nunca morre
            sys.stderr.write(f"watch: {e}\n")
        time.sleep(TICK)


def start(version):
    """Inicia UMA thread daemon de acompanhamento (chamadas repetidas não fazem nada)."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_loop, args=(version,), name="watch", daemon=True)
    t.start()
