"""Builds a real DESpriteTool-compatible PSD by editing pixel data inside a
known-working reference template, instead of assembling one from scratch.

Why: DESpriteTool.exe's PSD reader depends on undocumented specifics that
neither hand-built PSDs (pytoshop) nor generic understanding of the format
satisfy - confirmed against a template PSD from an AoE2DE modder (shared in
https://forums.ageofempires.com/t/tools-to-edit-open-extract-sld-files/218934)
that's known to produce real (non-empty) .sld output. Key things that
template revealed and that a from-scratch PSD was missing:
  - The whole document is 16-bit per channel, not 8-bit.
  - Player color is a separate, document-level *extra channel* named
    "Playercolor" (a real Photoshop spot/alpha channel, image resource 1006/
    1045), not baked into the Diffuse layer's own pixels.
  - For a 16-bit PSD, the real per-layer pixel data lives in the "Lr16"
    *additional layer information* tagged block, not the main Layer Info
    section (confirmed empirically: the main section's layer_records is
    empty; editing Lr16's channel data measurably changes DESpriteTool's
    output, byte-for-byte, while editing the main section does nothing).
  - The file also carries a proprietary image resource (signature `psdM`,
    from something called "PSDFileToolkit") that no standard-conformant PSD
    library can parse - psd-tools is patched at import time (see
    `_patch_lenient_resource_read`) to tolerate any resource signature
    instead of insisting on the spec's `8BIM`.
  - **The document canvas must stay square, but the size itself can be
    changed.** First-confirmed-broken case (real content, resized to a
    non-square 380x273) made DESpriteTool.exe silently encode every layer
    as empty (a degenerate run-length table with zero real blocks) despite
    the source PSD's pixel data round-tripping correctly through
    psd-tools. But that turned out to be about the *non-square aspect
    ratio*, not resizing itself: the same real content resized to a square
    800x800 canvas converted correctly (real, non-degenerate, appropriately
    larger output). So `resize_square_canvas` is safe to call with any
    square target size - never with a non-square one.
  - **Content must be authored at roughly 2x the pixel density
    `Scripts/conv.py`'s 95px/tile convention uses.** DESpriteTool
    auto-generates the "_x1" file (the *only* variant the shipped game
    actually uses - real building graphics have zero "_x2" files on disk)
    by downscaling our source PSD 50%. Measured against a real game asset
    (`b_medi_castle_age3_x1.sld`: content 404x452px for a 4x4-tile
    building) vs. our own conv.py-scale content run through the same
    pipeline (content ended up 192x140px after the automatic halving) -
    real buildings are authored roughly 2x denser per tile than conv.py's
    PNGs. `build_psd.py` upscales every layer 2x before handing it to this
    module, so the auto-generated "_x1" lands back at conv.py's intended
    on-screen size instead of coming out roughly half-scale.
  - Callers pad/position their (now up-scaled) content into a square
    canvas themselves (see `build_psd.paste_on_template_canvas`), choosing
    the paste offset so the building's real anchor point lands at the
    canvas center - which is what DESpriteTool derives as the sprite's
    hotspot in this mode.

The reference template is for a *unit* (has a "Blood" layer instead of
"Damage"); this project only targets buildings, so `write_building_psd`
renames that layer to "Damage" and otherwise leaves the template's proven
layer order/blend modes/clipping flags untouched - only pixel content is
edited, at the template's fixed native canvas size.
"""
import numpy as np

TEMPLATE_PATH = f"{__import__('os').path.dirname(__file__)}/psd_template/reference_template.psd"

_patched = False


def _patch_lenient_resource_read():
    """psd-tools' ImageResource.read() rejects any resource whose 4-byte
    signature isn't the spec-mandated b'8BIM'. The reference template has
    one (id 58151) written with signature b'psdM' by the devs' own
    proprietary "PSDFileToolkit", which no conformant library can parse.
    We don't need to understand that resource's content - just read it
    without crashing and preserve it unmodified on write."""
    global _patched
    if _patched:
        return
    import psd_tools.psd.image_resources as ir
    from psd_tools.constants import Resource
    from psd_tools.psd.image_resources import TYPES
    from psd_tools.psd.base import read_fmt
    from psd_tools.utils import read_pascal_string, read_length_block

    @classmethod
    def lenient_read(cls, fp, encoding="macroman", **kwargs):
        signature, key = read_fmt("4sH", fp)
        try:
            key = Resource(key)
        except ValueError:
            pass
        name = read_pascal_string(fp, encoding, padding=2)
        raw_data = read_length_block(fp, padding=2)
        data = TYPES[key].frombytes(raw_data) if key in TYPES else raw_data
        return cls(b"8BIM", key, name, data)

    ir.ImageResource.read = lenient_read
    _patched = True


def load_template():
    _patch_lenient_resource_read()
    from psd_tools import PSDImage

    return PSDImage.open(TEMPLATE_PATH)


def peek_native_size():
    """(width, height) from just the 26-byte PSD header, without a full
    parse - lets callers compute paste offsets before building pixel data."""
    import struct

    with open(TEMPLATE_PATH, "rb") as f:
        header = f.read(26)
    _sig, _version, _reserved, _channels, height, width, _depth, _mode = struct.unpack(
        ">4sH6sHIIHH", header
    )
    return width, height


def _lr16(psd):
    from psd_tools.constants import Tag

    return psd._record.layer_and_mask_information.tagged_blocks.get_data(Tag.LAYER_16)


def _to_16bit_be(arr_8bit):
    """8-bit (0-255) -> 16-bit big-endian raw bytes, PSD's raw channel format."""
    arr16 = (arr_8bit.astype(np.uint32) * 257).astype(">u2")  # 0->0, 255->65535
    return arr16.tobytes()


def native_size(psd):
    """(width, height) the template currently declares (post-resize, if
    `resize_square_canvas` was called)."""
    h = psd._record.header
    return h.width, h.height


def resize_square_canvas(psd, size):
    """Changes the document canvas to `size` x `size` and every Lr16 layer's
    rect to match. Square only - see module docstring for why."""
    psd._record.header.width = size
    psd._record.header.height = size
    lr16 = _lr16(psd)
    for rec in lr16.layer_records:
        rec.top, rec.left, rec.bottom, rec.right = 0, 0, size, size


def set_layer_pixels(psd, layer_name, rgb=None, alpha=None, mask=None):
    """Overwrites one Lr16 layer's channel data. `rgb` is an (H, W, 3) uint8
    array, `alpha`/`mask` are (H, W) uint8 arrays, all sized to the
    template's native canvas (see `native_size`) - the layer's rect is left
    untouched (always the full native canvas, per the module docstring)."""
    lr16 = _lr16(psd)
    idx = [r.name for r in lr16.layer_records].index(layer_name)
    rec = lr16.layer_records[idx]
    cdlist = lr16.channel_image_data[idx]
    width, height = native_size(psd)

    for ci, cd in zip(rec.channel_info, cdlist):
        if ci.id in (0, 1, 2) and rgb is not None:
            cd.set_data(_to_16bit_be(rgb[..., ci.id]), width, height, 16)
        elif ci.id == -1 and alpha is not None:
            cd.set_data(_to_16bit_be(alpha), width, height, 16)
        elif ci.id == -2 and mask is not None:
            cd.set_data(_to_16bit_be(mask), width, height, 16)


def rename_layer(psd, old_name, new_name):
    lr16 = _lr16(psd)
    rec = lr16.layer_records[[r.name for r in lr16.layer_records].index(old_name)]
    rec.name = new_name


def set_composite(psd, rgb, extra_channels):
    """Sets the document's trailing composite Image Data: `rgb` is an
    (H, W, 3) uint8 array sized to the native canvas, `extra_channels` a
    list of (H, W) uint8 arrays matching the document's declared extra
    channels (here: ["Alpha 1", "Playercolor"], per image resource 1006)."""
    planes = [_to_16bit_be(rgb[..., i]) for i in range(3)] + [
        _to_16bit_be(ch) for ch in extra_channels
    ]
    psd._record.image_data.set_data(planes, psd._record.header)


def save(psd, out_path):
    import os

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        psd.save(f)


def write_building_psd(out_path, *, canvas_size, diffuse_rgb, diffuse_alpha, diffuse_mask,
                        damage_rgb, damage_alpha,
                        ao_rgb, ao_alpha,
                        decal_rgb, decal_alpha,
                        background_rgb, background_alpha,
                        height_rgb, height_alpha,
                        normals_rgb, normals_alpha,
                        player_color_mask):
    """Assembles one building frame's PSD from the reference template.
    `canvas_size` is the square canvas side length every *_rgb/_alpha/_mask
    argument is already padded to (see `build_psd.paste_on_template_canvas`).
    `player_color_mask` is (H, W) uint8, the document-level Playercolor
    extra channel.
    """
    psd = load_template()
    resize_square_canvas(psd, canvas_size)

    rename_layer(psd, "Blood", "Damage")
    set_layer_pixels(psd, "Diffuse", rgb=diffuse_rgb, alpha=diffuse_alpha, mask=diffuse_mask)
    set_layer_pixels(psd, "Damage", rgb=damage_rgb, alpha=damage_alpha)
    set_layer_pixels(psd, "AmbientOcclusion", rgb=ao_rgb, alpha=ao_alpha)
    set_layer_pixels(psd, "Decal", rgb=decal_rgb, alpha=decal_alpha)
    set_layer_pixels(psd, "Background", rgb=background_rgb, alpha=background_alpha)
    set_layer_pixels(psd, "Height", rgb=height_rgb, alpha=height_alpha)
    set_layer_pixels(psd, "Normals", rgb=normals_rgb, alpha=normals_alpha)

    # Alpha 1 (first extra channel) mirrors the overall silhouette; Playercolor
    # is our real player-color intensity mask.
    set_composite(psd, diffuse_rgb, [diffuse_alpha, player_color_mask])

    save(psd, out_path)
