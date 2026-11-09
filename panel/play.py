"""Google Play Developer API v3 client (service account) — edits, uploads, tracks.

Docs: https://developers.google.com/android-publisher
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import jwt  # python3-jwt (+ python3-cryptography for RS256)

API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
# tipos de imagem da ficha da loja (Google Play)
IMAGE_KINDS = ("icon", "featureGraphic", "phoneScreenshots", "sevenInchScreenshots", "tenInchScreenshots")


class PlayError(Exception):
    pass


def _http_text(e):
    """Corpo de um HTTPError como texto; nunca levanta."""
    try:
        return e.read().decode("utf-8", "replace")
    except (OSError, http.client.HTTPException):
        return ""


class Play:
    def __init__(self, sa):
        if not (sa.get("client_email") and sa.get("private_key")):
            raise PlayError("chave da conta de serviço inválida")
        self.email, self.key = sa["client_email"], sa["private_key"]
        self.kid = sa.get("private_key_id")
        self.token_uri = sa.get("token_uri") or "https://oauth2.googleapis.com/token"
        self._tok, self._exp = None, 0

    def token(self):
        now = int(time.time())
        if not self._tok or now > self._exp - 60:
            claims = {"iss": self.email, "scope": SCOPE, "aud": self.token_uri,
                      "iat": now, "exp": now + 3600}
            try:
                assertion = jwt.encode(claims, self.key, algorithm="RS256",
                                       headers={"kid": self.kid} if self.kid else None)
            except Exception as e:
                raise PlayError(f"chave privada da conta de serviço inválida: {e}")
            if isinstance(assertion, bytes):
                assertion = assertion.decode()
            body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                           "assertion": assertion}).encode()
            r = urllib.request.Request(self.token_uri, data=body, method="POST",
                                       headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(r, timeout=120) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as e:
                txt = _http_text(e)
                try:
                    j = json.loads(txt)
                    msg = j.get("error_description") or j.get("error") or txt
                except (ValueError, AttributeError):
                    msg = txt
                raise PlayError(f"Google recusou a chave da conta de serviço: {str(msg or e.reason)[:1500]}")
            except (OSError, http.client.HTTPException) as e:
                raise PlayError(f"sem conexão com o Google: {e}")
            try:
                d = json.loads(raw)
            except ValueError:
                raise PlayError("resposta inválida do Google")
            if not isinstance(d, dict) or not d.get("access_token"):
                raise PlayError("resposta de token sem access_token")
            try:
                ttl = int(d.get("expires_in", 3600))
            except (TypeError, ValueError):
                ttl = 3600
            self._tok = d["access_token"]
            self._exp = now + ttl
        return self._tok

    def req(self, method, path, body=None, params=None, data=None, ctype=None, upload=False):
        url = (UPLOAD if upload else API) + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {self.token()}"}
        payload = None
        if data is not None:
            payload, headers["Content-Type"] = data, ctype or "application/octet-stream"
        elif body is not None:
            payload, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        r = urllib.request.Request(url, data=payload, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=900 if upload else 120) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            txt = _http_text(e)
            try:
                err = json.loads(txt)["error"]
                code, msg = err.get("code", e.code), err.get("message", txt)
            except (ValueError, KeyError, TypeError, AttributeError):
                code, msg = e.code, txt
            raise PlayError(f"Google Play {code}: {str(msg)[:1500]}")
        except (OSError, http.client.HTTPException) as e:
            raise PlayError(f"falha de rede com o Google Play: {e}")
        try:
            d = json.loads(raw) if raw else {}
        except ValueError:
            raise PlayError("resposta inválida do Google Play")
        if not isinstance(d, dict):
            raise PlayError("resposta inválida do Google Play")
        return d

    # ---------------- edits ----------------
    def edit_open(self, pkg):
        eid = self.req("POST", f"/{pkg}/edits", body={}).get("id")
        if not eid:
            raise PlayError("resposta inesperada do Google Play")
        return eid

    def edit_delete(self, pkg, edit_id):
        try:
            self.req("DELETE", f"/{pkg}/edits/{edit_id}")
        except PlayError:
            pass

    def edit_commit(self, pkg, edit_id, changes_not_sent_for_review=False):
        params = {"changesNotSentForReview": "true"} if changes_not_sent_for_review else None
        return self.req("POST", f"/{pkg}/edits/{edit_id}:commit", params=params)

    def tracks(self, pkg, edit_id):
        return self.req("GET", f"/{pkg}/edits/{edit_id}/tracks").get("tracks", [])

    # ---------------- upload ----------------
    def _upload(self, kind, pkg, edit_id, path, log):
        try:
            log(f"Enviando {os.path.basename(path)} ({os.path.getsize(path) / 1e6:.1f} MB)…")
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            raise PlayError(f"não foi possível ler {path}: {e}")
        r = self.req("POST", f"/{pkg}/edits/{edit_id}/{kind}", params={"uploadType": "media"},
                     data=data, ctype="application/octet-stream", upload=True)
        vc = r.get("versionCode")
        if vc is None:
            raise PlayError("resposta inesperada do Google Play")
        try:
            return int(vc)
        except (TypeError, ValueError):
            raise PlayError("resposta inesperada do Google Play")

    def upload_bundle(self, pkg, edit_id, path, log):
        return self._upload("bundles", pkg, edit_id, path, log)

    def upload_apk(self, pkg, edit_id, path, log):
        return self._upload("apks", pkg, edit_id, path, log)

    # ---------------- tracks ----------------
    def set_track(self, pkg, edit_id, track, version_codes, status, release_notes,
                  name=None, user_fraction=None):
        rel = {"versionCodes": [str(v) for v in version_codes], "status": status,
               "releaseNotes": [{"language": k, "text": v[:500]}
                                for k, v in release_notes.items() if v.strip()]}
        if name:
            rel["name"] = name
        if status == "inProgress":
            rel["userFraction"] = float(0.1 if user_fraction is None else user_fraction)
        return self.req("PUT", f"/{pkg}/edits/{edit_id}/tracks/{track}",
                        body={"track": track, "releases": [rel]})

    # ---------------- app info ----------------
    def app_info(self, pkg):
        eid = self.edit_open(pkg)
        try:
            lang = self.req("GET", f"/{pkg}/edits/{eid}/details").get("defaultLanguage", "")
            title = ""
            if lang:
                try:
                    title = self.req("GET", f"/{pkg}/edits/{eid}/listings/{lang}").get("title", "")
                except PlayError:
                    pass
            tracks = self.tracks(pkg, eid)
            max_vc = 0
            for t in tracks:
                for rel in t.get("releases", []):
                    for v in rel.get("versionCodes", []):
                        try:
                            max_vc = max(max_vc, int(v))
                        except (TypeError, ValueError):
                            raise PlayError("resposta inesperada do Google Play")
        finally:
            self.edit_delete(pkg, eid)
        return {"packageName": pkg, "title": title, "defaultLanguage": lang,
                "tracks": tracks, "maxVersionCode": max_vc}

    def listing(self, pkg):
        """Store page as it is in the Play Console: texts, images, contact and the newest releases."""
        eid = self.edit_open(pkg)
        try:
            det = self.req("GET", f"/{pkg}/edits/{eid}/details")
            lang = det.get("defaultLanguage", "")
            lst = {}
            if lang:
                try:
                    lst = self.req("GET", f"/{pkg}/edits/{eid}/listings/{lang}")
                except PlayError:
                    lst = {}
            def images(kind):
                try:
                    r = self.req("GET", f"/{pkg}/edits/{eid}/listings/{lang}/{kind}")
                except PlayError:
                    return kind, []
                return kind, [i["url"] for i in r.get("images", []) if isinstance(i, dict) and i.get("url")]

            kinds = ("icon", "featureGraphic", "phoneScreenshots", "sevenInchScreenshots", "tenInchScreenshots")
            with ThreadPoolExecutor(6) as ex:  # one request per image type: run them together
                fut_tracks = ex.submit(self.tracks, pkg, eid)
                imgs = dict(ex.map(images, kinds)) if lang else {}
                tracks = fut_tracks.result()
        finally:
            self.edit_delete(pkg, eid)
        return {"packageName": pkg, "defaultLanguage": lang, "title": lst.get("title", ""),
                "shortDescription": lst.get("shortDescription", ""), "fullDescription": lst.get("fullDescription", ""),
                "video": lst.get("video", ""), "contactEmail": det.get("contactEmail", ""),
                "contactWebsite": det.get("contactWebsite", ""), "contactPhone": det.get("contactPhone", ""),
                "images": imgs, "tracks": tracks}

    def test(self):
        self.token()
        return {"ok": True, "email": self.email}

    # ---------------- ficha da loja: textos ----------------
    def all_listings(self, pkg):
        """Textos da ficha em todos os idiomas (título, descrição curta e completa).

        Devolve {"defaultLanguage": str, "listings": {idioma: {"title", "shortDescription", "fullDescription"}}}.
        Usa uma edição só para leitura e a apaga em seguida.
        """
        eid = self.edit_open(pkg)
        try:
            lang = self.req("GET", f"/{pkg}/edits/{eid}/details").get("defaultLanguage", "")
            items = self.req("GET", f"/{pkg}/edits/{eid}/listings").get("listings", [])
            out = {}
            for it in items:
                if not isinstance(it, dict) or not it.get("language"):
                    continue
                out[it["language"]] = {"title": it.get("title", ""),
                                       "shortDescription": it.get("shortDescription", ""),
                                       "fullDescription": it.get("fullDescription", "")}
        finally:
            self.edit_delete(pkg, eid)
        return {"defaultLanguage": lang, "listings": out}

    def save_listings(self, pkg, listings, log=print):
        """Grava textos da ficha em uma única edição e faz commit.

        `listings` = {idioma: {"shortDescription"?, "fullDescription"?, "title"?}}. Para cada idioma
        envia PATCH só com as chaves recebidas. Se o PATCH falhar (idioma sem ficha), tenta PUT com o
        título recebido ou com o título do idioma padrão; sem título dá PlayError. Devolve a lista
        de idiomas gravados.
        """
        keys = ("title", "shortDescription", "fullDescription")
        todo = []
        for lang, fields in (listings or {}).items():
            if not isinstance(fields, dict):
                continue
            body = {k: str(fields[k]) for k in keys if fields.get(k) is not None}
            if body:
                todo.append((lang, body))
        if not todo:
            return []
        eid = self.edit_open(pkg)
        saved, ok = [], False
        try:
            default_title = None
            for lang, body in todo:
                try:
                    self.req("PATCH", f"/{pkg}/edits/{eid}/listings/{lang}", body=body)
                except PlayError as e:
                    msg = str(e).lower()
                    if "404" not in msg and "not found" not in msg:
                        raise  # erro real (ex.: texto acima do limite): relança o original
                    # a ficha do idioma ainda não existe: cria com PUT, que exige o título
                    title = body.get("title", "")
                    if not title:
                        if default_title is None:
                            dl = self.req("GET", f"/{pkg}/edits/{eid}/details").get("defaultLanguage", "")
                            default_title = ""
                            if dl:
                                try:
                                    default_title = self.req(
                                        "GET", f"/{pkg}/edits/{eid}/listings/{dl}").get("title", "") or ""
                                except PlayError:
                                    default_title = ""
                        title = default_title
                    if not title:
                        raise PlayError(f"o idioma {lang} ainda não existe na ficha do Google Play")
                    self.req("PUT", f"/{pkg}/edits/{eid}/listings/{lang}", body={**body, "title": title})
                saved.append(lang)
                log(f"Google Play: textos de {lang} preparados")
            self.edit_commit(pkg, eid)
            ok = True
        finally:
            if not ok:
                self.edit_delete(pkg, eid)
        log(f"Google Play: {len(saved)} idioma(s) gravado(s) na ficha")
        return saved

    # ---------------- ficha da loja: imagens ----------------
    def listing_images(self, pkg, lang):
        """Imagens da ficha de um idioma: {tipo: [{"id", "url", "sha1"}]} para cada tipo em IMAGE_KINDS.

        Usa uma edição só para leitura (tipos buscados em paralelo) e a apaga em seguida.
        Tipo sem imagens, ou idioma sem ficha, vira lista vazia.
        """
        if not lang:
            raise PlayError("idioma não informado")
        eid = self.edit_open(pkg)
        try:
            def one(kind):
                try:
                    r = self.req("GET", f"/{pkg}/edits/{eid}/listings/{lang}/{kind}")
                except PlayError:
                    return kind, []
                imgs = [{"id": i.get("id", ""), "url": i.get("url", ""), "sha1": i.get("sha1", "")}
                        for i in r.get("images", []) or [] if isinstance(i, dict) and i.get("url")]
                return kind, imgs

            with ThreadPoolExecutor(5) as ex:
                out = dict(ex.map(one, IMAGE_KINDS))
        finally:
            self.edit_delete(pkg, eid)
        return out

    def upload_image(self, pkg, lang, kind, path, log=print):
        """Envia uma imagem (PNG ou JPG) para o tipo `kind` do idioma `lang`, com commit.

        Recusa `kind` fora de IMAGE_KINDS e extensão que não seja png/jpg/jpeg (PlayError).
        Devolve {"id", "url", "sha1"} da imagem enviada (`image` da resposta).
        """
        if kind not in IMAGE_KINDS:
            raise PlayError(f"tipo de imagem inválido: {kind}")
        if not lang:
            raise PlayError("idioma não informado")
        ctypes = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        ext = os.path.splitext(str(path))[1].lower()
        if ext not in ctypes:
            raise PlayError("a imagem deve ser PNG ou JPG")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            raise PlayError(f"não foi possível ler {path}: {e}")
        log(f"Enviando {os.path.basename(path)} para {kind} ({lang})…")
        eid = self.edit_open(pkg)
        ok = False
        try:
            r = self.req("POST", f"/{pkg}/edits/{eid}/listings/{lang}/{kind}",
                         params={"uploadType": "media"}, data=data, ctype=ctypes[ext], upload=True)
            img = r.get("image")
            if not isinstance(img, dict):
                raise PlayError("resposta inesperada do Google Play")
            self.edit_commit(pkg, eid)
            ok = True
        finally:
            if not ok:
                self.edit_delete(pkg, eid)
        return {"id": img.get("id", ""), "url": img.get("url", ""), "sha1": img.get("sha1", "")}

    def delete_image(self, pkg, lang, kind, image_id):
        """Apaga uma imagem da ficha (idioma `lang`, tipo `kind`, id `image_id`) com commit.

        Recusa `kind` fora de IMAGE_KINDS. Não devolve nada.
        """
        if kind not in IMAGE_KINDS:
            raise PlayError(f"tipo de imagem inválido: {kind}")
        if not lang or not image_id:
            raise PlayError("idioma ou imagem não informados")
        img_part = urllib.parse.quote(str(image_id), safe="")
        eid = self.edit_open(pkg)
        ok = False
        try:
            self.req("DELETE", f"/{pkg}/edits/{eid}/listings/{lang}/{kind}/{img_part}")
            self.edit_commit(pkg, eid)
            ok = True
        finally:
            if not ok:
                self.edit_delete(pkg, eid)

    # ---------------- releases ----------------
    def release_summary(self, pkg):
        """Uma única leitura das faixas: {"live": dict|None, "others": [dict]}.

        "live" é a mesma coisa que `live_release` devolve (release de maior versionCode com status
        "completed" na faixa "production"; None se não houver). "others" traz, para cada faixa que
        não é "production", a melhor release (maior versionCode, qualquer status) com
        {"track","versionCode","name","status"}. `others` vem mesmo quando `live` é None.
        """
        eid = self.edit_open(pkg)
        try:
            tracks = self.tracks(pkg, eid)
        finally:
            self.edit_delete(pkg, eid)

        def best(rel):
            vcs = []
            for v in rel.get("versionCodes", []) or []:
                try:
                    vcs.append(int(v))
                except (TypeError, ValueError):
                    continue
            return max(vcs) if vcs else None

        live, others = None, {}
        for t in tracks:
            if not isinstance(t, dict):
                continue
            track = t.get("track", "")
            for rel in t.get("releases", []) or []:
                if not isinstance(rel, dict):
                    continue
                vc = best(rel)
                if vc is None:
                    continue
                cand = {"track": track, "versionCode": vc,
                        "name": rel.get("name", ""), "status": rel.get("status", "")}
                if track == "production":
                    if cand["status"] == "completed" and (live is None or vc > live["versionCode"]):
                        live = cand
                else:
                    cur = others.get(track)
                    if cur is None or vc > cur["versionCode"]:
                        others[track] = cand
        return {"live": live, "others": list(others.values())}

    def live_release(self, pkg):
        """Release publicada na produção: {"track","versionCode","name","status","others"} ou None.

        É a release de maior versionCode com status "completed" na faixa "production". `others` traz
        a melhor release de cada outra faixa (ver `release_summary`). Sem release live, devolve None.
        """
        s = self.release_summary(pkg)
        if s["live"] is None:
            return None
        return {**s["live"], "others": s["others"]}

    def set_release_notes(self, pkg, track, version_code, notes, log=print):
        """Grava as notas de versão (releaseNotes) da release que contém `version_code` na faixa `track`.

        `notes` = {idioma Play: texto}. Mescla com as notas já existentes (idiomas dados são
        substituídos; textos vazios são ignorados; corte em 500 caracteres). Envia PUT da faixa com
        TODAS as releases e faz commit. Sem release com esse build: PlayError.
        """
        if not track:
            raise PlayError("faixa não informada")
        wanted = str(version_code)
        eid = self.edit_open(pkg)
        ok = False
        try:
            t = self.req("GET", f"/{pkg}/edits/{eid}/tracks/{track}")
            releases = [r for r in (t.get("releases") or []) if isinstance(r, dict)]
            rel = None
            for r in releases:
                if wanted in [str(v) for v in (r.get("versionCodes") or [])]:
                    rel = r
                    break
            if rel is None:
                raise PlayError(f"esse build ainda não está em nenhuma release da faixa {track}")
            merged = {}
            for n in rel.get("releaseNotes") or []:
                if isinstance(n, dict) and n.get("language"):
                    merged[n["language"]] = n.get("text", "")
            for lang, text in (notes or {}).items():
                txt = str(text or "").strip()
                if lang and txt:
                    merged[lang] = txt[:500]
            rel["releaseNotes"] = [{"language": k, "text": v} for k, v in merged.items()]
            self.req("PUT", f"/{pkg}/edits/{eid}/tracks/{track}", body={"track": track, "releases": releases})
            self.edit_commit(pkg, eid)
            ok = True
        finally:
            if not ok:
                self.edit_delete(pkg, eid)
        log(f"Google Play: notas da versão {version_code} gravadas na faixa {track}")
