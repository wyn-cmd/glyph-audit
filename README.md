# glyph-audit

Report invisible, reordering and confusable characters in text files, so a line that reads one way on screen is not doing something else underneath.

Some characters occupy no width at all, some reorder the text that follows them, and some letters look identical to latin ones while belonging to another script. They survive a code review, they break parsers, and they are how a Trojan Source attack hides a comment marker or how a phishing domain passes a glance. glyph-audit walks a file or a directory and prints every one of them with its line, column, codepoint and Unicode name.

## What it reports

- zero-width characters: U+200B, U+200C, U+200D, U+FEFF and the word joiner U+2060.
- bidi control characters: the embeddings, overrides and isolates U+202A to U+202E and U+2066 to U+2069, plus the left-to-right and right-to-left marks.
- invisible operators and separators: the soft hyphen U+00AD and U+2061 to U+2064.
- space characters that are not U+0020: the no-break space, the quad and em spaces, the thin and hair spaces, and the ideographic space.
- mixed-script words: a word of two or more letters that carries Cyrillic or Greek letters next to latin ones, reported at the column of each foreign letter. Latin next to CJK or Hangul is ordinary mixed-language text and stays quiet.

## Install

    python3 -m pip install .

That puts a `glyph-audit` command on the path. Without installing anything, run it from the repository root as `python3 -m glyphaudit`.

## Usage

    glyph-audit [paths ...] [--json] [--quiet] [--category NAME]

- `paths`: files or directories, any number. Directories are walked and `.git`, `node_modules`, `__pycache__`, `.venv` and similar build directories are skipped.
- `--json`: machine readable output with the scanned count, the files skipped for not being UTF-8 or for being binary, and every finding.
- `--quiet`: the summary line only, for a pre-commit hook that only needs the exit code.
- `--category`: limit to one category, repeatable. One of `bidi`, `zero-width`, `invisible`, `space`, `mixed-script`.

## Example output

The run below is real, over a small directory holding a note with a spoofed domain, a shell script with a right-to-left override, an ini file with a no-break space, a binary file and a latin-1 file.

    $ glyph-audit ga-demo
    glyph-audit 1.0.0
    ga-demo/conf.ini:2:7: space: U+00A0 NO-BREAK SPACE (no-break space)
    ga-demo/deploy.sh:2:14: bidi: U+202E RIGHT-TO-LEFT OVERRIDE (right-to-left override)
    ga-demo/email.txt:2:28: mixed-script: U+0430 CYRILLIC SMALL LETTER A (latin word pаypal)
    ga-demo/email.txt:3:10: zero-width: U+200B ZERO WIDTH SPACE (zero width space)
    4 files scanned, 2 skipped, 4 findings in 3 files

Two files were skipped and are named only in the JSON output: one is binary, and one is not valid UTF-8. A file the tool could not read at all is printed on stderr as a warning, so a clean exit never hides a file that was never examined.

## Exit codes

- `0`: no findings.
- `1`: at least one finding, in either output mode.
- `2`: a path that does not exist, or no paths given.

## Tests

    python3 -m unittest discover -s tests -t .
    python3 tests/test_engine.py

The suite covers the engine and the command line: each hidden codepoint class, the column of a spoofed letter inside a word, two foreign letters in one word counted separately, CRLF line endings, a category filter, binary and non-UTF-8 files, an unreadable file, the `.git` skip, JSON output, and the three exit codes.

## Limits

The tool reads UTF-8 only and skips anything that does not decode, so a UTF-16 log has to be converted first. Mixed-script detection covers Latin against Cyrillic and Greek, which is the spoof pair that matters in domains, package names and log lines; it does not build a full Unicode confusables table, so a Cyrillic word that mimics a latin one as a whole word is not matched. Nothing is rewritten: every finding is a position to look at, not a fix.
