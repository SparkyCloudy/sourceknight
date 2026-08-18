# SourceKnight

A fast, reproducible build tool and dependency manager tailored specifically for SourceMod (SourcePawn) plugin development.

SourceKnight brings modern package management concepts to the SourceMod ecosystem, eliminating manual include header management, SDK extraction scripts, and the need to commit third-party vendor code into your plugin repositories.

---

## Why SourceKnight?

| Traditional Workflow | With SourceKnight |
| :--- | :--- |
| Manually downloading and unzipping SourceMod builds (`spcomp`). | Declare `type: smdrop` (e.g. `1.12.x`) and let SourceKnight manage the compiler automatically. |
| Committing vendor `.inc` files directly into your repository. | Declare dependencies in `sourceknight.yaml`; keep your repository clean and modular. |
| Slow serial compilation across multiple `.sp` plugin targets. | Parallel compilation (`-j` / `--parallel`) leveraging multi-core CPUs. |
| Verbose manual unpack rules for include folders. | Zero-config heuristic include discovery across standard directory structures. |
| Complex CI/CD shell scripts to set up include paths. | Single-step GitHub Action (`SparkyCloudy/sourceknight@master`) with built-in caching. |

---

## Features

- **Multi-Source Dependency Management**: Acquire dependencies from Git repositories, pre-built binary releases (GitHub, GitLab, Gitea), AlliedModders SMDrop builds, and archive files.
- **Parallel Compilation (`-j` / `--parallel`)**: Concurrently compiles multiple `.sp` targets in parallel.
- **Zero-Config Include Resolution**: Automatically scans and maps `addons/`, `include/`, `scripting/`, and loose `.inc` headers into the virtual build tree without requiring manual unpack mapping.
- **Resilient Compilation Loop**: Builds all targets and reports overall status, with optional `--fail-fast` and `--report json` output.
- **Formatted & Colorized Diagnostics**: Highlights compiler errors and warnings with ANSI colors in terminals and generates inline annotations in GitHub Actions.
- **Dynamic Dependency Overrides**: Override dependency versions at runtime via CLI flags (`--override-dep`) or environment variables (`SK_OVERRIDE_<NAME>`) for CI matrix testing.
- **Official GitHub Action**: Pre-packaged composite action with dependency caching support.

---

## Installation

Install via `pip` from GitHub:

```bash
pip install git+https://github.com/SparkyCloudy/sourceknight.git
```

Or clone and install locally in editable mode:

```bash
git clone https://github.com/SparkyCloudy/sourceknight.git
cd sourceknight
pip install -e .
```

*Requires Python >= 3.12.*

---

## Quickstart

### 1. Project Directory Layout

```text
my-plugin/
├── sourceknight.yaml
└── addons/
    └── sourcemod/
        └── scripting/
            ├── my_plugin.sp
            └── include/
                └── my_plugin_internal.inc
```

### 2. Configure `sourceknight.yaml`

```yaml
project:
  sourceknight: 0.6
  name: my-plugin

  dependencies:
    # Official SourceMod compiler & core headers
    - name: sourcemod
      type: smdrop
      version: 1.12.x

    # Third-party Git repository (auto-extracts include headers)
    - name: multicolors
      type: git
      repo: https://github.com/srcdslab/sm-plugin-MultiColors

    # Pre-built binary release asset (GitHub, GitLab, or Gitea)
    - name: ptah
      type: release
      repo: komashchenko/PTaH
      version: latest

  # Root source directory containing your plugin
  root: /addons/sourcemod/scripting

  # List of target .sp files to compile (without .sp extension)
  targets:
    - my_plugin
```

### 3. Build Plugin

```bash
sourceknight build
```

This command runs three steps automatically:
1. **`update`**: Concurrently downloads and caches all declared dependencies.
2. **`unpack`**: Stages headers and assets into an isolated build tree at `.sourceknight/build/`.
3. **`compile`**: Invokes `spcomp` across targets and outputs `.smx` binaries.

---

## Common Workflows

### Parallel Compilation

For projects with multiple plugin targets, compile concurrently across all available CPU cores:

```bash
sourceknight build -j 4
```

### Custom Output Directory

Specify where compiled `.smx` binaries should be placed:

```bash
sourceknight build -o plugins/
```

### Resilient CI Reporting

Generate a structured JSON compilation report and fail fast if desired:

```bash
sourceknight build --report json --fail-fast
```

---

## Dependency Driver Reference

| Driver (`type`) | Description | Example Configuration |
| :--- | :--- | :--- |
| `smdrop` | AlliedModders official SourceMod builds | `name: sourcemod`<br>`type: smdrop`<br>`version: 1.12.x` |
| `git` | Git repository (shallow clone) | `name: multicolors`<br>`type: git`<br>`repo: https://github.com/srcdslab/sm-plugin-MultiColors`<br>`version: master` |
| `release` | Release asset from GitHub / GitLab / Gitea | `name: ptah`<br>`type: release`<br>`repo: komashchenko/PTaH`<br>`version: latest`<br>`asset_pattern: "*linux*.zip"` |
| `zip` | Remote `.zip` archive URL | `name: lib`<br>`type: zip`<br>`location: https://example.com/lib.zip` |
| `tar` | Remote `.tar` / `.tar.gz` archive URL | `name: lib`<br>`type: tar`<br>`location: https://example.com/lib.tar.gz` |
| `file` | Local directory or archive in project | `name: local-sdk`<br>`type: file`<br>`location: ./vendor/sdk.zip` |

---

## CI/CD: GitHub Actions Integration

Use the official SourceKnight action in `.github/workflows/ci.yml`:

```yaml
name: CI

on: [push, pull_request, workflow_dispatch]

jobs:
  build:
    name: Build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup SourceKnight
        uses: SparkyCloudy/sourceknight@master

      - name: Build Plugins
        run: sourceknight build -j 4

      - name: Package Output
        run: |
          mkdir -p /tmp/package/addons/sourcemod/plugins
          cp addons/sourcemod/plugins/*.smx /tmp/package/addons/sourcemod/plugins/

      - name: Upload Artifact
        uses: actions/upload-artifact@v4
        with:
          name: plugins
          path: /tmp/package
```

---

## CLI Command Reference

| Command | Description |
| :--- | :--- |
| `sourceknight build` | Runs the full build cycle (`update` &rarr; `unpack` &rarr; `compile`). |
| `sourceknight update` | Concurrently fetches and updates all dependencies into `.sourceknight/cache`. |
| `sourceknight unpack` | Extracts dependencies from cache into `.sourceknight/build`. |
| `sourceknight compile [targets...]` | Compiles all or specific targets using the resolved compiler. |
| `sourceknight status` | Displays cache and unpack version state for all dependencies. |

### CLI Options

- `-j, --jobs, --parallel <N>`: Set maximum concurrent compilation worker threads.
- `-o, --output-dir <path>`: Specify destination directory for compiled `.smx` files.
- `--fail-fast`: Abort compilation immediately on the first target failure.
- `--report json`: Generate `compile_report.json` with detailed target metrics.
- `--no-color`: Disable ANSI color rendering in compiler diagnostics.
- `--override-dep <name>=<version>`: Override dependency versions at runtime.
- `-clean` / `-c` (for `unpack`): Clean the `.sourceknight/build` staging directory before unpacking.

---

## License

SourceKnight is open-source software licensed under the [MIT License](LICENSE).
