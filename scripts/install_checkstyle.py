#!/usr/bin/env python
"""Download the Checkstyle JAR needed by the Checkstyle linter.

Usage:
    python scripts/install_checkstyle.py [output.jar]
"""
from __future__ import annotations

import os
import sys
import urllib.request

CHECKSTYLE_VERSION = "13.9.0"
DEFAULT_OUTPUT = "checkstyle.jar"
URL = (
    "https://github.com/checkstyle/checkstyle/releases/download/"
    f"checkstyle-{CHECKSTYLE_VERSION}/checkstyle-{CHECKSTYLE_VERSION}-all.jar"
)


def main() -> int:
    output = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    if os.path.exists(output):
        print(f"{output} already exists, skipping download.")
        return 0
    print(f"Downloading Checkstyle {CHECKSTYLE_VERSION} -> {output} ...")
    try:
        urllib.request.urlretrieve(URL, output)
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    print("Done. Point CHECKSTYLE_JAR (or --checkstyle-jar) at this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
