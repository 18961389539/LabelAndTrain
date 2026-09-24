import os
import glob
import sys
import shutil
import subprocess
from PyQt6 import QtCore

#: Directories that never carry app strings. A bare ``**/*.py`` glob would
#: also walk the virtualenv and every build artefact, burying the real
#: strings under tens of thousands of dependency entries.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
}

#: Roots of the shipped application. Only this tree carries user-facing
#: strings, so tests and build scripts are left out and the catalog stays
#: free of assertion text.
SOURCE_ROOTS = ("anylabeling",)

#: Generated blobs: resources.py is a multi-megabyte byte literal, so there is
#: nothing to translate and parsing it just slows the extraction down.
SKIP_FILES = {"resources.py"}


def source_files() -> list[str]:
    """Python sources that can carry user-facing strings.

    Paths are normalized to forward slashes: pylupdate6 rejects backslashed
    arguments on Windows.
    """
    files = []
    for root in SOURCE_ROOTS:
        for path in glob.glob(
            os.path.join(root, "**", "*.py"), recursive=True
        ):
            normalized = path.replace("\\", "/")
            parts = normalized.split("/")
            if any(part in SKIP_DIRS for part in parts):
                continue
            if os.path.basename(normalized) in SKIP_FILES:
                continue
            files.append(normalized)
    return sorted(files)


def find_lupdate() -> str:
    """Return an available Qt string extractor."""
    candidates = ("pylupdate6", "pyside6-lupdate", "lupdate")
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            return executable
    raise RuntimeError(
        "No Qt string extractor found. 'pylupdate6' ships with PyQt6, so "
        "activate the project virtualenv (or add it to PATH) first."
    )


def find_lrelease() -> str:
    """Return an available Qt Linguist release compiler."""
    candidates = ("lrelease", "lrelease-qt6", "pyside6-lrelease")
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            return executable
    raise RuntimeError(
        "No Qt translation compiler found. Install lrelease or ensure "
        "pyside6-lrelease is available in the active environment."
    )


def compile_resources(output: str, qrc: str) -> None:
    """Compile a .qrc file to a PyQt6-compatible resources.py."""

    def normalize_imports(path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("from PySide6", "from PyQt6")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def add_rcc_commands(commands, base_command, needs_rewrite):
        # Force zlib resources when supported. Newer RCC builds may emit zstd
        # entries by default, which are not readable in some Windows Qt runtimes.
        commands.append(
            (
                [*base_command, "--compress-algo", "zlib", "-o", output, qrc],
                needs_rewrite,
            )
        )
        commands.append(([*base_command, "-o", output, qrc], needs_rewrite))

    commands = []
    add_rcc_commands(
        commands, [sys.executable, "-m", "PyQt6.pyrcc_main"], False
    )
    add_rcc_commands(commands, ["pyrcc6"], False)
    add_rcc_commands(commands, ["pyside6-rcc"], True)
    add_rcc_commands(commands, ["rcc", "-g", "python"], True)
    lrelease = shutil.which("lrelease")
    if lrelease:
        sibling_rcc = os.path.join(os.path.dirname(lrelease), "rcc")
        add_rcc_commands(commands, [sibling_rcc, "-g", "python"], True)
    for command, needs_rewrite in commands:
        executable = command[0]
        if executable != sys.executable and not shutil.which(executable):
            continue
        result = subprocess.run(command, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            continue
        if needs_rewrite:
            normalize_imports(output)
        return
    print(
        "Error: no Qt resource compiler found. Tried python -m PyQt6.pyrcc_main, pyrcc6, pyside6-rcc, rcc -g python, and lrelease-sibling rcc."
    )


TRANSLATIONS_DIR = "anylabeling/resources/translations"


def existing_catalogs():
    """Languages this checkout already ships a ``.ts`` catalog for."""
    return sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(TRANSLATIONS_DIR)
        if name.endswith(".ts")
    )


# Refresh what is there by default; name a language explicitly to start one
# that does not exist yet, e.g. ``generate_languages.py zh_CN en_US``.
supported_languages = sys.argv[1:] or existing_catalogs() or ["zh_CN"]
translations_path = TRANSLATIONS_DIR
lupdate = find_lupdate()
lrelease = find_lrelease()

for language in supported_languages:
    # Scan the project's own Python sources (never the virtualenv).
    py_files = source_files()
    if not py_files:
        raise RuntimeError(
            "No Python sources found to extract strings from."
        )
    print(f"Extracting from {len(py_files)} source files")

    # Create a QTranslator object to generate the .ts file
    translator = QtCore.QTranslator()

    # Translate all .ui files into .py files
    ui_files = glob.glob(os.path.join("**", "*.ui"), recursive=True)
    for ui_file in ui_files:
        py_file = os.path.splitext(ui_file)[0] + "_ui.py"
        command = f"pyuic6 -x {ui_file} -o {py_file}"
        os.system(command)

    # Extract translations from the .py file. Check the result: a missing
    # extractor used to print a shell error and then silently recompile the
    # stale .ts, which is how the catalog drifted out of date unnoticed.
    command = (
        f"{lupdate} --no-obsolete {' '.join(py_files)} "
        f"-ts {translations_path}/{language}.ts"
    )
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"String extraction failed (exit {result.returncode}). Is "
            "'pylupdate6' on PATH? Activate the project virtualenv first."
        )

    # Compile the .ts file into a .qm file
    translation_file = f"{translations_path}/{language}.ts"
    subprocess.run([lrelease, translation_file], check=True)

compile_resources(
    output="anylabeling/resources/resources.py",
    qrc="anylabeling/resources/resources.qrc",
)
