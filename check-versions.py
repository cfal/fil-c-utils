#!/usr/bin/env python3
"""Compare every pinned upstream version against the latest release.

Each utility pins its source version in its Dockerfile. This reads those pins
and asks each upstream for its newest release, then prints one row per
component and exits nonzero if any pin is behind or could not be checked.

It never stops at the first problem. A component that cannot be reached, or an
upstream whose listing has changed shape, is reported as an error and the walk
continues: a single unreachable host must not hide a stale pin somewhere else.
Every component is always in the table.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMEOUT = 30
RETRIES = 3
UA = "fil-c-utils-version-check"


# --------------------------------------------------------------------- fetching
def _get(url, headers=None):
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
    raise RuntimeError(f"{url}: {last}")


def get_text(url, headers=None):
    return _get(url, headers).decode("utf-8", "replace")


def get_json(url):
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return json.loads(_get(url, headers))


# ---------------------------------------------------------------- version logic
def as_tuple(version):
    """Dotted numeric version to an int tuple, e.g. '26.02' -> (26, 2)."""
    parts = re.findall(r"\d+", version)
    if not parts:
        raise ValueError(f"no numbers in version {version!r}")
    return tuple(int(p) for p in parts)


STABLE = re.compile(r"^\d+(\.\d+)*$")


def is_stable(version):
    return bool(STABLE.match(version))


def newest(versions):
    stable = [v for v in versions if is_stable(v)]
    if not stable:
        raise RuntimeError("no stable versions found in upstream listing")
    return max(stable, key=as_tuple)


# ----------------------------------------------------------------- upstreams
def github_latest(repo, strip="", underscores=False):
    """Newest non-prerelease tag for a GitHub repository.

    Prefers the release marked "latest"; falls back to the tag list for
    projects that publish releases without setting that flag.
    """
    def norm(tag):
        if strip and tag.startswith(strip):
            tag = tag[len(strip):]
        return tag.replace("_", ".") if underscores else tag

    try:
        tag = get_json(f"https://api.github.com/repos/{repo}/releases/latest")["tag_name"]
        version = norm(tag)
        if is_stable(version):
            return version
    except RuntimeError:
        pass  # no "latest" release marked, or transient; try the tag list

    tags = get_json(f"https://api.github.com/repos/{repo}/tags")
    return newest(norm(t["name"]) for t in tags)


def gnu_ftp(name, directory=None):
    # libidn2 releases live in the gnu/libidn/ directory alongside libidn's, so
    # the listing to read and the file prefix to match are not always the same.
    html = get_text(f"https://ftp.gnu.org/gnu/{directory or name}/")
    return newest(re.findall(rf"{re.escape(name)}-(\d+(?:\.\d+)+)\.tar\.", html))


def sourceware_bzip2():
    html = get_text("https://sourceware.org/pub/bzip2/")
    return newest(re.findall(r"bzip2-(\d+(?:\.\d+)+)\.tar\.gz", html))


def rarlab_unrar():
    # rarlab has no API. The current UnRAR source is linked from the add-ons
    # page and the main download page; take whichever gives the higher version.
    found = []
    for url in ("https://www.rarlab.com/rar_add.htm", "https://www.rarlab.com/download.htm"):
        try:
            found += re.findall(r"unrarsrc-(\d+(?:\.\d+)+)\.tar\.gz", get_text(url))
        except RuntimeError:
            continue
    if not found:
        raise RuntimeError("no unrarsrc-*.tar.gz link found on rarlab.com")
    return newest(found)


# ------------------------------------------------------------------ components
# Each row: label, Dockerfile, the ARG holding the pin, and how to find latest.
COMPONENTS = [
    ("7z",      "7z/Dockerfile",    "SEVENZIP_VERSION", lambda: github_latest("ip7z/7zip")),
    ("unrar",   "unrar/Dockerfile", "UNRAR_VERSION",    rarlab_unrar),
    ("tar",     "tar/Dockerfile",   "TAR_VERSION",      lambda: gnu_ftp("tar")),
    ("gzip",    "gzip/Dockerfile",  "GZIP_VERSION",     lambda: gnu_ftp("gzip")),
    ("bzip2",   "bzip2/Dockerfile", "BZIP2_VERSION",    sourceware_bzip2),
    ("xz",      "xz/Dockerfile",    "XZ_VERSION",       lambda: github_latest("tukaani-project/xz", "v")),
    ("zstd",    "zstd/Dockerfile",  "ZSTD_VERSION",     lambda: github_latest("facebook/zstd", "v")),
    ("curl",    "curl/Dockerfile",  "CURL_VERSION",     lambda: github_latest("curl/curl", "curl-", underscores=True)),
    ("openssl", "curl/Dockerfile",  "OPENSSL_VERSION",  lambda: github_latest("openssl/openssl", "openssl-")),
    ("zlib",    "curl/Dockerfile",  "ZLIB_VERSION",     lambda: github_latest("madler/zlib", "v")),
    ("wget",         "wget/Dockerfile", "WGET_VERSION",         lambda: gnu_ftp("wget")),
    ("libunistring", "wget/Dockerfile", "LIBUNISTRING_VERSION", lambda: gnu_ftp("libunistring")),
    ("libidn2",      "wget/Dockerfile", "LIBIDN2_VERSION",      lambda: gnu_ftp("libidn2", directory="libidn")),
    ("libpsl",       "wget/Dockerfile", "LIBPSL_VERSION",       lambda: github_latest("rockdaboot/libpsl")),
    ("pcre2",        "wget/Dockerfile", "PCRE2_VERSION",        lambda: github_latest("PCRE2Project/pcre2", "pcre2-")),
    ("cares",        "wget/Dockerfile", "CARES_VERSION",        lambda: github_latest("c-ares/c-ares", "v")),
]


def pinned_version(dockerfile, arg):
    text = (ROOT / dockerfile).read_text()
    match = re.search(rf"^ARG {re.escape(arg)}=(\S+)", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{arg} not found in {dockerfile}")
    return match.group(1)


def main():
    rows = []
    for label, dockerfile, arg, fetch_latest in COMPONENTS:
        pin = latest = status = detail = None
        try:
            pin = pinned_version(dockerfile, arg)
        except RuntimeError as exc:
            status, detail = "ERROR", str(exc)

        if pin is not None:
            try:
                latest = fetch_latest()
                if as_tuple(pin) == as_tuple(latest):
                    status = "ok"
                elif as_tuple(pin) < as_tuple(latest):
                    status = "OUTDATED"
                else:
                    status, detail = "ahead", "pinned newer than detected latest"
            except (RuntimeError, ValueError) as exc:
                status, detail = "ERROR", str(exc)

        rows.append((label, pin or "?", latest or "?", status, detail))

    width = max([len("component")] + [len(r[0]) for r in rows])
    print(f"{'component':<{width}}  {'pinned':<10} {'latest':<10} status")
    print("-" * (width + 32))
    for label, pin, latest, status, detail in rows:
        line = f"{label:<{width}}  {pin:<10} {latest:<10} {status}"
        if detail:
            line += f"  ({detail})"
        print(line)

    outdated = [r[0] for r in rows if r[3] == "OUTDATED"]
    errored = [r[0] for r in rows if r[3] == "ERROR"]
    print()
    if outdated:
        print(f"behind upstream: {', '.join(outdated)}")
    if errored:
        print(f"could not check: {', '.join(errored)}")
    if outdated or errored:
        print("FAIL")
        return 1
    print("all pins are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
