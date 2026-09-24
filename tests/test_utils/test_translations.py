"""The shipped zh_CN catalog must match the source tree.

The catalog used to be an inherited upstream artefact: 69 of its
``<location>`` entries pointed at files this YOLO-only fork deleted, and it
still advertised 725 strings for dialogs that no longer exist. Nothing
caught that, because nothing compared the catalog against the code.

These tests do, and they also check that the compiled ``.qm`` the app
actually loads still agrees with the ``.ts``.
"""

import os
import re
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    import anylabeling.resources.resources  # noqa: F401

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TS_PATH = os.path.join(
    REPO_ROOT, "anylabeling", "resources", "translations", "zh_CN.ts"
)
RESOURCE_QM = ":/languages/translations/zh_CN.qm"
APP_DIR = os.path.join(REPO_ROOT, "anylabeling")


def _load_catalog():
    return ET.parse(TS_PATH).getroot()


def _source_text():
    """Concatenated Python source of the application package."""
    chunks = []
    for base, dirs, files in os.walk(APP_DIR):
        dirs[:] = [name for name in dirs if name != "__pycache__"]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8", errors="ignore") as handle:
                chunks.append(handle.read())
    return "\n".join(chunks)


class TestCatalogMatchesSources(unittest.TestCase):

    def test_no_location_points_at_a_missing_file(self):
        """The bug: 772 locations referenced files that were deleted."""
        root = _load_catalog()
        ts_dir = os.path.dirname(TS_PATH)
        broken = set()
        for location in root.iter("location"):
            filename = location.get("filename")
            if not filename:
                continue
            if not os.path.exists(
                os.path.normpath(os.path.join(ts_dir, filename))
            ):
                broken.add(filename)
        self.assertEqual(
            sorted(broken),
            [],
            "zh_CN.ts points at files that do not exist. Re-run "
            "scripts/generate_languages.py to refresh the catalog.",
        )

    def test_every_context_is_a_live_class(self):
        """The bug: contexts like VideoClassifierDialog / PPOCRDialog were
        left over from upstream and no longer exist anywhere in the fork."""
        root = _load_catalog()
        class_names = set(
            re.findall(r"^class\s+(\w+)", _source_text(), re.MULTILINE)
        )
        unknown = sorted(
            {
                context.findtext("name")
                for context in root.findall("context")
            }
            - class_names
        )
        self.assertEqual(
            unknown,
            [],
            "zh_CN.ts still carries contexts for classes that are gone. "
            "Re-run scripts/generate_languages.py to drop them.",
        )

    def test_catalog_is_fully_translated(self):
        root = _load_catalog()
        unfinished = []
        for context in root.findall("context"):
            for message in context.findall("message"):
                translation = message.find("translation")
                text = "" if translation is None else (translation.text or "")
                if not text.strip():
                    unfinished.append(
                        (context.findtext("name"), message.findtext("source"))
                    )
        self.assertEqual(
            unfinished,
            [],
            f"{len(unfinished)} catalog entries have no Chinese text.",
        )


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for catalog compilation tests"
)
class TestCompiledCatalogIsInSync(unittest.TestCase):
    """The app loads the .qm from the Qt resource, not the .ts.

    A .ts edit without a rebuild is invisible at runtime, which is how the
    catalog drifted in the first place.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])
        cls.translator = QtCore.QTranslator()
        cls.loaded = cls.translator.load(RESOURCE_QM)
        if cls.loaded:
            cls.app.installTranslator(cls.translator)

    @classmethod
    def tearDownClass(cls):
        if cls.loaded:
            cls.app.removeTranslator(cls.translator)

    def test_compiled_resource_loads(self):
        self.assertTrue(
            self.loaded,
            f"{RESOURCE_QM} failed to load. Did resources.py get rebuilt "
            "after the .ts changed?",
        )

    def test_every_translated_entry_reaches_the_compiled_catalog(self):
        root = _load_catalog()
        compared = 0
        mismatches = []
        for context in root.findall("context"):
            name = context.findtext("name")
            for message in context.findall("message"):
                source = message.findtext("source") or ""
                translation = message.find("translation")
                expected = "" if translation is None else (
                    translation.text or ""
                ).strip()
                # Sources that are already Chinese translate to themselves,
                # so a missing rebuild is undetectable for them.
                if not expected or expected == source.strip():
                    continue
                compared += 1
                actual = QtCore.QCoreApplication.translate(name, source)
                if actual != expected:
                    mismatches.append((name, source, expected, actual))
        self.assertGreater(compared, 0)
        self.assertEqual(
            mismatches[:5],
            [],
            "The compiled .qm disagrees with zh_CN.ts -- run "
            "scripts/compile_languages.py after editing the catalog.",
        )
