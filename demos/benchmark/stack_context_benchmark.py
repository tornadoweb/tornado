#!/usr/bin/env python
"""Benchmark for stack_context functionality."""
import collections
import contextlib
import functools
import subprocess
import sys

from tornado import stack_context

class Benchmark(object):
    def enter_exit(self, count):
        """Measures the overhead of the nested "with" statements
        when using many contexts.
        """
        if count < 0:
            return
        with self.make_context():
            self.enter_exit(count - 1)

    def call_wrapped(self, count):
        """Wraps and calls a function at each level of stack depth
        to measure the overhead of the wrapped function.
        """
        # This queue is analogous to IOLoop.add_callback, but lets us
        # benchmark the stack_context in isolation without system call
        # overhead.
        queue = collections.deque()
        self.call_wrapped_inner(queue, count)
        while queue:
            queue.popleft()()

    def call_wrapped_inner(self, queue, count):
        if count < 0:
            return
        with self.make_context():
            queue.append(stack_context.wrap(
                functools.partial(self.call_wrapped_inner, queue, count - 1)))

class StackBenchmark(Benchmark):
    def make_context(self):
        return stack_context.StackContext(self.__context)

    @contextlib.contextmanager
    def __context(self):
        yield

class ExceptionBenchmark(Benchmark):
    def make_context(self):
        return stack_context.ExceptionStackContext(self.__handle_exception)

    def __handle_exception(self, typ, value, tb):
        pass

def main():
    base_cmd = [
        sys.executable, '-m', 'timeit', '-s',
        'from stack_context_benchmark import StackBenchmark, ExceptionBenchmark']
    cmds = [
        'StackBenchmark().enter_exit(50)',
        'StackBenchmark().call_wrapped(50)',
        'StackBenchmark().enter_exit(500)',
        'StackBenchmark().call_wrapped(500)',

        'ExceptionBenchmark().enter_exit(50)',
        'ExceptionBenchmark().call_wrapped(50)',
        'ExceptionBenchmark().enter_exit(500)',
        'ExceptionBenchmark().call_wrapped(500)',
        ]
    for cmd in cmds:
        print(cmd)
        subprocess.check_call(base_cmd + [cmd])

if __name__ == '__main__':
    main()
