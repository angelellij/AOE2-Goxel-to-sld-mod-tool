"""Surgical .gox file patcher: removes specific voxels while leaving every
other byte in the file untouched.

Unlike a full read-model-rewrite round-trip (which would risk subtly
corrupting chunks we don't fully understand, like the proprietary bits
other tools sometimes add), this only decodes and re-encodes the specific
BL16 block(s) that actually contain a voxel being removed, and copies every
other chunk's bytes verbatim. Since the .gox format (see gox_reader.py) is
just a flat sequence of independent, self-contained chunks with no global
offset table, changing one chunk's length needs no other updates anywhere
else in the file - a very safe edit model.
"""
import struct
from io import BytesIO

import numpy as np
from PIL import Image

from gox_reader import MAGIC, SUPPORTED_VERSION, TILE_SIZE, _decode_block, _read_dict, _read_exact, _read_int32


def set_box_xy(path, half_extent_xy, center_xy):
    """Rewrites the .gox file at `path` in place, overwriting just the X/Y
    entries of the IMG chunk's "box" matrix (Goxel's working-volume box -
    see gox_reader.GoxModel.box_bounds) - `half_extent_xy` sets box[0,0] and
    box[1,1] (the half-extent per axis), `center_xy` sets box[3,0] and
    box[3,1] (the box's center). Z is left untouched. The "box" dict value
    is a fixed 64-byte float32(4,4) blob, so this is a same-length in-place
    overwrite - no other chunk's length or CRC changes.

    Root cause this fixes (see SLD_PIPELINE_PLAN.md): most tile_size=1
    buildings' boxes were left at Goxel's default half-extent 8 (span 16),
    2x wider than their real content (confirmed: every affected building's
    actual voxels span exactly 8 units in X and Y) - `tower1`'s own box
    (half-extent 4, center -12) already has the correct values, confirmed
    against its own voxel extent, and is the reference this was checked
    against."""
    with open(path, "rb") as f:
        data = f.read()

    with open(path, "rb") as f:
        magic = _read_exact(f, 4)
        if magic != MAGIC:
            raise ValueError(f"{path}: not a .gox file")
        version = _read_int32(f)
        if version != SUPPORTED_VERSION:
            raise ValueError(f"{path}: unsupported version {version}")

        box_value_start = None
        box_value_len = None
        while True:
            chunk_start = f.tell()
            type_bytes = f.read(4)
            if not type_bytes:
                break
            chunk_type = type_bytes.decode("ascii")
            length = _read_int32(f)
            data_start = f.tell()

            if chunk_type == "IMG ":
                pos = 0
                while pos < length:
                    key_size = _read_int32(f)
                    pos += 4
                    if key_size == 0:
                        break
                    key = _read_exact(f, key_size).decode("utf-8", errors="replace")
                    pos += key_size
                    value_size = _read_int32(f)
                    pos += 4
                    value_start = f.tell()
                    if key == "box":
                        box_value_start, box_value_len = value_start, value_size
                    f.seek(value_size, 1)
                    pos += value_size
            else:
                f.seek(length, 1)

            f.seek(chunk_start + 8 + length, 0)
            _read_int32(f)  # CRC

    if box_value_start is None:
        raise ValueError(f"{path}: no IMG box entry found")
    if box_value_len != 64:
        raise ValueError(f"{path}: IMG box entry is {box_value_len} bytes, expected 64")

    box = np.frombuffer(data[box_value_start:box_value_start + 64], dtype="<f4").reshape(4, 4).copy()
    box[0, 0] = half_extent_xy
    box[1, 1] = half_extent_xy
    box[3, 0] = center_xy
    box[3, 1] = center_xy

    out = bytearray(data)
    out[box_value_start:box_value_start + 64] = box.astype("<f4").tobytes()

    with open(path, "wb") as f:
        f.write(out)


def _encode_block(grid):
    """Inverse of gox_reader._decode_block: (16,16,16,4) uint8 grid indexed
    [z,y,x] -> 64x64 PNG bytes, the exact reverse of the reshape used to
    decode it (see gox_reader.py's module docstring for why this reshape
    is correct: it's a direct memory-layout equivalence, not a guess)."""
    flat = grid.reshape(TILE_SIZE ** 3, 4)
    img = Image.fromarray(flat.reshape(64, 64, 4), mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def remove_voxels(path, positions):
    """Rewrites the .gox file at `path` in place, zeroing out (fully
    transparent) each world-space (x, y, z) in `positions`. Returns the
    number of voxels actually found and removed (0 if none of the given
    positions existed in any layer's blocks)."""
    positions = set(positions)
    if not positions:
        return 0

    with open(path, "rb") as f:
        data = f.read()

    with open(path, "rb") as f:
        magic = _read_exact(f, 4)
        if magic != MAGIC:
            raise ValueError(f"{path}: not a .gox file")
        version = _read_int32(f)
        if version != SUPPORTED_VERSION:
            raise ValueError(f"{path}: unsupported version {version}")

        # Pass 1: locate every BL16 chunk's byte range + decoded grid, and
        # every LAYR block placement, so we know which (block, local xyz)
        # pairs correspond to the world positions we want to remove.
        block_byte_ranges = []  # [(start_of_type_field, data_start, data_len)]
        block_grids = []
        edits = {}  # block_index -> list of (lz, ly, lx)

        while True:
            chunk_start = f.tell()
            type_bytes = f.read(4)
            if not type_bytes:
                break
            chunk_type = type_bytes.decode("ascii")
            length = _read_int32(f)
            data_start = f.tell()

            if chunk_type == "BL16":
                png_bytes = _read_exact(f, length)
                block_byte_ranges.append((chunk_start, data_start, length))
                block_grids.append(_decode_block(png_bytes))
            elif chunk_type == "LAYR":
                nb_blocks = _read_int32(f)
                placements = []
                for _ in range(nb_blocks):
                    index = _read_int32(f)
                    x = _read_int32(f)
                    y = _read_int32(f)
                    z = _read_int32(f)
                    _read_int32(f)
                    placements.append((index, x, y, z))
                consumed = 4 + nb_blocks * 20
                _read_dict(f, length - consumed)

                for index, bx, by, bz in placements:
                    for wx, wy, wz in positions:
                        lx, ly, lz = wx - bx, wy - by, wz - bz
                        if 0 <= lx < TILE_SIZE and 0 <= ly < TILE_SIZE and 0 <= lz < TILE_SIZE:
                            edits.setdefault(index, []).append((lz, ly, lx))
            else:
                f.seek(length, 1)

            f.seek(chunk_start + 8 + length, 0)
            _read_int32(f)  # CRC

    if not edits:
        return 0

    # Pass 2: re-encode only the edited blocks; splice their bytes into a
    # copy of the original file, leaving everything else untouched.
    out = bytearray(data)
    removed = 0
    # Splice from the end backwards so earlier offsets stay valid as chunk
    # lengths change.
    for block_index in sorted(edits, reverse=True):
        grid = block_grids[block_index].copy()
        for lz, ly, lx in edits[block_index]:
            grid[lz, ly, lx] = (0, 0, 0, 0)
            removed += 1
        new_png = _encode_block(grid)

        chunk_start, data_start, old_length = block_byte_ranges[block_index]
        new_length_bytes = struct.pack("<i", len(new_png))
        crc_bytes = data[data_start + old_length:data_start + old_length + 4]
        new_chunk = data[chunk_start:chunk_start + 4] + new_length_bytes + new_png + crc_bytes
        out[chunk_start:data_start + old_length + 4] = new_chunk

    with open(path, "wb") as f:
        f.write(out)

    return removed
