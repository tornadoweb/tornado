#!/usr/bin/env python
# Fuzzes tornado.httputil's headers parser (see httputil_targets.py).
#
# Usage (from the root of the repo; see README.md):
#   PYTHONPATH=. python maint/fuzz/fuzz_httputil_headers.py -max_total_time=600

import httputil_targets

if __name__ == "__main__":
    httputil_targets.main(httputil_targets.headers)
