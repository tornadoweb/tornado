# Contributing to Tornado

## The basics

* We use `black` as code formatter and recommend configuring your editor to run this automatically
  (using the version specified in `requirements.txt`). Commits that are not properly formatted
  by `black` will be rejected in CI.
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
* Tests can also be run with the standard library's `unittest` package CLI. This is useful
  for integration with some editors.
* Tornado does not use `pytest`. Some effort has been made to make the tests work with 
  the `pytest` runner, but this is not maintained.

## Documentation

We use Sphinx with the `autodoc` extension to build our docs. To build the docs run
`tox -e docs` and find the output in `./.tox/docs/tmp/html/index.html`

## AI policy

Tornado has a neutral stance towards AI-generated code. All pull requests, whether human
or machine-generated, are subject to strict code review standards. However, PRs that appear
to be AI-generated *and* contain clear flaws (such as failing CI) may be closed without
detailed review. 