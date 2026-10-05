"""Hand-writes the SLD "shadow" layer directly into an already-converted
.sld file, bypassing DESpriteTool's own shadow auto-generation entirely.

Why: DESpriteTool's auto-generated shadow channel is either an unusable
canvas-filling blob (oversized PSD canvas) or completely empty (correctly
sized canvas, current builds) - see SLD_PIPELINE_PLAN.md. Diffuse itself has
no real per-pixel alpha blending in-game (confirmed repeatedly), so it can't
render the footprint-diamond ground indicator as a translucent overlay - only
the shadow channel can. Since we can't control what DESpriteTool generates
there, this module overwrites that channel's raw bytes after conversion,
using the exact binary format `Scripts/psd_template.py`'s sibling decoder
work reverse-engineered (see decode_shadow_layer in the project's own
scratch decoder, ported from https://github.com/marcustunimus/sld-extractor).

Every masked-in 4x4 block is written as a flat single value (BC4-like
"index 0" always maps to the first endpoint byte regardless of which of the
format's two interpolation modes is selected, so only that one byte matters
here - no need to construct a real gradient for a uniform-strength shadow).
"""
import struct

import numpy as np


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read(self, n):
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def text(self, n):
        return self.read(n).decode("latin1")

    def u16(self, n=1):
        return list(struct.unpack(f"<{n}H", self.read(n * 2)))

    def i16(self, n=1):
        return list(struct.unpack(f"<{n}h", self.read(n * 2)))

    def u32(self, n=1):
        return list(struct.unpack(f"<{n}I", self.read(n * 4)))

    def u8(self, n=1):
        return list(self.read(n))


def build_draws(block_states):
    """block_states: list of bool (draw or not) in raster order. Returns the
    u8 run-length list matching the format's alternating skip/draw semantics
    (starts with a skip run, possibly length 0), splitting any run longer
    than 255 into extra zero-length runs of the opposite state, and padding
    to even length - the file's stored draw_count field is len(draws)/2, not
    len(draws) itself (verified against a real, empty shadow chunk: stored
    draw_count=1 but its actual draws array was 2 entries, [0, 0])."""
    if not block_states:
        return [0, 0]
    runs = []
    current = False  # sequence starts assuming "skip" state
    length = 0
    for b in block_states:
        if b == current:
            length += 1
        else:
            runs.append(length)
            current = b
            length = 1
    runs.append(length)

    out = []
    for n in runs:
        while n > 255:
            out.append(255)
            out.append(0)  # zero-length opposite-state run to keep parity
            n -= 255
        out.append(n)

    if len(out) % 2 != 0:
        out.append(0)
    return out


def shadow_block_bytes(value):
    value &= 0xFF
    return bytes([value, 0]) + bytes(6)  # c0=value, c1=0, all 16 indices=0 -> color=c0


def encode_shadow_layer(mask, x0, y0, x1, y1, value, coverage_threshold=8):
    """mask: 2D uint8 array (0-255 coverage, not boolean) indexed [y, x],
    same coordinate space as the frame's own width/height - a pre-blurred,
    anti-aliased footprint mask (see build_psd.build_layers), not a hard
    edge. x0, y0, x1, y1 must be multiples of 4 and define the block grid to
    cover. Returns the raw layer bytes (coords + flags + unknown +
    draw_count + draws + block data) - NOT including the leading u32
    declared_size (see `pad_chunk`).

    Each block's own shadow *value* is scaled by its average coverage
    (mean of its 16 mask pixels / 255), not just a flat on/off decision -
    a hard-edged mask's diagonal always shows a visible staircase at this
    format's 4x4-block granularity ("el borde... tendria que ser liso");
    scaling the value by local coverage instead turns that staircase into a
    smooth gradient along the edge, without changing the real block
    resolution. A block-majority *draw* threshold (skip a block entirely
    unless most of its pixels are covered) was tried earlier and reverted -
    this coverage-scaled *value* approach replaces that idea rather than
    combining with it: `coverage_threshold` (out of 255) only decides
    whether a block has anything worth drawing at all (avoids wasting a
    full block write encoding a value of 0-1)."""
    block_states = []
    block_values = []
    for y in range(y0, y1, 4):
        for x in range(x0, x1, 4):
            coverage = mask[y:y + 4, x:x + 4].mean()
            drawn = coverage >= coverage_threshold
            block_states.append(drawn)
            if drawn:
                block_values.append(int(round(value * (coverage / 255))))

    draws = build_draws(block_states)
    assert len(draws) % 2 == 0

    out = bytearray()
    out += struct.pack("<4h", x0, y0, x1, y1)
    out += bytes([1, 1])  # flags, unknown - mirrors DESpriteTool's own shadow-layer values
    out += struct.pack("<h", len(draws) // 2)
    out += bytes(draws)
    for block_value in block_values:
        out += shadow_block_bytes(block_value)
    return bytes(out)


def pad_chunk(raw):
    """Prefix with the u32 declared_size and pad data to a multiple of 4.
    Verified against two real chunks (a populated "normal" layer and an
    empty "shadow" layer) in an actual DESpriteTool-produced .sld:
    declared_size = len(raw) + 4 makes the decode-side
    `padded_len = ((declared_size - 1) >> 2) << 2` formula land exactly on
    ceil(len(raw)/4)*4 for every len(raw) mod 4 case."""
    declared_size = len(raw) + 4
    padded_len = (len(raw) + 3) // 4 * 4
    data = raw + bytes(padded_len - len(raw))
    return struct.pack("<I", declared_size) + data


def downscale_mask(mask_x2):
    """2x2 average-pooling of a continuous 0-255 coverage mask - matches
    DESpriteTool's own exact 50% downscale from our AUTHOR_SCALE=2 canvas to
    the real "_x1" asset the game actually uses. Average (not max/"any"),
    since this mask is now an anti-aliased coverage gradient, not a boolean -
    "any" would re-harden the very edge softness the blur was meant to keep."""
    h, w = mask_x2.shape
    h, w = h - h % 2, w - w % 2
    m = mask_x2[:h, :w].astype(np.float64)
    return (m[0::2, 0::2] + m[1::2, 0::2] + m[0::2, 1::2] + m[1::2, 1::2]) / 4


def patch_sld_shadow(sld_path, footprint_mask_x2, value=190):
    """Overwrites every frame's shadow-layer chunk in an already-converted
    .sld file with one hand-encoded from `footprint_mask_x2` (the footprint-
    diamond coverage mask - continuous 0-255, pre-blurred for anti-aliasing,
    not boolean - at AUTHOR_SCALE=2 canvas resolution, as returned by
    `build_psd.write_psd`). Every frame must already declare a shadow layer
    (frame_type bit 0x2) - true for every real building conversion so far.
    Writes the result back to `sld_path` in place.

    `footprint_mask_x2` is normally one mask, reused for every frame - correct
    for a living building's idle-animation frames, which all share the same
    silhouette. Pass a list/tuple instead for a destruction or foundation
    sequence, where each SLD frame's own building content differs frame to
    frame (a collapsing or rising silhouette exposes a different amount of
    background): mask `i` patches SLD frame `i`, and the *last* mask in the
    list is reused for any extra SLD frame beyond the list's own length (e.g.
    a stage repeated several times as identical SLD frames all get that
    stage's own mask). Reusing frame/stage 0's mask for every frame was tried
    first and confirmed wrong in-game (a large, disconnected shadow diamond
    floating away from wherever the building had actually shrunk/grown to) -
    the mask must track the content it was actually computed from.

    `value` (0-255) controls lightness, not darkness - confirmed in-game:
    lowering it from 120 to 70 made the line render *darker*, the opposite
    of the intent ("más claro"). Higher = lighter/more see-through."""
    with open(sld_path, "rb") as f:
        data = f.read()

    r = Reader(data)
    fmt = r.text(4)
    if fmt != "SLDX":
        raise ValueError(f"{sld_path}: not an SLDX file ({fmt!r})")
    _version, frame_count = r.u16(2)
    r.u32(2)  # unknown1, opacity

    if isinstance(footprint_mask_x2, (list, tuple)):
        masks_x1 = [downscale_mask(m) for m in footprint_mask_x2]
    else:
        masks_x1 = [downscale_mask(footprint_mask_x2)]
    out = bytearray(data[:r.pos])

    for frame_i in range(frame_count):
        mask_x1 = masks_x1[min(frame_i, len(masks_x1) - 1)]
        frame_header_start = r.pos
        width, height, _ax, _ay = r.i16(4)
        frame_type, _unknown = r.u8(2)
        r.i16()  # index
        out += data[frame_header_start:r.pos]

        if not (frame_type & 0x2):
            raise ValueError(f"{sld_path}: frame has no shadow layer (type={frame_type:#x})")

        for bit in (0x1,):  # normal layer: copy verbatim, comes before shadow
            if frame_type & bit:
                chunk_start = r.pos
                size = r.u32()[0]
                padded = ((size - 1) >> 2) << 2
                r.read(padded)
                out += data[chunk_start:r.pos]

        # shadow layer: this is the one we replace
        old_start = r.pos
        size = r.u32()[0]
        padded = ((size - 1) >> 2) << 2
        r.read(padded)

        mh, mw = mask_x1.shape
        fixed = mask_x1
        if (mh, mw) != (height, width):
            fixed = np.zeros((height, width), dtype=np.float64)
            ch, cw = min(mh, height), min(mw, width)
            fixed[:ch, :cw] = mask_x1[:ch, :cw]

        x1b = ((width + 3) // 4) * 4
        y1b = ((height + 3) // 4) * 4
        raw = encode_shadow_layer(fixed, 0, 0, x1b, y1b, value)
        out += pad_chunk(raw)

        for bit in (0x4, 0x8, 0x10):  # unknown4, smudge, player: copy verbatim
            if frame_type & bit:
                chunk_start = r.pos
                size = r.u32()[0]
                padded = ((size - 1) >> 2) << 2
                r.read(padded)
                out += data[chunk_start:r.pos]

    out += data[r.pos:]

    with open(sld_path, "wb") as f:
        f.write(out)
