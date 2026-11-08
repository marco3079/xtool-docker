"""App Store Connect API client (JWT ES256) — apps, signing assets, uploads, review.

Docs: https://developer.apple.com/documentation/appstoreconnectapi
"""
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt  # python3-jwt (+ python3-cryptography for ES256)

API = "https://api.appstoreconnect.apple.com"


class AscError(Exception):
    pass


class ASC:
    def __init__(self, issuer_id, key_id, p8):
        if not (issuer_id and key_id and p8):
            raise AscError("chave da API do App Store Connect não configurada para esta conta")
        self.issuer_id, self.key_id, self.p8 = issuer_id.strip(), key_id.strip(), p8
        self._tok, self._exp = None, 0

    def token(self):
        now = int(time.time())
        if not self._tok or now > self._exp - 60:
            self._exp = now + 15 * 60
            self._tok = jwt.encode({"iss": self.issuer_id, "iat": now, "exp": self._exp,
                                    "aud": "appstoreconnect-v1"},
                                   self.p8, algorithm="ES256",
                                   headers={"kid": self.key_id, "typ": "JWT"})
        return self._tok

    def req(self, method, path, body=None, params=None):
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            try:
                errs = json.loads(txt).get("errors", [])
                msg = "; ".join(f"{x.get('title','')}: {x.get('detail','')}" for x in errs) or txt
            except ValueError:
                msg = txt
            raise AscError(f"App Store Connect {e.code}: {msg[:1500]}")
        except urllib.error.URLError as e:
            raise AscError(f"sem conexão com o App Store Connect: {e.reason}")

    def get(self, path, **params):
        return self.req("GET", path, params=params or None)

    def all(self, path, **params):
        out, nxt = [], None
        params.setdefault("limit", 200)
        r = self.get(path, **params)
        while True:
            out += r.get("data", [])
            nxt = (r.get("links") or {}).get("next")
            if not nxt:
                return out
            r = self.req("GET", nxt)

    # ---------------- apps ----------------
    def apps(self):
        res = []
        for a in self.all("/v1/apps", **{"fields[apps]": "name,bundleId,sku,primaryLocale"}):
            at = a["attributes"]
            versions = self.get(f"/v1/apps/{a['id']}/appStoreVersions", limit=3,
                                **{"fields[appStoreVersions]": "versionString,appStoreState,createdDate,platform"}).get("data", [])
            res.append({
                "id": a["id"], "name": at.get("name"), "bundleId": at.get("bundleId"),
                "sku": at.get("sku"), "primaryLocale": at.get("primaryLocale"),
                "versions": [{"id": v["id"], **v["attributes"]} for v in versions],
            })
        return res

    def app_by_bundle(self, bundle_id):
        for a in self.all("/v1/apps", **{"filter[bundleId]": bundle_id, "fields[apps]": "name,bundleId,primaryLocale"}):
            if a["attributes"]["bundleId"] == bundle_id:
                return a
        raise AscError(f"não existe app no App Store Connect com o bundle ID {bundle_id}. "
                       "Crie o app em appstoreconnect.apple.com (Apps → +) primeiro.")

    def builds(self, app_id, limit=10):
        r = self.get("/v1/builds", **{"filter[app]": app_id, "sort": "-uploadedDate", "limit": limit,
                                      "include": "preReleaseVersion",
                                      "fields[builds]": "version,uploadedDate,processingState,expired,usesNonExemptEncryption,preReleaseVersion"})
        pre = {x["id"]: x["attributes"].get("version") for x in r.get("included", [])}
        out = []
        for b in r.get("data", []):
            rel = ((b.get("relationships") or {}).get("preReleaseVersion") or {}).get("data") or {}
            out.append({"id": b["id"], **b["attributes"], "marketingVersion": pre.get(rel.get("id"))})
        return out

    # ---------------- signing ----------------
    def bundle_id_resource(self, identifier):
        for b in self.all("/v1/bundleIds", **{"filter[identifier]": identifier}):
            if b["attributes"]["identifier"] == identifier:
                return b
        raise AscError(f"bundle ID {identifier} não está registrado na conta")

    def ensure_distribution_cert(self, store_dir, log=print):
        """Reuse our saved Apple Distribution cert if Apple still has it; otherwise create one."""
        os.makedirs(store_dir, exist_ok=True)
        key_pem = os.path.join(store_dir, "dist.key.pem")
        cert_pem = os.path.join(store_dir, "dist.cert.pem")
        meta_f = os.path.join(store_dir, "dist.json")
        if os.path.exists(meta_f) and os.path.exists(key_pem):
            meta = json.load(open(meta_f))
            try:
                c = self.get(f"/v1/certificates/{meta['id']}")["data"]
                if c["attributes"].get("expirationDate", "9") > time.strftime("%Y-%m-%dT%H:%M:%S"):
                    log(f"Certificado de distribuição: usando o salvo ({c['attributes'].get('name')})")
                    return meta["id"], key_pem, cert_pem
            except AscError:
                pass
            log("O certificado salvo não existe mais na Apple; criando outro…")
        log("Criando chave e certificado Apple Distribution…")
        subprocess.run(["openssl", "genrsa", "-out", key_pem, "2048"], check=True, capture_output=True)
        os.chmod(key_pem, 0o600)
        csr = subprocess.run(["openssl", "req", "-new", "-key", key_pem, "-subj", "/CN=xtool painel/O=xtool",
                              "-outform", "PEM"], check=True, capture_output=True, text=True).stdout
        try:
            r = self.req("POST", "/v1/certificates", {"data": {"type": "certificates", "attributes": {
                "certificateType": "DISTRIBUTION", "csrContent": csr}}})
        except AscError as e:
            if "limit" in str(e).lower() or "maximum" in str(e).lower():
                raise AscError("a conta já tem o máximo de certificados de distribuição. Revogue um "
                               "antigo em developer.apple.com → Certificates e tente de novo.")
            raise
        c = r["data"]
        der = base64.b64decode(c["attributes"]["certificateContent"])
        pem = subprocess.run(["openssl", "x509", "-inform", "DER", "-outform", "PEM"], input=der,
                             check=True, capture_output=True).stdout
        open(cert_pem, "wb").write(pem)
        json.dump({"id": c["id"], "name": c["attributes"].get("name")}, open(meta_f, "w"))
        log(f"Certificado criado: {c['attributes'].get('name')}")
        return c["id"], key_pem, cert_pem

    def app_store_profile(self, bundle_identifier, cert_id, log=print):
        bid = self.bundle_id_resource(bundle_identifier)
        name = f"xtool AppStore {bundle_identifier}"
        for p in self.all("/v1/profiles", **{"filter[name]": name, "filter[profileType]": "IOS_APP_STORE",
                                              "include": "certificates"}):
            certs = [c["id"] for c in (p.get("relationships", {}).get("certificates", {}).get("data") or [])]
            if p["attributes"].get("profileState") == "ACTIVE" and cert_id in certs:
                log("Perfil App Store: usando o existente")
                return base64.b64decode(p["attributes"]["profileContent"])
            log("Perfil antigo com outro certificado: removendo…")
            try:
                self.req("DELETE", f"/v1/profiles/{p['id']}")
            except AscError:
                pass
        log("Criando perfil de distribuição App Store…")
        r = self.req("POST", "/v1/profiles", {"data": {"type": "profiles",
            "attributes": {"name": name, "profileType": "IOS_APP_STORE"},
            "relationships": {"bundleId": {"data": {"type": "bundleIds", "id": bid["id"]}},
                              "certificates": {"data": [{"type": "certificates", "id": cert_id}]}}}})
        return base64.b64decode(r["data"]["attributes"]["profileContent"])

    # ---------------- upload ----------------
    def upload_ipa(self, app_id, ipa_path, version, build, log=print):
        size = os.path.getsize(ipa_path)
        log(f"Iniciando envio ({size/1e6:.1f} MB) da versão {version} ({build})…")
        up = self.req("POST", "/v1/buildUploads", {"data": {"type": "buildUploads",
            "attributes": {"cfBundleShortVersionString": version, "cfBundleVersion": str(build), "platform": "IOS"},
            "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}})["data"]
        f = self.req("POST", "/v1/buildUploadFiles", {"data": {"type": "buildUploadFiles",
            "attributes": {"assetType": "ASSET", "fileName": os.path.basename(ipa_path), "fileSize": size,
                           "uti": "com.apple.ipa"},
            "relationships": {"buildUpload": {"data": {"type": "buildUploads", "id": up["id"]}}}}})["data"]
        ops = f["attributes"].get("uploadOperations") or []
        md5 = hashlib.md5()
        with open(ipa_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                md5.update(chunk)
        with open(ipa_path, "rb") as fh:
            for i, op in enumerate(ops, 1):
                fh.seek(op["offset"])
                data = fh.read(op["length"])
                headers = {h["name"]: h["value"] for h in op.get("requestHeaders") or []}
                r = urllib.request.Request(op["url"], data=data, method=op.get("method", "PUT"), headers=headers)
                for attempt in range(4):
                    try:
                        urllib.request.urlopen(r, timeout=600).read()
                        break
                    except urllib.error.URLError as e:
                        if attempt == 3:
                            raise AscError(f"falha ao enviar parte {i}: {e}")
                        time.sleep(3 * (attempt + 1))
                log(f"  parte {i}/{len(ops)} enviada")
        self.req("PATCH", f"/v1/buildUploadFiles/{f['id']}", {"data": {"type": "buildUploadFiles", "id": f["id"],
            "attributes": {"uploaded": True,
                           "sourceFileChecksums": {"file": {"algorithm": "MD5", "hash": md5.hexdigest()}}}}})
        log("Arquivo enviado. Aguardando a Apple validar…")
        for _ in range(240):  # up to ~40 min
            st = self.get(f"/v1/buildUploads/{up['id']}")["data"]["attributes"]
            state = st.get("state") or {}
            s = state.get("state") if isinstance(state, dict) else state
            if s == "COMPLETE":
                for w in (state.get("warnings") or []) if isinstance(state, dict) else []:
                    log(f"  aviso: {w.get('description') or w}")
                log("Validação concluída ✔")
                return up["id"]
            if s == "FAILED":
                errs = (state.get("errors") or []) if isinstance(state, dict) else []
                raise AscError("a Apple recusou o build:\n" + "\n".join(
                    f"  • {e.get('code','')} {e.get('description') or e.get('message') or e}" for e in errs))
            time.sleep(10)
        raise AscError("tempo esgotado esperando a validação do upload")

    def wait_build(self, app_id, version, build, log=print, minutes=60):
        log("Aguardando o processamento do build na Apple (costuma levar 5–30 min)…")
        last = None
        for _ in range(minutes * 4):
            r = self.get("/v1/builds", **{"filter[app]": app_id, "filter[version]": str(build),
                                          "filter[preReleaseVersion.version]": version,
                                          "fields[builds]": "processingState,version"})
            d = r.get("data") or []
            if d:
                s = d[0]["attributes"]["processingState"]
                if s != last:
                    log(f"  estado: {s}")
                    last = s
                if s == "VALID":
                    return d[0]["id"]
                if s in ("FAILED", "INVALID"):
                    raise AscError(f"processamento do build terminou como {s}")
            time.sleep(15)
        raise AscError("tempo esgotado esperando o processamento do build")

    def set_no_encryption(self, build_id):
        try:
            self.req("PATCH", f"/v1/builds/{build_id}", {"data": {"type": "builds", "id": build_id,
                                                                   "attributes": {"usesNonExemptEncryption": False}}})
        except AscError:
            pass  # already answered (e.g. ITSAppUsesNonExemptEncryption in Info.plist)

    # ---------------- publish ----------------
    EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED",
                "INVALID_BINARY"}

    def ensure_version(self, app_id, version, log=print):
        vs = self.get(f"/v1/apps/{app_id}/appStoreVersions", **{"filter[platform]": "IOS", "limit": 20})["data"]
        for v in vs:
            if v["attributes"]["versionString"] == version:
                st = v["attributes"]["appStoreState"]
                if st not in self.EDITABLE:
                    raise AscError(f"a versão {version} já está em '{st}' e não pode ser editada")
                log(f"Versão {version} já existe ({st})")
                return v["id"]
        for v in vs:
            if v["attributes"]["appStoreState"] in self.EDITABLE:
                log(f"Renomeando versão em preparação {v['attributes']['versionString']} → {version}")
                self.req("PATCH", f"/v1/appStoreVersions/{v['id']}", {"data": {"type": "appStoreVersions",
                         "id": v["id"], "attributes": {"versionString": version}}})
                return v["id"]
        log(f"Criando versão {version} na App Store…")
        r = self.req("POST", "/v1/appStoreVersions", {"data": {"type": "appStoreVersions",
            "attributes": {"platform": "IOS", "versionString": version, "releaseType": "AFTER_APPROVAL"},
            "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}})
        return r["data"]["id"]

    def set_whats_new(self, version_id, texts, log=print):
        locs = self.get(f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations", limit=50)["data"]
        by = {l["attributes"]["locale"]: l for l in locs}
        for locale, text in texts.items():
            if not text.strip():
                continue
            if locale in by:
                self.req("PATCH", f"/v1/appStoreVersionLocalizations/{by[locale]['id']}", {"data": {
                    "type": "appStoreVersionLocalizations", "id": by[locale]["id"],
                    "attributes": {"whatsNew": text}}})
            else:
                self.req("POST", "/v1/appStoreVersionLocalizations", {"data": {
                    "type": "appStoreVersionLocalizations", "attributes": {"locale": locale, "whatsNew": text},
                    "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}}}})
            log(f"'O que há de novo' salvo em {locale}")

    def attach_build(self, version_id, build_id, log=print):
        self.req("PATCH", f"/v1/appStoreVersions/{version_id}/relationships/build",
                 {"data": {"type": "builds", "id": build_id}})
        log("Build vinculado à versão")

    def submit_for_review(self, app_id, version_id, log=print):
        subs = self.get("/v1/reviewSubmissions", **{"filter[app]": app_id, "filter[platform]": "IOS",
                                                    "filter[state]": "READY_FOR_REVIEW"})["data"]
        if subs:
            sub_id = subs[0]["id"]
        else:
            sub_id = self.req("POST", "/v1/reviewSubmissions", {"data": {"type": "reviewSubmissions",
                "attributes": {"platform": "IOS"},
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}}}})["data"]["id"]
        try:
            self.req("POST", "/v1/reviewSubmissionItems", {"data": {"type": "reviewSubmissionItems",
                "relationships": {"reviewSubmission": {"data": {"type": "reviewSubmissions", "id": sub_id}},
                                  "appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}}}})
        except AscError as e:
            if "already" not in str(e).lower():
                raise
        self.req("PATCH", f"/v1/reviewSubmissions/{sub_id}", {"data": {"type": "reviewSubmissions",
                 "id": sub_id, "attributes": {"submitted": True}}})
        log("Enviado para revisão da Apple ✔")
        return sub_id
