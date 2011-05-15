#!/usr/bin/env python
#
# A simple benchmark of tornado's HTTP stack.
# Requires 'ab' to be installed.
#
# Running without profiling:
# demos/benchmark/benchmark.py
#
# Running with profiling:
#
# python -m cProfile -o /tmp/prof demos/benchmark/benchmark.py
# python -c 'import pstats; pstats.Stats("/tmp/prof").strip_dirs().sort_stats("time").print_callers(20)'

from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import RequestHandler, Application

import signal
import subprocess


define("port", type=int, default=8888)
define("n", type=int, default=10000)
define("c", type=int, default=25)
define("keepalive", type=bool, default=False)

class RootHandler(RequestHandler):
    def get(self):
        self.write("Hello, world")

    def _log(self):
        pass

def handle_sigchld(sig, frame):
    IOLoop.instance().add_callback(IOLoop.instance().stop)

def main():
    parse_command_line()
    app = Application([("/", RootHandler)])
    app.listen(options.port)
    signal.signal(signal.SIGCHLD, handle_sigchld)
    args = ["ab"]
    args.extend(["-n", str(options.n)])
    args.extend(["-c", str(options.c)])
    if options.keepalive:
        args.append("-k")
    args.append("http://127.0.0.1:%d/" % options.port)
    proc = subprocess.Popen(args)
    IOLoop.instance().start()

if __name__ == '__main__':
    main()
