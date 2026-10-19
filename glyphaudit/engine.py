import os
import re
import unicodedata
from dataclasses import dataclass

# Codepoints that render with no width at all, or that reorder the text around
# them. A reviewer looking at a diff sees nothing here, which is why the tool
# reports them with the codepoint and the Unicode name rather than a warning.
HIDDEN = {
    0x00AD: ("invisible", "soft hyphen, renders only at a line break"),
    0x061C: ("bidi", "arabic letter mark"),
    0x180E: ("invisible", "mongolian vowel separator"),
    0x200B: ("zero-width", "zero width space"),
    0x200C: ("zero-width", "zero width non-joiner"),
    0x200D: ("zero-width", "zero width joiner"),
    0x200E: ("bidi", "left-to-right mark"),
    0x200F: ("bidi", "right-to-left mark"),
    0x202A: ("bidi", "left-to-right embedding"),
    0x202B: ("bidi", "right-to-left embedding"),
    0x202C: ("bidi", "pop directional formatting"),
    0x202D: ("bidi", "left-to-right override"),
    0x202E: ("bidi", "right-to-left override"),
    0x2060: ("zero-width", "word joiner"),
    0x2061: ("invisible", "function application"),
    0x2062: ("invisible", "invisible times"),
    0x2063: ("invisible", "invisible separator"),
    0x2064: ("invisible", "invisible plus"),
    0x2066: ("bidi", "left-to-right isolate"),
    0x2067: ("bidi", "right-to-left isolate"),
    0x2068: ("bidi", "first strong isolate"),
    0x2069: ("bidi", "pop directional isolate"),
    0xFEFF: ("zero-width", "zero width no-break space"),
}

# Space characters that are not U+0020. They survive a visual diff review and
# they break parsers that split on an ordinary space, so each one is a finding.
SPACE_CODEPOINTS = {0x00A0, 0x1680, 0x202F, 0x205F, 0x3000}
for _cp in range(0x2000, 0x200B):
    SPACE_CODEPOINTS.add(_cp)
del _cp

# Letters from these scripts inside an otherwise latin word are the classic
# spoof: Cyrillic small a in a domain, Greek omicron in a package name.
# Latin next to CJK or Hangul is ordinary mixed-language text, so only these
# two scripts raise a finding.
SPOOF_SCRIPTS = ("CYRILLIC", "GREEK")

# Directories that hold generated or vendored text. Scanning them buries the
# real findings under thousands of lines nobody wrote.
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}

# A run of letters. Digits and underscores are excluded so a version string or
# an identifier root does not get glued onto the word around it.
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    col: int
    codepoint: int
    category: str
    detail: str

    @property
    def name(self):
        return unicodedata.name(chr(self.codepoint), "UNNAMED")

    def render(self):
        return "%s:%d:%d: %s: U+%04X %s (%s)" % (
            self.path,
            self.line,
            self.col,
            self.category,
            self.codepoint,
            self.name,
            self.detail,
        )

    def as_dict(self):
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "codepoint": "U+%04X" % self.codepoint,
            "category": self.category,
            "name": self.name,
            "detail": self.detail,
        }


def script_of(ch):
    name = unicodedata.name(ch, "")
    if not name:
        return ""
    return name.split(" ")[0]


def classify(cp):
    # Returns a category and a detail string, or None when the codepoint is
    # ordinary printable text.
    if cp in HIDDEN:
        return HIDDEN[cp]
    if cp in SPACE_CODEPOINTS:
        return ("space", unicodedata.name(chr(cp), "unicode space").lower())
    return None


def spoof_tokens(line):
    # Yields (column, detail) once per foreign letter inside a latin word, so a
    # word carrying two Cyrillic letters reports both of their positions.
    for match in TOKEN_RE.finditer(line):
        token = match.group(0)
        if len(token) < 2:
            continue
        scripts = {script_of(ch) for ch in token}
        if "LATIN" not in scripts:
            continue
        for pos, ch in enumerate(token):
            if script_of(ch) not in SPOOF_SCRIPTS:
                continue
            # The column points at the foreign letter itself, not at the start
            # of the word, so an editor can jump to the character that spoofed.
            yield (match.start() + pos, "latin word %s" % token)


def scan_text(text, path="<text>", categories=None):
    findings = []
    for lineno, raw in enumerate(text.split("\n"), start=1):
        line = raw[:-1] if raw.endswith("\r") else raw
        for idx, ch in enumerate(line):
            cp = ord(ch)
            info = classify(cp)
            if info is None:
                continue
            category, detail = info
            if lineno == 1 and idx == 0 and cp == 0xFEFF:
                detail = "byte order mark at start of file"
            if categories and category not in categories:
                continue
            findings.append(Finding(path, lineno, idx + 1, cp, category, detail))
        if categories and "mixed-script" not in categories:
            continue
        for col, detail in spoof_tokens(line):
            findings.append(Finding(path, lineno, col + 1, ord(line[col]), "mixed-script", detail))
    findings.sort(key=lambda f: (f.line, f.col))
    return findings


def scan_file(path, categories=None):
    # Returns (findings, skip_reason). A null byte in the head means the file is
    # not text, and a decode failure means it is text in some other encoding,
    # so neither one is reported as a finding.
    with open(path, "rb") as fh:
        head = fh.read(8192)
        rest = fh.read()
    if b"\x00" in head:
        return [], "binary"
    try:
        text = (head + rest).decode("utf-8")
    except UnicodeDecodeError:
        return [], "not valid utf-8"
    return scan_text(text, path, categories), None


def iter_files(root):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def scan_paths(paths, categories=None):
    findings = []
    skipped = []
    unreadable = []
    scanned = 0
    for root in paths:
        for path in iter_files(root):
            try:
                found, reason = scan_file(path, categories)
            except OSError as exc:
                # A permission-denied file is reported rather than skipped, so
                # a clean exit never implies coverage that did not happen.
                unreadable.append((path, exc.strerror or str(exc)))
                continue
            if reason:
                skipped.append((path, reason))
                continue
            scanned += 1
            findings.extend(found)
    findings.sort(key=lambda f: (f.path, f.line, f.col))
    return findings, {"scanned": scanned, "skipped": skipped, "unreadable": unreadable}
