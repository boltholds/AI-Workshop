from pathlib import Path
import unittest


class SampleAppTest(unittest.TestCase):
    def test_fixture_contains_expected_ui_contract(self):
        html = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("WORKSHOP_SAMPLE", html)
        self.assertIn('id="move"', html)
        self.assertIn('id="box"', html)


if __name__ == "__main__":
    unittest.main()
