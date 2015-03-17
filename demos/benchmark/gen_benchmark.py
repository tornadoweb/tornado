#!/usr/bin/env python
#
# A simple benchmark of the tornado.gen module.
# Runs in two modes, testing new-style (@coroutine and Futures)
# and old-style (@engine and Tasks) coroutines.

from timeit import Timer

from tornado import gen
from tornado.options import options, define, parse_command_line

define('num', default=10000, help='number of iterations')

# These benchmarks are delicate.  They hit various fast-paths in the gen
# machinery in order to stay synchronous so we don't need an IOLoop.
# This removes noise from the results, but it's easy to change things
# in a way that completely invalidates the results.

@gen.engine
def e2(callback):
    callback()

@gen.engine
def e1():
    for i in range(10):
        yield gen.Task(e2)

@gen.coroutine
def c2():
    pass

@gen.coroutine
def c1():
    for i in range(10):
        yield c2()

def main():
    parse_command_line()
    t = Timer(e1)
    results = t.timeit(options.num) / options.num
    print('engine: %0.3f ms per iteration' % (results * 1000))
    t = Timer(c1)
    results = t.timeit(options.num) / options.num
    print('coroutine: %0.3f ms per iteration' % (results * 1000))

if __name__ == '__main__':
    main()
