"""Ler e gravar os textos e as imagens das lojas (App Store Connect e Google Play).

Usado pelas rotas /api/lojas/fields, /save, /image/upload e /image/delete do servidor.
Todos os idiomas que entram e saem daqui são os códigos estilo App Store; só aqui
se converte para os códigos do Google Play (lojas.play_lang / lojas.from_play_lang).
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

import ai
import asc
import lojas
import play

IOS_TEXT = ("whatsNew", "promotionalText", "description", "keywords")
IOS_INFO = ("subtitle",)
ANDROID_TEXT = ("shortDescription", "fullDescription")
ANDROID_NOTES = ("whatsNew",)
FIELDS = {
    "ios": IOS_TEXT + IOS_INFO,
    "android": ("whatsNew",) + ANDROID_TEXT,
}
PLAY_KINDS = [
    ("icon", "Ícone", "512×512"),
    ("featureGraphic", "Gráfico de recursos", "1024×500"),
    ("phoneScreenshots", "Capturas de tela (celular)", "16:9 ou 9:16, 320–3840 px"),
    ("sevenInchScreenshots", "Capturas (tablet 7\")", "16:9 ou 9:16, 320–3840 px"),
    ("tenInchScreenshots", "Capturas (tablet 10\")", "16:9 ou 9:16, 320–3840 px"),
]
NOTE_IOS = "Atualizar na loja não envia build nem submete a versão para revisão."
NOTE_ANDROID = ("Os textos do Google Play valem para a ficha inteira e são aplicados quando você atualizar; "
                "as notas valem só para a release escolhida")


def _nada(_msg=""):
    return None


class _erros:
    """Converte erros das APIs em LojasError (mensagens já estão em português)."""

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, tb):
        if isinstance(valor, (asc.AscError, play.PlayError)):
            raise lojas.LojasError(str(valor)) from None
        return False


# ---------------- validações ----------------
def _loja(store):
    if store == "pc":
        raise ValueError("a Steam não tem página editável pelo painel")
    if store not in ("ios", "android"):
        raise ValueError(f"loja desconhecida: {store}")


def _versao(version):
    if not str(version or "").strip():
        raise ValueError("escolha a versão")


def _idioma(locale):
    if locale not in {c["code"] for c in lojas.catalog()}:
        raise ValueError(f"idioma desconhecido: {locale}")


def _tipos(store):
    if store == "ios":
        return [k for k, _, _ in asc.SCREENSHOT_TYPES]
    return list(play.IMAGE_KINDS)


def _limites(store):
    return {f: ai.LIMITS[store][f] for f in FIELDS[store]}


def _codes(project, loja):
    codes = list(lojas.project_locales(project, extra=loja))
    for c in loja:
        if c not in codes:
            codes.append(c)
    return codes


# ---------------- App Store Connect ----------------
def _ios_ctx(project):
    ln = lojas.link(project, "ios")
    cli = lojas.asc_client(ln["accountId"])
    app = cli.app_by_bundle(ln["bundleId"])
    return cli, app["id"]


def _ios_versao(cli, app_id, version):
    for v in cli.app_versions(app_id):
        if v.get("versionString") == version:
            return v
    return None


def _ios_editavel(ver, version):
    if ver is None:
        return True, "A versão será criada na App Store ao atualizar"
    if ver["state"] in asc.ASC.EDITABLE:
        return True, ""
    return False, f"A versão {version} já está {ver['state']}: crie uma versão nova para mudar os textos"


def _ios_versao_editavel(cli, app_id, version):
    """Garante a versão para edição e devolve o id dela."""
    editavel, motivo = _ios_editavel(_ios_versao(cli, app_id, version), version)
    if not editavel:
        raise lojas.LojasError(motivo)
    return cli.ensure_version(app_id, version, log=_nada)


def _ios_vazio():
    return {k: [] for k, _, _ in asc.SCREENSHOT_TYPES}


def _ios_imagens(cli, loc_id):
    out = _ios_vazio()
    if not loc_id:
        return out
    for s in cli.screenshot_sets(loc_id):
        if s.get("displayType") in out:
            out[s["displayType"]] += [{"id": x["id"], "url": x.get("url") or "", "name": x.get("fileName") or ""}
                                      for x in s.get("screenshots") or []]
    return out


def _ios_load(project, version):
    cli, app_id = _ios_ctx(project)
    ver = _ios_versao(cli, app_id, version)
    editable, motivo = _ios_editavel(ver, version)
    if ver is not None:
        locs = cli.version_localizations(ver["id"])
    else:
        live = cli.live_version(app_id)
        locs = cli.version_localizations(live["id"]) if live else {}
    info = cli.app_info_localizations(app_id)
    loja = list(locs) + [c for c in info if c not in locs]
    codes = _codes(project, loja)

    campos = {}
    for c in codes:
        base = locs.get(c, {})
        d = {f: (base.get(f) or "") for f in IOS_TEXT}
        if ver is None:
            d["whatsNew"] = ""  # textos da versão ao vivo: o "o que há de novo" é de outra versão
        d["subtitle"] = (info.get(c) or {}).get("subtitle") or ""
        campos[c] = d

    imagens = {c: _ios_vazio() for c in codes}
    if ver is not None and locs:
        itens = list(locs.items())
        with ThreadPoolExecutor(4) as ex:
            outs = list(ex.map(lambda kv: _ios_imagens(cli, kv[1]["id"]), itens))
        for (c, _), o in zip(itens, outs):
            imagens[c] = o

    return {
        "store": "ios", "version": version, "editable": editable, "editReason": motivo,
        "note": NOTE_IOS,
        "fieldList": list(FIELDS["ios"]), "limits": _limites("ios"),
        "storeLocales": loja, "locales": campos, "images": imagens,
        "imageKinds": [{"kind": k, "label": l, "hint": h} for k, l, h in asc.SCREENSHOT_TYPES],
    }


def _ios_salvar(project, version, pendentes):
    cli, app_id = _ios_ctx(project)
    vid = _ios_versao_editavel(cli, app_id, version)
    por_loc = {}
    for loc, f, txt in pendentes:
        por_loc.setdefault(loc, {})[f] = txt
    salvos, avisos = [], []
    for loc, campos in por_loc.items():
        versao = {f: t for f, t in campos.items() if f in IOS_TEXT}
        if versao:
            cli.save_version_localization(vid, loc, versao, log=_nada)
            salvos += [f"{loc}/{f}" for f in versao]
        if "subtitle" in campos:
            try:
                cli.save_info_localization(app_id, loc, campos["subtitle"], log=_nada)
                salvos.append(f"{loc}/subtitle")
            except asc.AscError as e:
                avisos.append(str(e))
    return {"ok": True, "saved": salvos, "warnings": avisos}


# ---------------- Google Play ----------------
def _play_tracks(play_cli, pkg):
    eid = play_cli.edit_open(pkg)
    try:
        return play_cli.tracks(pkg, eid)
    finally:
        play_cli.edit_delete(pkg, eid)


def _play_find_build(tracks, build):
    """(faixa, release) da release que contém o versionCode `build`; (None, None) se não achar."""
    alvo = str(build)
    for t in tracks:
        for r in t.get("releases") or []:
            if alvo in [str(v) for v in r.get("versionCodes") or []]:
                return t.get("track"), r
    return None, None


def _vc(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def _play_producao(tracks):
    """Release concluída de maior versionCode na faixa de produção (a que está no ar)."""
    cand = []
    for t in tracks:
        if t.get("track") != "production":
            continue
        for r in t.get("releases") or []:
            if r.get("status") == "completed":
                for v in r.get("versionCodes") or []:
                    cand.append((_vc(v), r))
    return max(cand, key=lambda x: x[0])[1] if cand else None


def _play_vazio():
    return {k: [] for k, _, _ in PLAY_KINDS}


def _play_imagens(play_cli, pkg, locale):
    out = _play_vazio()
    raw = play_cli.listing_images(pkg, lojas.play_lang(locale))
    for k in out:
        out[k] = [{"id": i["id"], "url": i.get("url") or "", "name": ""} for i in raw.get(k) or []]
    return out


def _android_load(project, version, build):
    ln = lojas.link(project, "android")
    play_cli = lojas.play_client(ln["accountId"])
    pkg = ln["packageName"]
    listagem = play_cli.all_listings(pkg)

    loja, textos = [], {}
    for lang, l in (listagem.get("listings") or {}).items():
        c = lojas.from_play_lang(lang)
        if c not in textos:
            loja.append(c)
        textos[c] = {"shortDescription": l.get("shortDescription") or "",
                     "fullDescription": l.get("fullDescription") or ""}

    tracks = _play_tracks(play_cli, pkg)
    _, rel = _play_find_build(tracks, build)
    if rel is None:
        rel = _play_producao(tracks)
    notas = {}
    if rel is not None:
        notas = {lojas.from_play_lang(n.get("language") or ""): n.get("text") or ""
                 for n in rel.get("releaseNotes") or []}

    codes = _codes(project, loja)
    campos = {}
    for c in codes:
        base = textos.get(c, {})
        campos[c] = {"whatsNew": notas.get(c, ""),
                     "shortDescription": base.get("shortDescription", ""),
                     "fullDescription": base.get("fullDescription", "")}

    imagens = {c: _play_vazio() for c in codes}
    if loja:
        with ThreadPoolExecutor(4) as ex:
            outs = list(ex.map(lambda c: _play_imagens(play_cli, pkg, c), loja))
        for c, o in zip(loja, outs):
            imagens[c] = o

    return {
        "store": "android", "version": version, "editable": True, "editReason": "",
        "note": NOTE_ANDROID,
        "fieldList": list(FIELDS["android"]), "limits": _limites("android"),
        "storeLocales": loja, "locales": campos, "images": imagens,
        "imageKinds": [{"kind": k, "label": l, "hint": h} for k, l, h in PLAY_KINDS],
    }


def _android_salvar(project, build, track, pendentes):
    ln = lojas.link(project, "android")
    play_cli = lojas.play_client(ln["accountId"])
    pkg = ln["packageName"]
    listings, notas = {}, {}
    for loc, f, txt in pendentes:
        if f in ANDROID_TEXT:
            listings.setdefault(lojas.play_lang(loc), {})[f] = txt
        else:
            notas[lojas.play_lang(loc)] = txt

    avisos = []
    if listings:
        play_cli.save_listings(pkg, listings, log=_nada)
    salvos = [f"{loc}/{f}" for loc, f, _ in pendentes if f in ANDROID_TEXT]

    if notas:
        b = str(build or "").strip()
        if not b.isdigit():
            avisos.append("o build não foi informado: as notas da release não foram gravadas")
        else:
            faixa = track or _play_find_build(_play_tracks(play_cli, pkg), b)[0]
            if not faixa:
                avisos.append(f"o build {b} não está em nenhuma release do Google Play: "
                              "as notas não foram gravadas")
            else:
                try:
                    play_cli.set_release_notes(pkg, faixa, int(b), notas, log=_nada)
                    salvos += [f"{loc}/{f}" for loc, f, _ in pendentes if f in ANDROID_NOTES]
                except play.PlayError as e:
                    avisos.append(str(e))
    return {"ok": True, "saved": salvos, "warnings": avisos}


# ---------------- API pública ----------------
def load_fields(project, store, version, build=""):
    _loja(store)
    _versao(version)
    with _erros():
        if store == "ios":
            return _ios_load(project, version)
        return _android_load(project, version, build)


def save_fields(project, store, version, build, data, track=""):
    _loja(store)
    _versao(version)
    locs = data.get("locales") if isinstance(data, dict) else None
    if not isinstance(locs, dict):
        raise ValueError("dados inválidos: esperado {locales: {...}}")
    validos = {c["code"] for c in lojas.catalog()}
    limites = _limites(store)
    pendentes = []  # (locale, campo, texto)
    for loc, campos in locs.items():
        if loc not in validos or not isinstance(campos, dict):
            continue
        for f in FIELDS[store]:
            txt = campos.get(f)
            if not isinstance(txt, str) or not txt.strip():
                continue
            txt = txt.strip()
            if len(txt) > limites[f]:
                raise lojas.LojasError(
                    f"{loc}: o campo {f} tem {len(txt)} caracteres (limite {limites[f]})")
            pendentes.append((loc, f, txt))
    if not pendentes:
        return {"ok": True, "saved": [], "warnings": ["nenhum texto preenchido para gravar"]}
    with _erros():
        if store == "ios":
            return _ios_salvar(project, version, pendentes)
        return _android_salvar(project, build, track, pendentes)


def upload_image(project, store, version, locale, kind, path):
    _loja(store)
    _versao(version)
    _idioma(locale)
    if kind not in _tipos(store):
        raise ValueError(f"tipo de imagem inválido para esta loja: {kind}")
    if os.path.splitext(str(path))[1].lower() not in (".png", ".jpg", ".jpeg"):
        raise ValueError("a imagem precisa ser PNG ou JPG")
    if not os.path.isfile(path):
        raise ValueError("arquivo da imagem não encontrado")
    with _erros():
        if store == "ios":
            cli, app_id = _ios_ctx(project)
            vid = _ios_versao_editavel(cli, app_id, version)
            locs = cli.version_localizations(vid)
            if locale in locs:
                loc_id = locs[locale]["id"]
            else:
                loc_id = cli.save_version_localization(vid, locale, {}, log=_nada)
            cli.upload_screenshot(loc_id, kind, path, log=_nada)
            return {"images": _ios_imagens(cli, loc_id)}
        ln = lojas.link(project, "android")
        play_cli = lojas.play_client(ln["accountId"])
        pkg = ln["packageName"]
        play_cli.upload_image(pkg, lojas.play_lang(locale), kind, path, log=_nada)
        return {"images": _play_imagens(play_cli, pkg, locale)}


def delete_image(project, store, version, locale, kind, image_id):
    _loja(store)
    _versao(version)
    _idioma(locale)
    if kind not in _tipos(store):
        raise ValueError(f"tipo de imagem inválido para esta loja: {kind}")
    if not str(image_id or "").strip():
        raise ValueError("imagem não informada")
    with _erros():
        if store == "ios":
            cli, app_id = _ios_ctx(project)
            ver = _ios_versao(cli, app_id, version)
            if ver is None:
                raise lojas.LojasError(f"a versão {version} não existe na App Store")
            editavel, motivo = _ios_editavel(ver, version)
            if not editavel:
                raise lojas.LojasError(motivo)
            cli.delete_screenshot(image_id)
            loc_id = cli.version_localizations(ver["id"]).get(locale, {}).get("id")
            return {"images": _ios_imagens(cli, loc_id)}
        ln = lojas.link(project, "android")
        play_cli = lojas.play_client(ln["accountId"])
        pkg = ln["packageName"]
        play_cli.delete_image(pkg, lojas.play_lang(locale), kind, image_id)
        return {"images": _play_imagens(play_cli, pkg, locale)}


# ---------------- envio para revisão (App Store) e promoção (Google Play) ----------------
PROMO_STATUS = ("completed", "inProgress", "draft")
TRACK_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _play_faixas_do_build(tracks, build):
    """Nomes das faixas que têm uma release com o versionCode `build` (na ordem das faixas)."""
    alvo = str(build)
    out = []
    for t in tracks:
        for r in t.get("releases") or []:
            if alvo in [str(v) for v in r.get("versionCodes") or []]:
                out.append(t.get("track"))
                break
    return out


def submit_review(project, store, version, build=""):
    """App Store: anexa o maior build processado da versão (sem criptografia) e envia para revisão."""
    _loja(store)
    _versao(version)
    if store != "ios":
        raise lojas.LojasError("o envio para revisão é só da App Store: no Google Play use Promover para produção")
    with _erros():
        cli, app_id = _ios_ctx(project)
        rec = cli.version_record(app_id, version)
        if rec is None:
            raise lojas.LojasError(f"A versão {version} ainda não existe na App Store: "
                                   "grave os textos em Atualizar na loja primeiro")
        if rec["state"] not in asc.ASC.EDITABLE:
            raise lojas.LojasError(f"A versão {version} está em {asc.state_label(rec['state'])} "
                                   "e não pode ser enviada de novo")
        b = cli.build_for_version(app_id, version, str(build or "").strip())
        if b is None:
            raise lojas.LojasError(f"Não há build processado da versão {version} no App Store Connect: "
                                   "envie o .ipa em 📤 Enviar para a loja e espere o processamento")
        cli.set_no_encryption(b["id"])
        cli.attach_build(rec["id"], b["id"], log=_nada)
        cli.submit_for_review(app_id, rec["id"], log=_nada)
    return {"ok": True, "version": version, "build": b["version"],
            "message": f"Versão {version} (build {b['version']}) enviada para revisão da Apple"}


def promote(project, store, version, build, to_track="production", status="completed", fraction=None,
            from_track=""):
    """Google Play: copia a release do build (versionCode) da faixa de origem para a faixa de destino."""
    _loja(store)
    _versao(version)
    if store != "android":
        raise lojas.LojasError("promover para produção é só do Google Play")
    b = str(build or "").strip()
    if not b.isdigit():
        raise lojas.LojasError("o build precisa ser o número do versionCode do Google Play")
    to_track = str(to_track or "production").strip()
    if not TRACK_RE.match(to_track):
        raise lojas.LojasError(f"faixa de destino inválida: {to_track}")
    if status not in PROMO_STATUS:
        raise lojas.LojasError(f"status inválido: {status}")
    origem = str(from_track or "").strip()
    if origem and not TRACK_RE.match(origem):
        raise lojas.LojasError(f"faixa de origem inválida: {origem}")
    with _erros():
        ln = lojas.link(project, "android")
        cli = lojas.play_client(ln["accountId"])
        pkg = ln["packageName"]
        if not origem:
            faixas = _play_faixas_do_build(_play_tracks(cli, pkg), b)
            if not faixas:
                raise lojas.LojasError(f"o build {b} não está em nenhuma release do Google Play")
            outras = [f for f in faixas if f != to_track]
            origem = outras[0] if outras else faixas[0]
        if origem == to_track:
            raise lojas.LojasError(f"o build {b} já está na faixa {to_track}: escolha outra faixa de destino")
        cli.promote(pkg, origem, to_track, int(b), status=status, user_fraction=fraction, log=_nada)
    return {"ok": True, "message": f"Build {b} promovido de {origem} para {to_track} ({status})"}
