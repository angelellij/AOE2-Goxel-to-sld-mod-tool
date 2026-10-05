import math
import os
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

import DIRS
import voxel_render
import psd_template
from gox_reader import GoxModel, read_gox

PLAYER_COLOR_GRAY = (0x56, 0x56, 0x56)


def player_pixels(marker_mask):
    return [(int(x), int(y)) for y, x in np.argwhere(marker_mask)]


def paint_player_pixels(diffuse, pixels):
    out = np.array(diffuse).copy()
    for x, y in pixels:
        out[y, x, :3] = PLAYER_COLOR_GRAY
    return Image.fromarray(out, mode="RGBA")


def player_color_mask(pixels, size):
    out = np.zeros((size[1], size[0]), dtype=np.uint8)
    for x, y in pixels:
        out[y, x] = 255
    return out


TILE_PAD = 2


def _pad_tile(img, pad):
    fill = (0, 0, 0, 0) if img.mode == "RGBA" else 0
    return ImageOps.expand(img, border=(pad[0], pad[1], pad[0], pad[1]), fill=fill)


def _footprint_pad(tile_x, tile_y, footprint):
    if footprint is None:
        return (TILE_PAD, TILE_PAD)
    length, width, _axis = footprint
    need_x = math.ceil((length + width) * tile_x / 8 - tile_x / 2)
    need_y = math.ceil((length + width) * tile_y / 8 - tile_y / 2) + 24
    return (max(TILE_PAD, need_x), max(TILE_PAD, need_y))


def build_layers(building_name, tile_size, angle_x=60, angle_y=45, model=None, crop_box=None, margin=0, gox_name=None, debug_dir=None, footprint=None, fit_footprint=False, shift_y=0):
    if model is None:
        gox_path = f"{DIRS.MAIN}/{DIRS.GOX}/{gox_name or building_name}.gox"
        model = read_gox(gox_path)
    passes = voxel_render.render(model, angle_x=angle_x, angle_y=angle_y)
    if debug_dir is not None:
        os.makedirs(debug_dir, exist_ok=True)
        passes["diffuse"].save(f"{debug_dir}/{building_name}_raw_gox_Diffuse.png")
        passes["marker"].save(f"{debug_dir}/{building_name}_raw_gox_BlueMarker.png")
    if crop_box is None:
        crop_box = passes["box_crop_px"]
    place_kwargs = {}
    if fit_footprint and footprint is not None:
        tx, _ty, _a, _b = voxel_render.tile_params(building_name, tile_size)
        fp_w = math.ceil((footprint[0] + footprint[1]) * tx / 4)
        place_kwargs = {"canvas_w": fp_w + 4, "new_w": fp_w}
    aligned = {
        name: voxel_render.place_on_tile_canvas(img, building_name, tile_size, crop_box, margin, **place_kwargs)
        for name, img in passes.items()
        if name not in ("alpha", "box_crop_px")
    }
    diffuse = aligned.pop("diffuse").convert("RGBA")
    player_marker = np.array(aligned.pop("marker").convert("L")) > 0

    for name, img in aligned.items():
        if img.size != diffuse.size:
            aligned[name] = img.resize(diffuse.size)

    import building_config
    if footprint is None:
        axis = (building_config.load(building_name) or {}).get("footprint_axis")
        footprint = (2, 1, axis) if axis else None
    tile_x, tile_y, _mg_x, _mg_y = voxel_render.tile_params(building_name, tile_size)
    pad = _footprint_pad(tile_x, tile_y, footprint)
    diffuse = _pad_tile(diffuse, pad)
    player_marker = np.pad(player_marker, ((pad[1], pad[1]), (pad[0], pad[0])))
    aligned = {name: _pad_tile(img, pad) for name, img in aligned.items()}

    cx, cy = diffuse.width / 2, diffuse.height - tile_y / 2 - pad[1]
    if footprint is not None:
        length, width, axis = footprint
        step_ne = (tile_x / 4, -tile_y / 4)
        step_se = (tile_x / 4, tile_y / 4)
        long_u, short_v = (step_ne, step_se) if axis == "ne" else (step_se, step_ne)
        corner_offsets = [(0, 0), (length * long_u[0], length * long_u[1]),
                          (length * long_u[0] + width * short_v[0], length * long_u[1] + width * short_v[1]),
                          (width * short_v[0], width * short_v[1])]
        centroid = ((length * long_u[0] + width * short_v[0]) / 2, (length * long_u[1] + width * short_v[1]) / 2)
        corners = [(cx + ox - centroid[0], cy + oy - centroid[1]) for ox, oy in corner_offsets]
    else:
        hx, hy = tile_x / 2 + 1, tile_y / 2 + 1
        corners = [(cx, cy - hy), (cx + hx, cy), (cx, cy + hy), (cx - hx, cy)]
    edge_img = Image.new("L", diffuse.size, 0)
    edge_draw = ImageDraw.Draw(edge_img)
    for a, b in zip(corners, corners[1:] + corners[:1]):
        edge_draw.line([a, b], fill=255, width=1)
        edge_draw.line([(a[0], a[1] + 1), (b[0], b[1] + 1)], fill=255, width=1)
    diamond_edge = np.array(edge_img) > 0
    fill_img = Image.new("L", diffuse.size, 0)
    ImageDraw.Draw(fill_img).polygon(corners, fill=255)
    diamond_fill = np.array(fill_img)
    if fit_footprint and footprint is not None:
        content_alpha = np.array(diffuse)[..., 3] > 0
        diffs = []
        for x in range(diffuse.width):
            fy = np.nonzero(diamond_fill[:, x])[0]
            cy_col = np.nonzero(content_alpha[:, x])[0]
            if len(fy) and len(cy_col):
                diffs.append(cy_col.max() - fy.max())
        dy = shift_y
        if dy:
            def shift(img):
                out = Image.new(img.mode, img.size, (0, 0, 0, 0) if img.mode == "RGBA" else 0)
                out.paste(img, (0, dy))
                return out
            diffuse = shift(diffuse)
            aligned = {name: shift(img) for name, img in aligned.items()}
            player_marker = np.roll(player_marker, dy, axis=0)
            if dy > 0:
                player_marker[:dy] = False
            else:
                player_marker[dy:] = False
    diffuse_arr = np.array(diffuse)
    diffuse_arr[..., 3] = np.where(diffuse_arr[..., 3] >= 128, 255, 0)
    silhouette = Image.fromarray(diffuse_arr[..., 3].astype(np.uint8), mode="L")
    diffuse_arr[player_marker, 3] = 255
    occupied = diffuse_arr[..., 3] > 0
    diffuse_arr[diamond_edge & ~occupied] = (0x33, 0x33, 0x33, 255)
    diffuse = Image.fromarray(diffuse_arr, mode="RGBA")

    pixels = player_pixels(player_marker)
    diffuse = paint_player_pixels(diffuse, pixels)
    player_color = player_color_mask(pixels, diffuse.size)


    ao_alpha = (occupied * 255).astype(np.uint8)
    ao = np.dstack([np.full(ao_alpha.shape + (3,), 255, dtype=np.uint8), ao_alpha])

    return {
        "Diffuse": diffuse,
        "Damage": Image.new("RGBA", diffuse.size, (0, 0, 0, 0)),
        "AmbientOcclusion": Image.fromarray(ao, mode="RGBA"),
        "Height": Image.new("RGBA", diffuse.size, (0, 0, 0, 0)),
        "Normals": Image.new("RGBA", diffuse.size, (0, 0, 0, 0)),
        "player_color": player_color,
        "diamond": diamond_fill,
        "pad": pad,
        "anchor": (cx, cy),
        "silhouette": silhouette,
        "Background": Image.new("RGBA", diffuse.size, (0, 0, 0, 0)),
    }


def build_destruction_frames(building_name, tile_size, num_frames=5, angle_x=60, angle_y=45, margin=0, gox_name=None):
    gox_path = f"{DIRS.MAIN}/{DIRS.GOX}/{gox_name or building_name}.gox"
    base_model = read_gox(gox_path)
    base_passes = voxel_render.render(base_model, angle_x=angle_x, angle_y=angle_y)
    crop_box = base_passes["box_crop_px"]

    frames = []
    for frame_index in range(1, num_frames + 1):
        seed = zlib.crc32(f"{building_name}:{frame_index}".encode())
        frame_voxels = voxel_render.destruction_frame_voxels(
            base_model.voxels, frame_index, num_frames, seed=seed
        )
        frame_model = GoxModel(voxels=frame_voxels, box=base_model.box)
        frames.append(build_layers(
            building_name, tile_size, angle_x=angle_x, angle_y=angle_y, model=frame_model, crop_box=crop_box,
            margin=margin,
        ))
    return frames


def build_foundation_frames(
    building_name, tile_size, angle_x=60, angle_y=45, foundation_name=None, margin=0, include_full_stage=False,
    construction_gox=None, footprint=None, stage_fractions=None, base_frame=True, stage_extra_levels=0, rotate_90=False,
):
    if footprint is not None and construction_gox:
        base = _foundation_frames(building_name, tile_size, angle_x, angle_y, foundation_name, margin,
                                  include_full_stage, construction_gox, footprint, shift_y=0,
                                  stage_fractions=stage_fractions, base_frame=base_frame, stage_extra_levels=stage_extra_levels, rotate_90=rotate_90)
        sil = np.array(base[0]["silhouette"]) > 0
        dm = np.array(base[0]["diamond"]) > 0
        diffs = [np.nonzero(sil[:, x])[0].max() - np.nonzero(dm[:, x])[0].max()
                 for x in range(sil.shape[1]) if sil[:, x].any() and dm[:, x].any()]
        dy = -round(float(np.median(diffs)))
        return _foundation_frames(building_name, tile_size, angle_x, angle_y, foundation_name, margin,
                                  include_full_stage, construction_gox, footprint, shift_y=dy,
                                  stage_fractions=stage_fractions, base_frame=base_frame, stage_extra_levels=stage_extra_levels, rotate_90=rotate_90)
    return _foundation_frames(building_name, tile_size, angle_x, angle_y, foundation_name, margin,
                              include_full_stage, construction_gox, footprint, shift_y=0,
                              stage_fractions=stage_fractions, base_frame=base_frame, stage_extra_levels=stage_extra_levels, rotate_90=rotate_90)


def _staged_voxels(voxels, fraction, extra_levels=0):
    gate = {p: c for p, c in voxels.items() if -16 <= p[0] <= -1}
    rest = {p: c for p, c in voxels.items() if p not in gate}
    out = {}
    for group in (gate, rest):
        if group:
            out.update(voxel_render.construction_stage_voxels(group, fraction, extra_levels))
    return out


def _rotate_voxels_90(voxels):
    """Rotates voxels 90 degrees in the xy plane (z unchanged) around the
    center of their own xy bounding box, so a square footprint maps onto
    itself and the model stays centered on it."""
    xs = [p[0] for p in voxels]
    ys = [p[1] for p in voxels]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    out = {}
    for (x, y, z), color in voxels.items():
        nx = cx - (y - cy)
        ny = cy + (x - cx)
        out[(int(round(nx)), int(round(ny)), z)] = color
    return out


def _foundation_frames(building_name, tile_size, angle_x, angle_y, foundation_name, margin,
                       include_full_stage, construction_gox, footprint, shift_y,
                       stage_fractions=None, base_frame=True, stage_extra_levels=0, rotate_90=False):
    foundation_name = foundation_name or building_name
    import building_config
    living_gox = construction_gox or (building_config.load(building_name) or {}).get("gox") or building_name
    living_model = read_gox(f"{DIRS.MAIN}/{DIRS.GOX}/{living_gox}.gox")
    if rotate_90:
        living_model = GoxModel(voxels=_rotate_voxels_90(living_model.voxels), box=living_model.box)
    if construction_gox:
        foundation_name = construction_gox
    living_passes = voxel_render.render(living_model, angle_x=angle_x, angle_y=angle_y)
    crop_box = living_passes["box_crop_px"]

    foundation_path = f"{DIRS.MAIN}/{DIRS.GOX}/{foundation_name}0.gox"
    if base_frame and os.path.isfile(foundation_path):
        foundation_model = read_gox(foundation_path)
        foundation_model.box = living_model.box
        frames = [
            build_layers(
                building_name, tile_size, angle_x=angle_x, angle_y=angle_y, model=foundation_model, crop_box=crop_box,
                margin=margin, footprint=footprint, fit_footprint=True, shift_y=shift_y,
            ),
        ]
    else:
        frames = []
    default_fractions = (0.25, 0.50, 0.75) if construction_gox else (0.30, 0.55)
    for fraction in (stage_fractions or default_fractions):
        stage_voxels = _staged_voxels(living_model.voxels, fraction, stage_extra_levels)
        stage_model = GoxModel(voxels=stage_voxels, box=living_model.box)
        frames.append(build_layers(
            building_name, tile_size, angle_x=angle_x, angle_y=angle_y, model=stage_model, crop_box=crop_box,
            margin=margin, footprint=footprint, fit_footprint=True, shift_y=shift_y,
        ))
    if include_full_stage:
        frames.append(build_layers(
            building_name, tile_size, angle_x=angle_x, angle_y=angle_y, model=living_model, crop_box=crop_box,
            margin=margin, footprint=footprint, fit_footprint=True, shift_y=shift_y,
        ))
    return frames


AUTHOR_SCALE = 2


def anchor_point(building_name, tile_size, canvas_height, pad_x=TILE_PAD, pad_y=TILE_PAD):
    tile_x, tile_y, _mg_x, _mg_y = voxel_render.tile_params(building_name, tile_size)
    tile_x, tile_y = tile_x * AUTHOR_SCALE, tile_y * AUTHOR_SCALE
    return tile_x / 2 + pad_x * AUTHOR_SCALE, canvas_height - tile_y / 2 - pad_y * AUTHOR_SCALE


def paste_on_template_canvas(image, offset, canvas_size):
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.paste(image, (round(offset[0]), round(offset[1])), image)
    arr = np.array(canvas)
    return np.ascontiguousarray(arr[..., :3]), np.ascontiguousarray(arr[..., 3])


def paste_mask_on_template_canvas(mask_2d, offset, canvas_size):
    img = Image.fromarray(mask_2d, mode="L")
    canvas = Image.new("L", (canvas_size, canvas_size), 0)
    canvas.paste(img, (round(offset[0]), round(offset[1])))
    return np.array(canvas)


def _resize_rgba_no_alpha_ringing(img, size, rgb_resample=Image.LANCZOS):
    r, g, b, a = img.split()
    rgb = np.array(Image.merge("RGB", (r, g, b)).resize(size, rgb_resample))
    a = np.array(a.resize(size, Image.NEAREST))
    return Image.fromarray(np.dstack([rgb, a]), mode="RGBA")


def write_psd(layers, out_path, building_name, tile_size, debug_dir=None):
    scaled = {
            name: _resize_rgba_no_alpha_ringing(
                img, (img.width * AUTHOR_SCALE, img.height * AUTHOR_SCALE),
                Image.NEAREST if name == "Diffuse" else Image.LANCZOS,
            )
        for name, img in layers.items()
        if name not in ("player_color", "diamond", "pad", "anchor", "silhouette")
    }
    diamond_img = Image.fromarray(layers["diamond"], mode="L")
    diamond_scaled = np.array(diamond_img.resize((diamond_img.width * AUTHOR_SCALE, diamond_img.height * AUTHOR_SCALE), Image.BILINEAR))
    pc_img = Image.fromarray(layers["player_color"], mode="L")
    pc_scaled = np.array(pc_img.resize((pc_img.width * AUTHOR_SCALE, pc_img.height * AUTHOR_SCALE), Image.NEAREST))

    canvas_width, canvas_height = scaled["Diffuse"].size
    anchor_x, anchor_y = layers["anchor"]
    ax, ay = anchor_x * AUTHOR_SCALE, anchor_y * AUTHOR_SCALE
    margin = 40
    canvas_size = int(2 * max(ax, ay, canvas_width - ax, canvas_height - ay) + margin)
    offset = (canvas_size / 2 - ax, canvas_size / 2 - ay)

    def rgb_alpha(name):
        return paste_on_template_canvas(scaled[name], offset, canvas_size)

    diffuse_rgb, diffuse_alpha = rgb_alpha("Diffuse")
    damage_rgb, damage_alpha = rgb_alpha("Damage")
    _ao_rgb_unused, ao_alpha = rgb_alpha("AmbientOcclusion")
    ao_rgb = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    height_rgb, height_alpha = rgb_alpha("Height")
    background_rgb, background_alpha = rgb_alpha("Background")
    normals_rgb, normals_alpha = rgb_alpha("Normals")
    player_color = paste_mask_on_template_canvas(pc_scaled, offset, canvas_size)
    diamond_mask = paste_mask_on_template_canvas(diamond_scaled, offset, canvas_size)

    diffuse_mask = diffuse_alpha

    if debug_dir is not None:
        os.makedirs(debug_dir, exist_ok=True)
        prefix = os.path.splitext(os.path.basename(out_path))[0]

        def dump(name, rgb, alpha):
            Image.fromarray(np.dstack([rgb, alpha]), mode="RGBA").save(f"{debug_dir}/{prefix}_{name}.png")

        dump("Diffuse", diffuse_rgb, diffuse_alpha)
        dump("Damage", damage_rgb, damage_alpha)
        dump("AmbientOcclusion", ao_rgb, ao_alpha)
        dump("Height", height_rgb, height_alpha)
        dump("Normals", normals_rgb, normals_alpha)
        dump("Background", background_rgb, background_alpha)
        Image.fromarray(player_color, mode="L").save(f"{debug_dir}/{prefix}_PlayerColor.png")
        Image.fromarray(diamond_mask, mode="L").save(f"{debug_dir}/{prefix}_Diamond.png")

    psd_template.write_building_psd(
        out_path,
        canvas_size=canvas_size,
        diffuse_rgb=diffuse_rgb, diffuse_alpha=diffuse_alpha, diffuse_mask=diffuse_mask,
        damage_rgb=damage_rgb, damage_alpha=damage_alpha,
        ao_rgb=ao_rgb, ao_alpha=ao_alpha,
        decal_rgb=None, decal_alpha=None,
        background_rgb=background_rgb, background_alpha=background_alpha,
        height_rgb=height_rgb, height_alpha=height_alpha,
        normals_rgb=normals_rgb, normals_alpha=normals_alpha,
        player_color_mask=player_color,
    )
    return canvas_size, diamond_mask


def write_blank_psd(out_path, canvas_size=64):
    zeros_rgb = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)
    zeros_alpha = np.zeros((canvas_size, canvas_size), dtype=np.uint8)
    white_rgb = np.full((canvas_size, canvas_size, 3), 255, dtype=np.uint8)
    psd_template.write_building_psd(
        out_path,
        canvas_size=canvas_size,
        diffuse_rgb=zeros_rgb, diffuse_alpha=zeros_alpha, diffuse_mask=zeros_alpha,
        damage_rgb=zeros_rgb, damage_alpha=zeros_alpha,
        ao_rgb=white_rgb, ao_alpha=zeros_alpha,
        decal_rgb=None, decal_alpha=None,
        background_rgb=None, background_alpha=None,
        height_rgb=zeros_rgb, height_alpha=zeros_alpha,
        normals_rgb=zeros_rgb, normals_alpha=zeros_alpha,
        player_color_mask=zeros_alpha,
    )


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} <building_name> [tile_size]")
        sys.exit(1)

    building_name = sys.argv[1]
    tile_size = int(sys.argv[2]) if len(sys.argv) == 3 else voxel_render.find_tile_size(building_name)
    if tile_size is None:
        print(f"couldn't infer tile_size for {building_name!r}; pass it explicitly")
        sys.exit(1)

    layers = build_layers(building_name, tile_size)
    out_path = f"{DIRS.MAIN}/{DIRS.PSD}/buildings/{building_name}/{building_name}_0000.psd"
    write_psd(layers, out_path, building_name, tile_size)
    print(f"wrote {out_path}")
