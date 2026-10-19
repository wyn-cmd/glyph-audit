import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZWSP = "\u200b"
BIDI_OVERRIDE = "\u202e"


def run(args, cwd=None):
    # The module is run the way a user runs it, so argument parsing, output and
    # exit codes are all covered by these tests.
    proc = subprocess.run(
        [sys.executable, "-m", "glyphaudit"] + args,
        cwd=cwd or ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, body):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return path

    def test_clean_file_exits_zero(self):
        path = self.write("clean.txt", "nothing to see\n")
        proc = run([path])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("clean", proc.stdout)

    def test_finding_exits_one_and_prints_location(self):
        path = self.write("dirty.txt", "pass" + ZWSP + "word\n")
        proc = run([path])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("dirty.txt:1:5:", proc.stdout)
        self.assertIn("zero-width", proc.stdout)

    def test_quiet_prints_summary_only(self):
        path = self.write("dirty.txt", "a" + ZWSP + "b\n")
        proc = run([path, "--quiet"])
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("dirty.txt:1:", proc.stdout)
        self.assertIn("1 finding", proc.stdout)

    def test_missing_path_exits_two(self):
        proc = run([os.path.join(self.tmp, "nope.txt")])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no such file or directory", proc.stderr)

    def test_no_arguments_exits_two(self):
        proc = run([])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("give at least one file", proc.stderr)

    def test_json_output_parses_and_carries_the_finding(self):
        path = self.write("dirty.txt", "x" + BIDI_OVERRIDE + "y\n")
        proc = run([path, "--json"])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["scanned"], 1)
        finding = payload["findings"][0]
        self.assertEqual(finding["codepoint"], "U+202E")
        self.assertEqual(finding["line"], 1)
        self.assertEqual(finding["col"], 2)

    def test_binary_file_is_skipped_in_summary(self):
        path = os.path.join(self.tmp, "blob.bin")
        with open(path, "wb") as fh:
            fh.write(b"\x00\x01binary")
        proc = run([path])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1 skipped", proc.stdout)

    def test_category_limit_clears_a_dirty_file(self):
        path = self.write("bidi.txt", "a" + BIDI_OVERRIDE + "b\n")
        proc = run([path, "--category", "zero-width"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_directory_scan_reports_mixed_script(self):
        self.write("hosts.txt", "login p\u0430ypal.com\n")
        proc = run([self.tmp])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("mixed-script", proc.stdout)

    def test_version_prints_and_exits_zero(self):
        proc = run(["--version"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("glyph-audit", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
