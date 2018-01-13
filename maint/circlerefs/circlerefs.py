#!/usr/bin/env python
"""Test script to find circular references.

Circular references are not leaks per se, because they will eventually
be GC'd. However, on CPython, they prevent the reference-counting fast
path from being used and instead rely on the slower full GC. This
increases memory footprint and CPU overhead, so we try to eliminate
circular references created by normal operation.
"""
from __future__ import print_function

import gc
import traceback
import types
from tornado import web, ioloop, gen, httpclient


def find_circular_references(garbage=None):
    def inner(level):
        for item in level:
            item_id = id(item)
            if item_id not in garbage_ids:
                continue
            if item_id in visited_ids:
                continue
            if item_id in stack_ids:
                candidate = stack[stack.index(item):]
                candidate.append(item)
                found.append(candidate)
                continue

            stack.append(item)
            stack_ids.add(item_id)
            inner(gc.get_referents(item))
            stack.pop()
            stack_ids.remove(item_id)
            visited_ids.add(item_id)

    garbage = garbage or gc.garbage
    found = []
    stack = []
    stack_ids = set()
    garbage_ids = set(map(id, garbage))
    visited_ids = set()

    inner(garbage)
    inner = None
    return found


class CollectHandler(web.RequestHandler):
    @gen.coroutine
    def get(self):
        self.write("Collected: {}\n".format(gc.collect()))
        self.write("Garbage: {}\n".format(len(gc.garbage)))
        for circular in find_circular_references():
            print('\n==========\n Circular \n==========')
            for item in circular:
                print('    ', repr(item))
            for item in circular:
                if isinstance(item, types.FrameType):
                    print('\nLocals:', item.f_locals)
                    print('\nTraceback:', repr(item))
                    traceback.print_stack(item)


class DummyHandler(web.RequestHandler):
    @gen.coroutine
    def get(self):
        self.write('ok\n')


class DummyAsyncHandler(web.RequestHandler):
    @gen.coroutine
    def get(self):
        raise web.Finish('ok\n')


application = web.Application([
    (r'/dummy/', DummyHandler),
    (r'/dummyasync/', DummyAsyncHandler),
    (r'/collect/', CollectHandler),
], debug=True)


@gen.coroutine
def main():
    gc.disable()
    gc.collect()
    gc.set_debug(gc.DEBUG_STATS | gc.DEBUG_SAVEALL)
    print('GC disabled')

    print("Start on 8888")
    application.listen(8888, '127.0.0.1')

    # Do a little work. Alternately, could leave this script running and
    # poke at it with a browser.
    client = httpclient.AsyncHTTPClient()
    yield client.fetch('http://127.0.0.1:8888/dummy/')
    yield client.fetch('http://127.0.0.1:8888/dummyasync/', raise_error=False)

    # Now report on the results.
    resp = yield client.fetch('http://127.0.0.1:8888/collect/')
    print(resp.body)


if __name__ == "__main__":
    ioloop.IOLoop.current().run_sync(main)
