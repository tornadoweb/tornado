# Contributing to Tornado

## The basics

* We use `black` as code formatter and recommend configuring your editor to run this automatically
  (using the version specified in `requirements.txt`). Commits that are not properly formatted
  by `black` will be rejected in CI.
* We update `requirements.txt` infrequently. It is important to install the versions of tools
  like `black` and `mypy` from `requirements.txt` instead of running their latest versions
  (don't just use `uvx`). Older release branches like `branch6.5` have their own
  `requirements.txt` so reinstall these tools (or switch virtualenvs) when switching branches.
* The `types-pycurl` package should be installed when running `mypy`.
* Run `flake8` from the project root directory so it can see `.flake8`, this prevents spurious
  warnings.
* Before committing, it is recommended to run `tox -e lint,docs,py3`. This will verify that the
  code is formatted correctly, type checking with `mypy` passes, the `sphinx` build for docs has
  no errors, and the main test suite passes with the current version of python.
* Nearly all code changes should have new or updated tests covering the changed behavior.
  Red/green TDD is encouraged.

## Testing

* We use `tox` as a test runner to run tests in various configurations with the correct
  dependencies. `tox -e py3` runs most of the tests, while `tox -e py3-full` can be used
  to run a more extensive version of the test suite which as extra dependencies. The
  `-full` configurations are necessary when working on certain modules, including
  `curl_httpclient.py`, `twisted.py`, or `pycares.py`.
* The fastest way to run the tests is to bypass `tox` and run `python3 -m tornado.test`.
  To run a subset of tests, add a module, class, or method name to the command line:
  `python3 -m tornado.test.httputil_test`.
* `tox -e coverage` measures test coverage across the `-full` configurations and writes an
  HTML report to `.tox/coverage-data/html`. CI fails if total coverage drops below the floor
  set in `tox.ini`; raise the floor when you raise coverage.
* `tornado/test/property_test.py` holds property-based tests using `hypothesis`, which is
  installed in the `-full` configurations (the tests are skipped without it). They are a good
  place for invariants of parsers and encoders: round-trips, agreement with a simple model, and
  "malformed input raises `HTTPInputError` and nothing else". When one fails, also add the
  failing input as an example-based test so it stays covered.
* `tornado/test/api_test.py` compares the public API (names and signatures) to the snapshot in
  `tornado/test/api.txt`. When you change the API on purpose, run
  `python -m tornado.test.api_test --update` from the repository root (with the `-full`
  dependencies installed) and commit the updated snapshot. Imports are left out of the snapshot
  unless they use the `import X as X` form that marks a re-export. `tox -e docs` checks that everything in the docs
  is in the snapshot.
* Code that parses untrusted input should have resource-budget tests. `assert_linear_scaling`
  in `tornado/test/util.py` checks that time grows linearly with the input, and
  `assert_memory_budget` checks peak memory per byte of input (or per byte of a configured
  limit such as `max_body_size`). Look for the worst-case input (many tiny fields, deep
  escaping, highly compressible data) and keep sizes small enough that the test takes a
  fraction of a second. A fix for a denial-of-service bug should come with such a test, and
  the test should fail on the code before the fix.
* The "Compare benchmarks" CI job runs `maint/benchmark/ci_benchmark.py` against the PR and
  its base branch and fails if anything is more than 20% slower, or if an adversarial input
  exceeds its absolute budget (`BUDGETS` in that file). To run the comparison locally, check
  out the base in another directory and run
  `python maint/benchmark/compare_benchmarks.py --base ../base --head .`. When you add a
  parser or a resource-budget test for one, add a benchmark of its worst-case input too.
* Don't remove a public name, argument or behavior without deprecating it first: it should
  emit a `DeprecationWarning` and have a `.. deprecated::` note (saying what to use instead)
  for at least one minor release before it goes. See `maint/RELEASING.md`.
* `tox -e lint` runs flake8, black and mypy. mypy runs in strict mode, relaxed for the tests
  (see `setup.cfg`), and reports `# type: ignore` comments that are no longer needed. Names
  that a module re-exports need the `import X as X` form. It also type-checks the client code
  in `maint/test/mypy` against the installed package: add to `good.py` when you change
  annotations that applications rely on.
* Tests can also be run with the standard library's `unittest` package CLI. This is useful
  for integration with some editors. However, this mode skips a few checks, notably the
  requirement that tests do not generate any log output without corresponding ExpectLog
  assertions.
* Tornado does not use `pytest`. Some effort has been made to make the tests work with 
  the `pytest` runner, but this is not maintained.
* Tests must run on Linux, macOS, and Windows (unless they are testing platform-dependent
  functionality, in which case they should be skipped on other platforms).
* Use mocks sparingly. Prefer to use real sockets, servers, etc as much as possible.
  It is rarely appropriate to use mocks just to speed up a test. The most common reason
  to use mocks in Tornado tests is to simulate error conditions that cannot be
  reproduced without mocks.
* Most tests are covered by a default 5 second timeout. This can be changed during
  development with the env var `ASYNC_TEST_TIMEOUT`, or with the `timeout` argument
  to `@gen_test` (although most tests should be made fast instead of given an increased
  timeout)

## Documentation

We use Sphinx with the `autodoc` extension to build our docs. To build the docs run
`tox -e docs` and find the output in `./.tox/docs/tmp/html/index.html`

## AI policy

Tornado has a neutral stance towards AI-generated code. All pull requests, whether human
or machine-generated, are subject to strict code review standards. However, PRs that appear
to be AI-generated *and* contain clear flaws (such as failing CI) may be closed without
detailed review. 

## curl_httpclient notes

- Older versions of pycurl bundled specific versions of libcurl. This can be an easy way
  to test with old versions of libcurl. Specifically, `pycurl==7.45.4` installs libcurl
  8.11.1, which is not the oldest version of libcurl we support but is the oldest one that
  is easy to install.
- Easy handles are pooled and reused (_free_list, reset in _finish), so per-request state leaking
  into the following request is a live bug class: test_reuse_proxy_credentials and test_reuse_certs
  both exist because of it. New per-request state deserves a reuse test with max_clients=1.
- That state is smuggled in a dict attached to the handle (curl.info, rebuilt in _process_queue).
  There is a standing TODO about the approach; until it is addressed, this is where such state goes.

## PR Checklist

- [ ] Run `tox -e lint,docs,py3` locally and make sure it passes
- [ ] If you modify `curl_httpclient.py`, also run `tox -e py3-full`
- [ ] Review your changes for any backwards incompatibilities that may affect
      downstream applications using Tornado
