#!/usr/bin/env python3
"""Build → sign for App Store → upload → (optionally) publish. Runs as a panel job.

usage: release.py <args.json>
args: project, accountId, version, build ("auto" or number), steps: {upload, publish, submit},
      whatsNew: {locale: text}, noEncryption: bool
"""
import glob
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402
from asc import ASC, AscError  # noqa: E402

SDK = os.path.expanduser("~/.swiftpm/swift-sdks/darwin.artifactbundle")


def log(msg=""):
    print(msg, flush=True)


def step(title):
    log(f"\n\033[1;36m▶ {title}\033[0m")


def run(cmd, cwd=None, **kw):
    log(f"\033[2m$ {' '.join(cmd)}\033[0m")
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, **kw)
    out = (p.stdout + p.stderr).strip()
    if out:
        log(out[-6000:])
    if p.returncode != 0:
        raise SystemExit(f"comando falhou (código {p.returncode})")
    return p.stdout


def read_yaml_bundle(project_dir):
    try:
        txt = open(os.path.join(project_dir, "xtool.yml")).read()
    except OSError:
        return {}
    out = {}
    for k in ("bundleID", "orgID", "iconPath", "entitlementsPath", "product", "infoPath"):
        m = re.search(rf"^{k}:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", txt, re.M)
        if m:
            out[k] = m.group(1).strip()
    return out


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def dt_keys():
    """Values Xcode stamps into Info.plist, read from the installed Xcode SDK."""
    keys = {"DTPlatformName": "iphoneos", "DTCompiler": "com.apple.compilers.llvm.clang.1_0"}
    try:
        settings = json.load(open(glob.glob(f"{SDK}/**/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk/SDKSettings.json",
                                            recursive=True)[0]))
        ver = settings.get("Version")
        keys.update({"DTPlatformVersion": ver, "DTSDKName": f"iphoneos{ver}"})
    except (IndexError, OSError, ValueError):
        pass
    for f in glob.glob(f"{SDK}/**/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk/System/Library/CoreServices/SystemVersion.plist",
                       recursive=True)[:1]:
        sv = plistlib.load(open(f, "rb"))
        keys["DTSDKBuild"] = sv.get("ProductBuildVersion")
        keys["DTPlatformBuild"] = sv.get("ProductBuildVersion")
    try:
        xv = plistlib.load(open(f"{SDK}/Xcode.app/Contents/version.plist", "rb"))
        xi = plistlib.load(open(f"{SDK}/Xcode.app/Contents/Info.plist", "rb"))
        keys["DTXcodeBuild"] = xv.get("ProductBuildVersion")
        keys["DTXcode"] = xi.get("DTXcode")
        keys["BuildMachineOSBuild"] = xi.get("BuildMachineOSBuild") or xi.get("DTPlatformBuild")
    except OSError:
        pass
    return {k: v for k, v in keys.items() if v}


def compile_icons(project_dir, conf, app_dir, info, work):
    catalogs = [p for p in glob.glob(os.path.join(project_dir, "**", "*.xcassets"), recursive=True)
                if "/xtool/" not in p and "/.build/" not in p]
    icon_png = conf.get("iconPath") and os.path.join(project_dir, conf["iconPath"])
    if not catalogs and icon_png and os.path.exists(icon_png):
        size = png_size(icon_png)
        if size != (1024, 1024):
            log(f"\033[33m⚠ o ícone {conf['iconPath']} tem {size}, a App Store pede 1024x1024\033[0m")
        cat = os.path.join(work, "Generated.xcassets")
        iconset = os.path.join(cat, "AppIcon.appiconset")
        os.makedirs(iconset, exist_ok=True)
        shutil.copy(icon_png, os.path.join(iconset, "icon.png"))
        json.dump({"info": {"author": "xcode", "version": 1}}, open(os.path.join(cat, "Contents.json"), "w"))
        json.dump({"images": [{"filename": "icon.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"}],
                   "info": {"author": "xcode", "version": 1}}, open(os.path.join(iconset, "Contents.json"), "w"))
        catalogs = [cat]
    if not catalogs:
        log("\033[33m⚠ nenhum ícone (Assets.xcassets ou iconPath no xtool.yml). A Apple recusa apps sem ícone.\033[0m")
        return
    out = os.path.join(work, "assets-out")
    os.makedirs(out, exist_ok=True)
    partial = os.path.join(out, "partial.plist")
    run(["accord", "--compile", out, "--platform", "iphoneos",
         "--minimum-deployment-target", str(info.get("MinimumOSVersion", "17.0")),
         "--app-icon", "AppIcon", "--target-device", "iphone", "--target-device", "ipad",
         "--output-partial-info-plist", partial, *catalogs])
    for f in os.listdir(out):
        if f != "partial.plist":
            shutil.copy(os.path.join(out, f), os.path.join(app_dir, f))
    if os.path.exists(partial):
        info.update(plistlib.load(open(partial, "rb")))
    old = info.pop("CFBundleIconFile", None)
    if old and os.path.exists(os.path.join(app_dir, old + ".png")):
        os.remove(os.path.join(app_dir, old + ".png"))
    log("Ícones compilados em Assets.car")


def entitlements_from_profile(profile_bytes, project_dir, conf):
    pl = subprocess.run(["openssl", "smime", "-verify", "-noverify", "-inform", "DER"], input=profile_bytes,
                        capture_output=True).stdout
    prof = plistlib.loads(pl)
    ent = dict(prof.get("Entitlements", {}))
    team = (prof.get("TeamIdentifier") or [""])[0]
    app_id = ent.get("application-identifier", "")
    ent["get-task-allow"] = False
    if "keychain-access-groups" in ent:
        ent["keychain-access-groups"] = [app_id]
    if conf.get("entitlementsPath"):
        try:
            mine = plistlib.load(open(os.path.join(project_dir, conf["entitlementsPath"]), "rb"))
            for k, v in mine.items():
                if k in ent or k.startswith("com.apple.developer."):
                    ent[k] = v
        except OSError:
            pass
    return ent, team


def main():
    a = json.load(open(sys.argv[1]))
    project = a["project"]
    pdir = os.path.join("/work", project)
    conf = read_yaml_bundle(pdir)
    steps = a.get("steps", {})
    acc = store.account(a["accountId"])
    key = store.asc_key(a["accountId"])
    asc = ASC(key.get("issuerId"), key.get("keyId"), key.get("p8"))

    step("1/6 Conferindo o app no App Store Connect")
    bundle = a.get("bundleId") or conf.get("bundleID") or ""
    if not bundle:
        raise SystemExit("defina bundleID no xtool.yml")
    app = asc.app_by_bundle(bundle)
    app_id = app["id"]
    log(f"App: {app['attributes'].get('name')} ({bundle}) — conta {acc.get('label')}")
    version = a["version"].strip()
    build = str(a.get("build") or "auto")
    if build == "auto":
        nums = [int(b["version"]) for b in asc.builds(app_id, 50) if str(b.get("version", "")).isdigit()]
        build = str(max(nums + [0]) + 1)
    log(f"Versão {version}, build {build}")

    step("2/6 Compilando em modo release")
    run(["xtool", "dev", "build", "-c", "release"], cwd=pdir)
    apps = glob.glob(os.path.join(pdir, "xtool", "*.app"))
    if not apps:
        raise SystemExit("o build não gerou nenhum .app")
    src_app = max(apps, key=os.path.getmtime)
    work = os.path.join(pdir, "xtool", "release")
    shutil.rmtree(work, ignore_errors=True)
    payload = os.path.join(work, "Payload")
    os.makedirs(payload)
    app_dir = os.path.join(payload, os.path.basename(src_app))
    shutil.copytree(src_app, app_dir, symlinks=True)

    step("3/6 Preparando Info.plist e ícones")
    info_p = os.path.join(app_dir, "Info.plist")
    info = plistlib.load(open(info_p, "rb"))
    info["CFBundleShortVersionString"] = version
    if info.get("CFBundleIdentifier") != bundle:  # project linked to an App Store app with another ID
        log(f"Bundle ID: {info.get('CFBundleIdentifier')} → {bundle} (app vinculado)")
        info["CFBundleIdentifier"] = bundle
    info["CFBundleVersion"] = build
    info.update(dt_keys())
    if a.get("noEncryption", True):
        info.setdefault("ITSAppUsesNonExemptEncryption", False)
    compile_icons(pdir, conf, app_dir, info, work)
    plistlib.dump(info, open(info_p, "wb"), fmt=plistlib.FMT_BINARY)
    log("Info.plist: " + ", ".join(f"{k}={info.get(k)}" for k in ("DTSDKName", "DTXcode", "CFBundleIconName")))

    step("4/6 Assinando para a App Store")
    sign_dir = store.signing_dir(a["accountId"])
    cert_id, key_pem, cert_pem = asc.ensure_distribution_cert(sign_dir, log)
    profile = asc.app_store_profile(bundle, cert_id, log)
    open(os.path.join(app_dir, "embedded.mobileprovision"), "wb").write(profile)
    ent, team = entitlements_from_profile(profile, pdir, conf)
    ent_f = os.path.join(work, "entitlements.plist")
    plistlib.dump(ent, open(ent_f, "wb"))
    for nested in sorted(glob.glob(os.path.join(app_dir, "**", "*.framework"), recursive=True) +
                         glob.glob(os.path.join(app_dir, "**", "*.dylib"), recursive=True), key=len, reverse=True):
        run(["rcodesign", "sign", "--pem-file", cert_pem, "--pem-file", key_pem, nested])
    run(["rcodesign", "sign", "--pem-file", cert_pem, "--pem-file", key_pem,
         "--entitlements-xml-file", ent_f, app_dir])
    ipa = os.path.join(pdir, "xtool", f"{project}-{version}-{build}.ipa")
    if os.path.exists(ipa):
        os.remove(ipa)
    run(["zip", "-qry", ipa, "Payload"], cwd=work)
    log(f"IPA pronto: {ipa}")

    if not steps.get("upload"):
        log("\nParado aqui (envio desligado).")
        return
    step("5/6 Enviando para o App Store Connect")
    asc.upload_ipa(app_id, ipa, version, build, log)
    store.project_meta_update(project, {"lastUpload": {"version": version, "build": build, "at": time.time()}})

    if not steps.get("publish"):
        log("\nBuild enviado. Ele aparece no TestFlight quando a Apple terminar de processar.")
        return
    step("6/6 Publicando a versão na App Store")
    build_id = asc.wait_build(app_id, version, build, log)
    if a.get("noEncryption", True):
        asc.set_no_encryption(build_id)
    ver_id = asc.ensure_version(app_id, version, log)
    asc.set_whats_new(ver_id, a.get("whatsNew") or {}, log)
    asc.attach_build(ver_id, build_id, log)
    if steps.get("submit"):
        asc.submit_for_review(app_id, ver_id, log)
        log("\n\033[1;32m✔ Versão enviada para revisão. A Apple avisa por e-mail.\033[0m")
    else:
        log("\n\033[1;32m✔ Versão pronta no App Store Connect (não enviada para revisão).\033[0m")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=pdir, capture_output=True, text=True).stdout.strip()
    store.project_meta_update(project, {"lastRelease": {"version": version, "build": build,
                                                        "commit": head, "at": time.time()}})


if __name__ == "__main__":
    try:
        main()
    except (AscError, SystemExit, Exception) as e:  # noqa
        if isinstance(e, SystemExit) and e.code in (0, None):
            raise
        log(f"\n\033[1;31m✖ {e}\033[0m")
        sys.exit(1)
