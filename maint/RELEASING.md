# Releasing Tornado

Notes for maintainers. Pushing a `v*` tag runs the build workflow, which
builds the sdist and wheels and uploads them to PyPI, so everything up to
the tag has to be right before it is pushed.

## Tags and branches

- Each release has a tag of the form `vX.Y.Z` (such as `v6.5.0`). The tag
  always has all three numbers, although the trailing `.0` is usually left
  out elsewhere. Pre-releases have a suffix such as `a1`, `b1` or `rc1`
  (`v6.6.0b1`).
- Final release tags are annotated: create them with `git tag -a` and paste
  in the release notes. Pre-release tags don't need to be.
- `branchX.Y` tracks the latest release in each series. Pushes to it run
  the build workflow and the downstream testbed
  (`.github/workflows/downstream.yml`), which runs the test suites of the
  most popular dependents against the built package. These branches also
  host each version's documentation on readthedocs.org.
- `stable` tracks the latest release (the same commit as the newest
  `branchX.Y`) and is the default version of the docs, so that doc URLs
  stay the same across versions.

## Release steps

1. For a patch release, work on the appropriate `branchX.Y` and
   cherry-pick from master as needed.
2. Write the release notes in `docs/releases/vX.Y.Z.rst` and link them
   from `docs/releases.rst`.
3. Update `version` and `version_info` in `tornado/__init__.py` (the
   comments there explain `version_info`).
4. Run `python maint/scripts/pre_tag_checks.py vX.Y.Z` on the commit to be
   tagged. It checks the version number and release notes against the tag,
   runs the full test suite, lint, docs and coverage, and compares
   benchmarks with the previous release.
5. Tag the release (`git tag -a vX.Y.Z` for a final release, pasting in the
   release notes), then push the tag (`git push origin vX.Y.Z`) and all
   updated branches, including `stable` for a final release. CI builds the
   sdist and wheels and uploads them to PyPI.
6. If the release creates a new `branchX.Y`, enable builds for that branch
   on readthedocs.org.
7. On master, set the version to the next development version: between
   releases it has a `.dev1` suffix (`6.6.0` is followed by `6.7.dev1`), or
   occasionally `.dev2` and so on to mark milestones.
8. Announce the release on the
   [python-tornado](https://groups.google.com/g/python-tornado) and
   [python-tornado-announce](https://groups.google.com/g/python-tornado-announce)
   mailing lists, and in a GitHub release.

## Minor releases (X.Y.0)

Ship at least one pre-release (`vX.Y.0b1`, optionally an alpha first and a
release candidate after) and announce it the same way. Leave about two
weeks between the first beta and the final release, so downstream projects
and users have time to report problems.

### Deprecations

A public name, argument or behavior is removed only after at least one
minor release in which it emits a `DeprecationWarning` and is documented
with a `.. deprecated::` note saying what to use instead. The API snapshot
test (`tornado/test/api_test.py`) makes any removal show up in review.

## Patch releases (X.Y.Z)

Patch releases have no beta, so the pre-tag checks are the main
protection against regressions.

## Security releases

Security releases skip the public pre-release, and that is where recent
regressions have come from (6.5.3 was followed by 6.5.4, and 6.5.9 by
6.5.10). GitHub Actions doesn't run in a security advisory's private fork,
so the fix is developed and tested locally, and the public PR, CI run,
build and release happen as fast as possible once the fix is disclosed.
The aim is for that public CI run to be a formality, not the first real
test:

- Before anything is public, prepare the whole release on the fix branch:
  the version bump, the release notes, and a branch for each release line
  that gets the fix.
- Run `pre_tag_checks.py` on each of those branches. It covers the full
  suite with the optional dependencies (including the property tests and
  the regression tests from earlier security fixes), lint, docs, coverage
  and benchmarks. What it can't cover is Windows, macOS and the wheel
  builds, which first run in public CI.
- Keep each fix to the smallest behavior change that closes the hole. When
  a fix tightens behavior that applications may rely on, ship a way to opt
  out in the same release. Behavior changes are what downstream projects
  (tornado-testbed) catch, and for a security release they only see them
  after the release.
- Be ready to make a follow-up release within a day, and say so in the
  advisory.
