#!/usr/bin/env python
# Fuzzes tornado.httputil's header_params parser (see httputil_targets.py).
#
# Usage (from the root of the repo; see README.md):
#   PYTHONPATH=. python maint/fuzz/fuzz_httputil_header_params.py -max_total_time=600

import httputil_targets

if __name__ == "__main__":
    httputil_targets.main(httputil_targets.header_params)
