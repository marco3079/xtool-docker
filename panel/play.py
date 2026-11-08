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
