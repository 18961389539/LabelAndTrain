"""The shipped zh_CN catalog must match the source tree.

The catalog used to be an inherited upstream artefact: 69 of its
``<location>`` entries pointed at files this YOLO-only fork deleted, and it
still advertised 725 strings for dialogs that no longer exist. Nothing
caught that, because nothing compared the catalog against the code.

These tests do, and they also check that the compiled ``.qm`` the app
actually loads still agrees with the ``.ts``.
"""

import ast
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

#: Han ideographs. Enough to tell a Chinese source from an English one; CJK
#: punctuation and kana are not needed here, and treating them as "not Chinese"
#: only ever puts another string into the allowlist below.
_CJK = re.compile(r"[\u4e00-\u9fff]")


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
            # pylupdate6 writes separator-native paths: backslashes when the
            # catalog was built on Windows, which only resolve on Windows.
            # Normalise to forward slashes -- every os.path accepts them on
            # all three platforms -- so the check is platform-independent.
            candidate = os.path.normpath(
                os.path.join(ts_dir, *filename.replace("\\", "/").split("/"))
            )
            if not os.path.exists(candidate):
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
            {context.findtext("name") for context in root.findall("context")}
            - class_names
        )
        self.assertEqual(
            unknown,
            [],
            "zh_CN.ts still carries contexts for classes that are gone. "
            "Re-run scripts/generate_languages.py to drop them.",
        )

    def test_no_tr_call_is_invisible_to_the_extractor(self):
        """``widget.tr("...")`` never reaches the catalog, and says nothing.

        pylupdate6 can only name a context when it can see the receiver: a
        ``tr()`` call on ``self`` inside a class is attributed to that class,
        while the same call on *any other object* -- the widget a util
        function was handed -- is dropped from the catalog silently. That is
        how export.py shipped 21 dialog strings no locale could replace, and
        how the catalog once lost 772 locations without a sound.

        Module-level strings must use ``QCoreApplication.translate(ctx, ...)``,
        which the extractor does read; this test is what makes the difference
        visible at commit time instead of at translation time.
        """
        offenders = []
        for base, dirs, files in os.walk(APP_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if not name.endswith(".py") or name == "resources.py":
                    continue
                path = os.path.join(base, name)
                try:
                    tree = ast.parse(open(path, encoding="utf-8").read(), path)
                except SyntaxError:  # pragma: no cover - source is parsed
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "tr"
                        and isinstance(func.value, ast.Name)
                        and func.value.id not in ("self", "cls")
                    ):
                        rel = os.path.relpath(path, REPO_ROOT)
                        offenders.append(f"{rel}:{node.lineno}")
        self.assertEqual(
            sorted(offenders),
            [],
            f"{len(offenders)} tr() call(s) the extractor cannot place: "
            f"{sorted(offenders)[:8]}. Use "
            'QCoreApplication.translate("<context>", ...) -- a literal in '
            "these never enters zh_CN.ts.",
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

    #: Sources whose Chinese *is* the same characters: technical names the UI
    #: shows untranslated on purpose (metric labels, model-family names), and
    #: placeholder-only strings with no words to translate. Two-sided on
    #: purpose -- a new entry here is a string that stopped being answered in
    #: Chinese, and a vanished one means this list carries dead weight.
    SELF_TRANSLATING = {
        "AMG",
        "AI",
        "(unknown)",
        "YOLO HBB",
        "YOLO Seg",
        "YOLO OBB",
        "YOLO Pose",
        "loss %1",
        "mAP50 %1",
        "<b>%s</b>",
        "X: %d, Y: %d",
        "X: %d, Y: %d | H: %d, W: %d",
        "（%1）",
        "· %1x%2",
    }

    def _latin_only_messages(self):
        """(context, source, translation, type) for sources with no CJK.

        These are the strings where the catalog carries the whole weight of
        the UI: the fork writes Chinese sources, so an English source reaching
        the screen means the catalog did not answer it.
        """
        root = _load_catalog()
        rows = []
        for context in root.findall("context"):
            for message in context.findall("message"):
                source = (message.findtext("source") or "").strip()
                if not source or _CJK.search(source):
                    continue
                translation = message.find("translation")
                text = "" if translation is None else (translation.text or "")
                kind = (
                    ""
                    if translation is None
                    else (translation.get("type") or "")
                )
                rows.append(
                    (context.findtext("name"), source, text.strip(), kind)
                )
        return rows

    def test_every_english_source_is_answered_in_chinese(self):
        rows = self._latin_only_messages()
        self.assertGreater(len(rows), 900, "the scan found nothing to check")
        silent = [
            (ctx, src)
            for ctx, src, text, kind in rows
            if not text or kind == "unfinished"
        ]
        self.assertEqual(
            silent,
            [],
            f"{len(silent)} English source(s) would render as English: "
            f"{silent[:6]}",
        )

    def test_only_the_listed_english_names_are_left_as_they_are(self):
        rows = self._latin_only_messages()
        identical = {src for _, src, text, _ in rows if text == src}
        self.assertEqual(
            identical - self.SELF_TRANSLATING,
            set(),
            f"new English-on-screen strings: {sorted(identical - self.SELF_TRANSLATING)}",
        )
        self.assertEqual(
            self.SELF_TRANSLATING - identical,
            set(),
            f"no longer in the catalog, drop from SELF_TRANSLATING: "
            f"{sorted(self.SELF_TRANSLATING - identical)}",
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
                expected = (
                    ""
                    if translation is None
                    else (translation.text or "").strip()
                )
                # Sources that are already Chinese translate to themselves,
                # so a missing rebuild is undetectable for them.
                if not expected or expected == source.strip():
                    continue
                compared += 1
                # Both sides are stripped. A translation may deliberately
                # carry leading or trailing space -- 「 Deletion cannot be
                # undone.」 is appended to a "、"-joined list -- and this
                # check is about the words reaching the compiled catalog,
                # not about the padding around them.
                actual = QtCore.QCoreApplication.translate(
                    name, source
                ).strip()
                if actual != expected:
                    mismatches.append((name, source, expected, actual))
        self.assertGreater(compared, 0)
        self.assertEqual(
            mismatches[:5],
            [],
            "The compiled .qm disagrees with zh_CN.ts -- run "
            "scripts/compile_languages.py after editing the catalog.",
        )
