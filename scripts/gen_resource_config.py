"""One-off generator for config/resources.json - the resource counterpart
of config/buildings.json (see gen_building_config.py), built from
rename.renames_resources. Resources never use the civ area-prefix
expansion (renames_resources is always a flat target list, never an
{'areas': [...]} dict), so there's no area_prefix/destructible field here -
just the gox name, its target name(s), and tile_size where inferable.

Scope: only renames_resources keys with a matching files-gox/<key>.gox file
(2 of 12 - tree_big, tree_cut - have none and are skipped, same as
gen_building_config.py does for buildings)."""
import glob
import json
import os
import sys

import DIRS
import rename
import voxel_render

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "resources.json")


def main():
    # DIRS.MAIN-anchored, not a bare relative path - see gen_building_config.py's
    # own version of this same bug (running from the wrong cwd matched zero
    # .gox files and nearly wrote an empty config over hand-tuned data).
    gox_names = set(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(f"{DIRS.MAIN}/{DIRS.GOX}/*.gox")
    )
    existing = {}
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            existing = json.load(f)

    configs = {}
    gaps = []
    for key, targets in rename.renames_resources.items():
        if key not in gox_names:
            gaps.append(key)
            continue

        tile_size = voxel_render.find_tile_size(key)
        if tile_size is None and key in existing:
            tile_size = existing[key].get("tile_size")

        # config/resources.json is the hand-editable source of truth for
        # target names from here on, same as config/buildings.json - once a
        # key exists, its own "targets" list is preserved across
        # regeneration instead of being overwritten from rename.py every
        # time (rename.py is only ever consulted here, at generation time,
        # to bootstrap a *new* key - never at pipeline runtime). Add new
        # target names (e.g. a newly-added tree species) directly to this
        # file, not to rename.py.
        if key in existing and "targets" in existing[key]:
            targets = existing[key]["targets"]

        configs[key] = {
            "gox": key,
            "targets": targets,
            "tile_size": tile_size,
        }

    if existing and len(configs) < 0.5 * len(existing) and "--force" not in sys.argv:
        raise RuntimeError(
            f"refusing to write {len(configs)} resource(s) - existing config/resources.json "
            f"has {len(existing)}. This usually means the .gox glob matched nothing (wrong "
            f"cwd?) rather than a real drop in resources. Pass --force to overwrite anyway."
        )

    with open(CONFIG_PATH, "w") as f:
        json.dump(configs, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"wrote {len(configs)} resource(s) to {os.path.normpath(CONFIG_PATH)}")
    no_tile_size = [k for k, c in configs.items() if c["tile_size"] is None]
    if no_tile_size:
        print(f"\n{len(no_tile_size)} written WITHOUT a resolvable tile_size:")
        for k in sorted(no_tile_size):
            print(f"  {k}")

    print(f"\n{len(gaps)} rename.py key(s) skipped (no matching files-gox/<key>.gox):")
    for k in sorted(gaps):
        print(f"  {k}")


if __name__ == "__main__":
    main()
