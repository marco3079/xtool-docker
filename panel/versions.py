"""Where a project keeps its app version.

Each project picks a source in the panel (stored as projects.json → versionSource):
"auto" (next version after the last one sent to the store), "manual" (typed every time)
or one of the files below. Only sources that hold a version show up as options.
"""
import glob
import json
import os
import plistlib
import re
import subprocess

VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def _package_json(d):
    try:
        return str(json.loads(_read(os.path.join(d, "package.json")) or "{}").get("version") or "")
    except ValueError:
        return ""


def _xtool_yml(d):
    m = re.search(r"^version:\s*['\"]?([^'\"\n#]+?)['\"]?\s*$", _read(os.path.join(d, "xtool.yml")), re.M)
    v = m.group(1).strip() if m else ""
    return "" if re.fullmatch(r"\d+", v) else v  # a bare "1" is xtool's schema number


def _gradle(d):
    for gdir in ("android", "."):
        for name in ("build.gradle", "build.gradle.kts"):
            txt = _read(os.path.join(d, gdir, "app", name))
            # versionName "1.2.0", versionName = "1.2.0" or versionName(System.getenv('X') ?: '1.2.0')
            m = re.search(r"versionName\b[^\n]*?[\"'](\d[^\"']*)[\"']", txt)
            if m:
                return m.group(1)
    return ""


def _xcode(d):
    for pbx in glob.glob(os.path.join(d, "ios", "*", "*.xcodeproj", "project.pbxproj")) + \
            glob.glob(os.path.join(d, "*.xcodeproj", "project.pbxproj")):
        m = re.search(r"MARKETING_VERSION\s*=\s*\"?([\d.]+)\"?;", _read(pbx))
        if m:
            return m.group(1)
    for info in glob.glob(os.path.join(d, "ios", "*", "*", "Info.plist")):
        try:
            with open(info, "rb") as f:
                v = str(plistlib.load(f).get("CFBundleShortVersionString") or "")
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
        if v and "$(" not in v:
            return v
    return ""


def _git_tag(d):
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    # nearest tag behind HEAD; if none is reachable (tag made on another branch), the newest tag
    tag = git("describe", "--tags", "--abbrev=0") or \
        next(iter(git("tag", "--sort=-creatordate").splitlines()), "")
    m = re.search(r"(\d+(?:\.\d+){0,3})$", tag)
    return m.group(1) if m else ""


SOURCES = [
    ("package.json", "package.json (version)", _package_json),
    ("xtool.yml", "xtool.yml (version)", _xtool_yml),
    ("gradle", "build.gradle do Android (versionName)", _gradle),
    ("xcode", "projeto Xcode do iOS (MARKETING_VERSION)", _xcode),
    ("git-tag", "última tag do git", _git_tag),
]


def sources(project_dir):
    """Version sources that exist in this project: [{"id","label","value"}]."""
    out = []
    for sid, label, fn in SOURCES:
        v = fn(project_dir)
        if v:
            out.append({"id": sid, "label": label, "value": v})
    return out


def resolve(project_dir, source):
    """Version from the chosen source, or "" for auto/manual/unknown/missing."""
    for sid, _, fn in SOURCES:
        if sid == source:
            return fn(project_dir)
    return ""
