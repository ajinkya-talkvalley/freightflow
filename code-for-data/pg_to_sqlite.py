#!/usr/bin/env python3
"""
pg_to_sqlite.py — Convert a FreightFlow PostgreSQL dump to SQLite-compatible SQL.

Usage:
    python pg_to_sqlite.py [input] [output]

Defaults:
    input  : data/freightflow-db.sql
    output : data/freightflow-db-sqlite.sql

Transformations applied:
    1. Remove PostgreSQL-only SET directives (client_encoding, standard_conforming_strings)
    2. TRUNCATE TABLE x CASCADE  →  DELETE FROM x
    3. Boolean literals TRUE / FALSE  →  1 / 0
    4. Remove SELECT setval(...) sequence-reset calls
"""

import argparse
import os
import re
import sys

DEFAULT_INPUT  = os.path.join("data", "freightflow-db.sql")
DEFAULT_OUTPUT = os.path.join("data", "freightflow-db-sqlite.sql")

# Lines whose content matches these patterns are dropped entirely.
DROP_LINE_PATTERNS = [
    re.compile(r"^\s*SET\s+\w", re.IGNORECASE),           # SET client_encoding …
    re.compile(r"^\s*SELECT\s+setval\s*\(", re.IGNORECASE), # SELECT setval(…)
]

# TRUNCATE TABLE foo [CASCADE]; → DELETE FROM foo;
TRUNCATE_RE = re.compile(
    r"TRUNCATE\s+TABLE\s+(\S+)\s*(?:CASCADE\s*)?;",
    re.IGNORECASE,
)

# TRUE / FALSE as bare SQL keywords (not inside single-quoted strings).
# Strategy: split each line on single-quoted regions, apply replacement only
# to the unquoted segments, then reassemble.
QUOTED_SEGMENT_RE = re.compile(r"'(?:[^'\\]|\\.)*'")

def replace_booleans(line: str) -> str:
    """Replace bare TRUE/FALSE with 1/0, leaving quoted strings untouched."""
    parts = []
    last = 0
    for m in QUOTED_SEGMENT_RE.finditer(line):
        unquoted = line[last:m.start()]
        unquoted = re.sub(r"\bTRUE\b",  "1", unquoted)
        unquoted = re.sub(r"\bFALSE\b", "0", unquoted)
        parts.append(unquoted)
        parts.append(m.group())   # keep quoted segment unchanged
        last = m.end()
    tail = line[last:]
    tail = re.sub(r"\bTRUE\b",  "1", tail)
    tail = re.sub(r"\bFALSE\b", "0", tail)
    parts.append(tail)
    return "".join(parts)


def convert(src: str, dst: str) -> None:
    with open(src, encoding="utf-8") as fh:
        lines = fh.readlines()

    out_lines = []
    stats = {"dropped": 0, "truncate": 0, "bool": 0}

    for raw in lines:
        # 1. Drop PostgreSQL-only directives
        if any(p.search(raw) for p in DROP_LINE_PATTERNS):
            stats["dropped"] += 1
            continue

        # 2. TRUNCATE → DELETE FROM
        def _truncate_sub(m):
            stats["truncate"] += 1
            return f"DELETE FROM {m.group(1)};"

        line = TRUNCATE_RE.sub(_truncate_sub, raw)

        # 3. Boolean literals
        converted = replace_booleans(line)
        if converted != line:
            stats["bool"] += 1
        line = converted

        out_lines.append(line)

    with open(dst, "w", encoding="utf-8") as fh:
        fh.writelines(out_lines)

    in_kb  = os.path.getsize(src) / 1024
    out_kb = os.path.getsize(dst) / 1024
    print(f"Input : {src} ({in_kb:.1f} KB)")
    print(f"Output: {dst} ({out_kb:.1f} KB)")
    print(f"  {stats['truncate']} TRUNCATE -> DELETE FROM")
    print(f"  {stats['bool']} lines with TRUE/FALSE -> 1/0")
    print(f"  {stats['dropped']} PostgreSQL-only lines removed")


def main():
    parser = argparse.ArgumentParser(description="Convert PostgreSQL dump to SQLite SQL.")
    parser.add_argument("input",  nargs="?", default=DEFAULT_INPUT,  help="Source .sql file")
    parser.add_argument("output", nargs="?", default=DEFAULT_OUTPUT, help="Destination .sql file")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
