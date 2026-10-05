"""Orthographic renderer for Goxel voxel models: produces Normal, Height and
AmbientOcclusion passes using a fixed synthetic camera (standard_camera()
below) matching the game's real, constant viewing angle - not each .gox
file's own saved camera, which is per-file hand-set-in-Goxel state that can
drift or break outright (see standard_camera()'s docstring).

Approach (kept deliberately simple - this only needs to feed DESpriteTool,
not look photoreal):
  - A voxel is a unit cube at integer (x, y, z), spanning [x,x+1]x[y,y+1]x[z,z+1].
  - For a fixed orthographic view direction D, only 3 of a cube's 6 faces can
    ever face the camera (one per axis, whichever sign has normal . D < 0).
    A candidate face is only rendered if the neighboring voxel across it is
    empty (standard voxel face-culling) - this alone removes all interior
    geometry before rasterization.
  - Remaining faces are projected to screen space with the camera's
    right/up basis vectors and rasterized as two triangles each, with a
    z-buffer to resolve overlaps between unrelated voxels (e.g. a roof
    silhouette in front of a wall behind it).
  - Output pixel values: the face's flat outward normal (Normals pass), its
    world Z (Height pass), and a per-voxel-face ambient occlusion estimate
    from solid 26-neighborhood occupancy (AmbientOcclusion pass).

Absolute pixel scale/resolution is not calibrated to match Goxel's own PNG
export - that isn't needed. Scripts/conv.py already crops to the opaque
silhouette and resizes to a fixed tile-relative width, so as long as this
renderer uses the *same camera orientation* the artist rendered with (which
it does, read straight from the file), running its output through the same
crop/resize normalization lines it up with the existing Diffuse PNG.
"""
import math
import random
import sys

import numpy as np
from PIL import Image

from gox_reader import read_gox

# Mirrors Scripts/conv.py's tile-canvas placement math exactly (tile_x/tile_y,
# margins, crop-to-alpha-bbox, resize-to-tile-width, bottom-anchored paste) so
# a Height/Normals/AmbientOcclusion render lands on the *same* canvas as the
# already-processed Diffuse PNG for the same building. Duplicated rather than
# imported from conv.py to avoid touching that already-working script.
_NO_MARGIN = [
    'palisade', 'gate', 'stonewall', 'stonecorner', 'fortifiedwall', 'fortifiedcorner',
    'castle', 'krepost', 'donjon', 'towncenter', 'tower', 'outpost',
]


def tile_params(building_name, tile_size, margin=0):
    """`margin` (config/buildings.json's per-building "margin" field, default
    0) adds extra empty space around the building's own rendered content
    within its tile canvas - shrinking it a bit and pulling it in from the
    footprint-diamond's edge - WITHOUT affecting the diamond itself, which is
    sized from `tile_x`/`tile_y` alone wherever it's drawn (callers building
    the diamond, e.g. build_psd.build_layers, don't pass margin through).
    Buildings meant to sit flush with the diamond edge (town center, castle,
    walls, gates) use margin=0."""
    tile_x = 95 * tile_size
    tile_y = 47 * tile_size
    mg_x, mg_y = 18, 12
    if any(b in building_name for b in _NO_MARGIN):
        mg_x, mg_y = 1, 1
    return tile_x, tile_y, mg_x + margin, mg_y + margin


def compute_placement(image, building_name, tile_size, crop_box=None, margin=0, canvas_w=None, new_w=None):
    """Computes the crop box + resize + paste position `place_on_tile_canvas`
    would use for `image`, without applying it. Exposed separately so a
    sequence of frames (e.g. destruction animation) can all share the *one*
    placement computed from the undamaged model - otherwise each frame would
    independently crop-to-content and appear to rescale as it shrinks,
    instead of collapsing in place.

    `crop_box` overrides the default "tight bbox of `image`'s own opaque
    pixels" - pass `render()`'s "box_crop_px" here to crop to the .gox
    file's own IMG box footprint instead (see render()'s docstring)."""
    tile_x, tile_y, mg_x, mg_y = tile_params(building_name, tile_size, margin)
    if canvas_w is not None:
        tile_x = canvas_w

    if crop_box is None:
        arr = np.asarray(image)
        ys, xs = np.nonzero(arr[..., 3] > 0)
        if len(xs) == 0:
            raise ValueError("image has no opaque pixels to crop to")
        crop_box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    width, height = crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]

    new_width = new_w if new_w is not None else tile_x - mg_x
    new_height_content = math.ceil(height * new_width / width)

    canvas_height = math.ceil(new_height_content + mg_y / 2)
    if canvas_height < tile_y:
        canvas_height = tile_y
    paste_x = (tile_x - new_width) // 2 if canvas_w is not None else math.ceil(mg_x / 2)
    paste_y = canvas_height - new_height_content if canvas_w is not None else canvas_height - mg_y / 2 - new_height_content
    paste_xy = (paste_x, math.ceil(paste_y))

    return {
        "crop_box": crop_box,
        "resize": (new_width, new_height_content),
        "canvas_size": (tile_x, canvas_height),
        "paste_xy": paste_xy,
    }


def apply_placement(image, placement):
    """Applies a placement computed by `compute_placement` to `image`."""
    image = image.crop(placement["crop_box"]).resize(placement["resize"])
    canvas = Image.new("RGBA", placement["canvas_size"], (0, 0, 0, 0))
    canvas.paste(image, placement["paste_xy"], image)
    return canvas


def place_on_tile_canvas(image, building_name, tile_size, crop_box=None, margin=0, canvas_w=None, new_w=None):
    """Crops `image` (RGBA) to its opaque-alpha bounding box (or `crop_box`,
    if given), resizes it to the tile width used for `building_name`/
    `tile_size`, and pastes it bottom-anchored onto a transparent
    tile_x x tile_y(-or-taller) canvas - the same placement `conv.py` uses
    for the Diffuse PNG, so layers line up."""
    return apply_placement(image, compute_placement(image, building_name, tile_size, crop_box, margin, canvas_w, new_w))


def destruction_frame_voxels(voxels, frame_index, num_frames=5, seed=0):
    """Returns a new voxel dict for one frame of a progressive top-down
    collapse, per the user's exact spec: height is split into `num_frames`
    equal Z-bands (band 1 = topmost). For `frame_index` (1-based):
    every band above it (closer to the top, i.e. destroyed in an earlier
    frame) is fully gone, `frame_index`'s own band has 80% of its voxels
    randomly removed, and every band below is untouched. E.g. frame 1: 80%
    of the top 20% gone. Frame 2: 100% of the top 20% gone, 80% of the next
    20% down gone. And so on through frame `num_frames`.

    `seed` makes the random 80% selection reproducible across rebuilds
    (same building, same frame -> same voxels removed) instead of a fresh
    random pile shape every time the pipeline runs."""
    if not voxels:
        return dict(voxels)
    zmin = min(pos[2] for pos in voxels)
    zmax = max(pos[2] for pos in voxels)
    span = max(zmax - zmin, 1e-9)

    def band_of(z):
        frac_from_top = (zmax - z) / span  # 0.0 at the very top, 1.0 at the base
        return min(int(frac_from_top * num_frames) + 1, num_frames)  # 1-based, 1 = topmost

    rng = random.Random(seed)
    result = {}
    for pos, color in voxels.items():
        band = band_of(pos[2])
        if band < frame_index:
            continue  # a higher band, already fully collapsed by now
        if band == frame_index and rng.random() < 0.8:
            continue  # this frame's own band: 80% removed
        result[pos] = color

    if not result:
        # A small building's bottommost band can be just a handful of
        # voxels - independent 80% removal can, by chance, wipe out every
        # single one, leaving nothing at all (confirmed: outpost, 212
        # voxels total spread over 10 bands, raised "model has no voxels").
        # A frame with literally nothing to render is never the right
        # result for a "settled ruins" state - keep the lowest layer of
        # voxels (the true base of whatever's left) as a minimal remainder
        # instead of vanishing entirely.
        result = {pos: color for pos, color in voxels.items() if pos[2] == zmin}
    return result


def construction_stage_voxels(voxels, fraction, extra_levels=0):
    """Returns a new voxel dict keeping only the bottom `fraction` (0-1) of
    the building by height - the inverse of destruction_frame_voxels'
    top-down collapse: a building rises from the ground during
    construction, so this is a straight height cutoff (not randomized -
    "el 33 y 66 debe mostrar el 33% y el 66% del edificio", not a random
    rubble pile)."""
    if not voxels:
        return dict(voxels)
    zmin = min(pos[2] for pos in voxels)
    zmax = max(pos[2] for pos in voxels)
    span = max(zmax - zmin, 1e-9)
    cutoff = zmin + fraction * (span + extra_levels)
    return {pos: color for pos, color in voxels.items() if pos[2] <= cutoff}


# One of these 6 axis-aligned directions is picked per axis, whichever faces
# the camera (see `visible_face_normals`).
_AXES = [
    (0, np.array([1, 0, 0])),
    (1, np.array([0, 1, 0])),
    (2, np.array([0, 0, 1])),
]


def visible_face_normals(view_dir):
    """For a fixed orthographic view direction (camera -> scene, unit
    vector), returns the up-to-3 axis-aligned face normals that can ever
    face the camera: for each axis, whichever sign has normal . view_dir < 0."""
    normals = []
    for axis, unit in _AXES:
        d = unit if view_dir[axis] < 0 else -unit
        # Skip an axis the camera is looking exactly edge-on to (d.view_dir == 0):
        # such faces are infinitely thin in screen space and contribute nothing.
        if abs(view_dir[axis]) > 1e-6:
            normals.append((axis, d))
    return normals


def exposed_faces(voxels, view_dir):
    """Yields (voxel_pos, axis, normal) for every face that (a) is one of
    the up-to-3 camera-facing orientations and (b) borders empty space."""
    face_dirs = visible_face_normals(view_dir)
    for pos in voxels:
        x, y, z = pos
        for axis, normal in face_dirs:
            neighbor = (x + normal[0], y + normal[1], z + normal[2])
            if neighbor not in voxels:
                yield pos, axis, normal


def face_corners(pos, axis, normal):
    """Returns the 4 world-space corners (CCW as seen from outside) of one
    unit-cube face at integer position `pos`, for the given outward normal."""
    x, y, z = pos
    base = np.array([x, y, z], dtype=np.float64)
    # The two in-face axes (everything but `axis`).
    others = [a for a in range(3) if a != axis]
    u_axis = np.zeros(3)
    u_axis[others[0]] = 1
    v_axis = np.zeros(3)
    v_axis[others[1]] = 1
    # Face plane sits at the +axis side of the cube if normal is positive, else the cube's own side.
    plane = base.copy()
    if normal[axis] > 0:
        plane[axis] += 1
    corners = [
        plane.copy(),
        plane + u_axis,
        plane + u_axis + v_axis,
        plane + v_axis,
    ]
    # Ensure consistent winding (CCW when viewed from along -normal, i.e.
    # from outside looking at the face) so the rasterizer's edge tests are
    # orientation-independent (we don't backface-cull here, all input faces
    # are already known-visible).
    return corners


def ambient_occlusion(voxels, pos):
    """Cheap per-voxel AO: fraction of the 26-neighborhood that's solid."""
    x, y, z = pos
    solid = 0
    total = 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                if dx == dy == dz == 0:
                    continue
                total += 1
                if (x + dx, y + dy, z + dz) in voxels:
                    solid += 1
    return solid / total


def standard_camera(angle_x=60, angle_y=45):
    """Returns (right, up, view_dir) for the game's fixed camera convention -
    NOT read from any particular .gox file's own stored camera, which is
    per-file, hand-set-in-Goxel state that can drift or break outright
    (e.g. tower3.gox's saved camera has ortho=False - not usable at all).
    Confirmed every normal building's real, working .gox camera converges
    on the same angle pair (angle_x=60, angle_y=45); the one confirmed
    exception is palisade2_open (a gate viewed face-on), whose real camera
    matches (60, -45) instead - see SLD_PIPELINE_PLAN.md and
    config/buildings.json's per-building camera_angle_x/camera_angle_y.

    angle_x/angle_y are named to match Goxel's own camera-angle fields
    (reverse-engineered from castle.gox's camera: azimuth = 90 - angle_y,
    elevation-from-vertical = angle_x - verified to reproduce both
    castle.gox's real basis vectors and palisade2_open.gox's mirrored ones
    to 3 decimal places)."""
    azimuth = math.radians(90 - angle_y)
    elevation = math.radians(90 - angle_x)  # from horizontal
    right = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
    forward_horizontal = np.array([-math.sin(azimuth), math.cos(azimuth), 0.0])
    up = math.cos(elevation) * np.array([0.0, 0.0, 1.0]) + math.sin(elevation) * forward_horizontal
    view_dir = -np.cross(right, up)  # into the scene (see docstring/plan doc)
    return right, up, view_dir


def render(model, pixels_per_unit=24, margin=4, use_box_crop=True, angle_x=60, angle_y=45):
    """Renders Normals, Height, AmbientOcclusion and voxel-color Diffuse
    passes for `model` (a GoxModel with .voxels set) using the fixed
    standard_camera(angle_x, angle_y) - see its docstring for why this
    doesn't read model.active_camera. Returns a dict of PIL Images:
    {"normals", "height", "ao", "diffuse", "alpha"}, all the same size,
    with `alpha` usable as the shared silhouette mask.

    If `use_box_crop` and the model has an IMG box (see gox_reader.py),
    the canvas is sized/positioned to that box's own projected footprint
    rather than tightly around the rendered geometry - this is what makes
    `place_on_tile_canvas` line up with the existing Diffuse PNG's own crop
    now that files no longer need hand-placed "marker cube" corner voxels
    for that (see SLD_PIPELINE_PLAN.md and remove_gox_markers.py)."""
    right, up, view_dir = standard_camera(angle_x, angle_y)

    voxels = model.voxels
    if not voxels:
        raise ValueError("model has no voxels")
    # A FIXED reference point, not this model's own voxel centroid. The
    # comment this replaces reasoned that orthographic projection only ever
    # uses direction, so cam_pos's exact distance doesn't matter - true, but
    # it missed that cam_pos's *lateral* position (via centroid, a full 3D
    # point, not just a depth offset) still shifts every projected u/v by a
    # model-dependent constant. That's invisible rendering any *one* model in
    # isolation, but breaks any caller that renders several different models
    # (a living building vs its "<name>0.gox" foundation, or a destruction
    # frame's own reduced voxel set) and expects one shared crop_box/anchor
    # to line up across them - confirmed as the exact cause of a real,
    # visibly *shifted* foundation ("se ve corrida claramente" - monastery's
    # own foundation model has different geometry from the living building,
    # so its old centroid-based cam_pos differed enough from the living
    # model's to produce a visible offset once both were forced through the
    # same crop_box). Every .gox in this project shares one consistent world
    # origin/grid (confirmed: every box_bounds seen so far sits near the
    # same small range around zero) - using that fixed origin makes the
    # world-to-pixel mapping identical across every render() call, so a
    # crop_box computed from one model's render is valid on any other's.
    cam_pos = -view_dir * 100.0

    faces = list(exposed_faces(voxels, view_dir))
    if not faces:
        raise ValueError("no exposed faces found")

    # Project every face corner to (u, v, depth) up front, to size the canvas.
    def project(world_pt):
        rel = world_pt - cam_pos
        u = np.dot(rel, right)
        v = np.dot(rel, up)
        depth = np.dot(rel, view_dir)  # larger = farther from camera
        return u, v, depth

    # Flat per-face-orientation shading (top brightest, one side medium, the
    # other darkest) - a simple classic-voxel-art approximation, not meant to
    # match the artist's hand-shaded Diffuse exactly. Only used for the
    # "diffuse" pass (procedural destruction frames, where Diffuse must
    # change as blocks disappear, unlike the static hand-rendered PNG).
    def shade_for(normal):
        if normal[2] != 0:
            return 1.0
        return 0.75 if normal[0] != 0 else 0.6

    projected_faces = []
    all_u, all_v = [], []
    for pos, axis, normal in faces:
        corners = face_corners(pos, axis, normal)
        proj = [project(c) for c in corners]
        for u, v, _ in proj:
            all_u.append(u)
            all_v.append(v)
        ao = ambient_occlusion(voxels, pos)
        base = np.array(voxels[pos][:3], dtype=np.float64)
        is_player_marker = base[0] == 0 and base[1] == 0 and base[2] > 0
        color = np.append(base * shade_for(normal), 255.0 if is_player_marker else 0.0)
        projected_faces.append((proj, normal, pos, ao, color))

    box_bounds = model.box_bounds if use_box_crop else None
    if box_bounds is not None:
        box_min, box_max = box_bounds
        corners = [
            np.array([x, y, z])
            for x in (box_min[0], box_max[0])
            for y in (box_min[1], box_max[1])
            for z in (box_min[2], box_max[2])
        ]
        box_u, box_v = [], []
        for c in corners:
            u, v, _ = project(c)
            box_u.append(u)
            box_v.append(v)
        # Union with content extent: the box should already contain all
        # real geometry, but never let box crop clip actual rendered pixels
        # if a file's box turns out tighter than its content.
        min_u, max_u = min(min(all_u), min(box_u)), max(max(all_u), max(box_u))
        min_v, max_v = min(min(all_v), min(box_v)), max(max(all_v), max(box_v))
    else:
        min_u, max_u = min(all_u), max(all_u)
        min_v, max_v = min(all_v), max(all_v)

    width = int(np.ceil((max_u - min_u) * pixels_per_unit)) + 2 * margin
    height = int(np.ceil((max_v - min_v) * pixels_per_unit)) + 2 * margin

    def to_pixel(u, v):
        # Screen +v (up in world) maps to smaller row index (image row 0 = top).
        px = (u - min_u) * pixels_per_unit + margin
        py = (max_v - v) * pixels_per_unit + margin
        return px, py

    box_crop_px = None
    if box_bounds is not None:
        box_px = [to_pixel(u, v) for u, v in zip(box_u, box_v)]
        bxs = [p[0] for p in box_px]
        bys = [p[1] for p in box_px]
        box_crop_px = (
            max(int(np.floor(min(bxs))), 0),
            max(int(np.floor(min(bys))), 0),
            min(int(np.ceil(max(bxs))), width),
            min(int(np.ceil(max(bys))), height),
        )

    z_buffer = np.full((height, width), np.inf, dtype=np.float64)
    normal_buf = np.zeros((height, width, 3), dtype=np.float64)
    height_buf = np.zeros((height, width), dtype=np.float64)
    ao_buf = np.zeros((height, width), dtype=np.float64)
    color_buf = np.zeros((height, width, 4), dtype=np.float64)
    alpha_buf = np.zeros((height, width), dtype=np.uint8)

    for proj, normal, pos, ao, color in projected_faces:
        pts = [to_pixel(u, v) for u, v, _ in proj]
        depths = [d for _, _, d in proj]
        world_z = pos[2] + (1 if normal[2] > 0 else 0) if normal[2] != 0 else pos[2] + 0.5
        # Split the quad into two triangles: (0,1,2) and (0,2,3).
        for tri in ((0, 1, 2), (0, 2, 3)):
            _rasterize_triangle(
                [pts[i] for i in tri],
                [depths[i] for i in tri],
                z_buffer, normal_buf, height_buf, ao_buf, color_buf, alpha_buf,
                normal, world_z, ao, color,
            )

    def to_rgba(gray_or_rgb):
        if gray_or_rgb.ndim == 2:
            rgb = np.repeat(gray_or_rgb[..., None], 3, axis=2)
        else:
            rgb = gray_or_rgb
        return Image.fromarray(np.dstack([rgb, alpha_buf]), mode="RGBA")

    normal_rgb = (((normal_buf + 1) / 2) * 255).astype(np.uint8)
    hmin, hmax = height_buf[alpha_buf > 0].min(), height_buf[alpha_buf > 0].max()
    hrange = max(hmax - hmin, 1e-6)
    height_gray = np.where(
        alpha_buf > 0, ((height_buf - hmin) / hrange * 255), 0
    ).astype(np.uint8)
    ao_gray = (ao_buf * 255).astype(np.uint8)
    diffuse_rgb = np.clip(color_buf[..., :3], 0, 255).astype(np.uint8)
    marker_buf = color_buf[..., 3].astype(np.uint8)

    return {
        "normals": to_rgba(normal_rgb),
        "height": to_rgba(height_gray),
        "ao": to_rgba(ao_gray),
        "diffuse": to_rgba(diffuse_rgb),
        "alpha": Image.fromarray(alpha_buf, mode="L"),
        "marker": Image.fromarray(marker_buf, mode="L"),
        "box_crop_px": box_crop_px,  # (left, top, right, bottom) or None; see compute_placement
    }


def _rasterize_triangle(pts, depths, z_buffer, normal_buf, height_buf, ao_buf, color_buf, alpha_buf,
                         normal, world_z, ao, color):
    h, w = z_buffer.shape
    (x0, y0), (x1, y1), (x2, y2) = pts
    min_x = max(int(np.floor(min(x0, x1, x2))), 0)
    max_x = min(int(np.ceil(max(x0, x1, x2))), w - 1)
    min_y = max(int(np.floor(min(y0, y1, y2))), 0)
    max_y = min(int(np.ceil(max(y0, y1, y2))), h - 1)
    if min_x > max_x or min_y > max_y:
        return

    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denom) < 1e-12:
        return  # degenerate (edge-on) triangle

    ys, xs = np.mgrid[min_y:max_y + 1, min_x:max_x + 1]
    xs = xs.astype(np.float64) + 0.5
    ys = ys.astype(np.float64) + 0.5

    w0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / denom
    w1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / denom
    w2 = 1 - w0 - w1

    inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
    if not np.any(inside):
        return

    depth = w0 * depths[0] + w1 * depths[1] + w2 * depths[2]
    region_z = z_buffer[min_y:max_y + 1, min_x:max_x + 1]
    closer = inside & (depth < region_z)
    if not np.any(closer):
        return

    region_z[closer] = depth[closer]
    normal_buf[min_y:max_y + 1, min_x:max_x + 1][closer] = normal
    height_buf[min_y:max_y + 1, min_x:max_x + 1][closer] = world_z
    ao_buf[min_y:max_y + 1, min_x:max_x + 1][closer] = ao
    color_buf[min_y:max_y + 1, min_x:max_x + 1][closer] = color
    alpha_buf[min_y:max_y + 1, min_x:max_x + 1][closer] = 255


def find_tile_size(building_name):
    """Looks up which files-png/{n}x{n}/ folder holds this building's
    already-rendered Diffuse PNG, returning n. Returns None if not found."""
    import os
    import DIRS
    for n in range(1, 6):
        candidate = f"{DIRS.MAIN}/{DIRS.PNG_RAW}/{n}x{n}/{building_name}.png"
        if os.path.isfile(candidate):
            return n
    return None


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(f"usage: {sys.argv[0]} <file.gox> <out_prefix> [tile_size]")
        sys.exit(1)

    import os
    building_name = os.path.splitext(os.path.basename(sys.argv[1]))[0]
    tile_size = int(sys.argv[3]) if len(sys.argv) == 4 else find_tile_size(building_name)
    if tile_size is None:
        print(f"couldn't infer tile_size for {building_name!r}; pass it explicitly")
        sys.exit(1)

    model = read_gox(sys.argv[1])
    passes = render(model)
    for name, img in passes.items():
        out_path = f"{sys.argv[2]}_{name}.png"
        img.save(out_path)
        if name == "alpha":
            continue
        aligned = place_on_tile_canvas(img, building_name, tile_size)
        aligned_path = f"{sys.argv[2]}_{name}_aligned.png"
        aligned.save(aligned_path)
        print(f"wrote {aligned_path} ({aligned.size[0]}x{aligned.size[1]})")

    import DIRS
    diffuse_path = f"{DIRS.MAIN}/{DIRS.PNG_PROCESSED}/{tile_size}x{tile_size}/{building_name}.png"
    if os.path.isfile(diffuse_path):
        from PIL import Image as _Image
        dsize = _Image.open(diffuse_path).size
        print(f"existing processed Diffuse canvas: {dsize[0]}x{dsize[1]} ({diffuse_path})")
