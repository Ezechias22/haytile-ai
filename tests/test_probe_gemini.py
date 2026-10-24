import unittest

from scripts.probe_gemini import collect_models


class ModelDiscoveryTests(unittest.TestCase):
    def test_pagination_and_metadata_filter(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                return {
                    "models": [{"name": "models/test-fixture", "private": "discard"}],
                    "nextPageToken": "a+b/=",
                }
            return {"models": [{"name": "models/second-fixture"}]}

        result = collect_models(fetch)
        self.assertEqual(len(result), 2)
        self.assertNotIn("private", result[0])
        self.assertIn("pageToken=a%2Bb%2F%3D", calls[1])

    def test_repeated_cursor_fails(self):
        with self.assertRaises(ValueError):
            collect_models(lambda _: {"nextPageToken": "loop"})

    def test_malformed_catalog_fails(self):
        with self.assertRaises(ValueError):
            collect_models(lambda _: {"models": [{}]})


if __name__ == "__main__":
    unittest.main()
