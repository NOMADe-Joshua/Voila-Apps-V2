# Deploying the app suite to a NOMAD Oasis

By default the apps talk to the peroTF Oasis at KIT
(`http://elnserver.lti.kit.edu`, set in `shared/perotf_utils/config.py`). That
file is the only place the server address and the NOMAD entry type names
appear. A different deployment changes none of the code: everything it needs
lives in one gitignored file, `oasis_local_config.py`, read by `bootstrap.py`
at the top of every notebook.

---

## 1. Check the target Oasis is compatible

The apps assume a NOMAD Oasis that serves the peroTF schema classes
(`peroTF_Batch`, `peroTF_JVmeasurement`, ...) and offers the `voila` NORTH tool.
Confirm both before uploading anything:

```bash
curl -s http://<your-oasis>/nomad-oasis/api/v1/info | python -m json.tool
```

Look for:

| Field | Expected | Why it matters |
|---|---|---|
| `version` | 1.x, `oasis: true` | API shape the apps are written against |
| `plugin_packages` / schema | the package that defines the `peroTF_*` classes | `ENTRY_TYPES` in `shared/perotf_utils/config.py` names them; a different schema means those queries return nothing |
| `north_tools` | includes `voila` | how the apps are launched |

If your Oasis runs a different schema package, `ENTRY_TYPES` in
`shared/perotf_utils/config.py` is the single place to remap the names.

## 2. Upload the repo

Either drag the repo in as a NOMAD upload, or clone it from a NORTH terminal.
Whichever route you take, preserve the directory structure. The layout matters
more than the name: every notebook's cell 0 is

```python
import runpy

_ = runpy.run_path("../../bootstrap.py")
```

which resolves from `apps/<AppName>/` to the repo root. As long as `apps/`,
`shared/` and `bootstrap.py` keep their relative positions, the upload's own
`<slug>-<hash>` folder name is irrelevant. That is the whole point of the
bootstrap, and why no path in this repo names a specific upload.

To clone it, from a NORTH Jupyter terminal (File > New > Terminal), in the
uploads directory you want it to live in:

```bash
git clone https://github.com/NOMADe-Joshua/Voila-Apps-V2.git
```

**Moving over from the old flat repo** (`nomad-perotf-jupyter-voila-scripts`):
notebook URLs change (`apps/<AppName>/...` instead of `<AppName>/...`, and a
few notebooks were renamed), so keep the old upload in place until users have
switched, and point them at the App Dashboard. The usage log now lives at
`shared/perotf_utils/notebook_usage.log`; the old log stays in the old upload.

## 2a. Proxy for the terminal (proxied Oasis only)

If the container has no direct route out, `git clone` fails before it starts.
`oasis_local_config.py` cannot help here: it is applied by `bootstrap.py`,
which runs inside a kernel and lives inside the repo you are trying to clone.
Export the proxy in that shell instead:

```bash
export HTTPS_PROXY=http://proxy.example.org:3128
export HTTP_PROXY=$HTTPS_PROXY
export NO_PROXY=localhost,127.0.0.1
export http_proxy=$HTTP_PROXY https_proxy=$HTTPS_PROXY no_proxy=$NO_PROXY
```

libcurl (used by `git` and `curl`) reads only the lowercase `http_proxy` for
plain HTTP, hence both spellings. These exports last for that terminal session
only, and they do not carry into the Voila kernels that run the apps. That is
what `oasis_local_config.py` (step 3) is for.

## 3. Create `oasis_local_config.py` (only if you need overrides)

Create it at the repo root of the upload, next to `bootstrap.py`. It is
gitignored (same pattern as `secrets.py`) because it describes one deployment,
not the repo.

Every uppercase string assignment in it is exported as an environment variable
of the same name before `perotf_utils` is imported or installed. Anything
already set at the container level wins; this file never overwrites it. No
proxy is applied unless this file (or the container) sets one.

```python
# --- Which Oasis the apps talk to ---
PEROTF_URL_BASE = "https://nomad.example.org"
PEROTF_API_ENDPOINT = "/nomad-oasis/api/v1"

# --- Outbound network (only if the container needs a proxy) ---
HTTP_PROXY = "http://proxy.example.org:3128"
HTTPS_PROXY = "http://proxy.example.org:3128"
NO_PROXY = "localhost,127.0.0.1"
```

### What each variable does

| Variable | Needed when | Notes |
|---|---|---|
| `PEROTF_URL_BASE` | the apps should talk to another Oasis | Read by `shared/perotf_utils/config.py`. No trailing slash. |
| `PEROTF_API_ENDPOINT` | the API is not at `/nomad-oasis/api/v1` | |
| `PEROTF_GUI_ENDPOINT` | the GUI is not at `/nomad-oasis/gui` | Used for links to entries (JV app, Excel creator). |
| `PEROTF_NORTH_ENDPOINT` | NORTH is not at `/nomad-oasis/north` | Used by the App Dashboard's links. |
| `HTTP_PROXY`, `HTTPS_PROXY` | the container has no direct outbound route | Applied *before* `pip install shared/` runs, because pip may fetch `hatchling` from PyPI to build it. |
| `NO_PROXY` | whenever a proxy is set | Hosts reached *without* the proxy. Defaults to `localhost,127.0.0.1`. Only add the Oasis host if a direct call to it actually works from the container. |

### Ordering, and why it is not cosmetic

`bootstrap.py` applies the environment, then the proxy, then installs
`shared/`. Both halves of that order are load-bearing:

- `perotf_utils.config` reads `PEROTF_URL_BASE` **at import time**, so
  setting it after any app import has no effect.
- `pip install <local dir>` is not an offline operation unless `hatchling` is
  already installed. On a proxied Oasis, a bootstrap that installs before
  setting the proxy fails.

## 4. Launch and verify

Launch the `voila` NORTH tool against `apps/App_dashboard/app_dashboard.ipynb`
first; it exercises the NORTH URL construction and links every app.

Run this in a fresh kernel from any `apps/<AppName>/` folder to confirm the
environment before debugging anything else:

```python
import runpy

_ = runpy.run_path("../../bootstrap.py")

import os
from perotf_utils.config import API_ENDPOINT, URL_BASE

print("URL_BASE    :", URL_BASE)
print("API_ENDPOINT:", API_ENDPOINT)
print("proxy       :", os.environ.get("HTTPS_PROXY"))

import requests

print("info        :", requests.get(f"{URL_BASE}{API_ENDPOINT}/info", timeout=30).status_code)
```

A `200` from the `/info` call proves the URL and any proxy settings are
correct together.

Checklist for the dashboard itself:

- [ ] Dashboard renders with your username in the header
- [ ] App cards point at `<URL_BASE>/nomad-oasis/north/...`
- [ ] Clicking a card opens that app's Voila instance
- [ ] An API app (e.g. JV Analysis) can authenticate and list batches

## 5. Local development

The same variables apply. Export them in your shell instead of using
`oasis_local_config.py`:

```bash
export PEROTF_URL_BASE=http://elnserver.lti.kit.edu
export NOMAD_CLIENT_ACCESS_TOKEN=<your token>
```

See `README.md` for the local install.

## 6. Git cheat sheet for the NORTH terminal

```bash
git clone https://github.com/NOMADe-Joshua/Voila-Apps-V2.git
cd Voila-Apps-V2
git branch -a                    # every branch, including remote ones
git checkout <branch-name>       # switch
git pull                         # update
git fetch origin && git status   # see if you are behind without changing anything
```

Running a notebook in Jupyter writes its output cells back into the `.ipynb`,
so git reports it as modified and refuses to switch branches. Those outputs are
exhaust; look first, then discard them:

```bash
git status
git restore <notebook>.ipynb     # one file
git restore .                    # every modified tracked file
```

`git restore` does not touch untracked or ignored files, so
`oasis_local_config.py` and `secrets.py` are never at risk.

## 7. How dependencies get installed

Nothing on the Oasis runs `pip install` by hand. `bootstrap.py` does all of it
from cell 0, in this order:

1. **`shared/`**: the `perotf_utils` library every app imports. A failure here
   is fatal and raises, because no app works without it.
2. **The app's own directory**, when it has a `pyproject.toml`. The cwd is the
   notebook's own folder, so this installs exactly the app being launched,
   along with everything in its `dependencies` list.

Step 2 is why `apps/<App>/pyproject.toml` is worth keeping accurate: it is the
only thing that installs an app's third-party requirements.

**It runs once per container, not once per launch.** On success bootstrap
writes a marker into the temp directory, keyed on the app's path and the
contents of its `pyproject.toml`. Editing the dependency list changes the key,
so the next launch reinstalls.

**A failed app install is a warning, not an error.** Most apps need nothing
beyond what the NORTH image already provides, so pip failing here (no network)
must not take down an app that would otherwise run fine. Only the `shared/`
install is fatal.

### Import-time banners

Bootstrap also stops libraries printing into the app's UI while they are being
imported (some packages greet stdout with a multi-line banner, which under
Voila appears above the app and reads as an error). It replaces
`builtins.__import__` for the rest of the kernel's life, redirecting stdout for
each outermost import only; stderr and runtime output are untouched, and the
suppressed text is logged at debug level. To get that output back while
debugging an import:

```python
import os

os.environ["PEROTF_KEEP_IMPORT_OUTPUT"] = "1"  # before cell 0 runs
```
