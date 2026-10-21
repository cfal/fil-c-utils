#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_versions", ROOT / "check-versions.py"
)
VERSIONS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERSIONS)


class GitHubLatestTests(unittest.TestCase):
    def test_numeric_prerelease_tag_does_not_override_stable_release(self):
        def response(url):
            if "/releases?" in url:
                return [
                    {"tag_name": "26.05", "draft": False, "prerelease": True},
                    {"tag_name": "26.04", "draft": False, "prerelease": False},
                ]
            if "/tags?" in url:
                return [{"name": "26.05"}, {"name": "26.04"}]
            self.fail(f"unexpected URL: {url}")

        with mock.patch.object(VERSIONS, "get_json", side_effect=response):
            self.assertEqual(VERSIONS.github_latest("example/project"), "26.04")

    def test_unreleased_stable_tag_is_considered(self):
        def response(url):
            if "/releases?" in url:
                return [
                    {"tag_name": "26.04", "draft": False, "prerelease": False}
                ]
            if "/tags?" in url:
                return [{"name": "26.05"}, {"name": "26.04"}]
            self.fail(f"unexpected URL: {url}")

        with mock.patch.object(VERSIONS, "get_json", side_effect=response):
            self.assertEqual(VERSIONS.github_latest("example/project"), "26.05")


class GnuLatestTests(unittest.TestCase):
    def test_mirror_uses_short_budget_before_canonical_fallback(self):
        with mock.patch.object(
            VERSIONS,
            "get_text",
            side_effect=[RuntimeError("mirror down"), "gzip-1.15.tar.xz"],
        ) as get_text:
            self.assertEqual(VERSIONS.gnu_ftp("gzip"), "1.15")

        self.assertEqual(
            get_text.call_args_list,
            [
                mock.call(
                    "https://ftpmirror.gnu.org/gzip/", timeout=10, retries=1
                ),
                mock.call("https://ftp.gnu.org/gnu/gzip/"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
