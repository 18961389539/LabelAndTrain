"""A broken embedded ICC profile must be named, not muted.

Qt logs ``fromIccProfile: failed minimal tag size sanity`` and
``invalid tag offset alignment`` for these files, and ``app.py`` silences the
whole ``qt.gui.icc`` category -- so the annotator saw a wrong-colored image and
nothing anywhere said why. ``icc_profile_issue`` does the reading;
``note_icc_profile`` says it out loud, once per file per session.
"""

import os
import os.path as osp
import struct
import unittest
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.utils import file_lifecycle  # noqa: E402
from anylabeling.views.labeling.utils.image import (  # noqa: E402
    icc_profile_issue,
)


def _profile(
    size=None,
    signature=b"acsp",
    tag_count=1,
    tags=((b"desc", 144, 20),),
    truncate=None,
):
    """A conformant 164-byte profile by default; break one field to test."""
    table = bytearray()
    body = bytearray()
    for _name, offset, length in tags:
        table += _name + struct.pack(">II", offset, length)
    # 128-byte header, then the 4-byte tag count, then the tag table.
    for _name, offset, length in tags:
        gap = offset - (132 + 12 * tag_count + len(body))
        if gap > 0:
            body += b"\x00" * gap
        body += b"\x00" * length
    total = 132 + len(table) + len(body)
    header = bytearray(128)
    header[0:4] = struct.pack(">I", total if size is None else size)
    header[36:40] = signature
    out = (
        bytes(header)
        + struct.pack(">I", tag_count)
        + bytes(table)
        + bytes(body)
    )
    if truncate is not None:
        out = out[:truncate]
    return out


def _jpeg(profile_bytes=None):
    parts = [b"\xff\xd8"]
    if profile_bytes is not None:
        payload = b"ICC_PROFILE\x00" + bytes([1, 1]) + profile_bytes
        parts.append(
            b"\xff\xe2" + struct.pack(">H", len(payload) + 2) + payload
        )
    parts.append(b"\xff\xda" + struct.pack(">H", 2))
    return b"".join(parts)


def _jpeg_chunks(chunks, declared_count):
    parts = [b"\xff\xd8"]
    for seq, data in chunks:
        payload = b"ICC_PROFILE\x00" + bytes([seq, declared_count]) + data
        parts.append(
            b"\xff\xe2" + struct.pack(">H", len(payload) + 2) + payload
        )
    parts.append(b"\xff\xda" + struct.pack(">H", 2))
    return b"".join(parts)


def _png(profile_bytes=None, compressed=True):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + b"\x00\x00\x00\x00"  # CRC is not what this check reads
        )

    parts = [b"\x89PNG\r\n\x1a\n", chunk(b"IHDR", b"\x00" * 13)]
    if profile_bytes is not None:
        body = b"ColorScape\x00\x00"
        body += zlib.compress(profile_bytes) if compressed else profile_bytes
        parts.append(chunk(b"iCCP", body))
    parts.append(chunk(b"IDAT", b"\x00" * 8))
    return b"".join(parts)


class TestIccProfileIssue(unittest.TestCase):
    def test_valid_profiles_pass(self):
        good = _profile()
        self.assertIsNone(icc_profile_issue(good))
        self.assertIsNone(icc_profile_issue(_jpeg(good)))
        self.assertIsNone(icc_profile_issue(_png(good)))

    def test_files_without_a_profile_are_not_flagged(self):
        self.assertIsNone(icc_profile_issue(_jpeg()))
        self.assertIsNone(icc_profile_issue(_png()))
        self.assertIsNone(icc_profile_issue(b"GIF89a" + b"\x00" * 40))
        self.assertIsNone(icc_profile_issue(None))
        self.assertIsNone(icc_profile_issue(b""))

    def test_short_profile_is_the_minimal_tag_size_case(self):
        reason = icc_profile_issue(_jpeg(_profile(truncate=100)))
        self.assertIn("128", reason)

    def test_missing_signature_is_reported(self):
        reason = icc_profile_issue(_jpeg(_profile(signature=b"AAAA")))
        self.assertIn("acsp", reason)

    def test_declared_length_mismatch_is_reported(self):
        reason = icc_profile_issue(_jpeg(_profile(size=999)))
        self.assertIn("999", reason)

    def test_tag_reaching_past_the_end_is_reported(self):
        # The classic "invalid tag offset alignment": the table points outside
        # the profile while the header still describes the bytes present.
        broken = bytearray(_profile())
        broken[136:140] = struct.pack(">I", len(broken) + 400)
        reason = icc_profile_issue(_jpeg(bytes(broken)))
        self.assertIn("标签", reason)

    def test_png_with_a_broken_profile_is_reported(self):
        reason = icc_profile_issue(_png(_profile(truncate=64)))
        self.assertIsNotNone(reason)

    def test_png_with_an_uncompressed_profile_payload_reports_empty(self):
        # iCCP data is zlib-compressed by spec; raw bytes here fail to
        # decompress, which reads as an empty profile rather than silence.
        self.assertEqual(
            icc_profile_issue(_png(_profile(), compressed=False)),
            "内嵌配置为空",
        )

    def test_multichunk_jpeg_profile_is_reassembled(self):
        good = _profile()
        first, second = good[:80], good[80:]
        self.assertIsNone(
            icc_profile_issue(_jpeg_chunks([(1, first), (2, second)], 2))
        )
        # out of order must not corrupt the verdict either
        self.assertIsNone(
            icc_profile_issue(_jpeg_chunks([(2, second), (1, first)], 2))
        )

    def test_missing_chunk_is_named(self):
        reason = icc_profile_issue(_jpeg_chunks([(1, _profile()[:80])], 2))
        self.assertIn("分块缺失", reason)

    def test_detection_never_raises_on_garbage(self):
        # A JPEG whose APP2 claims an absurd length: the walk gives up, and an
        # unreadable profile is not the same as a broken one.
        junk = b"\xff\xd8\xff\xe2" + struct.pack(">H", 4) + b"\x00\x00"
        self.assertIsNone(icc_profile_issue(junk))


class _Widget:
    def __init__(self):
        self.lines = []

    def status(self, text, msec=None):
        self.lines.append(text)


class TestNoteIccProfile(unittest.TestCase):
    def setUp(self):
        file_lifecycle._ICC_WARNED.clear()
        self.widget = _Widget()
        self.bad = _jpeg(_profile(truncate=100))

    def tearDown(self):
        file_lifecycle._ICC_WARNED.clear()

    def test_clean_image_says_nothing(self):
        self.assertFalse(
            file_lifecycle.note_icc_profile(
                self.widget, "C:/imgs/clean.jpg", _jpeg(_profile())
            )
        )
        self.assertEqual(self.widget.lines, [])

    def test_broken_profile_is_surfaced_in_chinese(self):
        self.assertTrue(
            file_lifecycle.note_icc_profile(
                self.widget, "C:/imgs/card.jpg", self.bad
            )
        )
        self.assertEqual(len(self.widget.lines), 1)
        self.assertIn("ICC", self.widget.lines[0])
        self.assertIn("颜色", self.widget.lines[0])

    def test_one_line_per_file_per_session(self):
        for _ in range(3):
            file_lifecycle.note_icc_profile(
                self.widget, "C:/imgs/card.jpg", self.bad
            )
        self.assertEqual(len(self.widget.lines), 1)

    def test_a_different_file_gets_its_own_line(self):
        file_lifecycle.note_icc_profile(self.widget, "C:/imgs/a.jpg", self.bad)
        file_lifecycle.note_icc_profile(self.widget, "C:/imgs/b.jpg", self.bad)
        self.assertEqual(len(self.widget.lines), 2)

    def test_path_spelling_does_not_double_the_notice(self):
        one = osp.abspath("C:/imgs/card.jpg")
        file_lifecycle.note_icc_profile(self.widget, one, self.bad)
        file_lifecycle.note_icc_profile(
            self.widget, one.upper() + os.sep, self.bad
        )
        self.assertEqual(len(self.widget.lines), 1)


if __name__ == "__main__":
    unittest.main()
