"""Paths used by the whole tool, derived from config/settings.toml.

Only the mods folder and the mod name are configured; everything else is
derived from them, so nothing here is specific to one machine.
"""
import os
import sys
import tomllib

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
SETTINGS_PATH = f"{MAIN}/config/settings.toml"

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

# Where the mod is installed: the game's "mods/local" folder (config "mods_dir").
if not SETTINGS.get("mods_dir"):
    raise ValueError(f'{SETTINGS_PATH}: set "mods_dir" to your AoE2:DE mods/local folder')
AOEMODS = _path(SETTINGS["mods_dir"]) + "/"


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

# Mod every build installs into (config/settings.toml "mod").
MOD_SLD_TEST = SETTINGS.get("mod", "Power - Checker SLD test")
