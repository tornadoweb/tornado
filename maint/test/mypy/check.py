"""Type-check client code against an installed copy of Tornado.

This checks that the py.typed marker is respected and that Tornado's
published annotations work for applications: good.py must pass under
``--strict`` and bad.py must fail with the expected error.

Run it with Tornado and mypy installed (``tox -e lint`` does this). It
changes to this directory first, so the source tree is not on mypy's
search path and the installed package is used instead.
"""

import os
import subprocess
import sys


def run(*args: str) -> tuple[str, int]:
    # An empty --config-file keeps mypy from finding the repository's
    # setup.cfg; client code is checked with client settings.
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file=", "--no-incremental", *args],
        capture_output=True,
        encoding="utf-8",
    )
    return result.stdout + result.stderr, result.returncode


def main() -> None:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    failed = False

    output, status = run("--strict", "good.py")
    if status != 0:
        print("good.py should pass but did not:\n" + output)
        failed = True

    output, status = run("bad.py")
    if (
        status == 0
        or 'incompatible with supertype "tornado.web.RequestHandler"' not in output
    ):
        print("bad.py should fail with an override error but did not:\n" + output)
        failed = True

    if failed:
        sys.exit(1)
    print("maint/test/mypy: OK")


if __name__ == "__main__":
    main()
