"""Reads config/buildings.json and config/areas.json - the hand-edited,
single source of every building's settings and the game graphic names it
installs as."""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "buildings.json")
AREAS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "areas.json")


def load_area_groups():
    """Returns the whole {group_name: [civ_prefix, ...]} dict from
    config/areas.json - e.g. "areas" (12 civs), "more_areas" (22 civs),
    "castle_areas" (62 civs, castles get far more per-civ art than most
    buildings). Any group name here works as a building's area_prefix -
    nothing hardcodes just "areas"/"more_areas"."""
    with open(AREAS_CONFIG_PATH) as f:
        return json.load(f)


def expand(targets, area_prefix):
    """Turns a config's raw "targets" (un-prefixed area suffixes if
    area_prefix names a group in config/areas.json, otherwise already-full
    names) into real graphic names."""
    if area_prefix is None:
        return targets
    prefixes = load_area_groups()[area_prefix]
    return [f"b_{p}_{s}" for p in prefixes for s in targets]


def load_all():
    """Returns the whole {building_name: config} dict from config/buildings.json."""
    if not os.path.isfile(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load(building_name):
    """Returns the parsed config dict for `building_name`, or None if it
    has no entry in config/buildings.json."""
    return load_all().get(building_name)


def target_names(config):
    """The real, final graphic name(s) this building's output installs as."""
    return expand(config["targets"], config["area_prefix"])


def destruction_target_names(config):
    if "destruction_targets" in config:
        return expand(config["destruction_targets"], config["area_prefix"])
    """The game graphic name(s) for this building's destruction animation:
    "destruction_targets" from the config if set, otherwise every target
    with "_destruction" inserted before its trailing "_x1", expanded with the
    same area_prefix as the living building."""
    d_targets = [
        f"{t[:-3]}_destruction_x1" if t.endswith("_x1") else f"{t}_destruction"
        for t in config["targets"]
    ]
    return expand(d_targets, config["area_prefix"])


def damage_target_names(config, percent):
    """The real, final graphic name(s) for this building's static partial-
    damage snapshot at `percent` (25/50/75) - a separate, non-animated
    graphic slot from `destruction_target_names`'s own collapse animation
    (confirmed real: walls have both `wall_stone_destruction_x1`, the full
    collapse, AND `wall_stone_destr_25/50/75_x1`, three static "still
    standing but damaged" snapshots - different naming pattern, "_destr_N"
    not "_destruction", same per-target/area_prefix derivation as
    `destruction_target_names`)."""
    d_targets = [
        f"{t[:-3]}_destr_{percent}_x1" if t.endswith("_x1") else f"{t}_destr_{percent}"
        for t in config["targets"]
    ]
    return expand(d_targets, config["area_prefix"])
