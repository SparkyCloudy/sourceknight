# sourceknight

> **A modern, reproducible dependency manager and build tool tailored specifically for SourceMod plugin development.**

`sourceknight` brings modern package management and build automation (similar to `cargo` or `npm`) to the SourcePawn / SourceMod ecosystem. It eliminates the hassle of manually downloading `.inc` headers, juggling SDK zip files, or committing third-party libraries directly into your Git repositories.

---

## Why Sourceknight for SourceMod Developers?

| Traditional SourceMod Workflow                                             | With Sourceknight                                                                               |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Manually downloading and extracting SourceMod SDK & compiler (`spcomp`).   | Declare `type: smdrop` and let Sourceknight download the compiler automatically for your OS.    |
| Committing dozens of third-party `.inc` files into your plugin's git repo. | Declare Git repositories or archives as dependencies; keep your repository clean.               |
| Broken local builds due to header version mismatches between team members. | Hermetic, reproducible build environments generated from `sourceknight.yaml`.                   |
| Complex CI/CD GitHub Actions scripts just to compile `.sp` to `.smx`.      | Single-step GitHub Action (`setup-sourceknight`) with matrix support across SourceMod versions. |

---

## Key Features

- 🎯 **Tailored for SourceMod**: Native understanding of SourceMod directory hierarchies (`addons/sourcemod/scripting`, `include/`, `plugins/`, `gamedata/`, etc.).
- 🚀 **Smart SourceMod Resolution (`smdrop`)**: Automatically resolves and fetches the latest `spcomp` and headers (e.g., `version: 1.12.x` or `1.11.x`) from AlliedModders across Linux and Windows.

- 📦 **Multi-Source Dependency Management**: Pull third-party include libraries from **Git repos**, **Zip/Tar releases**, **Local files**, or **SMDrop**.
- 🪄 **Heuristic Auto-Unpacking**: Automatically extracts and maps includes and scripts to their proper locations in the build tree without requiring manual mapping rules.
- ⚡ **CI/CD Matrix Testing**: Easily test your plugin against multiple SourceMod versions using CLI flags (`--override-dep`) or environment variables.
- 🤖 **Official GitHub Action**: Pre-built composite action with built-in caching for fast, friction-free CI/CD pipelines.

---

## Installation

Clone the repository and install it locally using `pip`:

```bash
git clone https://github.com/SparkyCloudy/sourceknight.git
cd sourceknight
pip install .
```

Or install directly via Git with `pip`:

```bash
pip install git+https://github.com/SparkyCloudy/sourceknight.git
```

_Requires Python >= 3.12._


---

## Quickstart: Creating a SourceMod Plugin Project

### 1. Typical Project Directory Layout

```text
my-sourcemod-plugin/
├── sourceknight.yaml
└── plugins/
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
  sourceknight: 0.5
  name: my-sourcemod-plugin

  dependencies:
    # Official SourceMod compiler & core includes
    - name: sourcemod
      type: smdrop
      version: 1.12.x

    # Third-party library from GitHub (auto-extracted to scripting/include/)
    - name: sourcecolors
      type: git
      repo: https://github.com/Ilusion9/sourcecolors-inc-sm

    # Third-party include release archive
    - name: autoexecconfig
      type: zip
      location: https://github.com/Impact123/AutoExecConfig/releases/download/v1.0.0/autoexecconfig.zip

  # Path to your plugin source files
  root: /plugins

  # List of target .sp files to compile (without .sp extension)
  targets:
    - my_plugin
```

### 3. Write Your Plugin (`plugins/.../scripting/my_plugin.sp`)

```sourcepawn
#include <sourcemod>
#include <sourcecolors>
#include <autoexecconfig>

public Plugin myinfo = {
    name = "My Awesome Plugin",
    author = "Your Name",
    description = "Demonstrating Sourceknight dependency management",
    version = "1.0.0",
    url = "https://github.com/yourname/my-plugin"
};

public void OnPluginStart() {
    CPrintToChatAll("{green}[MyPlugin]{default} Successfully loaded with managed dependencies!");
}
```

### 4. Build Your Plugin

```bash
sourceknight build
```

**What happens behind the scenes:**

1. **`update`**: Downloads SourceMod (providing `spcomp`), `sourcecolors`, and `autoexecconfig` into `.sourceknight/cache`.
2. **`unpack`**: Stages all dependencies into an isolated virtual build environment at `.sourceknight/build/addons/sourcemod/`.
3. **`compile`**: Runs the resolved `spcomp` against `my_plugin.sp` and outputs `my_plugin.smx` directly into your workspace.

---

## Common SourceMod Plugin Scenarios

### Specifying an Output Folder for `.smx` Files

To output compiled `.smx` files into a `compiled/` or `plugins/` directory:

```bash
sourceknight build -o compiled/
```

Or configure it permanently in `sourceknight.yaml`:

```yaml
project:
  sourceknight: 0.5
  name: my-plugin
  root: /plugins
  output: /build/plugins
  targets:
    - my_plugin
```

### Building Multiple Plugin Targets

If your project compiles multiple `.sp` files (e.g. modular plugin architecture):

```yaml
targets:
  - my_core_plugin
  - my_admin_module
  - my_chat_module
```

You can build all targets at once with `sourceknight build`, or build a single target with:

```bash
sourceknight compile my_admin_module
```

### Manual Unpack Mapping

While Sourceknight automatically detects standard SourceMod directories (`scripting/`, `include/`, `plugins/`, etc.), you can specify custom extraction paths if an external repository uses a non-standard layout:

```yaml
dependencies:
  - name: nonstandard-lib
    type: git
    repo: https://github.com/example/nonstandard-lib
    unpack:
      - source: /src/headers
        dest: /addons/sourcemod/scripting/include
      - source: /gamedata/custom.txt
        dest: /addons/sourcemod/gamedata/custom.txt
```

---

## Dependency Driver Reference

| Driver (`type`) | Purpose                                                           | Required Fields                                      |
| --------------- | ----------------------------------------------------------------- | ---------------------------------------------------- |
| `smdrop`        | AlliedModders SourceMod builds (resolves `spcomp` + core headers) | `version` (e.g. `1.12.x`, `1.11.x`)                  |
| `git`           | Clones a Git repository                                           | `repo` (URL), optional `version` (branch/tag/commit) |
| `zip`           | Remote `.zip` archive (GitHub releases, AlliedMods attachments)   | `location` (URL), optional `version`                 |
| `tar`           | Remote `.tar` / `.tar.gz` archive                                 | `location` (URL), optional `version`                 |
| `file`          | Local file or archive within project directory                    | `location` (relative path)                           |

---

## CI/CD: Automated Multi-Version Plugin Testing

With Sourceknight's dynamic version override support, you can test and compile your SourceMod plugins across multiple SourceMod versions (e.g., 1.11 and 1.12) in GitHub Actions with zero boilerplate.

### Example GitHub Actions Workflow (`.github/workflows/build.yml`)

```yaml
name: Build SourceMod Plugins

on:
  push:
    branches: [master, main]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        sourcemod: ["1.11.x", "1.12.x"]

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Sourceknight
        uses: SparkyCloudy/sourceknight@master
        with:
          python-version: "3.12"
          cache: "true"


      - name: Build Plugins for SourceMod ${{ matrix.sourcemod }}
        run: |
          sourceknight build --override-dep sourcemod=${{ matrix.sourcemod }} -o dist/${{ matrix.sourcemod }}

      - name: Upload Compiled Plugins (.smx)
        uses: actions/upload-artifact@v4
        with:
          name: plugins-sm-${{ matrix.sourcemod }}
          path: dist/${{ matrix.sourcemod }}/*.smx
```

---

## CLI Command Reference

| Command                         | Description                                                            |
| ------------------------------- | ---------------------------------------------------------------------- |
| `sourceknight build`            | Runs the complete workflow: `update` &rarr; `unpack` &rarr; `compile`. |
| `sourceknight update`           | Fetches, downloads, and caches all declared dependencies.              |
| `sourceknight unpack`           | Extracts dependencies from cache into `.sourceknight/build`.           |
| `sourceknight compile [target]` | Invokes `spcomp` to compile all targets or a specific target.          |
| `sourceknight status`           | Shows cached vs unpacked version status for all dependencies.          |

### Global CLI Flags

- `-p, --path <path>`: Path to project directory containing `sourceknight.yaml` (default: current directory).
- `-o, --output <path>`: Directory to place compiled `.smx` files.
- `--override-dep <name>=<version>`: Override dependency versions at runtime (e.g., `--override-dep sourcemod=1.11.x`).
- `-clean` / `-c` (for `unpack`): Rebuild the `.sourceknight/build` staging directory from scratch.

---

## State & Workspace Cleaning

Sourceknight keeps all downloaded caches and temporary staging files inside `.sourceknight/` in your project root:

- `.sourceknight/cache/`: Downloaded archives and cloned repositories.
- `.sourceknight/build/`: Virtual SourceMod staging directory containing merged headers and include files.
- `.sourceknight/state.yaml`: State tracking for incremental builds.

To force a clean slate, delete `.sourceknight/`:

```bash
rm -rf .sourceknight
```

---

## License

Sourceknight is licensed under the [MIT License](LICENSE).
