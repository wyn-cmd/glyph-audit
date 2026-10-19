import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glyphaudit import engine

ZWSP = "\u200b"
BIDI_OVERRIDE = "\u202e"
BOM = "\ufeff"
CYRILLIC_A = "\u0430"
GREEK_OMICRON = "\u03bf"


class ScanTextTests(unittest.TestCase):
    def test_plain_ascii_is_clean(self):
        self.assertEqual(engine.scan_text("hello world\nsecond line\n"), [])

    def test_zero_width_space_reports_position_and_category(self):
        found = engine.scan_text("abc" + ZWSP + "def")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].codepoint, 0x200B)
        self.assertEqual(found[0].category, "zero-width")
        self.assertEqual(found[0].col, 4)
        self.assertEqual(found[0].line, 1)

    def test_bidi_override_is_reported(self):
        found = engine.scan_text("safe" + BIDI_OVERRIDE + "txet")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].category, "bidi")
        self.assertIn("right-to-left override", found[0].detail)

    def test_leading_byte_order_mark_is_named(self):
        found = engine.scan_text(BOM + "x = 1\n")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].detail, "byte order mark at start of file")

    def test_unicode_space_is_reported(self):
        found = engine.scan_text("a\u00a0b")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].category, "space")

    def test_cyrillic_letter_inside_latin_word(self):
        found = engine.scan_text("visit p" + CYRILLIC_A + "ypal.com now")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].category, "mixed-script")
        self.assertEqual(found[0].col, 8)
        self.assertEqual(found[0].codepoint, 0x0430)
        self.assertEqual(found[0].name, "CYRILLIC SMALL LETTER A")

    def test_greek_letter_inside_latin_word(self):
        found = engine.scan_text("micr" + GREEK_OMICRON + "soft")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].col, 5)
        self.assertEqual(found[0].name, "GREEK SMALL LETTER OMICRON")

    def test_two_foreign_letters_in_one_word_are_both_reported(self):
        found = engine.scan_text("p" + CYRILLIC_A + "yp" + CYRILLIC_A + "l")
        self.assertEqual(len(found), 2)
        self.assertEqual([f.col for f in found], [2, 5])

    def test_latin_next_to_cjk_is_not_flagged(self):
        # Mixed language text is ordinary, so only Cyrillic and Greek spoofs count.
        self.assertEqual(engine.scan_text("hello\u4e16\u754c"), [])

    def test_pure_cyrillic_word_is_not_flagged(self):
        self.assertEqual(engine.scan_text("\u043f\u0440\u0438\u0432\u0435\u0442"), [])

    def test_standalone_cyrillic_letter_is_not_flagged(self):
        # A lone Cyrillic letter is its own token, so it is not a latin word
        # carrying foreign letters and must stay quiet.
        self.assertEqual(engine.scan_text("yes \u0430 no"), [])

    def test_category_filter_limits_output(self):
        text = "abc" + ZWSP + "def p" + CYRILLIC_A + "ypal"
        only_bidi = engine.scan_text(text, categories={"bidi"})
        self.assertEqual(only_bidi, [])
        mixed = engine.scan_text(text, categories={"mixed-script"})
        self.assertEqual(len(mixed), 1)
        self.assertEqual(mixed[0].category, "mixed-script")

    def test_two_hidden_characters_on_one_line_are_counted_once_each(self):
        found = engine.scan_text("a" + ZWSP + "b" + ZWSP + "c")
        self.assertEqual(len(found), 2)
        self.assertEqual([f.col for f in found], [2, 4])

    def test_carriage_return_does_not_shift_columns(self):
        found = engine.scan_text("ab" + ZWSP + "\r\ncd\r\n")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].col, 3)
        self.assertEqual(found[0].line, 1)

    def test_line_numbers_advance(self):
        found = engine.scan_text("clean\nstill clean\nx" + BIDI_OVERRIDE + "y\n")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].line, 3)

    def test_render_names_the_codepoint(self):
        text = engine.scan_text("ab" + ZWSP, path="f.txt")[0].render()
        self.assertIn("f.txt:1:3:", text)
        self.assertIn("U+200B ZERO WIDTH SPACE", text)


class ScanFileTests(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        self.shutil = shutil
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_binary_file_is_skipped_not_flagged(self):
        path = self.write("blob.bin", b"\x00\x01\x02" + ZWSP.encode("utf-8"))
        found, reason = engine.scan_file(path)
        self.assertEqual(found, [])
        self.assertEqual(reason, "binary")

    def test_non_utf8_file_is_skipped(self):
        path = self.write("latin.txt", b"caf\xe9\n")
        found, reason = engine.scan_file(path)
        self.assertEqual(found, [])
        self.assertEqual(reason, "not valid utf-8")

    def test_utf8_file_is_scanned(self):
        path = self.write("dirty.txt", ("bad" + ZWSP + "word\n").encode("utf-8"))
        found, reason = engine.scan_file(path)
        self.assertIsNone(reason)
        self.assertEqual(len(found), 1)

    def test_walk_skips_git_directory(self):
        git_dir = os.path.join(self.tmp, ".git")
        os.makedirs(git_dir)
        self.write(".git/hidden.txt", ("a" + ZWSP + "b\n").encode("utf-8"))
        self.write("normal.txt", b"plain\n")
        found, stats = engine.scan_paths([self.tmp])
        self.assertEqual(found, [])
        self.assertEqual(stats["scanned"], 1)

    def test_unreadable_file_is_reported(self):
        if os.geteuid() == 0:
            self.skipTest("root can read anything")
        path = self.write("locked.txt", b"plain\n")
        os.chmod(path, 0o000)
        self.addCleanup(os.chmod, path, 0o644)
        found, stats = engine.scan_paths([path])
        self.assertEqual(found, [])
        self.assertEqual(len(stats["unreadable"]), 1)
        self.assertEqual(stats["scanned"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
