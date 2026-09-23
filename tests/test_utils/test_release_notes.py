"""Release notes must describe this fork, not upstream's download channels.

The script inherited from upstream wrote a PyPI page and a Baidu Cloud folder
that belong to X-AnyLabeling's own releases -- readers of a release here would
have downloaded someone else's binaries. It also required an older tag to exist,
so the first tag on a fork checkout could not be documented at all.
"""

import importlib.util
import os
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def _load_script():
    path = os.path.join(REPO_ROOT, "scripts", "generate_release_notes.py")
    spec = importlib.util.spec_from_file_location("genrel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestReleaseNotes(unittest.TestCase):
    def setUp(self):
        self.module = _load_script()

    def test_tag_matches_the_declared_version(self):
        version = self.module.read_version()
        with self.assertRaises(ValueError):
            self.module.generate_notes("v0.0.0", "someone/repo")
        self.assertTrue(version, "app_info.py lost __version__")

    def test_top_changelog_entry_is_the_release_being_tagged(self):
        tag = f"v{self.module.read_version()}"
        with mock.patch.object(
            self.module, "find_previous_tag", return_value=None
        ):
            notes = self.module.generate_notes(tag, "someone/repo")
        # Anything below the fork marker is X-AnyLabeling's own history, and it
        # must not be pasted into this fork's release.
        self.assertIn("Review state per image", notes)
        self.assertNotIn("# X-AnyLabeling Changelog", notes)
        self.assertNotIn("v4.0.0-beta", notes)

    def test_first_release_works_without_an_older_tag(self):
        # git describe fails when nothing older is reachable; that must not
        # abort the notes, it just means there is nothing to compare against.
        tag = f"v{self.module.read_version()}"
        with mock.patch.object(
            self.module, "find_previous_tag", return_value=None
        ):
            notes = self.module.generate_notes(tag, "someone/repo")
        self.assertNotIn("compare/", notes)

    def test_notes_do_not_point_at_upstream_download_channels(self):
        tag = f"v{self.module.read_version()}"
        with mock.patch.object(
            self.module, "find_previous_tag", return_value="v0.0.1"
        ):
            notes = self.module.generate_notes(
                tag, "18961389539/LabelAndTrain"
            )
        self.assertNotIn("pypi.org", notes)
        self.assertNotIn("pan.baidu.com", notes)
        # Attribution to upstream stays, because the GPL requires it.
        self.assertIn("CVHub520/X-AnyLabeling", notes)
        self.assertIn(f"compare/v0.0.1...{tag}", notes)


if __name__ == "__main__":
    unittest.main()
