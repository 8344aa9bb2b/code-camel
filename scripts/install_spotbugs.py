#!/usr/bin/env python
"""Download and unpack the SpotBugs distribution.

SpotBugs ships as a zip that contains the analysis jar plus its
dependency jars under ``lib/``. This script downloads and extracts it,
then prints the path to ``spotbugs.jar`` for the SPOTBUGS_JAR setting.

Usage:
    python scripts/install_spotbugs.py [install_dir]
"""
from __future__ import annotations

import os
import sys
import urllib.request
import zipfile

SPOTBUGS_VERSION = "4.10.3"
DEFAULT_DIR = "spotbugs-dist"
URL = (
    "https://github.com/spotbugs/spotbugs/releases/download/"
    f"{SPOTBUGS_VERSION}/spotbugs-{SPOTBUGS_VERSION}.zip"
)
JAR = os.path.join(
    f"spotbugs-{SPOTBUGS_VERSION}", "lib", "spotbugs.jar"
)


def main() -> int:
    install_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    os.makedirs(install_dir, exist_ok=True)
    jar_path = os.path.join(install_dir, JAR)
    if os.path.exists(jar_path):
        print(f"{jar_path} already exists, skipping download.")
        return 0

    zip_path = os.path.join(install_dir, f"spotbugs-{SPOTBUGS_VERSION}.zip")
    print(f"Downloading SpotBugs {SPOTBUGS_VERSION} -> {zip_path} ...")
    try:
        urllib.request.urlretrieve(URL, zip_path)
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    print("Extracting ...")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(install_dir)
    except zipfile.BadZipFile as exc:  # pragma: no cover - corrupted dl
        print(f"Extract failed: {exc}", file=sys.stderr)
        return 1
    finally:
        os.remove(zip_path)

    print(f"Done. Point SPOTBUGS_JAR (or --spotbugs-jar) at {jar_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
