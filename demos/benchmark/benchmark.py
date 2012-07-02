#!/usr/bin/env python
#
# A simple benchmark of tornado's HTTP stack.
# Requires 'ab' to be installed.
#
# Running without profiling:
# demos/benchmark/benchmark.py
# demos/benchmark/benchmark.py --quiet --num_runs=5|grep "Requests per second"
#
# Running with profiling:
#
# python -m cProfile -o /tmp/prof demos/benchmark/benchmark.py
# python -m pstats /tmp/prof
# % sort time
# % stats 20

from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import RequestHandler, Application

import random
import signal
import subprocess

# choose a random port to avoid colliding with TIME_WAIT sockets left over
# from previous runs.
define("min_port", type=int, default=8000)
define("max_port", type=int, default=9000)

# Increasing --n without --keepalive will eventually run into problems
# due to TIME_WAIT sockets
define("n", type=int, default=15000)
define("c", type=int, default=25)
define("keepalive", type=bool, default=False)
define("quiet", type=bool, default=False)

# Repeat the entire benchmark this many times (on different ports)
# This gives JITs time to warm up, etc.  Pypy needs 3-5 runs at
# --n=15000 for its JIT to reach full effectiveness
define("num_runs", type=int, default=1)

class RootHandler(RequestHandler):
    def get(self):
        self.write("Hello, world")

    def _log(self):
        pass

def handle_sigchld(sig, frame):
    IOLoop.instance().add_callback(IOLoop.instance().stop)

def main():
    parse_command_line()
    for i in xrange(options.num_runs):
        run()

def run():
    app = Application([("/", RootHandler)])
    port = random.randrange(options.min_port, options.max_port)
    app.listen(port, address='127.0.0.1')
    signal.signal(signal.SIGCHLD, handle_sigchld)
    args = ["ab"]
    args.extend(["-n", str(options.n)])
    args.extend(["-c", str(options.c)])
    if options.keepalive:
        args.append("-k")
    if options.quiet:
        # just stops the progress messages printed to stderr
        args.append("-q")
    args.append("http://127.0.0.1:%d/" % port)
    subprocess.Popen(args)
    IOLoop.instance().start()
    IOLoop.instance().close()
    del IOLoop._instance
    assert not IOLoop.initialized()

if __name__ == '__main__':
    main()
