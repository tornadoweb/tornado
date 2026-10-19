# Shared setup for the fuzzers in this directory (see README.md).

import logging
import os
import sys
from collections.abc import Callable, Iterable

import atheris


class ErrorLog(logging.Handler):
    """Turns error logs into exceptions, which the fuzzer reports as crashes.

    Tornado catches and logs the exceptions it doesn't expect (in request
    handlers, callbacks and the like), so an unexpected exception is an
    error log, not an exception that reaches the fuzzer.
    """

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))

    def install(self) -> None:
        for name in ("tornado", "asyncio"):
            logger = logging.getLogger(name)
            logger.addHandler(self)
            logger.propagate = False
        # Expected problems with the input are logged below ERROR; keep them
        # out of the fuzzer's output.
        logging.getLogger("tornado").setLevel(logging.ERROR)

    def check(self) -> None:
        if self.messages:
            messages, self.messages = self.messages, []
            raise RuntimeError("error logged:\n" + "\n".join(messages))


def main(
    name: str, test_one_input: Callable[[bytes], None], seeds: Iterable[bytes]
) -> None:
    """Runs the fuzzer, with libFuzzer's command line arguments.

    With no corpus directory on the command line, uses corpus/<name> next
    to this file, creating it from ``seeds`` if it is empty. Inputs that
    crash are saved in artifacts/ next to this file.

    ``--write-seeds=DIR`` writes the seeds to DIR and exits, for OSS-Fuzz's
    build script.
    """
    argv = sys.argv
    for arg in argv[1:]:
        if arg.startswith("--write-seeds="):
            write_seeds(arg.split("=", 1)[1], seeds)
            return
    # OSS-Fuzz runs the fuzzers as PyInstaller executables, with its own
    # corpus and artifact arguments.
    if not getattr(sys, "frozen", False):
        here = os.path.dirname(os.path.abspath(__file__))
        if not any(a.startswith("-artifact_prefix=") for a in argv):
            # Crashing inputs go in artifacts/ instead of the current directory.
            os.makedirs(os.path.join(here, "artifacts"), exist_ok=True)
            argv = argv + [f"-artifact_prefix={os.path.join(here, 'artifacts', name)}-"]
        if not any(not a.startswith("-") for a in argv[1:]):
            corpus = os.path.join(here, "corpus", name)
            if not os.path.isdir(corpus) or not os.listdir(corpus):
                write_seeds(corpus, seeds)
            argv = argv + [corpus]
    atheris.Setup(argv, test_one_input)
    atheris.Fuzz()


def write_seeds(directory: str, seeds: Iterable[bytes]) -> None:
    os.makedirs(directory, exist_ok=True)
    for i, seed in enumerate(seeds):
        with open(os.path.join(directory, f"seed{i:03d}"), "wb") as f:
            f.write(seed)
