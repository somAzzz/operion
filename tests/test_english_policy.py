import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "scripts/check_english.py"


class EnglishPolicyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_check(self):
        return subprocess.run(
            [sys.executable, str(CHECK), "--root", str(self.root)],
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_english_passes_and_source_data_and_ignored_history_are_excluded(self):
        self.write(".gitignore", "history/\n")
        self.write("README.md", "English documentation.\n")
        self.write("src/prompt.py", 'PROMPT = "Respond in English."\n')
        for name in (
            "data/canonical/source.json",
            "reports/old.json",
            "history/old.txt",
        ):
            self.write(name, chr(0x4E2D))
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stdout)

    def test_tracked_and_new_maintained_content_is_rejected_with_location(self):
        for name in (
            "docs/guide.md",
            "src/prompt.py",
            "apps/web/page.tsx",
            "tests/fixture.json",
            "data/README.md",
        ):
            with self.subTest(name=name):
                self.write(name, f"English\n{chr(0x4E2D)}\n")
                result = self.run_check()
                self.assertEqual(1, result.returncode)
                self.assertIn(f"file={name},line=2", result.stdout)
                self.assertNotIn(chr(0x4E2D), result.stdout)
                (self.root / name).unlink()
        self.write("tracked.md", chr(0x20000))
        subprocess.run(["git", "add", "--", "tracked.md"], cwd=self.root, check=True)
        self.assertEqual(1, self.run_check().returncode)

    def test_unicode_escapes_cannot_hide_han_in_prompts_or_fixtures(self):
        for suffix in ("u4e2d", "U00020000", "u{20000}", f"ud840{chr(92)}udc00"):
            with self.subTest(suffix=suffix):
                self.write("src/prompt.py", f'PROMPT = "{chr(92)}{suffix}"\n')
                result = self.run_check()
                self.assertEqual(1, result.returncode)
                self.assertIn("Unicode-escaped Han", result.stdout)

    def test_han_file_names_and_invalid_text_encoding_are_rejected(self):
        name = f"docs/{chr(0x4E2D)}.md"
        self.write(name, "English")
        self.assertEqual(1, self.run_check().returncode)
        (self.root / name).unlink()
        (self.root / "source.py").write_bytes(b"\xff")
        self.assertEqual(1, self.run_check().returncode)


if __name__ == "__main__":
    unittest.main()
