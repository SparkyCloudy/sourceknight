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
- **Native Packaging & Distribution Engine**: Smart auto-discovery and bundling of compiled `.smx` binaries alongside runtime assets (`translations`, `configs`, `gamedata`, `cfg`, `sound`, `models`, `materials`, `common`) into structured package directories or compressed release archives (`.zip` / `.tar.gz`).
- **Resilient Compilation Loop**: Builds all targets and reports overall status, with optional `--fail-fast` and `--report json` output.
- **Formatted & Colorized Diagnostics**: Highlights compiler errors and warnings with ANSI colors in terminals and generates inline annotations in GitHub Actions.
- **Dynamic Dependency Overrides**: Override dependency versions at runtime via CLI flags (`--override-dep`) or environment variables (`SK_OVERRIDE_<NAME>`) for CI matrix testing.
- **Official GitHub Action**: Pre-packaged composite action with standalone binary download and dependency caching support.

---

## Installation

### Option 1: Standalone Binary (Zero Dependencies)

Download the pre-compiled binary executable for your platform from the [latest GitHub Release](https://github.com/SparkyCloudy/sourceknight/releases/latest):

- **Linux (x86_64)**:
  ```bash
  curl -fsSL https://github.com/SparkyCloudy/sourceknight/releases/latest/download/sourceknight-linux-x86_64 -o /usr/local/bin/sourceknight
  chmod +x /usr/local/bin/sourceknight
  ```

- **Windows (x86_64)**:
  Download [`sourceknight-windows-x86_64.exe`](https://github.com/SparkyCloudy/sourceknight/releases/latest/download/sourceknight-windows-x86_64.exe) and add it to your system `PATH`.

---

### Option 2: Python Package (pip)

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

*Requires Python >= 3.12 (for pip installation).*

---

## Quickstart

### 1. Project Directory Layout

```text
my-plugin/
├── sourceknight.yaml
└── addons/
    └── sourcemod/
        ├── scripting/
        │   ├── my_plugin.sp
        │   └── include/
        │       └── my_plugin_internal.inc
        ├── translations/
        │   └── my_plugin.phrases.txt
        └── configs/
            └── my_plugin.cfg
```

### 2. Configure `sourceknight.yaml`

```yaml
project:
  sourceknight: 0.7
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

# Optional: Custom packaging & release distribution settings
package:
  output: build/package
  archive: zip                 # Options: "zip", "tar.gz", "both", or false
```

### 3. Build & Package Plugin

```bash
# Build only
sourceknight build

# Build and package for distribution in one command
sourceknight build --package -o dist/
```

This command runs the entire pipeline automatically:
1. **`update`**: Concurrently downloads and caches all declared dependencies.
2. **`unpack`**: Stages headers and assets into an isolated build tree at `.sourceknight/build/`.
3. **`compile`**: Concurrently invokes `spcomp` across targets and outputs `.smx` binaries.
4. **`package`**: Auto-discovers and bundles `.smx` binaries and runtime assets into `dist/`.

---

## Common Workflows

### Parallel Compilation

For projects with multiple plugin targets, compile concurrently across all available CPU cores:

```bash
sourceknight build -j 4
```

### Distribution Packaging & Archiving

Bundle compiled plugins and assets directly into `.zip` or `.tar.gz` release archives:

```bash
# Package into custom directory
sourceknight package -o /tmp/package

# Package and create both .zip and .tar.gz archives
sourceknight package -o dist/ --zip --tar
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

Use the official SourceKnight action in `.github/workflows/ci.yml` for fast, zero-boilerplate builds and packaging:

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

      - name: Build and Package
        run: sourceknight build --package -o /tmp/package

      - name: Upload Build Artifact
        uses: actions/upload-artifact@v4
        with:
          name: Linux
          path: /tmp/package
```

---

## CLI Command Reference

| Command | Description |
| :--- | :--- |
| `sourceknight build` | Runs the full build cycle (`update` &rarr; `unpack` &rarr; `compile`). |
| `sourceknight package` (alias `pack`) | Assembles compiled binaries and assets into a distribution package directory or archive. |
| `sourceknight update` | Concurrently fetches and updates all dependencies into `.sourceknight/cache`. |
| `sourceknight unpack` | Extracts dependencies from cache into `.sourceknight/build`. |
| `sourceknight compile [targets...]` | Compiles all or specific targets using the resolved compiler. |
| `sourceknight status` | Displays cache and unpack version state for all dependencies. |

### CLI Options

- `-P, --package`: Run packaging step after successful compilation (`sourceknight build -P`).
- `-o, --output <path>`: Specify destination output directory for packaging or compilation.
- `--zip`: Generate a compressed `.zip` release archive when packaging.
- `--tar, --tar-gz`: Generate a compressed `.tar.gz` release archive when packaging.
- `-j, --jobs, --parallel <N>`: Set maximum concurrent compilation worker threads.
- `--fail-fast`: Abort compilation immediately on the first target failure.
- `--report json`: Generate `compile_report.json` with detailed target metrics.
- `--no-color`: Disable ANSI color rendering in compiler diagnostics.
- `--override-dep <name>=<version>`: Override dependency versions at runtime.
- `--clean` (for `unpack` / `package`): Clean destination directories before unpacking or packaging.

---

## License

SourceKnight is open-source software licensed under the [MIT License](LICENSE).
