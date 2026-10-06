# AOE2 Checker mod tool

Converts Goxel voxel models (`files-gox/*.gox`) into Age of Empires II:
Definitive Edition `.sld` graphics and installs them straight into a local mod.
For each building it generates the living building, the destruction animation
and the construction (foundation) stages.

Works on **Linux**. **Windows** is supported by the configuration but has
**not been tested yet**: the paths and the native `DESpriteTool.exe` call are
in place, but no build has been run on Windows. Please report any problem you
find there.

## Requirements

- **AoE2:DE installed through Steam.** The tool uses `DESpriteTool.exe`, which
  ships with the game in `AoE2DE/Tools_Builds/Sprites`.
- **Python 3.14 or newer.**
- **[uv](https://docs.astral.sh/uv/)** to install the dependencies and run the
  scripts (recommended). `pip` with a virtual environment also works.
- **Linux only:** `wine` and `xvfb` (for `xvfb-run`). DESpriteTool is a Windows
  program; on Linux it runs through Wine on a virtual display.

  ```bash
  # Debian / Ubuntu
  sudo apt install wine xvfb
  ```

## Installation

```bash
git clone <repo-url>
cd AOE2-Checker-mod-tool
uv sync
```

With `pip` instead of `uv sync`:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install numpy pillow psd-tools pytoshop six
```

## Configuration

Everything that depends on your machine lives in `config/settings.toml`. Only
two things are needed: your mods folder and the mod name.

```toml
# AoE2:DE "mods/local" folder.
# Linux:   ~/.local/share/Steam/steamapps/compatdata/813780/pfx/drive_c/users/steamuser/Games/Age of Empires 2 DE/<steam id>/mods/local
# Windows: C:/Users/<you>/Games/Age of Empires 2 DE/<steam id>/mods/local
mods_dir = "..."

# Mod folder inside mods_dir where every build is installed.
mod = "Power - Checker buildings SD"

# true = also build UHD (_x2) graphics. false = SD only (_x1): faster, much smaller mod.
uhd = false

# Folder with the .gox models. Empty = the repo's own files-gox folder.
gox_dir = ""
```

| Key | What it does |
| --- | --- |
| `mods_dir` | Your AoE2:DE `mods/local` folder. `<steam id>` is the long numeric folder inside `Games/Age of Empires 2 DE`. |
| `mod` | Name of the mod folder the graphics are installed into. If it doesn't exist, it is created with a basic `info.json`. |
| `uhd` | `true`: builds SD (`_x1`) and UHD (`_x2`) graphics. `false`: builds SD only, which is faster and makes the mod much smaller (about 2 GB instead of 12 GB). |
| `gox_dir` | Folder with your own `.gox` models. Empty = `files-gox/` in this repo. File names must match the `gox` names in `config/buildings.json`. A full build only builds the buildings whose `.gox` is in this folder and skips the rest. |

The game install folder (`AoE2DE`, where `DESpriteTool.exe` is) is found
automatically: on Linux from `mods_dir`, on Windows in Steam's default location.
If your game is in another Steam library, add
`game_dir = "<path to AoE2DE>"`.

You can use `/` in paths on Windows too.

## Usage

Always from the repo root:

```bash
# Everything: living buildings, destructions and constructions.
uv run build_sld.py

# A single building, without destruction or construction.
uv run build_sld.py --name castle --no-des --no-foun

# Several buildings (--name can be repeated).
uv run build_sld.py --name monastery --name castle

# Save every frame's layers as PNGs in debug/ to inspect them.
uv run build_sld.py --name castle --debug

# Number of parallel jobs (default 16).
uv run build_sld.py --workers 8
```

`--name` values are the keys of `config/buildings.json`.

After building, enable the mod in the game's mods menu (or restart the game if
it was already open).

## Pipeline config files

- `config/buildings.json`: one entry per building (`.gox` model, camera, size in
  tiles, frame count, names of the game graphics it replaces, and construction
  parameters). Edited by hand.
- `config/areas.json`: civilization groups (each building is installed under
  the name of every civ in its group).
- `config/resources.json`: resources (trees, mines, etc.).

`config/buildings.json` is the only source of building names and settings.
To add a new `.gox`, add its entry there by hand.

## How it works

The pipeline details (voxel rendering, PSD layers, footprint diamond, shadow,
SLD format) are in [how_it_works.md](how_it_works.md).

## Troubleshooting

- **`AoE2DE not found`**: the game is not in Steam's default location; add
  `game_dir` to `config/settings.toml`.
- **The mod doesn't show up in the game**: make sure the folder is inside
  `mods/local` and has an `info.json`.
- **Linux: conversion fails**: check that `wine` and `xvfb-run` work from the
  terminal.

## Disclaimer

The tool that builds the pipeline from `.gox` to `.sld` (code and
documentation) was made with AI (Claude, by Anthropic). However, all the 3D
assets (the voxel models in `files-gox/`) were made by hand by me.
