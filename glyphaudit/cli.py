import argparse
import json
import os
import sys

from . import engine

VERSION = "1.0.0"

CATEGORIES = ("bidi", "zero-width", "invisible", "space", "mixed-script")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="glyph-audit",
        description="Report invisible, reordering and confusable characters in text files.",
    )
    parser.add_argument("paths", nargs="*", help="files or directories to scan")
    parser.add_argument("--json", action="store_true", help="print machine readable output")
    parser.add_argument("--quiet", action="store_true", help="print only the summary line")
    parser.add_argument(
        "--category",
        action="append",
        choices=CATEGORIES,
        help="limit the scan to one category, repeatable",
    )
    parser.add_argument("--version", action="version", version="glyph-audit " + VERSION)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.paths:
        parser.print_usage(sys.stderr)
        sys.stderr.write("glyph-audit: error: give at least one file or directory\n")
        return 2

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        for path in missing:
            sys.stderr.write("glyph-audit: error: no such file or directory: %s\n" % path)
        return 2

    categories = set(args.category) if args.category else None
    findings, stats = engine.scan_paths(args.paths, categories)

    if args.json:
        payload = {
            "version": VERSION,
            "scanned": stats["scanned"],
            "skipped": [{"path": p, "reason": r} for p, r in stats["skipped"]],
            "unreadable": [{"path": p, "reason": r} for p, r in stats["unreadable"]],
            "total": len(findings),
            "findings": [f.as_dict() for f in findings],
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
        return 1 if findings else 0

    if not args.quiet:
        print("glyph-audit %s" % VERSION)
        for finding in findings:
            print(finding.render())

    parts = ["%d file%s scanned" % (stats["scanned"], "" if stats["scanned"] == 1 else "s")]
    if stats["skipped"]:
        parts.append("%d skipped" % len(stats["skipped"]))
    if stats["unreadable"]:
        parts.append("%d unreadable" % len(stats["unreadable"]))
    files = {f.path for f in findings}
    if findings:
        parts.append("%d finding%s in %d file%s" % (
            len(findings),
            "" if len(findings) == 1 else "s",
            len(files),
            "" if len(files) == 1 else "s",
        ))
    else:
        parts.append("clean")
    print(", ".join(parts))

    for path, reason in stats["unreadable"]:
        sys.stderr.write("glyph-audit: warning: could not read %s (%s)\n" % (path, reason))
    return 1 if findings else 0
