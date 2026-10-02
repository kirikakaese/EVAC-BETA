#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Attribution check (CLAUDE.md, section 0.1): the repository owner is the sole author of EVAC.

Fails (exit 1) when
* a commit's author or committer is an AI tool / bot identity (Claude, Anthropic, ...),
* a commit message carries a co-author trailer, a "generated with" line or a session link,
* a tracked file credits an AI tool as author, co-author, contributor or copyright holder.

Usage: ``python scripts/check_attribution.py [--range <rev-range>]`` (default: every commit of HEAD).
Allowlisted files quote the forbidden patterns on purpose: this script, CLAUDE.md and docs/BRIEF.md.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

ALLOWLIST = {"scripts/check_attribution.py", "CLAUDE.md", "docs/BRIEF.md"}
AI = r"(claude|anthropic)"
MESSAGE_PATTERNS = [
    re.compile(r"^\s*co-authored-by\s*:", re.I | re.M),
    re.compile(r"generated\s+(with|by)\s+\[?" + AI, re.I),
    re.compile(r"claude-session\s*:", re.I),
    re.compile(r"claude\.ai/code", re.I),
    re.compile(r"noreply@anthropic\.com", re.I),
]
IDENTITY = re.compile(AI + r"|noreply@anthropic", re.I)
CREDIT_WORDS = re.compile(r"author|contributor|copyright|credit|acknowledg|generated|written|maintainer|"
                          r"thanks|byline|spdx-filecopyrighttext", re.I)
AI_WORD = re.compile(r"\b" + AI + r"\b", re.I)
FILE_PATTERNS = MESSAGE_PATTERNS + [re.compile(r"\bai[- ]generated\b", re.I)]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def check_commits(rev_range: str) -> list[str]:
    problems = []
    fmt = "%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B%x1e"
    try:
        out = git("log", f"--format={fmt}", rev_range)
    except subprocess.CalledProcessError:
        return problems
    for record in filter(None, (r.strip("\n") for r in out.split("\x1e"))):
        sha, an, ae, cn, ce, body = record.split("\x1f", 5)
        short = sha[:10]
        for label, value in (("author", f"{an} <{ae}>"), ("committer", f"{cn} <{ce}>")):
            if IDENTITY.search(value):
                problems.append(f"commit {short}: {label} is an AI/bot identity: {value}")
        for pat in MESSAGE_PATTERNS:
            if pat.search(body):
                problems.append(f"commit {short}: message matches {pat.pattern!r}")
    return problems


def check_files() -> list[str]:
    problems = []
    for path in git("ls-files").splitlines():
        if path in ALLOWLIST:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(lines, 1):
            text = line.replace("CLAUDE.md", "")
            for pat in FILE_PATTERNS:
                if pat.search(text):
                    problems.append(f"{path}:{n}: matches {pat.pattern!r}")
            if AI_WORD.search(text) and CREDIT_WORDS.search(text):
                problems.append(f"{path}:{n}: credits an AI tool: {line.strip()[:120]}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--range", default="HEAD", help="git revision range of commits to check")
    parser.add_argument("--no-files", action="store_true")
    args = parser.parse_args()
    problems = check_commits(args.range)
    if not args.no_files:
        problems += check_files()
    for p in problems:
        print(p)
    if problems:
        print(f"\nAttribution check FAILED ({len(problems)} problem(s)). See CLAUDE.md, section 0.1.")
        return 1
    print("Attribution check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
