#!/usr/bin/env python
"""Checks to run on a release branch before pushing a release tag.

Usage (from the root of the repo, on the commit to be tagged):

    python maint/scripts/pre_tag_checks.py v6.7.0b1
    python maint/scripts/pre_tag_checks.py v6.6.1 --quick   # metadata only

This matters most for security releases, which skip the betas that would
otherwise catch regressions. See maint/RELEASING.md for the parts of the
process that can't be automated.

The checks:

* The working tree is clean.
* ``tornado.version`` and ``tornado.version_info`` match the tag.
* The release notes exist, are in docs/releases.rst, and (for a final
  release) have a date.
* Unless ``--quick``: the full test suite with the optional dependencies
  (property tests and the curl client included), lint, docs and coverage,
  via tox.
* Unless ``--quick``: maint/benchmark/compare_benchmarks.py against the
  previous release tag (``--previous`` overrides the guess).
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from typing import NamedTuple

_TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?")
_PRERELEASE_INFO = {"a": -99, "b": -98, "rc": -97}


class Version(NamedTuple):
    version: str
    version_info: tuple[int, int, int, int]
    notes: str


def expected_version(tag: str) -> Version:
    """Returns what tornado/__init__.py and the notes should say for ``tag``.

    >>> expected_version("v6.5.0")
    Version(version='6.5', version_info=(6, 5, 0, 0), notes='v6.5.0')
    >>> expected_version("v6.5.10")
    Version(version='6.5.10', version_info=(6, 5, 10, 0), notes='v6.5.10')
    >>> expected_version("v6.6.0b1")
    Version(version='6.6b1', version_info=(6, 6, 0, -98), notes='v6.6.0')
    """
    m = _TAG_RE.fullmatch(tag)
    if m is None:
        raise ValueError(f"not a release tag: {tag!r}")
    major, minor, patch = int(m[1]), int(m[2]), int(m[3])
    base = f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"
    if m[4]:
        # Pre-releases have used the same fourth element for every
        # number so far (6.6a1 and 6.5b1 alike), so only the kind is
        # checked.
        return Version(
            base + m[4] + m[5],
            (major, minor, patch, _PRERELEASE_INFO[m[4]]),
            f"v{major}.{minor}.{patch}",
        )
    return Version(base, (major, minor, patch, 0), tag)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def check_metadata(tag: str) -> list[str]:
    errors = []
    if git("status", "--porcelain"):
        errors.append("the working tree has uncommitted changes")

    expected = expected_version(tag)
    with open("tornado/__init__.py") as f:
        init = f.read()
    version = re.search(r'^version = "(.*)"$', init, re.M)
    info = re.search(r"^version_info = (\(.*\))$", init, re.M)
    if version is None or version[1] != expected.version:
        errors.append(
            f"tornado.version is {version and version[1]!r}, expected "
            f"{expected.version!r}"
        )
    if info is None or info[1] != repr(expected.version_info):
        errors.append(
            f"tornado.version_info is {info and info[1]}, expected "
            f"{expected.version_info}"
        )

    notes = f"docs/releases/{expected.notes}.rst"
    if not os.path.exists(notes):
        errors.append(f"{notes} does not exist")
    else:
        with open("docs/releases.rst") as f:
            if f"releases/{expected.notes}\n" not in f.read():
                errors.append(f"{notes} is not listed in docs/releases.rst")
        with open(notes) as f:
            if expected.version_info[3] == 0 and re.search(r"\bXX\b", f.read()):
                errors.append(f"{notes} still has a placeholder (XX) date")
    return errors


def previous_tag(tag: str) -> str:
    # The highest final release below tag. Release branches aren't merged
    # back, so this can't be found from the commit history.
    target = expected_version(tag).version_info[:3]
    finals = []
    for t in git("tag", "--list", "v*").split():
        m = _TAG_RE.fullmatch(t)
        if m and not m[4]:
            v = (int(m[1]), int(m[2]), int(m[3]))
            if v < target:
                finals.append((v, t))
    if not finals:
        raise ValueError("no previous release tag found")
    return max(finals)[1]


def run(*cmd: str) -> bool:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="the tag to be pushed, such as v6.7.0b1")
    parser.add_argument("--previous", help="release to compare benchmarks with")
    parser.add_argument(
        "--quick", action="store_true", help="skip the tests and benchmarks"
    )
    args = parser.parse_args()

    errors = check_metadata(args.tag)
    for e in errors:
        print("error:", e)
    if not args.quick:
        if not run(sys.executable, "-m", "tox", "-e", "py3-full,lint,docs,coverage"):
            errors.append("tox failed")
        previous = args.previous or previous_tag(args.tag)
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, previous)
            git("worktree", "add", "--detach", base, previous)
            try:
                if not run(
                    sys.executable,
                    "maint/benchmark/compare_benchmarks.py",
                    "--base",
                    base,
                    "--head",
                    ".",
                ):
                    errors.append(f"benchmarks regressed since {previous}")
            finally:
                git("worktree", "remove", "--force", base)
    if errors:
        print(f"\n{len(errors)} problem(s); do not tag {args.tag} yet.")
        return 1
    print(f"\nAll checks passed for {args.tag}. See maint/RELEASING.md for the rest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
