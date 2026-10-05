"""One-off cleanup: finds and removes the red single-voxel "marker cube"
convention some .gox files use (3 isolated corner voxels at ground level,
marking the intended tile footprint for conv.py's crop-to-content step -
see SLD_PIPELINE_PLAN.md). Now redundant: the pipeline reads the .gox
file's own IMG "box" metadata for that instead (voxel_render.py), so these
no longer need to be modeled by hand.

Detection rule (matches every marker cube found in files-gox/ during
investigation - single-voxel, reddish, sitting at the model's own lowest
z-layer): a connected component of size 1, red-dominant color, at
z == min(z for all voxels in the model).
"""
import sys

import DIRS
from gox_reader import read_gox
from gox_writer import remove_voxels


def connected_components(voxels):
    voxset = set(voxels.keys())
    seen = set()
    comps = []
    for start in voxset:
        if start in seen:
            continue
        stack = [start]
        comp = []
        seen.add(start)
        while stack:
            x, y, z = stack.pop()
            comp.append((x, y, z))
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                n = (x + dx, y + dy, z + dz)
                if n in voxset and n not in seen:
                    seen.add(n)
                    stack.append(n)
        comps.append(comp)
    return comps


def is_reddish(rgba):
    r, g, b, a = rgba
    return a > 0 and r > 150 and g < 100 and b < 100


def find_marker_cubes(model):
    if not model.voxels:
        return []
    min_z = min(z for _, _, z in model.voxels)
    comps = connected_components(model.voxels)
    markers = []
    for comp in comps:
        if len(comp) != 1:
            continue
        pos = comp[0]
        if pos[2] == min_z and is_reddish(model.voxels[pos]):
            markers.append(pos)
    return markers


def main():
    import glob

    paths = sys.argv[1:] or sorted(glob.glob(f"{DIRS.MAIN}/{DIRS.GOX}/*.gox"))
    total_files = 0
    total_cubes = 0
    errors = []
    for path in paths:
        try:
            model = read_gox(path)
            markers = find_marker_cubes(model)
            if not markers:
                continue
            removed = remove_voxels(path, markers)
            total_files += 1
            total_cubes += removed
            print(f"{path}: removed {removed} marker cube(s) at {markers}")
        except Exception as e:
            errors.append((path, str(e)))
            print(f"{path}: SKIPPED ({e})")
    print(f"\ndone: {total_cubes} marker cubes removed across {total_files} files "
          f"({len(errors)} file(s) skipped due to errors)")
    if errors:
        print("skipped files:")
        for path, err in errors:
            print(f"  {path}: {err}")


if __name__ == "__main__":
    main()
