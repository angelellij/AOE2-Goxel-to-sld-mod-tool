"""Paths used by the whole tool, from settings.toml at the repo root.

settings.toml is the user's own (git-ignored) copy; without it the tool falls
back to default_settings.toml, so nothing here is specific to one machine.
"""
import os
import sys
import tomllib

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
SETTINGS_PATH = f"{MAIN}/settings.toml"
if not os.path.isfile(SETTINGS_PATH):
    SETTINGS_PATH = f"{MAIN}/default_settings.toml"

PNG_RAW = "files-png"
PNG_PROCESSED = "files-png-processed"
GOX = "files-gox"
PSD = "files-psd"
SLD = "files-sld"
SMX = "files-smx"
AOEGRAPHICS = '/resources/_common/drs/graphics/'

def load_settings():
    with open(SETTINGS_PATH, "rb") as f:
        return tomllib.load(f)


SETTINGS = load_settings()

WINDOWS = sys.platform == "win32"


def _path(p):
    return os.path.expandvars(os.path.expanduser(p)).replace("\\", "/").rstrip("/")


# Folder with the .gox models (config "gox_dir"); empty = the repo's own files-gox.
GOX_DIR = _path(SETTINGS.get("gox_dir") or f"{MAIN}/{GOX}")
if not os.path.isdir(GOX_DIR):
    raise ValueError(f'{SETTINGS_PATH}: gox_dir "{SETTINGS.get("gox_dir")}" -> {GOX_DIR} does not exist')

# buildings.json / resources.json (config "buildings_config" / "resources_config");
# empty = the repo's own config/ files.
BUILDINGS_CONFIG = _path(SETTINGS.get("buildings_config") or f"{MAIN}/config/buildings.json")
RESOURCES_CONFIG = _path(SETTINGS.get("resources_config") or f"{MAIN}/config/resources.json")
for _name, _file in (("buildings_config", BUILDINGS_CONFIG), ("resources_config", RESOURCES_CONFIG)):
    if not os.path.isfile(_file):
        raise ValueError(f'{SETTINGS_PATH}: {_name} -> {_file} does not exist')


def _detect_mods_dir():
    """The standard AoE2:DE mods/local folder, when there is a single Steam
    profile (the long numeric folder) that has one."""
    if WINDOWS:
        games = _path("~/Games/Age of Empires 2 DE")
    else:
        games = _path("~/.local/share/Steam/steamapps/compatdata/813780/pfx/drive_c/users/steamuser"
                      "/Games/Age of Empires 2 DE")
    found = []
    if os.path.isdir(games):
        found = [d for d in os.listdir(games)
                 if d.isdigit() and len(d) > 5 and os.path.isdir(f"{games}/{d}/mods")]
    if len(found) != 1:
        raise ValueError(
            f'{SETTINGS_PATH}: could not auto-detect the mods folder under {games} '
            f'(profiles found: {found or "none"}) - set mods_dir'
        )
    return f"{games}/{found[0]}/mods/local"


# Where the mod is installed: the game's "mods/local" folder (config "mods_dir").
AOEMODS = (_path(SETTINGS["mods_dir"]) if SETTINGS.get("mods_dir") else _detect_mods_dir()) + "/"


def _game_dir():
    """The AoE2DE install folder (DESpriteTool and the vanilla graphics live
    there). Found from mods_dir instead of being configured: on Linux the mods
    folder sits inside Steam's own tree (Proton prefix), on Windows Steam is
    looked up in its default location. "game_dir" in the config overrides it."""
    if SETTINGS.get("game_dir"):
        return _path(SETTINGS["game_dir"])
    if "/steamapps/" in AOEMODS:
        candidate = AOEMODS.split("/steamapps/")[0] + "/steamapps/common/AoE2DE"
    else:
        candidate = "C:/Program Files (x86)/Steam/steamapps/common/AoE2DE"
    if not os.path.isdir(candidate):
        raise ValueError(
            f'{SETTINGS_PATH}: AoE2DE not found at {candidate} - add game_dir = "<your AoE2DE folder>"'
        )
    return candidate


GAME_DIR = _game_dir()
SPRITES_TOOL = f"{GAME_DIR}/Tools_Builds/Sprites"
# Vanilla game graphics, for checking real game file names.
AOE2DE_GRAPHICS = f"{GAME_DIR}/resources/_common/drs/graphics"

# Mod every build installs into (settings "mod").
MOD_SLD_TEST = SETTINGS.get("mod", "Power - Checker SLD test")
# Mod the resources (build_sld.py --resources) install into (config "resources_mod").
MOD_RESOURCES = SETTINGS.get("resources_mod", "Power - Checker resources SD")
