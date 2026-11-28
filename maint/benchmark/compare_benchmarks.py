#!/usr/bin/env python
#
# Runs ci_benchmark.py against two Tornado source trees and reports how the
# second ("head") compares to the first ("base"). Exits with status 1 if
# any benchmark is slower in head by more than --threshold, or exceeds its
# absolute budget.
#
# Usage:
#   python maint/benchmark/compare_benchmarks.py --base ../tornado-master --head .
#
# Timing on shared CI machines is noisy: the machine as a whole speeds up
# and slows down over seconds, and each process has its own speed (from
# memory layout and the like). So each round starts a fresh worker process
# for each tree and measures every benchmark --reps times, alternating
# between the two workers, so that both sample the same moments. The
# fastest measurement over all rounds is used for each tree: interference
# can only make a measurement slower, so the minimum is a stable estimate.
# Even so, one side sometimes gets a fast or slow process, so anything that
# looks slower is measured again with twice as many processes, and fails
# only if that agrees.
#
# The benchmark script always comes from this directory, so both trees run
# the same benchmarks; a benchmark that fails against base (for example
# because it uses a new API) is reported as new.

import argparse
import json
import os
import subprocess
import sys
from typing import IO, Any

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_benchmark.py")


class Worker:
    def __init__(self, tree: str) -> None:
        env = dict(os.environ, PYTHONPATH=os.path.abspath(tree))
        self.proc = subprocess.Popen(
            [sys.executable, SCRIPT, "--worker"],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )

    def measure(self, name: str) -> dict[str, Any]:
        stdin = _pipe(self.proc.stdin)
        stdin.write(name + "\n")
        stdin.flush()
        line = _pipe(self.proc.stdout).readline()
        if not line:
            raise RuntimeError(f"benchmark worker exited during {name}")
        result: dict[str, Any] = json.loads(line)
        return result

    def close(self) -> None:
        _pipe(self.proc.stdin).close()
        self.proc.wait()


def _pipe(f: IO[str] | None) -> IO[str]:
    assert f is not None
    return f


def faster(a: dict[str, Any] | None, b: dict[str, Any]) -> dict[str, Any]:
    if a is None or b.get("us_per_unit", float("inf")) < a.get(
        "us_per_unit", float("inf")
    ):
        return b
    return a


def compare(
    base_tree: str, head_tree: str, names: list[str], rounds: int, reps: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    base: dict[str, Any] = {}
    head: dict[str, Any] = {}
    for i in range(rounds):
        workers = {"base": Worker(base_tree), "head": Worker(head_tree)}
        for name in names:
            for j in range(reps):
                order = ["base", "head"] if (i + j) % 2 == 0 else ["head", "base"]
                for which in order:
                    best = base if which == "base" else head
                    best[name] = faster(best.get(name), workers[which].measure(name))
        for w in workers.values():
            w.close()
        print(f"round {i + 1}/{rounds} done", file=sys.stderr)
    return base, head


def ratio(b: dict[str, Any], h: dict[str, Any]) -> float:
    if "us_per_unit" not in b or "us_per_unit" not in h:
        return 0.0
    r: float = h["us_per_unit"] / b["us_per_unit"] - 1
    return r


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="source tree to compare against")
    parser.add_argument("--head", required=True, help="source tree being tested")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.2,
        help="fail if head is slower than base by more than this fraction",
    )
    parser.add_argument("--markdown", help="also write the report to this file")
    args = parser.parse_args()

    names = subprocess.run(
        [sys.executable, SCRIPT, "--list"],
        env=dict(os.environ, PYTHONPATH=os.path.abspath(args.head)),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    base, head = compare(args.base, args.head, names, args.rounds, args.reps)
    # Rerun anything that looks slower, with fresh processes and more of
    # them, and believe it only if the rerun agrees. A single comparison is
    # thrown off whenever one side happens to get a fast (or slow) process.
    suspects = [n for n in names if ratio(base[n], head[n]) > args.threshold]
    if suspects:
        print(f"rechecking {', '.join(suspects)}", file=sys.stderr)
        base2, head2 = compare(
            args.base, args.head, suspects, 2 * args.rounds, args.reps
        )
        for n in suspects:
            if ratio(base2[n], head2[n]) <= args.threshold:
                base[n], head[n] = base2[n], head2[n]

    failed = False
    lines = [
        "| Benchmark | Base | Head | Change | Budget | |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, h in head.items():
        b = base.get(name, {})
        label = name if h["unit"] == "byte" else f"{name} (per {h['unit']})"
        budget = h["budget"]
        status = ""
        if "us_per_unit" not in h:
            status = "error: " + h["error"]
            failed = True
            lines.append(f"| {label} | | | | | {status} |")
            continue
        hv = h["us_per_unit"]
        bv = b.get("us_per_unit")
        change = ""
        if bv is None:
            status = "new"
        else:
            r = hv / bv - 1
            change = f"{r:+.0%}"
            if r > args.threshold:
                status = "slower"
                failed = True
        if budget is not None and hv > budget:
            status = "over budget"
            failed = True
        lines.append(
            f"| {label} | {fmt(bv)} | {fmt(hv)} | {change} | "
            f"{fmt(budget)} | {status} |"
        )
    lines.append("")
    lines.append(
        f"Microseconds of CPU per unit (byte unless noted), fastest of "
        f"{args.rounds * args.reps} measurements in {args.rounds} processes. "
        f"Fails above {args.threshold:.0%} slower (and again when rechecked "
        f"with {2 * args.rounds} processes) or over budget."
    )
    report = "\n".join(lines) + "\n"
    print(report)
    if args.markdown:
        with open(args.markdown, "a") as f:
            f.write("## Benchmarks\n\n" + report)
    return 1 if failed else 0


def fmt(v: float | None) -> str:
    if v is None:
        return ""
    return f"{v:.3g}"


if __name__ == "__main__":
    sys.exit(main())
