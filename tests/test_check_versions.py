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
    class Response:
        def __init__(self, body):
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body

    def test_canonical_uses_short_budget_before_mirror_fallback(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request.full_url, timeout))
            if request.full_url == "https://ftp.gnu.org/gnu/gzip/":
                raise VERSIONS.http.client.BadStatusLine("bad response")
            return self.Response("gzip-1.15.tar.xz")

        with mock.patch.object(VERSIONS.urllib.request, "urlopen", side_effect=urlopen):
            self.assertEqual(VERSIONS.gnu_ftp("gzip"), "1.15")

        self.assertEqual(
            calls,
            [
                ("https://ftp.gnu.org/gnu/gzip/", 10),
                ("https://ftpmirror.gnu.org/gzip/", 10),
            ],
        )

    def test_malformed_canonical_listing_uses_mirror(self):
        responses = iter(
            [self.Response("no release archives here"), self.Response("nano-9.2.tar.xz")]
        )

        with mock.patch.object(
            VERSIONS.urllib.request,
            "urlopen",
            side_effect=lambda *_args, **_kwargs: next(responses),
        ) as urlopen:
            self.assertEqual(VERSIONS.gnu_ftp("nano"), "9.2")

        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
