#!/usr/bin/env python3
"""Build the Calibre-installable LubimyCzytac plugin ZIP."""
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "__init__.py"
DIST = ROOT / "dist"

# Keep this list explicit: only runtime files belong in the plugin package.
PACKAGE_FILES = (
    "__init__.py",
    "worker.py",
    "config.py",
    "plugin-import-name-lubimyczytac.txt",
    "images/lubimyczytac.png",
    "translations/pl.mo",
    "translations/cs.mo",
)

def plugin_version():
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"^\s*PLUGINVER\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
        text,
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("Nie udało się odczytać PLUGINVER z __init__.py.")
    return ".".join(match.groups())

def main():
    missing = [name for name in PACKAGE_FILES if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Brak wymaganych plików:\n  " + "\n  ".join(missing))

    version = plugin_version()
    DIST.mkdir(exist_ok=True)
    output = DIST / ("LubimyCzytac-" + version + ".zip")

    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PACKAGE_FILES:
            archive.write(ROOT / name, arcname=name)

    with zipfile.ZipFile(output, "r") as archive:
        actual = set(archive.namelist())
        expected = set(PACKAGE_FILES)
        if actual != expected:
            if output.exists():
                output.unlink()
            raise RuntimeError(
                "Nieprawidłowa zawartość ZIP-a.\n"
                "Brakujące: " + repr(sorted(expected - actual)) + "\n"
                "Nadmiarowe: " + repr(sorted(actual - expected))
            )
        bad_member = archive.testzip()
        if bad_member:
            if output.exists():
                output.unlink()
            raise RuntimeError("Uszkodzony element archiwum: " + bad_member)

    print("Utworzono:", output)
    print("Wersja:", version)
    print("Pliki w paczce:")
    for name in PACKAGE_FILES:
        print("  " + name)

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        print("Błąd budowania:", error, file=sys.stderr)
        sys.exit(1)
