#!/usr/bin/env python
import sys
from tornado.options import options, define, parse_command_line
from twisted.python import log
from twisted.internet import reactor
from autobahn.fuzzing import FuzzingClientFactory

define('servers', type=str, multiple=True,
       default=['Tornado=ws://localhost:9000'])

define('cases', type=str, multiple=True,
       default=["*"])
define('exclude', type=str, multiple=True,
       default=["9.*"])

if __name__ == '__main__':
   parse_command_line()
   log.startLogging(sys.stdout)
   servers = []
   for server in options.servers:
      name, _, url = server.partition('=')
      servers.append({"agent": name, "url": url, "options": {"version": 17}})
   spec = {
       "options": {"failByDrop": False},
       "enable-ssl": False,
       "servers": servers,
       "cases": options.cases,
       "exclude-cases": options.exclude,
       "exclude-agent-cases": {},
       }
   fuzzer = FuzzingClientFactory(spec)
   reactor.run()
