import unittest

from anylabeling.views.labeling.utils.shortcuts_help import (
    SHORTCUT_GROUPS,
    build_shortcut_rows,
    filter_shortcut_rows,
)


SAMPLE = {
    "open": "Ctrl+I",
    "open_next": "D",
    "open_prev": "A",
    "create_rectangle": "R",
    "undo": "Ctrl+Z",
    "undo_last_point": "Ctrl+Z",
    "save": None,
    "zoom_in": ["Ctrl++", "Ctrl+="],
}


class TestBuildShortcutRows(unittest.TestCase):

    def test_groups_cover_known_keys(self):
        keys = {
            key
            for _title, entries in SHORTCUT_GROUPS
            for key, _desc in entries
        }
        self.assertIn("create_rectangle", keys)
        self.assertIn("auto_labeling_run", keys)
        self.assertIn("open_settings", keys)

    def test_builds_rows_and_skips_empty(self):
        rows = build_shortcut_rows(SAMPLE)
        texts = {row[1] for row in rows}
        self.assertIn("D", texts)          # open_next
        self.assertIn("Ctrl+I", texts)     # open
        # save is None -> skipped
        self.assertFalse(any(row[2] == "保存标注" for row in rows))

    def test_hidden_key_excluded(self):
        rows = build_shortcut_rows(SAMPLE)
        self.assertFalse(
            any("撤销最后一点" in row[2] for row in rows)
        )

    def test_list_shortcut_joined(self):
        rows = build_shortcut_rows(SAMPLE)
        zoom = [row for row in rows if row[2] == "放大"]
        self.assertEqual(len(zoom), 1)
        self.assertEqual(zoom[0][1], "Ctrl++ / Ctrl+=")

    def test_non_dict_input(self):
        self.assertEqual(build_shortcut_rows(None), [])
        self.assertEqual(build_shortcut_rows([]), [])


class TestFilterShortcutRows(unittest.TestCase):

    def test_filter_by_description(self):
        rows = build_shortcut_rows(SAMPLE)
        matched = filter_shortcut_rows(rows, "下一张")
        self.assertTrue(matched)
        self.assertTrue(all("下一张" in row[2] for row in matched))

    def test_filter_by_key(self):
        rows = build_shortcut_rows(SAMPLE)
        matched = filter_shortcut_rows(rows, "Ctrl+z")
        self.assertTrue(matched)
        self.assertTrue(all("CTRL+Z" in row[1].upper() for row in matched))

    def test_empty_query_returns_all(self):
        rows = build_shortcut_rows(SAMPLE)
        self.assertEqual(filter_shortcut_rows(rows, ""), rows)
        self.assertEqual(filter_shortcut_rows(rows, None), rows)

    def test_no_match_returns_empty(self):
        rows = build_shortcut_rows(SAMPLE)
        self.assertEqual(filter_shortcut_rows(rows, "zzzz"), [])


class TestAdvertisedShortcuts(unittest.TestCase):
    """The help dialog is the only place users learn the bindings, so a row
    must never point at a key that nothing reads (see the six `create_*`
    keys that were advertised for years without a QAction)."""

    def setUp(self):
        from anylabeling.views.labeling.settings.schema import (
            SHORTCUT_DUPLICATE_WHITELIST,
            load_template_config,
        )

        self.shortcuts = load_template_config().get("shortcuts", {})
        self.whitelist = SHORTCUT_DUPLICATE_WHITELIST

    def test_every_advertised_key_exists_in_config(self):
        unknown = sorted(
            key
            for _title, entries in SHORTCUT_GROUPS
            for key, _desc in entries
            if key not in self.shortcuts
        )
        self.assertEqual(
            unknown, [], "help rows pointing at missing config keys"
        )

    def test_no_duplicate_rows(self):
        pairs = [
            (title, key)
            for title, entries in SHORTCUT_GROUPS
            for key, _desc in entries
        ]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_no_ambiguous_binding(self):
        by_value = {}
        for key, value in self.shortcuts.items():
            for item in value if isinstance(value, list) else [value]:
                if item:
                    by_value.setdefault(str(item), []).append(key)
        ambiguous = {
            value: sorted(keys)
            for value, keys in by_value.items()
            if len(keys) > 1
            and frozenset(f"shortcuts.{k}" for k in keys)
            not in self.whitelist
        }
        self.assertEqual(
            ambiguous, {}, "two actions share one key: Qt drops both"
        )

    def test_every_supported_shape_is_advertised(self):
        from anylabeling.views.labeling.shape import Shape

        advertised = {
            key
            for _title, entries in SHORTCUT_GROUPS
            for key, _desc in entries
        }
        missing = sorted(
            f"create_{shape}"
            for shape in Shape.get_supported_shape()
            if f"create_{shape}" not in advertised
        )
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
