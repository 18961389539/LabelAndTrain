"""The doc manifest and the user guides must not point at missing pages.

``docs/site.yml`` declared a ``video-classifier`` workflow whose document
exists in neither locale, and ``user_guide.md`` linked the same missing page
from its "Advanced Features" list.  Nothing looked: the manifest is not read
by any code path and a dead markdown link fails silently in every renderer.

These checks are deliberately narrow.  They do not crawl the whole tree for
links -- the archived upstream pages are full of external URLs -- only the
two places this fork is responsible for: its own manifest, and the relative
links out of the guides it maintains.
"""

import os
import re
import unittest

import yaml

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
SITE_YML = os.path.join(REPO_ROOT, "docs", "site.yml")
USER_GUIDES = (
    os.path.join("docs", "en", "user_guide.md"),
    os.path.join("docs", "zh_cn", "user_guide.md"),
)

RELATIVE_MD_LINK = re.compile(r"\]\((\./[^)#\s]+\.md)\)")


def _site_manifest():
    with open(SITE_YML, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestSiteManifest(unittest.TestCase):
    def test_every_workflow_document_exists_in_every_locale(self):
        manifest = _site_manifest()
        locales = manifest["docs"]["locales"]
        self.assertTrue(locales, "site.yml declares no locales")

        missing = []
        for workflow in manifest.get("workflows", []):
            for locale, directory in locales.items():
                path = os.path.join(
                    REPO_ROOT, directory, workflow["document"]
                )
                if not os.path.isfile(path):
                    missing.append((workflow["id"], locale, path))

        self.assertEqual(
            missing,
            [],
            "site.yml advertises workflows whose document is not in the "
            "tree; drop the entry or add the page",
        )

    def test_the_locale_directories_exist(self):
        for locale, directory in _site_manifest()["docs"]["locales"].items():
            self.assertTrue(
                os.path.isdir(os.path.join(REPO_ROOT, directory)),
                f"locale {locale!r} points at a missing directory",
            )


class TestUserGuideLinks(unittest.TestCase):
    def test_relative_markdown_links_resolve(self):
        broken = []
        for guide in USER_GUIDES:
            path = os.path.join(REPO_ROOT, guide)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for target in RELATIVE_MD_LINK.findall(text):
                resolved = os.path.normpath(
                    os.path.join(os.path.dirname(path), target)
                )
                if not os.path.isfile(resolved):
                    broken.append((guide, target))

        self.assertEqual(
            broken, [], "user_guide.md links to pages that are not there"
        )

    def test_the_guides_still_advertise_something_this_build_ships(self):
        """A guard on the guard: the link regex must keep matching."""
        for guide in USER_GUIDES:
            with open(os.path.join(REPO_ROOT, guide), encoding="utf-8") as fh:
                text = fh.read()
            self.assertTrue(
                RELATIVE_MD_LINK.findall(text),
                f"{guide} has no relative .md links left -- the pattern "
                "probably stopped matching, not the links",
            )


if __name__ == "__main__":
    unittest.main()
