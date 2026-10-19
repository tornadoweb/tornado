# Security Policy

## Supported Versions

In general, due to limited maintainer bandwidth, only the latest version of
Tornado is supported with patch releases. Exceptions may be made depending
on the severity of the bug and the feasibility of backporting a fix to
older releases. 

## Reporting a Vulnerability

Tornado uses GitHub's security advisory functionality for private vulnerability
reports. To make a private report, use the "Report a vulnerability" button on
https://github.com/tornadoweb/tornado/security/advisories

## Denial of service

Any server spends CPU time processing the requests it receives, so the fact
that a client can make Tornado consume CPU is not in itself a vulnerability.
As a baseline, processing a stream of tiny pipelined HTTP/1.1 requests (to a
trivial handler) costs about 9µs of CPU per byte received (CPython 3.13 on a
typical cloud VM; this will vary with hardware and Python version). Tornado
also yields to the event loop between requests, so processing them stalls
other connections for only a few milliseconds at a time.

A report of a denial-of-service vulnerability should demonstrate either an
input that costs substantially more CPU per byte than this baseline, or one
that blocks the event loop (stalling all other connections) for substantially
longer than this.

## Tests for security fixes

A security fix should have the unit tests appropriate to the code it
changes, and also a test in `tornado/test/security_corpus_test.py`. That
file sends the trigger input of each past vulnerability to a real server
(or explains where the tests are for fixes that can't be reached that
way), and checks only what a client can see, so that its tests keep
working when the code they cover is rewritten.
