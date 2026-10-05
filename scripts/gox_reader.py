"""Pure-Python reader for Goxel's .gox voxel file format.

Format reference (confirmed against goxel/src/formats/gox.c and
goxel/src/volume.c, guillaumechereau/goxel, 2026-09):

    4 bytes magic "GOX ", 4 bytes version (int32), then a list of chunks:
        4 bytes type, 4 bytes data length (int32), N bytes data, 4 bytes CRC
        (CRC is always written as 0 and never validated - safe to skip).

    A chunk's data may end with a dict: repeated
        (int32 key_size, key bytes, int32 value_size, value bytes)
    until key_size == 0.

    BL16: one 16^3 voxel block, stored as a 64x64 RGBA PNG. Goxel writes the
    block's flat voxel array (index = x + y*16 + z*256) directly as the PNG's
    pixel buffer (index = row*64 + col), so decoding is a straight reshape:
    a (64, 64, 4) array flattened and reshaped to (16, 16, 16, 4) gives
    grid[z, y, x] = RGBA, no custom tiling logic needed.

    LAYR: nb_blocks (int32), then for each block:
        index (int32, 0-based position among BL16 chunks in file order),
        x, y, z (int32, block origin in voxel space), reserved (int32, 0).
    Followed by a dict tail with "name", "visible", "mat" (unused for
    placement - see below), etc.

    Confirmed quirk: for version 1 files only, block positions are offset by
    -8 in each axis; version 2 (current) files use raw positions. This
    reader only supports version 2.

    Confirmed: the reference reader does NOT apply a layer's "mat" transform
    to its block positions (volume_blit uses x, y, z as-is). This reader
    does the same. If a real .gox file in this repo turns out to have a
    non-identity "mat", voxel placement here will not reflect it.
"""
import struct
import sys
from dataclasses import dataclass, field
from io import BytesIO

import numpy as np
from PIL import Image

MAGIC = b"GOX "
SUPPORTED_VERSION = 2
TILE_SIZE = 16


@dataclass
class GoxLayer:
    name: str
    visible: bool
    voxels: dict  # (x, y, z) -> (r, g, b, a)


@dataclass
class GoxCamera:
    name: str
    ortho: bool
    dist: float
    mat: "np.ndarray"  # (4, 4) float32, row-major: rows 0-2 = right/up/forward
    # basis vectors in world space (each unit length), row 3 = world position.


@dataclass
class GoxModel:
    layers: list = field(default_factory=list)  # list[GoxLayer]
    voxels: dict = field(default_factory=dict)  # merged, visible layers only
    active_camera: "GoxCamera | None" = None
    box: "np.ndarray | None" = None  # (4, 4) float32, Goxel's own working-volume
    # box for this file (IMG chunk). Rows 0-2 scale a unit cube's half-extent
    # per axis, row 3 is the box's center - see gox_reader.box_bounds().

    @property
    def bbox(self):
        """Returns ((min_x, min_y, min_z), (max_x, max_y, max_z)) or None if empty."""
        if not self.voxels:
            return None
        xs, ys, zs = zip(*self.voxels.keys())
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    @property
    def box_bounds(self):
        """Goxel's own working-volume box (IMG chunk), as world-space
        (min_xyz, max_xyz) - the artist-set reference for "this is the
        intended footprint", independent of how far the actual voxels
        reach. None if the file has no IMG box (shouldn't happen for
        version-2 files but not guaranteed). Confirmed empirically to be a
        diagonal scale (half-extent per axis) + translation (box center)
        matrix, i.e. it maps the unit cube [-1,1]^3 to the box."""
        if self.box is None:
            return None
        half_extent = np.diag(self.box[:3, :3])
        center = self.box[3, :3]
        return tuple(center - half_extent), tuple(center + half_extent)


def _read_exact(f, n):
    data = f.read(n)
    if len(data) != n:
        raise EOFError(f"expected {n} bytes, got {len(data)}")
    return data


def _read_int32(f):
    return struct.unpack("<i", _read_exact(f, 4))[0]


def _read_dict(f, data_len):
    """Reads a dict tail from a chunk's remaining bytes: (key_size, key,
    value_size, value) repeated until key_size == 0. `data_len` bounds how
    many bytes remain in the chunk so we never read past it."""
    result = {}
    pos = 0
    while pos < data_len:
        key_size = _read_int32(f)
        pos += 4
        if key_size == 0:
            break
        key = _read_exact(f, key_size).decode("utf-8", errors="replace")
        pos += key_size
        value_size = _read_int32(f)
        pos += 4
        value = _read_exact(f, value_size)
        pos += value_size
        result[key] = value
    return result, pos


def _decode_block(png_bytes):
    """Decodes a BL16 chunk's PNG bytes into a (16, 16, 16, 4) uint8 array
    indexed as grid[z, y, x] = (r, g, b, a)."""
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    if img.size != (64, 64):
        raise ValueError(f"expected 64x64 block image, got {img.size}")
    flat = np.asarray(img, dtype=np.uint8).reshape(-1, 4)  # row-major, len 4096
    return flat.reshape(TILE_SIZE, TILE_SIZE, TILE_SIZE, 4)  # [z, y, x, rgba]


def read_gox(path):
    """Parses a .gox file and returns a GoxModel with per-layer and merged
    (visible layers only, later layers overwrite earlier ones at the same
    coordinate) voxel dicts of (x, y, z) -> (r, g, b, a)."""
    blocks = []  # list of (16,16,16,4) arrays, in BL16 file order
    model = GoxModel()

    with open(path, "rb") as f:
        magic = _read_exact(f, 4)
        if magic != MAGIC:
            raise ValueError(f"{path}: not a .gox file (bad magic {magic!r})")
        version = _read_int32(f)
        if version != SUPPORTED_VERSION:
            raise ValueError(
                f"{path}: unsupported .gox version {version} "
                f"(only version {SUPPORTED_VERSION} is supported)"
            )

        while True:
            type_bytes = f.read(4)
            if not type_bytes:
                break  # EOF
            if len(type_bytes) != 4:
                raise EOFError("truncated chunk header")
            chunk_type = type_bytes.decode("ascii")
            length = _read_int32(f)
            data_start = f.tell()

            if chunk_type == "BL16":
                png_bytes = _read_exact(f, length)
                blocks.append(_decode_block(png_bytes))

            elif chunk_type == "LAYR":
                nb_blocks = _read_int32(f)
                placements = []
                for _ in range(nb_blocks):
                    index = _read_int32(f)
                    x = _read_int32(f)
                    y = _read_int32(f)
                    z = _read_int32(f)
                    _read_int32(f)  # reserved, always 0
                    placements.append((index, x, y, z))
                consumed = 4 + nb_blocks * 20
                dict_data, _ = _read_dict(f, length - consumed)

                name = dict_data.get("name", b"").rstrip(b"\x00").decode(
                    "utf-8", errors="replace"
                ) or f"layer{len(model.layers)}"
                visible = dict_data.get("visible", b"\x01")[0] != 0

                voxels = {}
                for index, bx, by, bz in placements:
                    grid = blocks[index]
                    nz, ny, nx = np.nonzero(grid[..., 3])  # alpha > 0
                    for lz, ly, lx in zip(nz, ny, nx):
                        r, g, b, a = grid[lz, ly, lx]
                        voxels[(bx + int(lx), by + int(ly), bz + int(lz))] = (
                            int(r), int(g), int(b), int(a)
                        )

                model.layers.append(GoxLayer(name=name, visible=visible, voxels=voxels))
                if visible:
                    model.voxels.update(voxels)

            elif chunk_type == "CAMR":
                dict_data, _ = _read_dict(f, length)
                if "active" in dict_data:
                    name = dict_data.get("name", b"").rstrip(b"\x00").decode(
                        "utf-8", errors="replace"
                    )
                    ortho = dict_data.get("ortho", b"\x00")[0] != 0
                    dist = struct.unpack("<f", dict_data["dist"])[0] if "dist" in dict_data else 0.0
                    mat_bytes = dict_data.get("mat")
                    mat = (
                        np.frombuffer(mat_bytes, dtype="<f4").reshape(4, 4).copy()
                        if mat_bytes and len(mat_bytes) == 64
                        else None
                    )
                    model.active_camera = GoxCamera(name=name, ortho=ortho, dist=dist, mat=mat)

            elif chunk_type == "IMG ":
                dict_data, _ = _read_dict(f, length)
                box_bytes = dict_data.get("box")
                if box_bytes and len(box_bytes) == 64:
                    model.box = np.frombuffer(box_bytes, dtype="<f4").reshape(4, 4).copy()

            else:
                # PREV, MATE, LIGH, or anything else: not needed for voxel
                # reconstruction, skip.
                f.seek(length, 1)

            # Every chunk (including ones we parsed field-by-field) is
            # exactly `length` bytes of data followed by a 4-byte CRC.
            f.seek(data_start + length, 0)
            _read_int32(f)  # CRC, unvalidated

    return model


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <file.gox>")
        sys.exit(1)

    m = read_gox(sys.argv[1])
    print(f"{sys.argv[1]}")
    print(f"  layers: {len(m.layers)}")
    for layer in m.layers:
        vis = "visible" if layer.visible else "hidden"
        print(f"    - {layer.name!r} ({vis}): {len(layer.voxels)} voxels")
    print(f"  total voxels (visible layers, merged): {len(m.voxels)}")
    bbox = m.bbox
    if bbox:
        (minx, miny, minz), (maxx, maxy, maxz) = bbox
        print(f"  bbox: x[{minx},{maxx}] y[{miny},{maxy}] z[{minz},{maxz}]")
        print(f"  size: {maxx-minx+1} x {maxy-miny+1} x {maxz-minz+1}")
    if m.active_camera:
        c = m.active_camera
        print(f"  active camera: {c.name!r} ortho={c.ortho} dist={c.dist}")
        print(f"    right={c.mat[0,:3]}")
        print(f"    up={c.mat[1,:3]}")
        print(f"    forward={c.mat[2,:3]}")
    else:
        print("  active camera: none found")
