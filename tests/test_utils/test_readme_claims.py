"""README must advertise only what this build can actually do.

Two directions, because the failure was one-sided before: upstream text
promised videos, ~90 models, OCR/VQA/chatbot and a dozen exchange formats that
this fork pruned. These tests do not restate the whole feature list - they pin
the specific claims that were wrong, so restoring one of them fails loudly
until the feature is genuinely back (then delete the entry from the list).
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
READMES = ("README.md", "README_zh-CN.md")

# Model families that exist upstream but cannot be loaded by this build.
PHANTOM_MODEL_TYPES = (
    "yolov5",
    "yolov6",
    "yolov7",
    "yolov9",
    "yolov10",
    "yolov8_obb",
    "gold_yolo",
    "rfdetr",
    "grounding_dino",
    "deim",
    "dfine",
    "dwpose",
    "rtmo",
    "scrfd",
    "sam_hq",
    "mobilesam",
    "edge_sam",
    "ram_plus",
    "ppocr",
    "pp-ocr",
    "paddleocr-vl",
    "florence",
    "rex-omni",
    "qwen3-vl",
    "clrnet",
    "countgd",
    "yoloworld",
    "yolo-world",
    "yoloe",
    "locateanything",
    "tracktrack",
    "botsort",
    "bot-sort",
    "bytetrack",
    "depth anything",
    "rmbg",
)

# Capabilities this build does not have, in the wording upstream used.
PHANTOM_CAPABILITY_CLAIMS = (
    "支持`图像`和`视频`",
    "Supports both `images` and `images`",
    "Processes both `images` and `videos`",
    "支持远程推理服务",
    "Supports remote inference service",
    "DOTA",
    "VLM-R1",
    "ShareGPT",
    "ja_JP",
    "ko_KR",
)


def _read(name):
    with open(os.path.join(REPO_ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


# The "Fork scope" section is the one place where an absent feature may legally
# be named, so denylist checks look at every *other* section. Without this the
# test cannot tell "we support X" from "we do not support X".
SCOPE_HEADINGS = ("Fork scope", "分支范围")
# Model-family names are only policed inside sections that enumerate models:
# elsewhere they legitimately appear as credits (PPOCRLabel in Acknowledgement).
MODEL_SECTION_MARKERS = ("model", "模型")


def _sections(name):
    parts = re.split(r"(?m)^## ", _read(name))
    out = []
    for body in parts[1:]:
        heading = body.splitlines()[0].strip()
        out.append((heading, body))
    return out


def _claims_only(name):
    return " ".join(
        body
        for heading, body in _sections(name)
        if not any(marker in heading for marker in SCOPE_HEADINGS)
    )


def _model_sections(name):
    return " ".join(
        body
        for heading, body in _sections(name)
        if any(marker in heading.lower() for marker in MODEL_SECTION_MARKERS)
        and not any(marker in heading for marker in SCOPE_HEADINGS)
    )


class TestReadmeClaims(unittest.TestCase):
    def test_every_loadable_model_type_is_documented(self):
        from anylabeling.services.auto_labeling import _CUSTOM_MODELS

        for name in READMES:
            text = _read(name).lower()
            for model_type in _CUSTOM_MODELS:
                self.assertIn(
                    model_type.lower(),
                    text,
                    f"{name} does not mention loadable type {model_type}",
                )

    def test_no_phantom_model_families_are_advertised(self):
        for name in READMES:
            text = _model_sections(name).lower()
            self.assertTrue(text, f"{name} has no model section to check")
            for model_type in PHANTOM_MODEL_TYPES:
                self.assertNotIn(
                    model_type.lower(),
                    text,
                    f"{name} advertises {model_type}, which cannot load here",
                )

    def test_no_pruned_capability_claims_survive(self):
        for name in READMES:
            text = _claims_only(name)
            for claim in PHANTOM_CAPABILITY_CLAIMS:
                self.assertNotIn(
                    claim,
                    text,
                    f"{name} still claims {claim!r}, absent from this build",
                )

    def test_local_links_resolve(self):
        pattern = re.compile(r"\]\((\./[^#)]+)\)")
        for name in READMES:
            text = _read(name)
            for target in pattern.findall(text):
                path = os.path.normpath(
                    os.path.join(REPO_ROOT, os.path.dirname(name), target)
                )
                self.assertTrue(
                    os.path.exists(path),
                    f"{name} links to a missing path: {target}",
                )

    def test_upstream_credit_stays_visible(self):
        # The fork's GPL terms require the upstream brand and source URL.
        for name in READMES:
            text = _read(name)
            self.assertIn("CVHub520/X-AnyLabeling", text)
            self.assertIn("GPL-3.0", text)


class TestDocsInventory(unittest.TestCase):
    def test_readme_docs_lists_point_at_existing_files(self):
        docs_dir = os.path.join(REPO_ROOT, "docs")
        listed = set()
        for name in READMES:
            for target in re.findall(
                r"\]\((\./docs/[a-z_]+/[^)]+\.md)\)", _read(name)
            ):
                listed.add(os.path.normpath(os.path.join(REPO_ROOT, target)))
        self.assertTrue(listed)
        for path in listed:
            self.assertTrue(os.path.isfile(path), path)

    def test_every_shipped_doc_is_named_somewhere(self):
        # A doc file that exists but is never mentioned is how stale upstream
        # documentation quietly survives a feature removal. One README is
        # enough: the English page drops what only Chinese readers would look
        # for, and vice versa.
        combined = " ".join(_read(name) for name in READMES)
        unlisted = []
        for language in ("en", "zh_cn"):
            folder = os.path.join(REPO_ROOT, "docs", language)
            for filename in sorted(os.listdir(folder)):
                if filename.endswith(".md") and filename not in combined:
                    unlisted.append(f"docs/{language}/{filename}")
        self.assertEqual(unlisted, [])


if __name__ == "__main__":
    unittest.main()
