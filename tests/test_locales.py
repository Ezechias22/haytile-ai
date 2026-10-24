import json
from pathlib import Path
import unittest


class LocalesTest(unittest.TestCase):
    def test_all_nine_locales_cover_all_labels_without_empty_values(self):
        directory = Path(__file__).resolve().parents[1] / "packages" / "i18n"
        expected = {"ht", "en", "fr", "pt-BR", "es", "ar", "zh-Hans", "id", "sw"}
        files = {p.stem: p for p in directory.glob("*.json")}
        self.assertEqual(set(files), expected)
        baseline = json.loads(files["en"].read_text())
        for locale, path in files.items():
            with self.subTest(locale=locale):
                values = json.loads(path.read_text())
                self.assertEqual(set(values), set(baseline))
                self.assertTrue(
                    all(isinstance(v, str) and v.strip() for v in values.values())
                )
