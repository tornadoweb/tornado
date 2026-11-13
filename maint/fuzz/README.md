# Fuzzers

Coverage-guided fuzzers for Tornado's HTTP parsing, using
[atheris](https://github.com/google/atheris) (`pip install -r
maint/fuzz/requirements.txt`, which needs Linux or macOS and a CPython it has
wheels for).

CI runs each fuzzer for 5,000 inputs (the `fuzz` job in
`.github/workflows/test.yml`), so that changes don't break them; longer runs
are up to you, or to OSS-Fuzz.

| Fuzzer | What each input is | Speed |
| --- | --- | --- |
| `fuzz_httputil.py` | The input to one parser in `tornado.httputil` (header block, start line, cookie, header parameters, multipart or form body), picked by the first byte | ~10,000/s |
| `fuzz_http_server.py` | Everything a client sends on one connection to an `HTTPServer`, including websocket frames after a handshake | ~2,000/s |
| `fuzz_http_client.py` | Everything a server sends in reply to a `SimpleAsyncHTTPClient` request | ~1,000/s |

Each one counts as a crash any exception other than the ones the code
documents for bad input, and anything Tornado logs as an error (which is
how it reports exceptions it catches, such as one in a request handler).

## Running

From the root of the repo:

    PYTHONPATH=. python maint/fuzz/fuzz_http_server.py -max_total_time=600 -timeout=5

The arguments are [libFuzzer's](https://llvm.org/docs/LibFuzzer.html#options).
`-timeout` reports any single input that takes longer than that many
seconds, which catches the quadratic parsing behind several past
advisories. Use `-fork=N` (or run several copies) to use more cores.

With no corpus directory on the command line, the fuzzer uses
`maint/fuzz/corpus/<name>/`, seeded on the first run from the inputs in
`tornado/test/security_corpus_test.py`. Inputs it finds that reach new code
are added there, so later runs pick up where earlier ones stopped. Crashing
inputs are written to `maint/fuzz/artifacts/`; rerun one with

    PYTHONPATH=. python maint/fuzz/fuzz_http_server.py maint/fuzz/artifacts/http_server-crash-...

Both directories are ignored by git. `--write-seeds=DIR` writes a
fuzzer's seed inputs to DIR and exits, for builds such as OSS-Fuzz's that
manage the corpus themselves.

## When it finds something

A crash in a parser is often a security bug (a 500 error or a hang that a
client can trigger at will), so treat it as one until you know otherwise:
report it privately as SECURITY.md describes rather than in a public issue
or PR. Once it is fixed, add the input to
`tornado/test/security_corpus_test.py` as well as to the unit tests, so that
every later change, and the fuzzers' seeds, include it.
