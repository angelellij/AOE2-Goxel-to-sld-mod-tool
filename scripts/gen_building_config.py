"""One-off generator for config/buildings.json - the single-file config the
SLD pipeline (build_sld.py) reads instead of re-deriving target names from
rename.py and tile_size from folder-sniffing on every run.

Scope (confirmed with the user): only rename.renames_buildings keys that
have a matching files-gox/<key>.gox file. rename.py also has ~35 keys with
no matching .gox - foundation ("*f", now handled separately below) and
destruction-endstate ("*d", unused since #18) signal entries, plus gate/wall
orientation variants with no .gox modeled yet at all. Those are printed as a
gap report and intentionally left out - add the missing .gox before
regenerating instead of guessing here.

A couple of keys had real naming drift against the actual .gox filename
instead (confirmed: 'dock1' has no "dock1.gox", the real file is "dock.gox";
'barracks' has no "barracks.gox", the real file is "barracks1.gox" - both
are a family's Dark Age tier, filed under a plain, undecorated name).
Resolved with a symlink in files-gox/ (dock1.gox -> dock.gox, barracks.gox
-> barracks1.gox) rather than a code-level name-mapping table, so every
other place that looks up a building's own .gox by its config key (there
are several) doesn't need to know about the exception. This is exactly why
the Dark Age dock never rendered in-game ("el dock no se ve") - "dock1" was
always silently treated as an unfixable gap, never actually built.

destructible: True if "{key}d" is also a rename.renames_buildings key whose
resolved target name(s) contain "destruction" - i.e. rename.py already
records that this building has a destroyed end-state, which is exactly the
signal the new pipeline needs to know it must generate a procedural 5-frame
destruction animation from this same .gox (see SLD_PIPELINE_PLAN.md).
"""
import glob
import json
import os
import sys

import DIRS
import building_config
import rename
import voxel_render


def resolve(entry):
    """Same expansion rename.py itself does - returns (targets, area_prefix)
    where targets is the raw target list (un-prefixed area suffixes if
    area_prefix is set, otherwise the full explicit names)."""
    if isinstance(entry, dict):
        if entry.get("areas") is not None:
            return entry["areas"], "areas"
        if entry.get("more_areas") is not None:
            return entry["more_areas"], "more_areas"
        return [], None
    return entry, None


_REAL_GRAPHICS_FILES = None


def _real_graphics_files():
    # Cached: is_destructible() is called once per building (~54 times).
    global _REAL_GRAPHICS_FILES
    if _REAL_GRAPHICS_FILES is None:
        _REAL_GRAPHICS_FILES = set(os.listdir(DIRS.AOE2DE_GRAPHICS))
    return _REAL_GRAPHICS_FILES


def is_destructible(targets, area_prefix):
    """True if the real, shipped game actually has "_destruction" art for
    this building's own targets. rename.py's separate "<name>d" keys used to
    answer this (and still name destruction_target_names' *fallback* civ
    coverage bug - see building_config.destruction_target_names) but are
    incomplete: confirmed missing entirely for stable2/3, towncenter1-4,
    monastery, tower1-4, house1-3, outpost, university, and 15+ others that
    definitely have real destruction art in-game. Checking the real installed
    game files directly (source of truth, no rename.py gap possible) found
    45 truly-destructible buildings vs. only 15 rename.py's "<name>d" keys
    covered."""
    config = {"targets": targets, "area_prefix": area_prefix}
    d_targets = building_config.destruction_target_names(config)
    real_files = _real_graphics_files()
    return any(f"{t}.sld" in real_files for t in d_targets)


# Keys with no .gox source because there's genuinely nothing to draw - the
# real graphic is meant to render as fully transparent (construction-stage
# decor pieces, snow decals). build_sld.py writes a blank PSD for these
# instead of running the normal voxel pipeline - see build_psd.write_blank_psd.
EMPTY_KEYS = ("empty", "empty2")

# rename.py's own area_prefix per key is sometimes just wrong for real,
# shipped assets - confirmed for castle: the real mod has per-civ castle
# graphics for 62 civs (config/areas.json's "castle_areas"), not the 22 of
# "more_areas" rename.py says. Override here rather than editing rename.py
# itself (still used by the old .smx pipeline, which may have its own reasons).
AREA_PREFIX_OVERRIDES = {
    "castle": "castle_areas",
}

# Per-building "margin" (see voxel_render.tile_params/build_psd.build_layers):
# extra empty space added around the building within its own tile canvas, so
# it sits a bit smaller and pulled in from the footprint-diamond's edge
# rather than touching it - purely cosmetic, doesn't affect the diamond's own
# size. DEFAULT_MARGIN applies to every building except NO_MARGIN_KEYS, which
# must sit flush with the diamond edge instead: town center and castle (large
# "anchor" buildings), walls/corners/gates (need to line up edge-to-edge with
# the next wall segment), and towers/outpost (thin, already-tight footprints
# where shrinking further looked wrong).
DEFAULT_MARGIN = 10
NO_MARGIN_KEYS = {
    "castle",
    "towncenter1", "towncenter2", "towncenter3", "towncenter4",
    "stonewall", "fortifiedwall", "palisade",
    "stonecorner", "fortifiedcorner", "palisade_gate_corner",
    "stone2_open", "stone2_closed", "palisade2_open", "palisade2_closed",
    "stone22_open", "stone22_closed", "palisade22_open", "palisade22_closed",
    "tower1", "tower2", "tower3", "tower4",
    "outpost",
}

# A wall gate only ever needs ONE real .gox per shape (straight, diagonal) -
# every other orientation is the exact same model viewed from a camera
# rotated 90 degrees around the vertical axis, not a separate model to build
# by hand (explicit user instruction: "los gates es el mismo archivo, pero
# tenes que girar la camara... el resto debe ser generado x vos girando la
# camara con un flag en config que indique que es gate" - confirmed against
# the real game's own naming: "_e_"/straight and "_n_"/rotated-straight gates
# share the exact same physical gate structure, just facing a different wall
# direction). {new_key: (source_key, angle_y_delta)} - new_key reuses
# source_key's own .gox (via its "gox" field, see build_and_install's
# gox_name handling) and rotates camera_angle_y by angle_y_delta from
# source_key's own value. -90 is a first attempt (a 90-degree azimuth swing,
# per standard_camera's azimuth = 90 - angle_y) - needs visual confirmation
# in-game like every other camera-angle tuning in this project; adjust here
# if it renders facing the wrong way.
GATE_ROTATIONS = {
    "palisade22_open": ("palisade2_open", -90),
    "palisade22_closed": ("palisade2_closed", -90),
    "stone22_open": ("stone2_open", -90),
    "stone22_closed": ("stone2_closed", -90),
    # palisade_gate_corner has no separate corner .gox at all (unlike
    # stonecorner/fortifiedcorner, which are their own real, distinct files -
    # confirmed explicitly by the user after a wrong guess in the other
    # direction: "VES QUE STONE WALL CORNER ES ALGO A PARTE O NO?" - stone/
    # fortified corners are NOT derived from their wall, they're their own
    # asset, built normally by the main loop below from their own
    # stonecorner.gox/fortifiedcorner.gox). Stand in with the plain wall's
    # own model as a last resort for palisade only (not a correct corner
    # joint shape, but never invisible, which is strictly better than the
    # alternative until a real one is modeled).
    "palisade_gate_corner": ("palisade", 0),
}


def main():
    os.makedirs(os.path.dirname(building_config.CONFIG_PATH), exist_ok=True)
    # DIRS.MAIN-anchored, not a bare relative path: running this from any
    # CWD other than the project root used to silently match zero .gox
    # files and overwrite config/buildings.json (untracked by git, no
    # history to recover from) with a near-empty stub - confirmed this
    # actually happened once, recovered only by re-deriving every
    # building's tile_size from its own .gox voxel extent. See also the
    # entry-count safety check below, added for the same reason.
    gox_names = set(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(f"{DIRS.MAIN}/{DIRS.GOX}/*.gox")
    )
    existing_all = building_config.load_all()

    configs = {}
    gaps = []
    for key, entry in rename.renames_buildings.items():
        if key in EMPTY_KEYS:
            targets, area_prefix = resolve(entry)
            configs[key] = {
                "gox": None,
                "targets": targets,
                "area_prefix": area_prefix,
                "tile_size": None,
                "destructible": False,
                "frame_count": 1,
                "camera_angle_x": None,
                "camera_angle_y": None,
                "empty": True,
            }
            continue
        if key not in gox_names:
            gaps.append(key)
            continue

        targets, area_prefix = resolve(entry)
        area_prefix = AREA_PREFIX_OVERRIDES.get(key, area_prefix)
        tile_size = voxel_render.find_tile_size(key)
        if tile_size is None:
            # Fall back to whatever's already on disk - a few buildings
            # (e.g. blacksmith2, market3) have no plain "<name>.png" to
            # sniff a folder from (only "_des*"/percent-built variants
            # exist), so their tile_size was hand-verified once and
            # shouldn't get clobbered back to null on every regeneration.
            existing = existing_all.get(key)
            if existing is not None:
                tile_size = existing.get("tile_size")

        # How many idle-animation frames to generate (all identical content
        # for now - see SLD_PIPELINE_PLAN.md/build_psd.py). Most buildings
        # are static (1); a few (stable, mill, house...) need many more or
        # the game renders them as invisible - hand-set per building as
        # they're found during testing, and preserved across regeneration.
        frame_count = existing_all.get(key, {}).get("frame_count", 1)

        # Whether frame_count above means N distinct shape *variants* (one
        # picked per individually-placed building, so build_and_install_
        # destruction must repeat its collapse sequence that many times to
        # keep the destruction SLD's frame indexing aligned with the living
        # one - see its docstring) rather than a continuous idle animation
        # loop (mill/stable - a much larger frame_count that must NOT be
        # multiplied). Confirmed per-building against the real game's own
        # files, not inferable from frame_count's value alone - hand-set,
        # preserved across regeneration like frame_count itself.
        frame_count_is_variants = existing_all.get(key, {}).get("frame_count_is_variants", False)

        # The fixed synthetic camera voxel_render.standard_camera() builds
        # (see its docstring) - (60, 45) for virtually everything. The one
        # confirmed exception is palisade2_open, a gate viewed face-on,
        # whose real .gox camera matches (60, -45) instead. Preserved across
        # regeneration like tile_size/frame_count.
        camera_angle_x = existing_all.get(key, {}).get("camera_angle_x", 60)
        camera_angle_y = existing_all.get(key, {}).get("camera_angle_y", 45)

        default_margin = 0 if key in NO_MARGIN_KEYS else DEFAULT_MARGIN
        margin = existing_all.get(key, {}).get("margin", default_margin)

        configs[key] = {
            "gox": key,
            "targets": targets,
            "area_prefix": area_prefix,
            "tile_size": tile_size,
            "destructible": is_destructible(targets, area_prefix),
            "frame_count": frame_count,
            "frame_count_is_variants": frame_count_is_variants,
            "camera_angle_x": camera_angle_x,
            "camera_angle_y": camera_angle_y,
            "margin": margin,
        }

    # Gate orientations generated by rotating another gate's own camera
    # instead of needing their own .gox - see GATE_ROTATIONS.
    for key, (source_key, angle_y_delta) in GATE_ROTATIONS.items():
        if source_key not in configs:
            continue  # source itself not buildable (no .gox yet) - skip
        entry = rename.renames_buildings.get(key)
        if entry is None:
            continue  # no real target name known for this orientation yet
        targets, area_prefix = resolve(entry)
        source = configs[source_key]
        default_margin = 0 if key in NO_MARGIN_KEYS else DEFAULT_MARGIN
        configs[key] = {
            **source,
            "gox": source_key,
            "targets": targets,
            "area_prefix": area_prefix,
            # Recomputed for THIS key's own real targets, not inherited from
            # source - confirmed necessary: "palisade" (the plain wall) isn't
            # destructible, but "palisade_gate_corner" (reusing its model as
            # a stand-in) really is in the real game, and blindly spreading
            # source's own False silently produced a corner with no rubble.
            "destructible": is_destructible(targets, area_prefix),
            "camera_angle_y": source["camera_angle_y"] + angle_y_delta,
            "margin": existing_all.get(key, {}).get("margin", default_margin),
        }
    gaps = [k for k in gaps if k not in configs]

    # Foundation entries ("<base>f", e.g. "castlef") - a real, separate
    # graphic slot (see building_config's "foundation" flag /
    # build_sld.foundation_families) that has no .gox of its own (it's built
    # from the living building's own .gox plus the family's shared
    # "<base>0.gox" - see build_psd.build_foundation_frames), so the main
    # loop above always skips it as a "gap". Previously build_sld.py read
    # these straight from rename.py at *runtime* - the one place that still
    # did, after #18/#21 moved every other target-name lookup onto
    # config/buildings.json. Folded in here instead so config/buildings.json
    # is the single, hand-editable source of truth for every building-ish
    # target name, foundations included, and rename.py is never consulted
    # once the pipeline is actually running.
    for key, entry in rename.renames_buildings.items():
        if key in configs or not key.endswith("f") or key.endswith("ff"):
            continue
        targets, area_prefix = resolve(entry)
        configs[key] = {
            "targets": targets,
            "area_prefix": area_prefix,
            "foundation": True,
        }
    # These just got real config entries above - not actually gaps.
    gaps = [k for k in gaps if k not in configs]

    # config/buildings.json is untracked by git - there is no history to
    # recover from if this silently writes a near-empty file (e.g. because
    # the .gox glob above matched nothing). Refuse rather than clobber
    # good data with a much smaller result; --force bypasses this for a
    # genuine, intentional shrink (e.g. removing buildings from rename.py).
    if existing_all and len(configs) < 0.5 * len(existing_all) and "--force" not in sys.argv:
        raise RuntimeError(
            f"refusing to write {len(configs)} building(s) - existing config/buildings.json "
            f"has {len(existing_all)}. This usually means the .gox glob matched nothing (wrong "
            f"CWD?) rather than a real drop in buildings. Pass --force to overwrite anyway."
        )

    with open(building_config.CONFIG_PATH, "w") as f:
        json.dump(configs, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"wrote {len(configs)} building(s) to {os.path.normpath(building_config.CONFIG_PATH)}")
    no_tile_size = [
        k for k, c in configs.items()
        if not c.get("empty") and not c.get("foundation") and c.get("tile_size") is None
    ]
    if no_tile_size:
        print(f"\n{len(no_tile_size)} written WITHOUT a resolvable tile_size (no files-png/*x*/<name>.png found):")
        for k in sorted(no_tile_size):
            print(f"  {k}")

    print(f"\n{len(gaps)} rename.py key(s) skipped (no matching files-gox/<key>.gox):")
    for k in sorted(gaps):
        print(f"  {k}")


if __name__ == "__main__":
    main()
