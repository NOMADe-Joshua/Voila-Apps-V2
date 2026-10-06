# Contributing

This repo hosts the peroTF NOMAD Analysis Apps (`apps/<AppName>/`), all reachable
from the [App Dashboard](apps/App_dashboard/). See `CLAUDE.md` for the
codebase conventions (layout, shared utils, lint rules). This file covers the
process for proposing and landing a change.

## 1. Open an issue first

Every change (bug fix, feature, improvement) starts as a GitHub issue on
[NOMADe-Joshua/Voila-Apps-V2](https://github.com/NOMADe-Joshua/Voila-Apps-V2/issues),
using the *Bug report* or *Feature request* template. This is how we keep a
record of *why* something changed, not just what the diff says.

Small exceptions that don't need an issue: typo fixes, CI/tooling-only
changes, and repo-wide sweeps (lint config, dependency bumps) that don't
change app behavior.

## 2. Open a PR that references it

Use `Fixes #123` or `Closes #123` in the PR description so the issue closes
automatically on merge. Fill out the PR template checklist.

This repo is a GitHub fork of HZB's `nomad-hzb/nomad-pv-analysis-apps`, and
`gh pr create` in a fork targets the *upstream* repo by default. Run
`gh repo set-default NOMADe-Joshua/Voila-Apps-V2` once per clone so PRs land
here, and only open a PR against HZB on purpose (see section 5).

## 3. Bump the app's version if the change is user-visible

Each app has its own `version` in `apps/<AppName>/pyproject.toml`, following
[SemVer](https://semver.org/):

| Change type | Bump | Example |
|---|---|---|
| Bug fix, no behavior change | patch | `1.0.0` -> `1.0.1` |
| New feature, backward-compatible | minor | `1.0.0` -> `1.1.0` |
| Breaking change (removed feature, changed data/export format, etc.) | major | `1.0.0` -> `2.0.0` |

Bump the version in the same PR as the change, for that app only. Internal
refactors, test-only changes, and changes to `shared/perotf_utils/` don't
require an app version bump (a `perotf_utils` change is a separate,
cross-cutting decision, see `CLAUDE.md` rule 2).

## 4. Releases

"What's new" is surfaced via [GitHub Releases](https://github.com/NOMADe-Joshua/Voila-Apps-V2/releases),
linked from the top-right of the App Dashboard. When a meaningful batch of
merged, issue-linked PRs has landed, cut a release:

```
gh release create <tag> --generate-notes
```

`--generate-notes` builds the changelog from merged PR titles since the last
tag, so PR titles should be descriptive on their own (not just "fix bug").
There's no separate hand-maintained CHANGELOG file to keep in sync.

## 5. Exchanging apps with HZB

HZB's repo has the same structure, so an app can move between the two repos
as a folder. The remote is set up as `upstream`:

```
git fetch upstream
git checkout upstream/main -- apps/<AppName>    # bring one HZB app over
```

Then, in that app only:

1. Replace `hysprint_utils` with `perotf_utils` in every import (`.py` and
   notebooks). The config keys are the same (`URL_BASE`, `API_ENDPOINT`,
   `ENTRY_TYPES["jv"]`, ...), so the app then talks to our Oasis and queries our
   `peroTF_*` entry types without further changes.
2. If it uses an `ENTRY_TYPES` key we do not have, add our class name for it
   to `shared/perotf_utils/config.py` (never as a literal in the app).
3. If it imports an HZB-only shared function, bring that function into
   `perotf_utils` as its own reviewed change rather than copying it into the app.
4. Add the app to the App Dashboard catalog
   (`apps/App_dashboard/data_manager.py::CATEGORIES`) and give it tests under
   `tests/<AppName>/`.

Going the other way works the same with the replacement reversed.
