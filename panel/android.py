#!/usr/bin/env python3
"""Android: detecta o projeto Gradle, gerencia chaves de assinatura e faz o build
(+ envio para a Google Play). Roda como job do painel.

usage: android.py <args.json>
args: project, packageName, kind ("aab"|"apk"|"both"), debug, versionName, versionCode ("auto"|"123"),
      preBuild ("" = padrão detectado, "-" = pular), upload, playAccountId, track, status,
      userFraction, releaseNotes, existing
existing (opcional): caminho absoluto de um .aab ou .apk release já pronto. Com ele o job NÃO roda
      pré-build nem Gradle: só confere a versão na Play, valida e envia. Exige upload verdadeiro,
      versionName e versionCode (só dígitos; "auto" não vale) informados.
"""
import glob
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402
import versions  # noqa: E402
from play import Play, PlayError  # noqa: E402

KEY_EXTS = ("p12", "pfx", "jks", "keystore")
PRE_SCRIPTS = ["build:client:prod", "build:prod", "build:client", "build"]
TASKS = {"aab": [":app:bundleRelease"], "apk": [":app:assembleRelease"],
         "both": [":app:bundleRelease", ":app:assembleRelease"]}


def log(msg=""):
    print(msg, flush=True)


def step(title):
    log(f"\n\033[1;36m▶ {title}\033[0m")


VERSION_INIT = """allprojects {
    pluginManager.withPlugin('com.android.application') {
        def ac = extensions.getByName('androidComponents')
        ac.onVariants(ac.selector().all()) { variant ->
            variant.outputs.each { out ->
                out.versionCode.set(@CODE@)
                out.versionName.set(@NAME@)
            }
        }
    }
}
"""


def run(cmd, cwd=None, env=None, shell=False):
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    shown = re.sub(r"(-Pandroid\.injected\.signing\.[\w.]*password=)\S+", r"\1***", shown)
    log(f"\033[2m$ {shown}\033[0m")
    # sem capturar: a saída vai direto para o terminal do job (progresso do npm/gradle)
    rc = subprocess.run(cmd, cwd=cwd, env=env, shell=shell).returncode
    if rc != 0:
        raise SystemExit(f"comando falhou (código {rc})")


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def detect(project_dir):
    def has(*parts):
        return os.path.exists(os.path.join(project_dir, *parts))

    if has("android", "gradlew") or has("android", "settings.gradle") or has("android", "settings.gradle.kts"):
        gdir = "android"
    elif has("settings.gradle") or has("settings.gradle.kts"):
        gdir = "."
    else:
        return None

    gradle = ""
    for f in ("build.gradle", "build.gradle.kts"):
        if has(gdir, "app", f):
            gradle = read_text(os.path.join(project_dir, gdir, "app", f))
            break

    pkg = ""
    m = re.search(r"applicationId\s*=?\s*[\"']([\w.]+)[\"']", gradle)
    if m:
        pkg = m.group(1)
    capacitor = next((f for f in ("capacitor.config.ts", "capacitor.config.js", "capacitor.config.json")
                      if has(f)), None)
    if not pkg and capacitor:
        txt = read_text(os.path.join(project_dir, capacitor))
        if capacitor.endswith(".json"):
            try:
                pkg = str(json.loads(txt).get("appId") or "")
            except (ValueError, AttributeError):
                pass
        else:
            m = re.search(r"appId\s*:\s*[\"']([\w.]+)[\"']", txt)
            if m:
                pkg = m.group(1)

    vn = ""
    m = re.search(r"versionName\s*=?\s*\(?\s*[\"']([^\"']+)[\"']", gradle)
    if m and "$" not in m.group(1):
        vn = m.group(1)

    pkg_json = has("package.json")
    pre = ""
    if pkg_json:
        try:
            scripts = json.loads(read_text(os.path.join(project_dir, "package.json"))).get("scripts") or {}
        except (ValueError, AttributeError):
            scripts = {}
        parts = ["npm ci" if has("package-lock.json") else "npm install"]
        s = next((x for x in PRE_SCRIPTS if x in scripts), None)
        if s:
            parts.append(f"npm run {s}")
        if capacitor:
            parts.append("npx cap sync android")
        pre = " && ".join(parts)

    return {"gradleDir": gdir, "module": "app", "packageName": pkg, "capacitor": bool(capacitor),
            "packageJson": pkg_json, "defaultPreBuild": pre, "versionName": vn}


def fingerprints(path, storepass, alias):
    p = subprocess.run(["keytool", "-list", "-v", "-keystore", path, "-storepass", storepass, "-alias", alias],
                       capture_output=True, text=True)
    txt = p.stdout + p.stderr
    sha1 = re.search(r"SHA1:\s*([0-9A-Fa-f:]+)", txt)
    sha256 = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", txt)
    if p.returncode != 0 or not sha1 or not sha256:
        raise ValueError("senha ou alias errados para essa chave")
    return sha1.group(1), sha256.group(1)


def check_package(package):
    if not re.fullmatch(r"[A-Za-z0-9_.]+", package or ""):
        raise ValueError("nome de pacote inválido")


def keygen(package, cn="", org=""):
    check_package(package)
    old = store.android_key(package).get("file")
    if old and os.path.exists(old):
        raise ValueError("já existe uma chave para esse app — gerar outra impede atualizar o app na Play Store; "
                         "remova antes se tiver certeza")
    pw = ""
    while len(pw) < 24:
        pw += secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    pw = pw[:24]
    os.makedirs(store.ANDROID_KEYS_DIR, exist_ok=True)
    path = os.path.join(store.ANDROID_KEYS_DIR, package + ".p12")
    if os.path.exists(path):
        os.remove(path)  # arquivo órfão de uma tentativa anterior
    dname = f"CN={cn or package}, O={org or cn or package}, C=BR"
    p = subprocess.run(["keytool", "-genkeypair", "-keystore", path, "-storetype", "PKCS12", "-alias", "upload",
                        "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000", "-dname", dname,
                        "-storepass", pw, "-keypass", pw], capture_output=True, text=True)
    if p.returncode != 0:
        raise ValueError("keytool falhou: " + (p.stdout + p.stderr).strip()[-500:])
    os.chmod(path, 0o600)
    sha1, sha256 = fingerprints(path, pw, "upload")
    store.android_key_set(package, {"file": path, "storePassword": pw, "keyAlias": "upload", "keyPassword": pw,
                                    "sha1": sha1, "sha256": sha256, "created": int(time.time())})
    return store.android_key_public(package)


def key_import(package, data, store_password, key_alias, key_password, ext="p12"):
    check_package(package)
    ext = (ext or "p12").lower()
    if ext not in KEY_EXTS:
        raise ValueError("extensão de chave não suportada (use p12, pfx, jks ou keystore)")
    key_password = key_password or store_password
    os.makedirs(store.ANDROID_KEYS_DIR, exist_ok=True)
    path = os.path.join(store.ANDROID_KEYS_DIR, f"{package}.{ext}")
    tmp = path + ".new." + ext  # valida antes de substituir a chave que já existe
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o600)
    try:
        sha1, sha256 = fingerprints(tmp, store_password, key_alias)
    except Exception:
        os.remove(tmp)
        raise
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    old = store.android_key(package).get("file")
    if old and old != path and os.path.exists(old):
        os.remove(old)  # chave anterior com outra extensão, só depois do replace
    store.android_key_set(package, {"file": path, "storePassword": store_password, "keyAlias": key_alias,
                                    "keyPassword": key_password, "sha1": sha1, "sha256": sha256,
                                    "created": int(time.time())})
    return store.android_key_public(package)


def drop_edit(play, pkg, edit):
    try:
        play.edit_delete(pkg, edit)
    except PlayError:
        pass


def commit(play, pkg, edit):
    try:
        play.edit_commit(pkg, edit)
    except PlayError as e:
        if "changesNotSentForReview" not in str(e):
            raise
        play.edit_commit(pkg, edit, True)


def copy_newest(pattern, dest, what):
    found = glob.glob(pattern)
    if not found:
        raise SystemExit(f"o Gradle não gerou o {what}")
    shutil.copy2(max(found, key=os.path.getmtime), dest)
    return dest


def install_and_launch(apk, pkg, serial):
    """Install the APK on a phone connected by adb and open the app."""
    step("Instalando no celular Android")
    if not apk:
        raise SystemExit("não há APK para instalar")
    if not serial:
        out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
        found = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip().endswith("device")]
        if not found:
            raise SystemExit("nenhum celular Android conectado: pareie e conecte em Android → Instalar no celular")
        if len(found) > 1:
            raise SystemExit(f"há {len(found)} celulares conectados ({', '.join(found)}): escolha um em Projetos")
        serial = found[0]
    s = ["-s", serial]
    run(["adb", *s, "install", "-r", apk])
    run(["adb", *s, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
    log(f"\n\033[1;32m✔ {pkg} instalado e aberto em {serial}\033[0m")


def merge_meta(project, patch):
    cur = dict(store.project_meta(project).get("android", {}))
    cur.update(patch)
    store.project_meta_update(project, {"android": cur})


def publish_to_play(play, pkg, a, vn, vc, aab_out, apk_out, pdir):
    """Envia aab_out (ou apk_out) para a faixa da Play e grava lastRelease no projeto."""
    project = os.path.basename(pdir.rstrip("/\\"))
    track = a.get("track") or "internal"
    status = a.get("status") or "completed"
    notes = a.get("releaseNotes") or {}
    for loc, txt in notes.items():
        if len(txt) > 500:
            log(f"\033[33m⚠ notas em {loc} têm {len(txt)} caracteres; a Play aceita 500 e o texto será cortado\033[0m")
    name = f"{vn} ({vc})"
    final = status
    edit = play.edit_open(pkg)  # só agora: o edit não pode ficar aberto durante o build
    try:
        if aab_out:
            play.upload_bundle(pkg, edit, aab_out, log)
        else:
            play.upload_apk(pkg, edit, apk_out, log)
        play.set_track(pkg, edit, track, [vc], status, notes, name=name, user_fraction=a.get("userFraction"))
        try:
            commit(play, pkg, edit)
        except PlayError as e:
            if "draft" not in str(e).lower() or status == "draft":
                raise
            log("\033[33m⚠ o app ainda não foi publicado na Play; o lançamento vai como rascunho. "
                "Publique pelo Play Console.\033[0m")
            play.set_track(pkg, edit, track, [vc], "draft", notes, name=name)
            final = "draft"
            commit(play, pkg, edit)
    except Exception:
        drop_edit(play, pkg, edit)
        raise

    log(f"\n\033[1;32m✔ Enviado para a faixa {track} ({name}, status {final}).\033[0m")
    log("Confira em https://play.google.com/console")
    head = ""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=pdir, capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    merge_meta(project, {"lastRelease": {"versionName": vn, "versionCode": vc, "track": track,
                                         "commit": head, "at": time.time()}})


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        a = json.load(f)
    project = a["project"]
    pdir = os.path.join("/work", project)
    existing = (a.get("existing") or "").strip()
    if existing:  # build release já pronto: sem pré-build, sem Gradle, só confere e envia
        upload = bool(a.get("upload"))
        low = existing.lower()
        if not os.path.isfile(existing) or not low.endswith((".aab", ".apk")):
            raise SystemExit(f"o arquivo não existe ou não é .aab/.apk: {existing}")
        android_dir = os.path.realpath(os.path.join("/work", project, "xtool", "android"))
        if not os.path.realpath(existing).startswith(android_dir + os.sep):
            raise SystemExit("o arquivo precisa estar na pasta xtool/android do projeto")
        if re.search(r"-debug\.(aab|apk)$", os.path.basename(existing)):
            raise SystemExit("este é um build de debug: a Play só aceita release assinado")
        vn = (a.get("versionName") or "").strip()
        vcode = "" if a.get("versionCode") is None else str(a.get("versionCode")).strip()
        if not re.fullmatch(r"\d+(\.\d+){0,3}", vn) or not re.fullmatch(r"\d+", vcode):
            raise SystemExit("informe a versão e o versionCode do arquivo")
        vc = int(vcode)
        if not upload:
            raise SystemExit("nada a fazer: ligue o envio para a Play")
        info = detect(pdir) or {}
        pkg = (a.get("packageName") or info.get("packageName") or "").strip()
        if not pkg:
            raise SystemExit("não achei o packageName (applicationId) do app")

        step("1/2 Conferindo na Google Play")
        try:
            conta = store.play_account(a.get("playAccountId") or "")
        except ValueError as e:
            raise SystemExit(str(e))
        log(f"Conta: {conta.get('label')} ({conta.get('email')})")
        play = Play(conta["json"])
        max_play = play.app_info(pkg)["maxVersionCode"]  # abre e apaga o edit por dentro
        if vc <= max_play:
            raise SystemExit(f"o versionCode {vc} já existe na Play (último: {max_play}): compile um build novo")
        log(f"App: {pkg}")
        log(f"Versão {vn}, build {vc}")
        log(f"Arquivo: {existing}")
        if low.endswith(".apk") and shutil.which("aapt2"):
            badging = subprocess.run(["aapt2", "dump", "badging", existing], capture_output=True, text=True).stdout
            pl = next((ln for ln in badging.splitlines() if ln.startswith("package:")), "")
            if pl:
                log(pl)
            m = re.search(r"versionCode='(\d+)'", pl)
            if m and int(m.group(1)) != vc:
                log(f"\033[33m⚠ o versionCode dentro do APK ({m.group(1)}) é diferente de {vc}\033[0m")
            m = re.search(r"versionName='([^']*)'", pl)
            if m and m.group(1) != vn:
                log(f"\033[33m⚠ o versionName dentro do APK ({m.group(1)}) é diferente de {vn}\033[0m")

        step("2/2 Enviando para o Google Play")
        aab_out = existing if low.endswith(".aab") else None
        apk_out = existing if low.endswith(".apk") else None
        publish_to_play(play, pkg, a, vn, vc, aab_out, apk_out, pdir)
        merge_meta(project, {"lastVersionCode": vc, "lastVersionName": vn})
        return

    info = detect(pdir)
    if not info:
        raise SystemExit("o projeto não tem pasta android/ com Gradle")
    pkg = (a.get("packageName") or info["packageName"] or "").strip()
    if not pkg:
        raise SystemExit("não achei o packageName (applicationId) do app")
    meta = store.project_meta(project).get("android", {})
    upload = bool(a.get("upload"))
    debug = a.get("debug")
    if debug == "auto":  # quick builds from Projetos: signed release if the app has a key, else debug
        k = store.android_key(pkg)
        debug = not (k.get("file") and os.path.exists(k["file"]))
        if debug:
            log("\033[33mEste app ainda não tem chave de assinatura: gerando APK de debug "
                "(instala no celular, mas não serve para a Play Store).\033[0m")
    debug = bool(debug)
    kind = a.get("kind") or "aab"
    if debug:
        if upload:
            raise SystemExit("build de debug não pode ir para a Play (use release)")
        tasks = [":app:assembleDebug"]
    elif kind in TASKS:
        tasks = TASKS[kind]
    else:
        raise SystemExit(f"tipo de pacote desconhecido: {kind}")

    step("1/5 Conferindo versão")
    src = store.project_meta(project).get("versionSource") or "auto"
    vn = (a.get("versionName") or "").strip() or versions.resolve(pdir, src) \
        or meta.get("lastVersionName") or info["versionName"] or "1.0.0"
    if not (a.get("versionName") or "").strip() and src not in ("auto", "manual"):
        log(f"Versão lida de {src}")
    vcode = str(a.get("versionCode") or "auto")
    play = edit = None
    max_play = 0
    if upload:
        try:
            conta = store.play_account(a.get("playAccountId") or "")
        except ValueError as e:
            raise SystemExit(str(e))
        log(f"Conta: {conta.get('label')} ({conta.get('email')})")
        play = Play(conta["json"])
        max_play = play.app_info(pkg)["maxVersionCode"]  # abre e apaga o edit por dentro
    if vcode == "auto":
        vc = max(max_play, meta.get("lastVersionCode") or 0) + 1
    else:
        try:
            vc = int(vcode)
        except ValueError:
            raise SystemExit("versionCode precisa ser 'auto' ou um número")
        if upload and vc <= max_play:
            raise SystemExit(f"o build {vc} já existe na Play (último: {max_play})")
    log(f"App: {pkg}")
    log(f"Versão {vn}, build {vc}")

    step("2/5 Preparando o projeto web")
    pre = (a.get("preBuild") or "").strip()
    if pre == "-":
        log("Pré-build pulado (você escolheu pular).")
    else:
        cmd = pre or info["defaultPreBuild"]
        if cmd:
            run(["bash", "-lc", cmd], cwd=pdir)
        else:
            log("Não há pré-build para este projeto.")

    step("3/5 Compilando com Gradle")
    gdir = os.path.join(pdir, info["gradleDir"])
    gw = os.path.join(gdir, "gradlew")
    if not os.path.exists(gw):
        raise SystemExit(f"não achei o gradlew em {gdir}")
    os.chmod(gw, os.stat(gw).st_mode | 0o111)
    # Gradle from the command line ignores android.injected.version.*: an init script sets the
    # version on every variant of the app module, whatever the build.gradle does.
    init = os.path.join(pdir, "xtool", "android", "panel-version.init.gradle")
    os.makedirs(os.path.dirname(init), exist_ok=True)
    with open(init, "w", encoding="utf-8") as f:
        f.write(VERSION_INIT.replace("@CODE@", str(vc)).replace("@NAME@", json.dumps(vn)))
    props = [f"--init-script={init}"]
    if not debug:
        key = store.android_key(pkg)
        if not key.get("file") or not os.path.exists(key["file"]):
            raise SystemExit("este app ainda não tem chave de assinatura: gere ou importe em Android → Chave de assinatura")
        props += [f"-Pandroid.injected.signing.store.file={key['file']}",
                  f"-Pandroid.injected.signing.store.password={key['storePassword']}",
                  f"-Pandroid.injected.signing.key.alias={key['keyAlias']}",
                  f"-Pandroid.injected.signing.key.password={key.get('keyPassword') or key['storePassword']}"]
    env = dict(os.environ, ANDROID_VERSION_CODE=str(vc), ANDROID_VERSION_NAME=vn, CI="true")
    sdk = os.environ.get("ANDROID_HOME", "")
    lp = os.path.join(gdir, "local.properties")
    if sdk and not os.path.exists(lp):
        with open(lp, "w", encoding="utf-8") as f:
            f.write(f"sdk.dir={sdk}\n")
    run(["./gradlew", "--no-daemon", "--console=plain", *props, *tasks], cwd=gdir, env=env)

    step("4/5 Juntando os arquivos")
    out = os.path.join(pdir, "xtool", "android")
    os.makedirs(out, exist_ok=True)
    outs = os.path.join(gdir, "app", "build", "outputs")
    base = f"{project}-{vn}-{vc}"
    aab_out = apk_out = None
    if debug:
        apk_out = copy_newest(os.path.join(outs, "apk", "debug", "*.apk"),
                              os.path.join(out, f"{base}-debug.apk"), "APK de debug")
    else:
        if kind in ("aab", "both"):
            aab_out = copy_newest(os.path.join(outs, "bundle", "release", "*.aab"),
                                  os.path.join(out, f"{base}.aab"), "AAB")
        if kind in ("apk", "both"):
            apk_out = copy_newest(os.path.join(outs, "apk", "release", "*.apk"),
                                  os.path.join(out, f"{base}.apk"), "APK")
    files = [f for f in (aab_out, apk_out) if f]
    for f in files:
        log(f"{f} ({os.path.getsize(f) / 1e6:.1f} MB)")
    if apk_out and shutil.which("aapt2"):
        badging = subprocess.run(["aapt2", "dump", "badging", apk_out], capture_output=True, text=True).stdout
        pl = next((ln for ln in badging.splitlines() if ln.startswith("package:")), "")
        if pl:
            log(pl)
        m = re.search(r"versionCode='(\d+)'", pl)
        if m and int(m.group(1)) != vc:
            log(f"\033[33m⚠ o versionCode dentro do APK ({m.group(1)}) é diferente de {vc}\033[0m")
        m = re.search(r"versionName='([^']*)'", pl)
        if m and m.group(1) != vn:
            log(f"\033[33m⚠ o versionName dentro do APK ({m.group(1)}) é diferente de {vn}\033[0m")
    merge_meta(project, {"lastVersionCode": vc, "lastVersionName": vn,
                         "lastBuild": {"versionName": vn, "versionCode": vc, "files": files, "at": time.time()}})

    if a.get("install"):
        install_and_launch(apk_out, pkg, (a.get("serial") or "").strip())
        return
    if not upload:
        log("\nParado aqui (envio para a Play desligado).")
        return

    step("5/5 Enviando para o Google Play")
    publish_to_play(play, pkg, a, vn, vc, aab_out, apk_out, pdir)


if __name__ == "__main__":
    try:
        main()
    except (PlayError, SystemExit, Exception) as e:  # noqa
        if isinstance(e, SystemExit) and e.code in (0, None):
            raise
        log(f"\n\033[1;31m✖ {e}\033[0m")
        sys.exit(1)
