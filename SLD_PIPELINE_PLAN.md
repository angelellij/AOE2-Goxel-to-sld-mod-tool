# PNG/Goxel → real SLD pipeline

## Status (2026-09-05)

**Working end-to-end for static (non-animated) buildings.** `.gox` → real
`.sld` now produces genuine, non-empty output, verified on both a small
building (berry bush, 95x68) and a large one (castle, 380x273), each
producing plausibly-sized compressed `.sld` files (hundreds to a couple
thousand bytes, scaling with canvas size/complexity) instead of degenerate
16-byte stubs.

Two things changed substantially from the original plan below, discovered
empirically:

1. **Building the PSD from scratch (via `pytoshop`) never worked**, even
   once every structural bug was fixed (missing composite section, inverted
   layer order, a `DESpriteTool.exe` parser limitation on 3+-layer tagged
   blocks - all real bugs, all fixed). Every from-scratch PSD converted
   "successfully" but produced an identical, degenerate 16-byte `.sld`
   regardless of content. This turned out to match a **known issue reported
   by another AoE2DE modder** on the official forums
   (https://forums.ageofempires.com/t/tools-to-edit-open-extract-sld-files/218934):
   "I can output SLD files, but these only consist of the 16 bytes header
   and no layer data" - resolved only after obtaining a real reference
   template PSD. We found and downloaded that same template and confirmed
   empirically (via a patched `psd-tools` that tolerates the file's
   proprietary resource block) that:
   - The whole document must be **16-bit per channel**, not 8-bit.
   - **Player color is a separate document-level extra/spot channel**
     literally named "Playercolor" (Photoshop's real extra-channel
     feature, image resource 1006/1045) - not colors baked into Diffuse's
     own pixels as originally assumed.
   - For a 16-bit PSD, real per-layer pixel data lives in the **`Lr16`
     additional-layer-information tagged block**, not the main Layer Info
     section (confirmed by editing each and observing which one actually
     changes `DESpriteTool.exe`'s output).

   The fix: `Scripts/psd_template.py` now edits pixel data **inside that
   real reference template** (kept at `Scripts/psd_template/reference_template.psd`)
   instead of assembling a PSD from scratch. `Scripts/build_psd.py` was
   reworked accordingly - `pytoshop` is no longer used at all.

2. Player-color handling in `build_psd.py` was simplified to match: no more
   ramp-color repainting of Diffuse pixels - `conv.py`'s existing green-pixel
   marker (from its `d.png` output) is now written directly as the
   Playercolor channel's intensity.

**Confirmed scope: buildings only** (per user instruction) - the reference
template is for a unit (has a "Blood" layer instead of "Damage"); we rename
that one layer and otherwise leave its proven structure untouched.

3. **A second, separate empty-output bug** surfaced only once real (non-toy)
   building content and an installed in-game test were tried: castle showed
   up completely invisible on the map (selectable, correct HP, but no model
   rendered) even though `DESpriteTool.exe` had converted without error.
   Root-caused by writing a small Python port (`decode_sld.py`, algorithm
   ported from the open-source
   https://github.com/marcustunimus/sld-extractor) of the actual `.sld`
   pixel format, to check our own output without needing the game at all.
   That proved the "normal" (Diffuse) layer was being encoded as a
   degenerate, content-free run-length table (`draws=[0,0]`) despite the
   source PSD's pixel data itself round-tripping correctly through
   `psd-tools` - i.e. the bug was specifically in what `DESpriteTool.exe`
   does with our file, not in what we wrote.

   Isolated by testing the *same* real castle pixel content two ways: (a)
   resized to the building's own 380x273 canvas (header.width/height and
   every layer rect changed away from the template's native 400x400) -
   produced the degenerate empty result; (b) pasted into an *unmodified*
   400x400 canvas at a fixed position - produced correct, real, colorful
   output (verified visually via `decode_sld.py`, including the artist's
   original orange tower-roof color). **Conclusion: the document canvas
   size must never be changed from the template's native value** - most
   likely the undocumented proprietary `psdM` resource block carries its
   own size/bounds metadata that goes stale (and gets cross-checked) once
   the declared canvas size changes.

   Fix: `psd_template.py` no longer touches canvas size or layer rects at
   all - every layer is always the full native canvas. `build_psd.py` now
   pastes each rendered layer onto that fixed-size canvas at an offset
   chosen so the building's own anchor point (same formula `conv.py`
   already prints: `tile_x/2, canvas_height - tile_y/2`) lands at the
   canvas center - which is what `DESpriteTool.exe` derives as the sprite's
   in-game hotspot when no explicit `-Hx`/`-Hy` is given (CLI flags are
   ignored entirely in the folder/batch conversion mode this pipeline
   uses - only `settings.json` keys have any effect there).

   Caveat: the template's native canvas (400x400) comfortably fits
   buildings up to 4x4 tiles (max width 380px); a 5x5 tile building (475px
   wide) would currently overflow it. Not yet hit in practice - revisit if/
   when a 5x5 building is converted.

**Verified installed for in-game testing**: berry bush and castle, in a
**separate test mod** (`Power - Checker SLD test`, not the real
`Power - Checker buildings` mod), via the new `Scripts/build_sld.py`
end-to-end orchestrator (PSD build → `wine DESpriteTool.exe` → copy into
`mods/local/<mod>/resources/_common/drs/graphics/` under every real civ
graphic name `rename.py` maps the building to). Note `rename.py`'s own
target names already end in `_x1` (the game's standard/high-res asset
convention, matching `DESpriteTool`'s own `_x1.sld`/`_x2.sld` output) - the
x1 variant maps straight to `{target}.sld`, and x2 replaces the trailing
`_x1` with `_x2`; it does not get a second suffix appended.

4. **Two more issues found from the first real in-game test** (castle showed
   up correctly-colored this time, per the canvas-fix above, but at the
   wrong size and with a solid black backdrop):
   - **Scale**: real building graphics have **zero `_x2.sld` files** in the
     whole game install (`find .../resources/_common/drs/graphics -iname
     "*_x2.sld" | wc -l` → 0) - the game only ever uses `_x1`, which
     `DESpriteTool.exe` auto-generates by downscaling our source PSD 50%.
     Measured a real asset (`b_medi_castle_age3_x1.sld`: content 404x452px
     for a 4x4-tile building) against our own conv.py-scale (95px/tile)
     content run through the same pipeline (content ended up 192x140px
     after the automatic halving): real buildings are authored roughly 2x
     denser per tile than conv.py's PNGs. Fix: `build_psd.py` now upscales
     every layer by `AUTHOR_SCALE = 2` before handing it to `psd_template.py`,
     so the auto-generated `_x1` lands back at conv.py's intended on-screen
     size (verified: our castle's `_x1` content came out 384x276px vs the
     real one's 404x452 - width now matches within ~5%; the remaining
     height difference tracks with conv.py's own existing Diffuse PNG
     aspect ratio for this specific castle model, not a scale bug).
   - **Non-square canvas resize was the real trigger for the "empty content"
     bug**, not resizing itself: re-tested the exact same real castle pixel
     content resized to a *square* 800x800 canvas (instead of the
     400x400-native/380x273-content mismatch tried earlier) and it
     converted correctly. So canvas size can and does need to scale with
     the building (to fit the 2x-authored content) - it just has to stay
     square. `psd_template.resize_square_canvas` replaces the old
     "never resize" rule.
   - **Solid black backdrop**: leaving `Background`/`Decal` as an explicit
     all-zero (black RGB, zero alpha) placeholder rendered in-game as an
     opaque black square behind the building, rather than transparent as
     intended - some flattening step apparently doesn't respect alpha for
     at least the `Background` layer. Fix: `build_psd.py` no longer
     overwrites `Decal`/`Background` at all (passes `None`, which
     `psd_template.set_layer_pixels` already treated as "leave this
     channel untouched"), keeping the reference template's own proven
     content instead of guessing at a safe "empty" value. Not yet
     redesigned for buildings specifically - awaiting the next in-game
     test to see whether the original unit-template content there is
     visually acceptable or needs real building-specific art.

5. **Open problem: the SLD "shadow" channel covers far more area than it
   should**, showing up in-game as a large semi-transparent dark/tinted
   overlay behind the building (not just a solid black square as first
   reported - that was actually the scale bug making a modest-sized overlay
   look absolute; the underlying flat-fill issue was there from the start).
   Wrote a from-scratch Python decoder for the actual `.sld` binary format
   (`decode_sld.py` in the scratchpad, algorithm ported from
   https://github.com/marcustunimus/sld-extractor's JS source) to inspect
   our own output directly, and compared against a real shipped asset
   (`resources/_common/drs/graphics/b_medi_castle_age3_x1.sld`, extracted
   directly - loose files on disk, no DRS unpacking needed). Findings:
   - The game **only ever uses `_x1.sld` files for buildings** - zero
     `_x2.sld` files exist anywhere in `resources/_common/drs/graphics`.
   - Real castle's shadow channel: sparse, ~2.4% of its canvas, a proper
     localized cast-shadow shape offset to one side of the building.
   - Ours: a flat, spatially-uniform value covering the **entire**
     transparent region of the canvas (81-88% of it, depending on canvas
     padding) - clearly wrong, not just "differently shaped."
   - **Bisected which of the 7 PSD layers drives it**, by forcing each to
     all-zero one at a time and diffing the resulting `.sld` bytes:
     Decal, Background, AmbientOcclusion, Height, Normals, and Damage each
     individually produced **byte-for-byte identical** output - none of
     them affect the shadow channel at all. Only **Diffuse's own alpha
     channel** does: forcing it fully opaque (255) across the *entire*
     canvas removes the shadow channel from the frame's type flags
     entirely (`0x1f` → `0x1d`), but then the "normal" (diffuse) layer
     itself fills the whole canvas instead (just moves the same problem to
     a different channel, not a fix).
   - Real assets also have large genuinely-transparent padding regions
     (their canvas is ~2x their content on each axis, similar ratio to
     ours) without triggering this flat-fill behavior - so canvas padding
     ratio isn't the distinguishing factor either. What actually
     distinguishes a real asset's alpha pattern from ours (that lets
     DESpriteTool compute a real localized shadow instead of falling back
     to a flat fill) is **not yet found**. Plausible remaining leads: the
     undocumented proprietary `psdM` resource block might carry real
     lighting/shadow-casting data the devs' own internal "PSDFileToolkit"
     writes and that a hand-edited PSD simply doesn't have; or there's an
     eighth, undiscovered PSD layer/mechanism for authoring the shadow
     directly that the readme doesn't document.
   - **Fix found**: `settings.json`'s `"ShadowThreshold": 8` (also exposed
     as CLI `-ST=###`, though CLI flags are ignored in folder/batch mode -
     only `settings.json` keys apply there) controls this. Setting it to
     255 removes the shadow channel from the frame's type flags entirely,
     verified on a freshly-rebuilt (non-debug) PSD to leave the
     Diffuse/normal layer byte-identical to the known-good result (same
     content coords, same pixel count). `build_sld.py`'s staging step now
     writes `{"ShadowThreshold": 255}` into the batch folder automatically.
     (An earlier test of this same setting appeared to also break Diffuse -
     that was testing against a stale PSD left over from unrelated
     debugging, not a real effect of the setting itself.)

6. **Castle came out much darker than the source PNG/gox colors.** Cause:
   `AmbientOcclusion` is MULTIPLY-blended onto Diffuse in the template, so
   its own RGB acts as a per-pixel darkening factor - and
   `voxel_render.ambient_occlusion()` has two bugs feeding it bad values:
   it counts all 26 neighbors (including the ~13 that are trivially
   "solid" just from being inside the object's own bulk, not real
   occlusion) as one flat fraction, and uses that fraction directly as
   brightness un-inverted, so even fully-exposed well-lit faces came out
   ~50% gray - darkening the whole building via multiply. Fixed for now by
   neutralizing AO's RGB to full white in `build_psd.py` (multiply-by-white
   is a no-op) rather than risk a half-correct partial fix under time
   pressure. A real hemispherical (outward-neighbors-only), inverted AO
   calculation is still a worthwhile follow-up for genuine corner/crevice
   shading, just not urgent now that the systematic darkening is gone.

7. **Dark diamond patch at the building's base.** `conv.py` bakes a
   semi-transparent black "footprint diamond" guide mark directly into the
   Diffuse PNG (drawn on the canvas before the building is pasted on top,
   so it only shows through in the gaps the building doesn't cover) - a
   visual aid for the old SLX Studio anchor-setting step, not meant to be
   part of final art (real game sprites don't have a footprint shape
   painted into their diffuse texture). `build_layers()` now uses `d.png`'s
   own red marker (it already flags exactly these pixels) to drop them to
   fully transparent before use.

**Verified visually (our own decoder, not yet a fresh in-game screenshot)
with all of the above applied**: castle renders at the correct size, no
shadow-channel overlay, correct (non-darkened) colors matching the source
Diffuse PNG, and no leftover footprint-guide artifact at its base.

8. **Removed the "marker cube" convention from the .gox files entirely**,
   per user request. Confirmed via connected-component analysis that every
   `.gox` file used the same convention: 2-4 isolated single-voxel red
   cubes at the model's own lowest z-layer, sitting at corners of the
   intended tile footprint - existing purely so `conv.py`'s crop-to-content
   step would always capture the full tile area, not just whatever the
   model's own geometry happened to reach.
   - Confirmed a viable replacement first: the `.gox` file's own `IMG` "box"
     chunk (Goxel's working-volume/grid setting) already records a
     reasonable bounding region in every file checked across multiple tile
     sizes (X/Y half-extent came out to a clean 4.0 world-units-per-tile for
     3x3/4x4/5x5 buildings; less exact for some files like the castle
     example, but always comfortably containing the real geometry).
   - `gox_reader.py` now parses this box (`GoxModel.box`/`.box_bounds`).
     `voxel_render.render()` projects the box's footprint through the same
     camera used for the geometry, and returns it as `box_crop_px`;
     `build_psd.py` uses that (via `compute_placement`'s new `crop_box`
     param) to align Height/Normals/AmbientOcclusion to the tile canvas
     instead of each pass's own tight content bbox.
   - Wrote `Scripts/gox_writer.py`, the project's first `.gox` *writer* -
     surgically edits only the specific voxels being removed (decodes just
     the affected `BL16` block(s), zeroes the target voxel, re-encodes,
     splices the new chunk bytes into an unmodified copy of the rest of the
     file) rather than a full round-trip rewrite, since the format's
     flat/self-contained chunk structure makes that safe and low-risk.
   - `Scripts/remove_gox_markers.py` batch-applies this: connected
     components of size 1, reddish color, at the model's own minimum z.
     Run across all of `files-gox/`: **480 marker cubes removed across 196
     files** (one pre-existing unrelated file, `blacksmith0.gox`, was
     skipped - it's actually a PNG with a `.gox` extension, not something
     this change touched). All modified files verified to still parse
     correctly afterward.
   - Caveat carried over from finding #6 above: since box-based cropping
     isn't pixel-identical to the old marker-cube-based crop, and the
     already-generated Diffuse PNGs in `files-png-processed/` still reflect
     the old (now-removed-from-source) marker cubes until re-exported from
     Goxel, `build_layers()` now resizes (rather than hard-fails) if a
     voxel-rendered pass's box-cropped canvas doesn't exactly match the
     existing Diffuse PNG's size - width matches exactly, height can drift
     slightly. This resolves itself once PNGs are re-exported from the
     cleaned `.gox` files.

9. **Player color rendered as an ugly flat dark-maroon blotch** instead of
   a proper tinted region (visible on a real building next to it using its
   actual gold/tan team color correctly). Isolated by forcing our
   "Playercolor" channel to all-zero: the frame's `player` type flag
   (0x10) disappeared and the region that had shown maroon reverted to
   plain **blue** in the Diffuse/normal layer - confirming (a) our channel
   does correctly drive real in-game recoloring (this journey's `#1`
   design decision was right), and (b) the artist's Diffuse art uses a
   reference **blue**, not the reference-red convention old-school SLP
   used. The bug was in what *value* we filled that channel with: a flat
   255 (boolean "recolor this pixel, full strength") likely maps to one
   fixed, wrong shade of whatever ramp the channel indexes into. Fixed
   `build_psd.py`'s `player_color_mask` to use the *luminance* of the
   original reference-blue Diffuse pixel there instead of a flat value -
   preserving the artist's own shading so recoloring reads as a hue swap,
   not a flat block.

   In-game re-test showed it got *worse* - scattered red squiggly blobs
   instead of a clean tint, still not the real player's color. Fixed the
   decoder bug that had blocked verifying this channel directly (it reads
   `hasSize=False` and reuses the Normal layer's own coords - confirmed
   from `createPlayerLayer` in sld-extractor.html - not its own coords
   header like Shadow; our decoder wrongly assumed the latter). With that
   fixed:
   - Decoding a **real** building's player channel showed a sparse
     (~1% of canvas), smoothly-graded (250 unique values) thin trim/
     ornament pattern - not a big filled area.
   - Decoding **ours** crashed partway through (ran out of encoded data
     mid-block), and the encoded chunk was tiny relative to a real one
     (652 vs 7048 bytes) despite comparable total marked area - our region
     needed far more RLE runs to describe (648 vs 386), i.e. it's much
     more *fragmented* (several separate window rects) than real assets'
     more contiguous trim.
   - Bisected two competing theories: (a) shape/fragmentation - tested a
     dilated blob and a single solid bounding-box rectangle; the bbox
     version was *worse* (2046 RLE runs, chunk grew to 7032 bytes but
     still corrupted) - ruled out. (b) Diffuse's own colors being
     independently cross-checked against the reference ramp - repainted
     Diffuse's marked pixels onto the red ramp and re-tested: the
     Playercolor channel's encoding came out **byte-identical** to before
     the repaint - ruled out too.
   - What actually worked: **eroding** the marked region (`ImageFilter.
     MinFilter(9)`) shrank the encoded chunk from 652 to 108 bytes -
     i.e. DESpriteTool appears to pre-allocate this channel's buffer sized
     for something like real assets' actual usage (sparse trim, ~1% of
     canvas), and a big densely-detailed region simply overflows it
     regardless of shape or Diffuse's colors. `player_color_mask` now
     erodes before use. Diffuse is still also repainted onto the reference
     ramp (per the original theory in point form above) since that part
     was never disproven, only shown to not affect *this specific*
     channel's encoding size - it may still matter for get the right hue
     once the channel itself decodes cleanly.
   In-game re-test after erosion: **no more corruption**, but the region
   rendered solid **black** instead of any team color. Cause: the
   luminance formula (`0.299R+0.587G+0.114B`) badly under-weights blue -
   the artist's reference placeholder is a medium-bright blue, which that
   formula scores as quite *dark*, pushing the ramp-shade lookup toward
   the reference ramp's near-black end almost everywhere. Fixed by
   switching both `repaint_diffuse_player_color` and `player_color_mask`
   from luminance to HSV-style "value" (`max(R, G, B)`, added as a shared
   `_brightness()` helper) - hue-independent, so it doesn't matter that
   the reference color happens to be blue.
   Confirmed in-game: real dynamic recoloring is working (player 1 showed
   red - AoE2's actual default color for that player slot, not a
   coincidental fixed value). Two rounds of polish after that:
   - Blurred the brightness map (`ImageFilter.GaussianBlur(2)`) before the
     ramp lookup in `repaint_diffuse_player_color` - the artist's original
     blue shading was carrying straight through as visibly darker patches
     within the repainted red.
   - Still showed *two different reds* after that - traced to Diffuse's
     repaint and the Playercolor channel using two *different* masks (the
     former the full marked region, the latter eroded down for the buffer-
     size reason above). Where they agreed showed real dynamic per-player
     red; everywhere Diffuse alone still covered showed a static,
     un-recolored ramp-red left over. Fixed by extracting one shared
     `_eroded_player_mask()` and feeding it to both functions, so they can
     no longer disagree on which pixels are player-colored.
   That "fix" itself made things visibly *worse* in-game: most of the
   window area came back as plain unpainted reference-**blue**, since
   Diffuse's repaint now only covered the small eroded core. Reverted to
   two masks on purpose: `_full_player_mask` (un-eroded) for Diffuse's own
   repaint, so nothing is left blue, and `_eroded_player_mask` only for
   the separate Playercolor channel, for the buffer-size reason. This
   knowingly brings back the "two different reds" seam from the previous
   round, which is a real but *minor* cosmetic mismatch - clearly
   preferable to visible unpainted blue patches. Not yet re-confirmed
   in-game.

## Status (2026-09-20) — footprint-diamond ground indicator, size/shape solved

10. **Real, correctly-sized footprint-diamond ground indicator under the
    building, matching the old SLX-Studio convention** (a translucent
    diamond/shadow where `d.png` marks red under the building's base).
    Confirmed working end-to-end through the real `build_sld.py` pipeline
    for `castle` (opaque, correct size/shape - not yet real per-pixel
    translucency, see below). This took several rounds of chasing what
    looked like "regressions" that turned out to be pre-existing bugs in
    `write_psd()`/`build_sld.py` that a one-off manual test (bypassing both)
    had never hit:

    - **Root cause of the giant shadow blob (again)**: finding #5 above
      ("Open problem: the SLD shadow channel covers far more area than it
      should") turned out to have the wrong root cause. It's **not** an
      unfixable property of hand-authored PSDs vs. real assets - the
      shadow channel's bounding box is a function of **the PSD canvas size
      alone**, not of any pixel content in any of the 7 layers (confirmed:
      blanking every layer still gave a full-canvas shadow; two unrelated
      buildings sharing one canvas size produced byte-identical shadow
      bboxes). Shrinking the canvas to just barely fit the content, instead
      of the old flat 2x-content "for safety" margin, produces a real,
      correctly-sized, genuinely alpha-blended shadow. **The formula that
      is actually confirmed correct (byte-for-byte reproducible, then
      verified in-game) is:**
      ```python
      canvas_size = int(1.1 * max(canvas_width, canvas_height))
      offset = (canvas_size / 2 - ax, canvas_size / 2 - ay)
      ```
      A "more principled"-looking alternative (`2 * max(ax, ay,
      canvas_width - ax, canvas_height - ay) + margin`, sized off the
      anchor point so content can't clip at its paste offset) was tried
      instead and, despite computing a *smaller* canvas for castle (800 vs
      836), produced the giant blob again. The shadow bbox is **not**
      simply proportional to canvas size in an obvious way - don't swap in
      a formula that merely looks safer without re-verifying in-game.
    - **`ShadowThreshold: 255` (finding #5's "fix") must NOT be used
      anymore.** That setting fully suppresses the shadow channel - it was
      the right workaround when the canvas-size root cause above was still
      unknown, but now that the canvas is sized correctly, leaving the
      shadow channel at its default (unsuppressed) threshold is exactly
      what makes the footprint-diamond area (painted as ordinary opaque
      Diffuse content) render as real in-game translucency. `build_sld.py`
      still had the old `{"ShadowThreshold": 255}` override hardcoded into
      every batch's `settings.json` - this silently killed the effect for
      every build that went through the real pipeline (vs. a one-off
      manual script that used `{}`), which is exactly what made it look
      like the diamond was "regressing" across several rounds when really
      the real pipeline had just never had the fix applied. Fixed: writes
      `{}` (tool default) now.
    - **Finding #4's "Solid black backdrop" fix (`Background`/`Decal`
      passed as `None`, left untouched at the reference template's own
      content) is correct and must be kept that way.** A later edit
      (unrelated to this session's diamond work) had started actively
      computing and passing real `Background` layer data (blanked to
      fully transparent) instead of `None` - this is NOT equivalent:
      explicitly writing all-zero-alpha Background content makes
      DESpriteTool render it as a large, roughly canvas-sized opaque plate
      instead of nothing. Reverted back to `None`.
    - **Dead code from an abandoned dither experiment was silently
      clobbering the diamond on every build.** An earlier attempt at real
      per-pixel translucency (encoding the footprint area as an ordered
      8x8-block dither of solid-black/fully-transparent blocks, trying to
      dodge BC1's whole-block draw/skip granularity) was abandoned as a
      dead end (still read as solid in-game after DESpriteTool's own 50%
      downscale re-blurred it), but the code implementing it was never
      removed from `write_psd()`. It ran *after* `build_layers()` had
      already correctly painted the footprint area as opaque `GRID_COLOR`,
      and unconditionally overwrote that same region with its own
      black/transparent checkerboard - meaning every color/opacity change
      made to `GRID_COLOR` during this session had **zero effect** on the
      real pipeline's output, only on the one-off manual bypass scripts
      that called `psd_template.write_building_psd()` directly. Removed
      entirely, along with the now-unused `footprint_guide` plumbing.

    **Current confirmed-working recipe** (`Scripts/build_psd.py`,
    `Scripts/build_sld.py`):
    - `build_layers()` paints the footprint-diamond area (from `d.png`'s
      red marker) as flat opaque `GRID_COLOR = (170, 165, 140)` directly
      into Diffuse, alongside forcing Diffuse's alpha to 255 there (part of
      the same "non-magenta -> opaque" rule already used for the building
      itself).
    - `write_psd()` sizes the canvas via the `1.1 * max(w, h)` formula
      above, and passes `decal_rgb=None, decal_alpha=None,
      background_rgb=None, background_alpha=None` (both layers untouched).
    - `build_sld.py`'s `convert_via_wine()` writes `{}` to the batch's
      `settings.json` (no `ShadowThreshold` override).
    - Result (verified in-game on `castle`): diamond renders at the
      correct size and diamond *shape* (not a canvas-sized square), no
      giant background blob. **Not yet real per-pixel translucency** - it
      currently reads as a flat, fully opaque light-gray fill ("está
      sólido el diamante gris" - user feedback, 2026-09-20). Making it
      genuinely alpha-blended (matching the old SLX diamond's actual
      translucency, not just a solid ground marker) is the next open task.

11. **Real per-pixel translucency for the footprint-diamond indicator -
    solved.** #10's opaque `GRID_COLOR` fill in Diffuse was confirmed
    working for size/shape, but read as a flat solid patch, not a blended
    overlay ("está sólido el diamante gris"). Diffuse itself has **no real
    per-pixel alpha blending in-game** - proven repeatedly and exhaustively
    in earlier sessions (dither at multiple granularities, hand-patched
    BC1 blocks with and without a transparent index, all render solid). The
    only channel that can show genuine translucency is the SLD "shadow"
    channel - but DESpriteTool's own auto-generation of it is unusable
    (either an oversized blob pre-#10's canvas fix, or completely empty
    post-fix: decoding a #10-era build showed its shadow layer at 0%
    nonzero coverage). **Fix: stop relying on DESpriteTool to generate the
    shadow channel at all - hand-write it directly**, using the SLD binary
    format decoded in finding #5 (ported to `Scripts/patch_shadow.py` as
    the write-side counterpart of the project's scratch decoder). This
    works because the format's "index 0 always maps to the block's first
    endpoint byte" property (true in both of its two interpolation modes)
    means a uniform-value block only needs 2 meaningful bytes (the value,
    plus a second byte that doesn't matter) and 6 zero index bytes - no
    need to construct a real gradient.

    Two file-format details had to be reverse-engineered by direct trial
    (not documented anywhere): the stored `draw_count` field is
    `len(draws) / 2`, not `len(draws)` itself (found by comparing a real,
    empty shadow chunk's field value against its actual decoded array
    length) - so the RLE run list must always be padded to even length;
    and a chunk's leading `declared_size` field is exactly
    `len(real_content) + 4` (verified against two real chunks, holds for
    every `len(real_content) % 4` case via the decode side's
    `((declared_size-1)>>2)<<2` rounding formula).

    Pipeline wiring: `build_psd.build_layers()` now leaves the footprint-
    diamond area **fully transparent** in Diffuse (not opaque `GRID_COLOR`)
    and returns a `"footprint_guide"` boolean mask; `write_psd()` scales/
    pastes it the same way as every other layer and returns
    `(canvas_size, footprint_guide_mask)`; `build_sld.py`'s
    `build_and_install()` passes that mask to
    `patch_shadow.patch_sld_shadow()` right after `convert_via_wine()`
    produces the real `.sld`, which splices a hand-encoded shadow chunk
    into the file in place (only `_x1.sld` - the game never uses `_x2` for
    buildings, so it's left untouched). Confirmed in-game: real, correctly-
    positioned alpha-blended translucency.

    **Mask shape/value tuning (all confirmed empirically, several dead
    ends included on purpose so they aren't retried)**:
    - d.png's red marker is a **thick filled wedge** (up to 25px, ~12px
      average, on castle), only covering the diamond's front (wherever the
      building doesn't itself cover it). Encoding the whole fill reads as a
      blobby patch, not a line ("el borde se ve raro... no es una linea").
    - **Confirmed-good recipe**: erode the fill with `ImageFilter.
      MinFilter(5)` (shrink ~2px each side) before use, as both the
      transparent-in-Diffuse mask and the shadow-encoding mask. Renders as
      a clean single line. `value=190` in `patch_shadow.patch_sld_shadow`
      (**counterintuitively, HIGHER = LIGHTER/more see-through** - lowering
      it from 120 to 70 made the line render *darker*, the opposite of
      "más claro"). This exact combination is the current shipped state -
      confirmed by the user as correct twice after two different
      regressions below were reverted away from.
    - **Dead end 1**: an *interior ring* (fill minus a slightly-eroded copy,
      meant to trace the true outer edge without shifting it inward) -
      tried to fix "no ocupa la grilla" (doesn't line up with the tile
      grid). Made both problems worse: jagged/spiky edge, still
      misaligned. Reverted.
    - **Dead end 2**: an *outward dilation* (grow the fill outward, keep
      only the newly-added band) - tried to fix both "too small" and "only
      traces the front, not a full outline" at once (it does produce a
      complete diamond outline, and a bigger one, when inspected in
      isolation). But dilating in every direction also grows back into the
      building's own silhouette on the side the wedge is bounded by it -
      even after restricting the dilated band to only-former-background
      pixels (`is_bg`), this reintroduced a solid black patch ("Hiciste
      cualquier cosa"), confirmed by decoding the normal layer directly
      and seeing the dilated ring poke a transparent notch into the
      building's own base. This is the same "mixed opaque/transparent 4x4
      block renders solid black regardless of alpha" pathology proven in
      an earlier session (a fully-opaque, no-transparency-index
      hand-patched block in this same spot still rendered black) -
      confirms it's specifically about blocks straddling the
      building/background boundary, not about alpha or color content.
      Reverted per explicit user request to go back to the last good state.
    - **Still open (cosmetic polish, not urgent)**: the confirmed-good line
      is "medio grueso" (somewhat thick) and only traces the diamond's
      front edge, not a complete outline, so it doesn't perfectly line up
      with the tile placement grid. Both dead ends above show this is
      trickier than it looks - any fix must avoid the dilated mask ever
      overlapping pixels that were part of the building's own opaque
      silhouette, even by one pixel, in the *original* (pre-erosion/
      dilation) art, not just in the processed mask.

12. **`build_sld.py --all` run across every building (2026-09-23).** 50/52
    succeeded on the first pass; the 2 failures (`blacksmith2`, `market3`)
    were a pre-existing gap, not a new bug - `build_layers()` unconditionally
    read `files-png/<tile_size>x<tile_size>/<name>.png` (the artist's
    hand-approved render) and these two never had one (only their `_des*`
    destruction variants were ever hand-drawn - confirmed their `.gox` voxel
    model DOES exist). Fixed: when that PNG is missing, `build_layers()` now
    falls back to the "diffuse" pass `voxel_render.render()` already computes
    for Height/Normals/AO (flatter per-face shading than hand-painted art,
    and no footprint-diamond guide mark, since that's baked into the
    hand-rendered PNG by the artist with nothing to derive it from
    otherwise) instead of hard-failing. Both buildings now build and install
    successfully. A block-majority draw-threshold tweak to
    `patch_shadow.encode_shadow_layer` (tried to thin the footprint line
    further) was reverted per explicit user request before this run, back to
    the plain "any pixel in the block" rule documented in #11 - the
    line-thickness/tile-grid-alignment polish noted there is still open.

13. **The voxel-fallback path (see #12) was a stub that only fixed the
    "doesn't crash" case - three real bugs found once `market3` was actually
    checked in-game.** User's framing was right: "si borro los files-png se
    irian todos los edificios a la mierda" - the fallback needs to actually
    match the hand-rendered convention, not just avoid crashing.
    - **Giant solid black rectangle.** The hand-rendered path keys its
      background as flat magenta and *derives* alpha from that
      (`is_bg = diffuse == MAGENTA`); the voxel-rendered fallback already has
      a real, correct alpha channel from the rasterizer (background is
      black-and-*transparent*, not magenta). Applying the magenta-keying
      rule anyway forced alpha=255 across the *entire* canvas (since none of
      it is magenta), turning the transparent background into a solid black
      plate. Fixed: `build_layers()` only derives alpha that way when the
      hand PNG exists; the fallback path keeps the rasterizer's own alpha.
    - **No player-color tinting.** Solved by checking the actual voxel
      color palettes: `market2`/`market3`/`blacksmith2`/`blacksmith3`'s
      `.gox` files all use one exact shared color, `(0, 0, 255, 255)`, at
      comparable voxel counts - the same reference-blue convention the
      hand-rendered art uses (`finding #9`), just baked directly into the
      geometry instead of drawn on top of a 2D render. Since
      `voxel_render`'s per-face shading only ever scales a color down
      (never shifts hue), a shaded pure-blue voxel is still exactly
      zero-red/zero-green in the rendered pixel - `_voxel_player_mask()`
      detects that directly, no dmask needed.
    - **No footprint-diamond guide.** There's no dmask to read a hand-drawn
      red marker from, but the diamond doesn't need one - it's just the
      tile's own footprint shape, same `tile_x`/`tile_y`/anchor math
      `anchor_point()` already uses, centered on the anchor, minus wherever
      the building's own (voxel-rendered) silhouette covers it. Synthesized
      directly with `ImageDraw.polygon` instead of guessing at art that was
      never drawn - visually confirmed (an RGB overlay of the diamond
      against the building's own silhouette) to trace the same "peeks out
      wherever the building doesn't cover it" shape the hand-drawn
      convention produces.
    All three fixed in `build_layers()`'s `not have_raw_png` branch;
    confirmed via `market3`/`blacksmith2` rebuilds (nonzero player-color and
    footprint-guide pixel counts, correct alpha) before reinstalling.

14. **Full pipeline unification - `files-png/` dropped entirely, everything
    now sourced from `.gox`.** #12/#13's `have_raw_png` branch (prefer the
    hand-rendered PNG, fall back to a voxel render only for the couple of
    buildings missing one) produced visibly inconsistent results across
    buildings on two different code paths - explicit user instruction to
    collapse this to one: "NECESITO 1 FORMA DE HACER LAS COSAS... TODO salga
    del gox", then, to remove any ambiguity, "Ahi te simplifique las
    cosas. solo tenes los gox." `build_layers()` no longer reads
    `files-png/` at all; every building now goes through the same voxel-
    render -> geometric-diamond -> voxel-blue-player-mask path #13
    introduced for the fallback case. Traded away: the hand-painted PNGs'
    shading detail (voxel_render's own per-face flat shading is simpler) -
    an accepted, explicit trade-off for uniformity, not an oversight.
    - Also fixed in the same pass: `build_damage_layer`'s "eligible" pixel
      test used to check for flat magenta (the hand-PNG's background
      convention) - with every Diffuse now voxel-rendered (real alpha,
      transparent-black background, never magenta), that check would have
      matched the *entire* canvas as "eligible", not just the building.
      Switched to `alpha > 0`.
    - Removed now-dead code: `_full_player_mask` (read a dmask that no
      longer exists), the `have_raw_png` branching itself, `conv.
      process_diffuse` call, and the `os` import that only supported the
      file-existence check.
    - `build_sld.py --all 10` run against the fully unified pipeline: 48/52
      succeeded first pass; all 4 failures (`market2`, `stonecorner`,
      `stone2_open`, `stone2_closed`) were a concurrency race in the 10-way
      Wine/`xvfb-run` batch runner, not a real content bug - confirmed by
      re-running `market2`'s exact already-generated PSD through
      DESpriteTool standalone (succeeded immediately), then re-running all
      4 sequentially (all succeeded). `convert_via_wine`'s own docstring
      claim of "confirmed with a real 2-way concurrent run" apparently
      doesn't hold at 10-way concurrency - a real, still-unexplained
      reliability gap in the batch runner itself (Wine/X display race,
      most likely), not in anything this session's pipeline changes touch.
      **52/52 built and installed** after the sequential re-run.

15. **Two more bugs found from the first in-game look at the unified (#14)
    pipeline**, both user-spotted:
    - **1x1 (and other small) buildings rendered undersized** ("las cosas
      que son 1x1... la imagen esta mas chica"). Root-caused with the user:
      nearly every `tile_size=1` building's `.gox` file (fortifiedcorner,
      fortifiedwall, outpost, palisade, stonecorner, stonewall,
      tower1/2/4 - confirmed by comparing each one's own IMG "box" against
      its tight alpha bbox) shares one identical box that's ~2x too wide in
      world units ("las grillas en 16x16 en vez de 8x8") - the artist never
      shrank Goxel's default working-volume box down for these smaller
      models, unlike multi-tile ones (castle, house1) where the box does
      fit closely. Cropping to that box and resizing to the tile width
      shrank the real content inside the frame. Rather than hand-edit
      dozens of `.gox` files' box metadata, `build_layers()` now falls back
      to the tight alpha bbox whenever the box is >1.3x looser than it in
      either dimension - naturally distinguishes a customized box (house1:
      ratio ~1.0, stays box-cropped) from an untouched default one
      (outpost: ~2.3x, falls back), with no need to know which numeric
      convention was intended.
    - **Footprint-diamond showed extra floating patches inside the
      building's own silhouette** ("esos rebordes cuadriculados que no
      entiendo de donde vienen"). `footprint_fill = diamond & (alpha==0)`
      caught more than just the diamond's true perimeter - any interior
      alpha==0 gap in the building's own structure (market3's open
      colonnade, gaps between a tower's corner posts) satisfied that same
      condition, showing up as small, disconnected extra blobs. Fixed by
      flood-filling the background from a known-exterior corner `(0, 0)`
      first - only background actually *connected* to the outside counts
      as footprint area; an interior hole the flood fill doesn't reach is
      excluded. Hit a real PIL quirk along the way: `ImageDraw.floodfill`
      silently no-ops on an `Image.fromarray`-backed image (confirmed with
      a minimal repro, `PIL 12.1.1`) - needs `.copy()` first to force PIL's
      own native buffer.

16. **#15's undersized-1x1-building fix (fall back to the tight alpha bbox
    when the .gox box looks untouched) caused a worse regression** - towers
    rendered comically oversized ("agrandaste todas las imagenes") -
    reverted per explicit user request ("Pero no agrandes todo..."), back
    to `build_layers()` always honoring `box_crop_px` unconditionally, no
    heuristic. The user's own diagnosis was more precise anyway: "En los
    .gox que son 1x1 hay que poner que el box tiene x e y de tamaño 8" -
    fix the actual `.gox` box data, not the code that reads it. Checked
    every `tile_size=1` building's own real voxel extent against its box:
    all 10 have voxel content spanning exactly 8 units in X and Y
    (`x[-16,-9] y[-16,-9]`); `tower3` already has the box that correctly
    matches that (half-extent 4, center -12 - "tamaño 8" is the resulting
    *span*, half-extent*2), while the other 9 (fortifiedcorner,
    fortifiedwall, outpost, palisade, stonecorner, stonewall, tower1/2/4)
    were all still at Goxel's untouched default (half-extent 8, center -8 -
    a span of 16, exactly 2x too wide, with the box's far edge sitting
    entirely past the real content). Added `gox_writer.set_box_xy()` (a
    same-length, 64-byte in-place overwrite of the IMG chunk's "box" entry -
    same safe, surgical edit model `remove_voxels` already uses) and applied
    `half_extent_xy=4, center_xy=-12` to all 9 - confirmed each file still
    parses with its voxel count unchanged, and every one's rendered Diffuse
    width now correctly fills its tile (95px, matching `tower3`'s own,
    already-correct 95px).

17. **Procedural destruction animation - implemented and confirmed on
    `castle`.** Exact user spec: height split into 5 equal Z-bands (band 1 =
    topmost); frame 1 = 80% of the top band removed; frame 2 = that top band
    100% gone plus 80% of the next band down; and so on through frame 5.
    Each of these 5 visually-distinct stages is repeated 3 times as real SLD
    frames (same "duplicate the still image" convention already used for
    idle-animation frame counts), for 15 total frames.
    - `voxel_render.destruction_frame_voxels(voxels, frame_index, num_frames,
      seed)` is a pure function computing one stage's reduced voxel dict -
      `seed` (derived from building name + frame index) makes the random 80%
      selection reproducible across rebuilds instead of a different rubble
      shape every run.
    - `build_layers()` gained optional `model`/`crop_box` params so a frame
      sequence can share the *undamaged* model's own placement (crop_box
      from `box_crop_px`) - without this, each frame would independently
      crop-to-its-own-shrinking-content and appear to rescale bigger as it
      loses material, instead of visibly collapsing in place. This was
      already flagged as needed groundwork in an earlier session.
    - `build_psd.build_destruction_frames()` loads the `.gox` once, computes
      the shared placement, and returns one `build_layers()`-style dict per
      stage - nothing is ever written to disk as an intermediate `.gox`
      file, only ever an in-memory voxel dict (per explicit user
      instruction: "Estos gox reeplicados NO SE DEBEN GUARDAR").
    - `build_sld.build_and_install_destruction()` resolves the real
      destruction target name(s) from rename.py's separate "<name>d" entry
      (e.g. `castle` -> `castled` -> `castle_age3_destruction_x1` - a
      genuinely different graphic slot from the living building, and
      confirmed to have a *different*, smaller civ-area group than castle's
      own 62-civ `castle_areas` override), stages the 15 frames in a temp
      dir (same auto-cleanup convention as `build_and_install`), converts,
      and installs.
    - Confirmed via decode: nonzero-pixel count strictly decreases stage to
      stage (60107 -> 57399 -> 52347 -> 46046 -> 27171) and the content's own
      top edge (`y0` in the decoded coords) moves down each stage - i.e. it's
      really collapsing from the top down, not just losing material
      uniformly. Each stage's 3 repeated frames are byte-identical, as
      intended.
    - Simplification carried over from `build_and_install`: only `_x1`
      matters (buildings never use `_x2` in a real install), and every
      frame reuses stage 0's footprint-diamond mask rather than
      recalculating it per stage (the diamond's own position doesn't move
      as the building collapses - only exactly which background pixels
      count as "exterior" could drift a little frame to frame, not
      revisited yet).
    - Scoped to `castle` only so far, per explicit user request ("Proba lo
      que haces solo con el castillo") - not yet wired into
      `build_sld.py --all`, not yet run for any other destructible building.
    - Tuned after the user saw it in-game ("es muy bella"): bumped from 5 to
      `num_stages=10` for a more gradual collapse, and the final stage
      (settled ruins) now repeats 3x longer than every other stage
      (`stage_repeat * 3`) so the end result reads as more deliberate
      instead of cutting away immediately - 36 total frames for `castle`
      (9 stages x 3 + 1 final stage x 9). A separate report that the
      destruction looks darker than the living building was left alone per
      explicit user instruction ("la segunda parte no lo toques").

18. **#17's destruction target resolution (rename.py's separate "<name>d"
    entry) was itself the bug user-reported as "no se ve la destruccion":**
    a real, confirmed civ-coverage gap - castle's living targets get
    config's 62-civ "castle_areas" override, but rename.py's raw "castled"
    entry only ever named the 22-civ "more_areas", so 40 civs (including
    whichever southeast-Asian-architecture one the user's screenshot showed)
    got our custom living castle but fell back to *vanilla* destruction art
    mid-battle. A first fix patched just the area_prefix mismatch - reverted
    per broader, explicit user instruction: "Lo que hiciste no tiene que
    usar castled. Tiene que usar la mismo info que castle... los
    <building>d no van mas. Una destruccion usa lo mismo que el padre." Now
    `building_config.destruction_target_names(config)` derives destruction
    targets straight from the *living* building's own `targets`/
    `area_prefix` - no separate rename.py lookup at all - by inserting
    "_destruction" before each target's trailing "_x1" (confirmed as the
    universal real-game naming convention against every "<name>d" entry
    rename.py did have: barracks2/3, blacksmith2/3, market2/3 all matched
    exactly). This also fixes buildings that had no "<name>d" entry in
    rename.py at all (stable2/3, towncenter2/3) despite definitely having
    real destruction art in-game - they now get one derived the same way,
    with no dependence on rename.py's own (incomplete) coverage of that key
    pattern. Re-confirmed on `castle`: 124 files installed, all 62
    `castle_areas` civs covered including the one that was missing before.

19. **Foundation/under-construction graphic - implemented and confirmed on
    `castle`.** Investigated the real game files first rather than guessing:
    grep'd every "33"/"66"-named vanilla graphic and found the pattern is
    **exclusively used for resource depletion states** (`berry33`/`gold66`/
    etc in rename.py) - there is not one single building in the entire
    vanilla install with a "_33_"/"_66_" graphic name (checked `castle` and
    `barracks` specifically). Decoding the real
    `b_misc_foundation_castle_x1.sld` directly explained why: it's a real
    **3-frame** SLD, with strictly growing content and a rising top edge
    across its 3 frames (31401 -> 37161 -> 57397 nonzero px, `y0` 164 -> 140
    -> 72) - 33%/66%-built are frames *within* the one foundation graphic,
    not separate target names.
    - `voxel_render.construction_stage_voxels(voxels, fraction)`: keeps only
      the bottom `fraction` of the building by height - a straight cutoff,
      not randomized (unlike destruction's rubble) per the user's own spec
      ("debe mostrar el 33% y el 66% del edificio").
    - `build_psd.build_foundation_frames()`: frame 0 uses the *real*,
      separate, hand-modeled "<name>0.gox" (confirmed: a flat, z=0-only
      footprint outline, with `box_bounds` coinciding almost exactly with
      the living model's) per explicit user instruction (foundations use
      the real "0" file, unlike 33/66 which must be generated); frames 1/2
      are the living `.gox`'s own voxels cut at 33%/66% height. All 3 frames
      share the *living* model's own `box_crop_px` so the foundation doesn't
      rescale relative to the building it becomes.
    - `build_sld.build_and_install_foundation()`: unlike destruction,
      foundation *does* still use rename.py's "<name>f" entry for target
      resolution (e.g. `castlef` -> `b_misc_foundation_castle_x1`) - no civ-
      coverage gap risk here, since real foundation graphics are one shared,
      non-per-civ slot to begin with (confirmed against the real file).
    - Confirmed on `castle`: 3 frames, content growing frame to frame
      (29734 -> 44759 -> 57847 px), installed under the single shared target
      name with no civ expansion, matching the real asset's own shape.
    - Scoped to `castle` only so far ("probemos con el castillo primero") -
      not yet run for any other building, not yet wired into `--all`.

20. **Monastery foundation "corrida" (shifted) - root cause found and fixed:
    `voxel_render.render()`'s `cam_pos` was centroid-dependent.** User report
    ("se ve corrida claramente") ruled out my first hypothesis (excessive
    blue player-color voxels in `monastery0.gox` causing a solid-red repaint
    - user confirmed that's normal across *all* foundations, not a bug).
    Real cause: `cam_pos = centroid - view_dir*100.0` used each model's own
    voxel centroid. Since the orthographic projection is
    `u,v = dot(world_pt - cam_pos, right/up)` with `right`/`up` fixed unit
    vectors, a model-dependent `centroid` shifts every projected `u,v` by a
    model-dependent constant - invisible rendering one model alone, but
    breaks any shared `crop_box`/anchor across *different* models (a living
    building vs. its independently-modeled `<name>0.gox` foundation, which
    have different centroids). Fixed with a fixed world-origin reference
    instead: `cam_pos = -view_dir*100.0` (valid since every `.gox` file in
    this project shares one consistent world origin/grid). Verified via an
    overlay of frame0 vs frame1 before/after. This affects *any*
    multi-model sequence (destruction and foundation both build several
    `GoxModel`s sharing one `crop_box`), not just monastery, so both batches
    were rebuilt afterward.

21. **`is_destructible()` fixed - was gating on rename.py's incomplete
    "<name>d" keys even after #18 removed that dependency for the actual
    target-name derivation.** Flagged as a "not yet done" risk in #19; turned
    out to be real and large. Checked the real, shipped game's own graphics
    folder (`DIRS.AOE2DE_GRAPHICS`) directly as the authoritative source -
    for each building, ran `building_config.destruction_target_names()` and
    checked whether any resulting name has a matching `.sld` actually
    installed by the base game. Result: **45 buildings truly have real
    destruction art, vs. only 15 rename.py's "<name>d" keys covered** -
    missing entirely: `monastery`, `outpost`, `university`, `tower1-4`,
    `house1-3`, `stable2/3`, `towncenter1-4`, `krepost`, `caravanserai`,
    `folwark1-3`, `siege`, `mining`, `lumber`, `settlement1-3`,
    `stonecorner`, `fortifiedcorner`, `dock4`. `gen_building_config.py`'s
    `is_destructible(targets, area_prefix)` now takes the resolved
    targets/prefix directly (post `AREA_PREFIX_OVERRIDES`) instead of a bare
    `key`, and checks real files instead of rename.py. `config/buildings.json`
    regenerated (54 buildings, safety guard did not trigger) and
    `build_many_destruction()` re-run for the full new 45-building set.

22. **Severe near-incident: `config/buildings.json` almost got clobbered to
    2 entries.** `gen_building_config.py` used a bare relative
    `glob.glob("files-gox/*.gox")` - running it from `Scripts/` (the wrong
    CWD) matched zero files, and `main()` would silently write a near-empty
    config (only the two no-`.gox`-needed `EMPTY_KEYS`), destroying
    `tile_size`/`frame_count`/`camera_angle_*` for 52 buildings.
    `config/buildings.json` is untracked by git (confirmed via
    `git status --short` showing `??`) - no history to recover from. Fixed
    two ways: (1) root cause - glob now uses `f"{DIRS.MAIN}/{DIRS.GOX}/*.gox"`
    (absolute, CWD-independent); (2) defense in depth - `main()` now refuses
    to write if the new config has less than half the entries of the
    existing one, unless `--force` is passed. Recovered the one time this
    did happen by re-deriving every building's `tile_size` straight from its
    own `.gox` voxel coordinate span
    (`math.floor(max(xspan,yspan)/8 + 0.5)` - note `math.floor(x+0.5)` not
    Python's `round()`, since `round()`'s banker's-rounding silently picked
    the wrong `tile_size` for `monastery`'s exact-2.5-tile span), validated
    100% against 7 known-correct buildings, then manually re-applying the
    handful of remembered special-case overrides
    (`house1/2/3.frame_count=8`, `stable2/3.frame_count=100`,
    `palisade2_open.camera_angle_y=-45`). Side effect once the CWD bug was
    fixed: `mill1`/`mill2` became pickable for the first time (their `.gox`
    files already existed but had *always* been silently excluded by this
    exact bug, not just during the incident) - the mill family's living,
    destruction and foundation graphics were built and installed as part of
    closing this out.

23. **Wall/corner pieces (stonewall, stonecorner, fortifiedwall,
    fortifiedcorner, palisade...) rendered invisible in-game for some
    civs - traced to `"areas"`/`"more_areas"` missing 3 real architecture
    groups entirely: `greek`, `thracian`, `puru`.** User screenshot showed a
    stone wall corner rendering as empty space next to visibly-fine wall
    segments. Checked the real game's own files directly (same method as
    #12/persian/nors): `archery_range_age2`, `market_age2`, `university_age3`
    all have **17** real civ-prefix variants, not our `"areas"` group's 14 -
    missing `greek` (Athenians/Spartans, `hud_style: "CivGreek"` in
    `civilizations.json`), `thracian` (Thracians, `"CivThracian"`), and
    `puru` (Puru, `"CivPuru"`) - all 3 "antiquity"-era civs added since the
    last time this list was checked. Confirmed **not** adding a separate
    `macedonian` entry: Macedonians (`"CivMacedonian"`) have zero regular-
    building files of their own in the real game (`b_macedonian_archery*`
    etc. don't exist) - only a unique castle, already covered by
    `castle_areas`'s existing `macedonian` entry - so for regular buildings
    they silently fall back to reusing `greek`, same pattern as Danes/
    Saxons/Varangians reusing other prefixes for regular buildings while
    keeping their own castle. Added `greek`/`thracian`/`puru` to both
    `"areas"` and `"more_areas"` in `config/areas.json`; full `--all`/
    destruction/foundation rebuild re-run afterward so every building
    picks up the 3 new civs, not just walls.

24. **`convert_via_wine`'s concurrency race, root-caused and fixed (not just
    worked around) - `xvfb-run -a`'s free-display-number scan has a real
    check-then-act race under real parallelism.** Previously only tolerated
    by re-running sequentially (see #14's "not yet done"). Forced to actually
    fix it after `castlef` failed with a bare `[Errno 2] No such file` deep
    inside a 16-way parallel `--all-foundation` batch (never in isolation).
    `xvfb-run -a` auto-picks a display number by scanning for one not
    already in use - two concurrent calls can both see the same number as
    free before either has actually bound it, so they collide on one X
    display and one of the two wine/DESpriteTool runs silently fails or
    writes garbage. Fixed by handing out a unique display number ourselves
    (a thread-safe `itertools.count` + lock in `build_sld.py`, no scanning,
    no race) and passing it via `xvfb-run -n <N>` instead of `-a`. Also added,
    as defense in depth: (1) `convert_via_wine` retries its whole
    stage/convert/verify cycle up to 3x on failure instead of raising
    immediately; (2) `install()`'s `shutil.copy` retries up to 3x on a
    transient `FileNotFoundError` (a source `.sld` that `os.listdir()` just
    confirmed exists but isn't fully readable yet - a filesystem/Wine sync
    gap, not the same bug as the display race, but the same class of
    "trust-but-verify" fix).

25. **House's destruction animation looked wrong because its destruction SLD's
    frame count didn't match its living SLD's - fixed, but *not* by blindly
    multiplying every multi-frame building's destruction the same way.**
    User noticed: "como son 4 orientaciones, me parece que son 4
    destrucciones distintas" (referring to house's several look-variants).
    Decoded the real, shipped files directly: `b_medi_house_age2_x1.sld` has
    exactly 3 frames (real, distinct shape variants - one picked per
    individually-placed house) and its `_destruction_x1.sld` has exactly
    300 = 3 x 100 frames, not one flat sequence - reproduced on
    `b_dark_house_age1`. The engine almost certainly picks a house's shape
    variant once and indexes its destruction frames the same way, so a
    mismatched destruction frame count picks the wrong (or out-of-range)
    collapse frames for any variant but the first.
    First attempt multiplied *every* building with `frame_count > 1` by that
    same count - wrong: decoding mill/stable's real files too showed their
    living `frame_count` (90-181) is a continuous idle ANIMATION LOOP (e.g.
    mill's rotating sails), not shape variants - their real destruction
    frame count (100) is *not* a multiple of the living one at all
    (confirmed on mill age1/2 and stable age2/3), so multiplying would have
    been actively wrong for them, producing a nonsensical multi-thousand-
    frame destruction SLD. Settled on an explicit config flag,
    `frame_count_is_variants` (only `true` for `house1`/`house2`/`house3`),
    rather than inferring behavior from `frame_count`'s value alone -
    `gen_building_config.py` preserves it across regeneration the same way
    it already does for `frame_count`/`camera_angle_x/y`.
    `build_and_install_destruction` now repeats its whole collapse sequence
    `variant_count` times (from that flag, default 1) instead of always
    once; house1/2/3's destruction rebuilt and reinstalled with the fix,
    mill/stable's untouched (already correct, flat sequence).

26. **New per-building `"margin"` config field - shrinks a building a bit
    within its own tile canvas, pulling it in from the footprint-diamond's
    edge, without resizing the diamond.** User request: add visible breathing
    room between a building's base and the diamond outline for most
    buildings, but NOT for ones that need to sit flush against it: town
    center, castle, walls/corners/gates (need to line up edge-to-edge with
    the next segment), towers, and outpost. Implemented by adding `margin` to
    `voxel_render.tile_params()`'s existing `mg_x`/`mg_y` pixel margins (which
    already controlled the building's own placement within its tile canvas)
    - threaded through `compute_placement`/`place_on_tile_canvas` and from
    there into `build_psd.build_layers`/`build_destruction_frames`/
    `build_foundation_frames`, and finally read from
    `config["margin"]` in all three `build_sld.py` entry points. Critically,
    the footprint-diamond itself (drawn in `build_layers`) and `anchor_point`
    call `tile_params()` *without* passing margin, so only the building's own
    content shrinks - the diamond's size and position are margin-independent.
    `gen_building_config.py` writes `margin` for every building now
    (`DEFAULT_MARGIN = 10`, `NO_MARGIN_KEYS` = the flush-with-diamond set
    above with `margin = 0`), preserved across regeneration like
    `frame_count`/`camera_angle_x/y`. Full `--all`/destruction/foundation
    rebuild re-run afterward so every building picks up its own margin.

27. **Footprint-diamond only ever covered its front wedge, not the whole
    shape - fixed by dropping the exterior-only restriction entirely, now
    that the effect lives purely in the shadow channel.** Flagged since #11
    as a cosmetic "not solved yet" (`footprint_fill = diamond & exterior_bg`,
    where `exterior_bg` excluded anything not flood-fill-reachable from
    outside the building's silhouette) - confirmed the actual extent of the
    problem via the new `--debug` PNG dump (`errores.md` item 7, "todos,
    fondo de diamante no esta entero negro"; user pointed at the dumped
    `..._FootprintGuide.png` directly - it showed only a thin V-shaped wedge
    at the diamond's front, not the diamond at all). The `exterior_bg`
    restriction was needed back when the diamond was painted as opaque
    *Diffuse* content (a stray interior alpha==0 hole, e.g. market3's
    colonnade gaps, would show as a disconnected visible patch) - but the
    diamond has painted only the *shadow* channel for a while now, a
    separate layer the building's own opaque Diffuse pixels already sit on
    top of and hide wherever they exist. So the restriction no longer served
    any purpose and was actively wrong: `footprint_fill = diamond` (the
    *whole* diamond polygon) directly, no flood-fill/exterior check at all.
    Verified via the debug PNG (mill3): now a complete, solid diamond.
    Simpler code too - removed the `ImageDraw.floodfill`/`.copy()` PIL-quirk
    workaround entirely. Full rebuild re-run afterward.
    **Reverted in #28** - wrong in-game despite the debug PNG looking right.

28. **#27 reverted; real bug was destruction/foundation reusing frame 0's
    shadow mask for every SLD frame instead of recomputing it per frame.**
    In-game, #27's "whole diamond" change produced a large, disconnected
    solid-shadow diamond floating away from the building, on ground that had
    nothing to do with it - not the "complete diamond under the building"
    #27 intended. Root cause was actually a separate, longstanding bug #27
    incidentally made much more visible: `build_and_install_destruction`/
    `build_and_install_foundation` each compute a `footprint_guide` mask
    *per frame* (via `build_psd.write_psd`, since each frame's own building
    content differs as it collapses/rises) but only ever kept frame 0's/
    stage 0's mask, then called `patch_shadow.patch_sld_shadow` with that
    ONE mask reused for every frame in the whole SLD. With #27's
    unconditional whole-diamond mask, stage 0 (an almost-intact building)
    computed a mask that's nearly the *full* diamond every time regardless
    of which real stage was being patched - explaining the disconnected
    floating patch. Fixed at the actual source: `patch_shadow.
    patch_sld_shadow` now accepts a list of masks (one per SLD frame,
    reusing the last if the list is shorter) instead of only one mask reused
    for all frames; both `build_and_install_destruction` (mapping each
    stage's own mask across its repeated SLD frames, including the
    variant-padding frames) and `build_and_install_foundation` (one mask per
    of its 3 frames) now pass a real per-frame list. #27's diamond change
    itself was reverted back to the exterior-only mask (`diamond &
    exterior_bg`) since the per-frame fix alone was the real, sufficient fix
    - re-confirmed working on `castle` (both its 65-civ destruction and its
    foundation) before a full rebuild.

29. **Two more real bugs found from the errores.md re-test round: semi-
    transparent Diffuse pixels not counted as footprint, and the Dark Age
    dock/barracks never being built at all.**
    - The exterior-background mask (`diamond & exterior_bg`, see #27/#28)
      only counted pixels with `alpha == 0` as background - a *semi*-
      transparent pixel (any partial alpha) fell through as neither "the
      building" nor "background", showing through as a visibly not-darkened
      patch inside an otherwise-dark diamond ("algunos pixeles no son
      oscuros... si tiene algo de transparencia el png, y esta dentro del
      diamante, que lo pise"). Changed the threshold from `alpha == 0` to
      `alpha < 255` - anything not fully opaque is fair game for the
      footprint mask now.
    - "el dock no se ve" traced to a real, previously-documented-but-never-
      fixed gap: rename.py's `dock1` key (the Dark Age dock, visible from
      game start) has no `dock1.gox` - the real file is `dock.gox`. Same
      issue for `barracks` (Dark Age barracks) -> real file `barracks1.gox`.
      `gen_building_config.py`'s own module docstring already named this
      exact drift as a known gap, but nothing had ever actually resolved it
      - both keys were silently skipped by every regeneration since, meaning
      neither tier had *ever* been built by this pipeline. Fixed with a
      symlink in `files-gox/` (`dock1.gox -> dock.gox`,
      `barracks.gox -> barracks1.gox`) rather than a code-level name-mapping
      table, since several different places construct a building's own .gox
      path from its config key - a symlink fixes all of them at once instead
      of requiring every call site to learn about the exception. `tile_size`
      for both hand-derived from their own voxel content span (3, matching
      the rest of their families) since neither has a reference PNG to sniff
      it from. Both built and installed for the first time ever.

30. **Gate orientations ("_n_"/rotated-straight) generated by rotating the
    camera on the SAME .gox, not by modeling a separate file per direction -
    per explicit user instruction.** User: "los gates es el mismo archivo,
    pero tenes que girar la camara. no hace falta que haga uno para cada
    orientacion, solo hace falta que haga 1 en diagonal y uno recto. el resto
    debe ser generado x vos girando la camara con un flag en config que
    indique que es gate." Confirmed against real files: a gate's "_n_"
    variant is the exact same physical structure as its "_e_" one, just
    facing the other wall direction - not distinct art. Implemented as:
    - `build_psd.build_layers()` gained a `gox_name` parameter (default
      `building_name`) - loads a *different* .gox than the one named after
      the config key. Threaded through from `build_and_install()`'s
      `config.get("gox") or building_name` (previously `config["gox"]` was
      pure metadata, never actually used to pick which file to load - every
      real load hardcoded `building_name` itself, per #29's dock1/barracks
      finding).
    - `gen_building_config.py`'s new `GATE_ROTATIONS` dict (`{new_key:
      (source_key, angle_y_delta)}`) generates `palisade22_open/closed` and
      `stone22_open/closed` by copying their straight sibling's config,
      pointing `"gox"` at the sibling's own file, resolving `"targets"` from
      rename.py's real entry for the *new* key (e.g.
      `b_dark_gate_palisade_n_open_x1`), and rotating `camera_angle_y` by
      `angle_y_delta` (`standard_camera`'s `azimuth = 90 - angle_y`, so this
      is a 90-degree azimuth swing) from the source's own tuned angle.
    - `angle_y_delta = -90` is a first attempt, NOT yet visually confirmed -
      needs the same in-game check/iteration every other camera angle in
      this project got (unlike most of those, this one couldn't be dialed in
      by eye before committing code, since there was nothing rendering at
      all to compare against). Adjust `GATE_ROTATIONS`'s deltas if the
      rotated gate faces the wrong way in-game.
    - The diagonal orientations (`_ne_`/`_se_`) still need one new diagonal
      .gox from the user (not yet provided) before the same rotation
      mechanism can generate both from it the same way.
    - All 4 built and installed successfully (`b_dark_gate_palisade_n_open/
      closed_x1`, `b_medi_gate_stone_n_open/closed_x1` +
      `gate_fortified_n_open/closed` for all 17 civs) - not yet confirmed
      correct in-game.

31. **Palisade's own wall corner ("estan invisibles las paredes de las
    esquinas... es pq no estas poniendo el nombre que va") - re-verified the
    target name is actually correct (`b_dark_gate_palisade_corner_x1`,
    confirmed byte-for-byte against the real game and against
    `stonecorner`/`fortifiedcorner`, which install fine under the equivalent
    `gate_stone_corner`/`gate_fortified_corner` names) - the real cause is
    still #4-6's original finding: no .gox at all models an actual L-shaped
    palisade corner joint (unlike stonecorner/fortifiedcorner, which are
    real, distinct, square models). Rather than leave it rendering nothing
    (a bare health bar over empty ground) until a real corner is modeled,
    added it to `GATE_ROTATIONS` (#30) as a *stand-in*: reuses the plain
    straight palisade wall's own model (`"palisade"`, angle_y_delta=0, no
    rotation) under the corner's real target name. Not a correct corner
    joint shape, but never invisible - strictly better until real geometry
    exists.
    - Found and fixed a second real bug in the same change: `GATE_ROTATIONS`
      entries were spreading `**source`'s config wholesale, including its
      `destructible` flag - correct for the two gate open/closed rotations
      (their source gates aren't destructible either), but silently wrong
      for the corner (`"palisade"`, the plain wall, isn't destructible, but
      `gate_palisade_corner` really is in the real game). Now recomputes
      `destructible` from the *new* key's own real target name via
      `is_destructible()`, not inherited from source.
    - Found and fixed a third: `gox_name` (the "load a different .gox than
      my own name" override #30 added) only ever reached the *living*
      build path (`build_and_install`/`build_layers`) - destruction
      (`build_and_install_destruction`/`build_psd.build_destruction_frames`)
      still hardcoded loading `f"{building_name}.gox"` directly, so
      `palisade_gate_cornerd` failed outright (`palisade_gate_corner.gox`
      doesn't exist - only `palisade.gox`, its stand-in source, does).
      Threaded `gox_name` through the destruction path too.

32. **`stonecorner`/`fortifiedcorner` consolidated to derive from their own
    wall's model instead of maintaining a separate, nearly-duplicate .gox
    file.** User, after much back-and-forth trying to find a "wrong name"
    bug: "STONEWALL TIENE QUE CREAR 2 ARCHIVOS DE PARED, EL WALL Y EL WALL
    CORNER" - one source model should produce both real installed target
    names, not two independently-maintained .gox files that happen to need
    to stay in sync. Verified this was *already* true by coincidence -
    byte-diffed `stonewall.gox` vs `stonecorner.gox` and `fortifiedwall.gox`
    vs `fortifiedcorner.gox`: both pairs were already near-identical (only
    the declared IMG box differed). Made the relationship explicit instead
    of relying on manually keeping two files in sync: added `"stonecorner":
    ("stonewall", 0)` and `"fortifiedcorner": ("fortifiedwall", 0)` to
    `GATE_ROTATIONS` (#30's mechanism, despite the name applying generally to
    "derive this target from that other config key's own model") - both now
    read `stonewall.gox`/`fortifiedwall.gox` directly, no separate corner
    .gox needed or read anymore.
    - Explored and explicitly rejected copying the equivalent, already-
      finished .smx assets from the real, published production mod
      (`238283_Power - Checker buildings`, which does have complete,
      working art for every corner/diagonal/rotated gate orientation, for
      its original 12 "areas" civs) as a shortcut - user: "NO HAY QUE
      COPIAR ESOS ARCHIVOS YA HECHOS." Everything in this pipeline comes
      from `.gox` and this project's own generation, not by re-importing
      finished legacy assets, even working ones.
    - The diagonal orientations (`_ne_`/`_se_`) and the true, correct corner
      *joint* shape (still just a reused straight-wall stand-in, not real
      corner geometry) remain open - user has not yet decided how to
      resolve those (declined "leave unbuilt" and "I'll model them soon" as
      the only two options offered; asked to reconsider next).
    - **Reverted right after** - this whole consolidation was a
      misunderstanding of the original instruction. User, immediately after
      seeing the resulting config: "VES QUE STONE WALL CORNER ES ALGO A
      PARTE O NO?" - stone/fortified corners are their OWN separate,
      distinct asset, not derived from their wall at all (unlike palisade's
      corner, which genuinely has no separate .gox and still uses the
      stand-in). Removed `"stonecorner"`/`"fortifiedcorner"` from
      `GATE_ROTATIONS` entirely - both go back through the ordinary main
      loop, reading their own real `stonecorner.gox`/`fortifiedcorner.gox`
      files, exactly as before item #32 started. Net effect of #32: zero
      config change for stone/fortified corners (confirmed: `"gox"` field
      back to `"stonecorner"`/`"fortifiedcorner"` respectively) - only the
      palisade corner stand-in (added in #31) survives from this detour.

33. **The real fix for #32, after finally understanding the instruction:
    `stonewall`/`fortifiedwall` merged into ONE config entry each that
    installs under BOTH real target names, instead of two separate config
    entries.** User, after #32's revert still wasn't right either: "ES UN
    GOX CON TARGETS Y LOS TENES SEPARADOS" - one `.gox`, a `"targets"` list
    with more than one real name (the same pattern `market3`/`university`
    already use for multiple age tiers from one model) - NOT two config
    entries pointing at two nearly-duplicate files, and NOT one entry
    deriving from another's `"gox"` field either (#32's approach). Concretely:
    `stonewall`'s `"targets"` is now `["wall_stone_x1",
    "gate_stone_corner_x1"]` (was two entries: `stonewall` with one target,
    `stonecorner` with the other) - one render, installed under both real
    names, `destructible` recomputed True (the corner name's own destruction
    art makes it True even though the plain wall's own destruction naming
    differs - see below). Same for `fortifiedwall`. The now-redundant
    `stonecorner.gox`/`fortifiedcorner.gox` files are unused (not deleted -
    left alone) and the `stonecorner`/`fortifiedcorner` config keys removed
    entirely.
    - **Applied by hand-editing `config/buildings.json` directly, NOT by
      running `gen_building_config.py`** - explicit, repeated, absolute user
      instruction by this point: "RENAME.py no va mas" (not just "don't read
      it at runtime", which #29-#30 already achieved for build_sld.py - the
      *generator* itself must stop being the mechanism for this kind of
      edit too, since it still iterates rename.py's keys independently and
      would silently regenerate `stonecorner` as its own entry again,
      undoing the merge). `gen_building_config.py` itself was NOT modified
      for this - it still contains the old #32-reverted `GATE_ROTATIONS`
      logic untouched; it just wasn't run. Any *future* regeneration of
      `config/buildings.json` via that script would currently undo this
      merge - worth fixing gen_building_config.py itself to stop being
      rename.py-driven at all, or to preserve hand-merged targets, next time
      it needs to run for an unrelated reason.
    - One known imperfection accepted, not chased further: destruction names
      are derived uniformly per-target (`t + "_destruction"`) - the real
      game's plain wall destruction actually uses a different, percentage-
      based naming (`wall_stone_destr_25/50/75`, not `wall_stone_destruction`
      - see #19's own file dump), so merging produces one extra, harmless,
      never-looked-up `wall_stone_destruction_x1` file alongside the real,
      correct `gate_stone_corner_destruction_x1`.

34. **`frame_count` as an "avoid invisible" knob, confirmed on more
    buildings - and a real, fully-solved wall-foundation frame-structure bug
    chased across several wrong turns before landing on the right answer.**
    - Dock (`dock1-4`) and `university` were completely invisible in-game
      despite valid, correctly-named, non-degenerate installed files
      (confirmed via debug-PNG render and raw `.sld` header decode - nothing
      wrong with the content itself). Per the user's own direct instruction
      ("tenes mas de 1 frame count? Si tenes menos mandale 100") rather than
      more file archaeology: bumped `frame_count` to 100 for both. Fixed
      immediately - matches the established pattern (stable/mill/house were
      already known to need this) now confirmed on two more buildings,
      reinforcing that a too-low `frame_count` can make an otherwise-correct
      asset render as nothing at all, for reasons still not fully understood
      mechanically but empirically reliable to fix the same way.
    - stonewall/fortifiedwall's own foundation (`stonewallf`/
      `fortifiedwallf`, now a 20-frame sequence per #34's `include_full_stage`
      - see below) went through 3 wrong structures before the real one,
      each ruled out by a specific in-game symptom the user reported:
      (a) pad extra "variants" with the LAST frame only (destruction's own
      fix, copied over) - wrong: some wall tiles under construction looked
      permanently stuck near-finished while others started from a thin
      outline, inconsistent side by side ("la stonewall tiene 2 tipos de
      foundations"); (b) repeat the whole 3-stage sequence per variant
      (every variant plays 0%-30%-55% for real) - wrong: different tiles'
      construction visibly jumped backward mid-sequence ("si arranca en 30,
      el que seria 30 es 55" - confirmed this is because the engine indexes
      construction by a continuous build-progress fraction, not a per-
      instance fixed variant pick the way a living building's own art
      might be, so concatenating several short 0%-55% cycles back to back
      makes progress-based indexing land mid-cycle and then cross into the
      next cycle's own low stage); (c) stretch each of the 3 real stages in
      place instead (monotonic, no cycling) - still wrong, and the user's
      own "faltan frames" ("todos esos son foundations de distintos
      tamaños") turned out to be the real, deeper issue underneath both
      (b) and (c): there are only 3 real stages being cut into a 15-frame
      total (3 x the living wall's own 5-frame `frame_count`), but decoding
      `b_medi_wall_stone_constr_x1.smx` directly showed the real asset has
      **20** frames, not 15 - a 4th stage was missing the whole time. Added
      it: `build_foundation_frames` gained `include_full_stage` (appends a
      4th stage at 100%, the living building unmodified) - `False` by
      default (preserves the confirmed-correct 3-frame structure every
      other, "b_misc_foundation_X"-style building already uses, e.g. castle/
      market - verified via `b_misc_foundation_castle_x1.sld` itself back in
      #19), `True` only for buildings with `frame_count_is_variants` set
      (currently just stonewall/fortifiedwall - reusing that existing flag
      as the signal rather than adding a third near-identical config field,
      since every building confirmed to need one so far needs the other
      too). With 4 real stages x5 = 20 total frames, cycling
      (0%-30%-55%-100%-0%-30%-55%-100%-...) rather than stretching, every
      building instance's own fixed-progress-fraction index now always
      lands on one of exactly 4 real, consistently-sized stages - confirmed
      resolved in-game ("impecable resuelto").
    - Also fixed in the same investigation: `write_blank_psd`'s "empty"
      graphic slots (`EMPTY_KEYS`, e.g. palisade's flag decal, snow decals)
      left the shadow channel completely untouched, relying on there being
      nothing to patch - but DESpriteTool auto-generates a *default* shadow
      from canvas size alone when nothing overrides it (a long-confirmed
      quirk - see #14/#27), so a blank Diffuse still got a visible
      translucent rectangle in-game under some flags ("algunos tienen las
      banderas con un recuadro transparente"). Fixed by explicitly patching
      an all-zero mask for `empty` buildings instead of skipping the patch
      step - suppresses it for real instead of leaving it to chance.

35. **New: static partial-damage snapshots (`_destr_25/50/75`) - a separate,
    non-animated real graphic slot from the full collapse animation
    (`_destruction`).** User request, after confirming the exact real names
    directly (`wall_stone_destr_25/50/75_x1`, `wall_fortified_destr_25/50/
    75_x1`, 17 civs each, alongside the already-covered
    `wall_stone_destruction_x1`/`wall_fortified_destruction_x1`). Added
    `building_config.damage_target_names(config, percent)` (same
    `t[:-3]+f"_destr_{percent}_x1"` derivation pattern as
    `destruction_target_names`) and `build_sld.
    build_and_install_damage_states(building_name)`. Implementation reuses
    `build_psd.build_destruction_frames`'s own top-down band-collapse logic
    directly instead of new voxel code: calling it with `num_frames=4`
    produces 4 progressively-more-destroyed frames with the same already-
    validated spec - frames 1/2/3 (of 4) stand in for the 25%/50%/75%
    snapshots (frame 4, ~100% band-collapsed, is skipped - that's what the
    real "_destruction" animation's own last frame already covers). Each
    percent gets installed as its own single-frame static SLD, not an
    animated sequence. Built and installed for both `stonewall` and
    `fortifiedwall` (both real targets each, matching #33's wall+corner
    merge). Not yet wired into the main `--all` CLI batch - standalone
    function only so far, called directly per building. A single-frame SLD
    rendered invisible in-game the same way dock/university/stonewallf had
    (frame_count=1 - see #34) - fixed by padding each percent to 6 identical
    duplicate frames (not 100; user explicitly: "100 para esto es mucho,
    deben ser 6" - a much smaller static icon than a full building, needing
    fewer padding frames empirically).

36. **Real bug: reused `frame_count_is_variants` (the living building's own
    flag) to also gate `build_and_install_foundation`'s 4-stage-vs-3-stage
    and stage-repeat-vs-not structure - wrong, these are two unrelated
    properties that only coincided for the first two buildings (stonewall/
    fortifiedwall) this was built for.** Surfaced the moment a THIRD
    building (`house1`) also got `frame_count_is_variants=True` (for its
    own, correct, unrelated reason - destruction needs to repeat per living
    shape variant, see #25) and its foundation silently ballooned to 24-32
    frames (3-4 stages x8 variants) when decoding the real, shipped
    `b_misc_foundation_house_x1.smx` directly shows exactly **3** frames,
    same confirmed-correct structure every non-wall-style foundation uses
    (castle, market, etc. - see #19). Fixed by moving both decisions onto a
    *new*, independent flag read from the **foundation's own** config entry
    (`f_config.get("wall_style")`), not the living building's: `"wall_style":
    true` added to `stonewallf`/`fortifiedwallf` only - `stage_repeat` and
    `include_full_stage` (#34) both now key off this instead of
    `frame_count_is_variants`. Re-verified: `housef` back to 3 frames,
    `stonewallf`/`fortifiedwallf` still correctly 20 (4 stages x5).

**Not yet done:**
- Wire `build_and_install_destruction`/`build_and_install_foundation` into
  the `--all` batch path (right now both are standalone functions, only
  called manually for `castle`) once the user confirms both look right
  in-game.
- Polish the footprint-diamond line's thickness/full-outline alignment
  with the tile grid (see #11's "still open" note) - real translucency,
  color and rough size/shape are confirmed working; this is cosmetic.
- Re-run `build_sld.py --all` and do a full in-game visual pass with #15's
  floodfill fix and #16's `.gox` box fix both applied - only spot-checked
  (`market3`, `castle`, and the 9 just-fixed tile_size=1 buildings) so far,
  not the whole 52-building set.
- Full in-game visual review of the unified pipeline (#14) across the whole
  52-building set, not just the handful (`castle`, `market3`, `outpost`,
  `blacksmith2`) spot-checked so far - the voxel-rendered Diffuse's flatter
  shading and the geometric diamond haven't been seen on most buildings yet.
- Animated buildings (multiple `_0000`/`_0001`... frames) - only tested
  with single-frame statics so far. Per user: only the destruction state
  needs animation (5 frames, progressively removing random voxel blocks
  from the base `.gox` per frame - not the existing hand-authored
  `*_des1..6.gox` variants). Groundwork laid: `voxel_render.py` gained a
  real "diffuse" pass rendered directly from voxel colors (needed because
  the static hand-rendered Diffuse PNG can't reflect disappearing blocks),
  plus `compute_placement`/`apply_placement` helpers so a frame sequence
  can share one fixed crop/scale instead of each frame rescaling
  independently as content shrinks. Still needed: the actual random-removal
  frame generator and wiring multi-frame PSDs through `build_sld.py`.
- Wiring into `DIRS.py`/`rename.py` for real mod distribution beyond the
  test mod (Milestone 6) - i.e. installing into the actual
  `Power - Checker buildings` mod once visually confirmed correct.
- Full in-game visual confirmation with the canvas-size fix applied (the
  invisible-castle report predates this fix; awaiting a fresh test).

## Original context (superseded in part by Status above)

The mod pipeline currently ends at `.smx`, produced by manually loading processed
PNGs into SLX Studio (Windows GUI), setting anchors, and exporting. `context.md`
hoped `DESpriteTool.exe` (the official converter shipped with AoE2DE, found at
`Tools_Builds/Sprites/` in the local Steam install and runnable under Wine, which
is already installed on this machine) could take PNGs directly to `.sld`. Reading
its actual `readme.txt`/`settings.json` shows that's not the case:

- `DESpriteTool.exe` converts **PSD → SLD**, not PNG → SLD.
- Each frame must be a layered PSD (`name_0000.psd`, `name_0001.psd`, ...) with 7
  specific layers: `Diffuse` (masked with a white-on-black bitmap), `Damage`
  (clipping mask of Diffuse), `AmbientOcclusion` (clipping mask of Diffuse),
  `Decal`, `Background`, `Height`, `Normals`.
- Separately, `DESpriteTool.exe` also has a scriptable **SLP → SMX** path
  (`convert_slp.bat`), but that only ever produces SMX/SMP, never SLD.

So real SLD requires building the missing PSD layers, not just repackaging
existing PNGs. The user confirmed they're fine extending the pipeline to make
this happen and wants to target SLD directly (not stop at the smaller SLP→SMX
automation).

Key enabling facts confirmed during research:
- **`.gox` is a fully documented, non-proprietary chunk format** (PNG-style:
  4-byte magic `GOX `, version, then `type/length/data/CRC` chunks). Relevant
  chunks: `IMG ` (bounding box), `BL16` (one 16³ voxel block, stored as a 64×64
  PNG), `LAYR` (block index + x/y/z placement list + transform + visibility),
  `MATE`/`CAMR`/`LIGH`. This means the full voxel grid (position + RGBA per
  voxel) can be reconstructed with a pure-Python parser — no Goxel binary or
  Wine needed for this step. Source: `goxel/src/formats/gox.c` in
  guillaumechereau/goxel.
- **`pytoshop`** (mdboom/pytoshop) can write multi-layer PSD/PSB files and
  explicitly supports both `LayerRecord.clipping` (base vs. clipped-to-layer-
  below, exactly what Damage/AmbientOcclusion need) and `LayerRecord.mask`
  (a `LayerMask` with its own image data, for Diffuse's white-on-black mask).
- **Player-color mechanism is palette-based, not a separate mask file.**
  `_palettes/playercolor_default.pal` is a standard JASC-PAL file: 8 ramps of
  16 shades each, ramp 0 = pure red (255,0,0) fading to black. `settings.json`
  has `PlayerColorPalette`/`PlayerColorThreshold`. This is the classic AoE
  convention: player-color regions are painted directly into the Diffuse layer
  using this reserved red ramp (shade = local brightness), and DESpriteTool
  detects/recolors those pixels at conversion time. There's no separate
  player-color mask layer in the PSD spec — it's baked into Diffuse pixels.
  Conveniently, `conv.py`'s existing `d.png` generation already computes
  *which* pixels are player-color (the green-channel heuristic at
  `Scripts/conv.py:136`) — that boolean selection can be reused, just repainted
  with ramp colors instead of flat green.
- Damage-decal placement logic already exists (`conv.py`'s `_dmg.png`
  generation) and maps naturally onto the PSD `Damage` layer (clipped to
  Diffuse) instead of a separate flat PNG.

## Scope decision

Per user's answer, when weighing "reuse the existing hand-rendered Diffuse
PNGs" vs. "re-render Diffuse from voxels too" the recommended, lower-risk
option is used: **keep the existing `files-png/` Diffuse renders as-is**, and
only derive the *new* layers (Height, Normals, AmbientOcclusion) from the
`.gox` voxel model. This avoids touching/regressing already-approved art. The
new voxel renders must be aligned (same camera + the same crop/resize
normalization `conv.py` already does) to match the existing Diffuse PNG
pixel-for-pixel — this alignment is a real risk and must be verified
empirically per building before scaling to all 236 files (see Milestone 2).

## Implementation milestones

### Milestone 1 — `.gox` parser (`Scripts/gox_reader.py`)
Pure-Python reader for the chunk format above. Output: for a given `.gox`
path, a dense (or sparse dict-based) 3D grid of `(x, y, z) -> RGBA`, built by
decoding each referenced `BL16` block's 64×64 PNG (via Pillow, already a repo
dependency) into its 16³ sub-voxels, then placing blocks per `LAYR` block
offsets, respecting layer visibility/transform. Verify against 2-3 known
files (e.g. `files-gox/castle.gox`) by dumping a voxel count / bounding box
and sanity-checking against the building's visual size.

Confirmed from Goxel's actual source (`gox.c`) during research:
- File header: `"GOX "` magic + int32 version (native/little-endian), then a
  loop of chunks: 4-byte type, int32 length, N bytes data, int32 CRC (CRC is
  always written as 0 and never validated, so it can be ignored on read).
- Dict sub-format used inside `IMG `/`LAYR`/`MATE`/`CAMR`/`LIGH` chunk data:
  loop of `(int32 key_size, key bytes, int32 value_size, value bytes)` until
  `key_size == 0`. Value sizes are always explicit in the file, so unknown/
  unneeded fields (`mat`, `id`, `base_id`, `material`, `mode`, ...) can be
  read generically as raw bytes and skipped without hardcoding struct sizes.
- `LAYR` block list, read straight from the C loop:
  ```
  4 bytes: nb_blocks (int32)
  for each block:
      4 bytes: index into the BL16 table (int32)
      4 bytes: x, 4 bytes: y, 4 bytes: z (int32 each)
      4 bytes: reserved (always 0)
  ```
  then the generic dict tail (name, mat, visible, etc.).
- Block lookup: `hash_find_at(blocks_table, index)` walks the block hash
  table by **position**, not by a stored id — meaning `index` is simply
  0-based, in the order `BL16` chunks appeared in the file. So: keep a plain
  Python list of decoded blocks appended in file order, and index into it
  directly with each `LAYR` block's `index` field.
- Confirmed the reader **does not apply `layer.mat` to block x/y/z** —
  `volume_blit(layer->volume, data->v, x, y, z, 16, 16, 16, NULL)` uses the
  raw block coordinates as-is. `mat` is stored on the layer but not used for
  placement in this code path. Unresolved: whether a non-identity `mat` ever
  shows up on real files in this repo and would need applying anyway for
  correct rendering — check by parsing a few real `.gox` files and printing
  their layers' `mat` values before assuming identity is always safe.
- **Not yet resolved** (this is where research was interrupted): the exact
  pixel-layout mapping between the `BL16` 64×64 PNG and the 16×16×16 voxel
  block. That encode/decode logic lives in `img_write_to_mem`/
  `img_read_from_mem`, declared in `file_format.h` but implemented in a
  different source file (not `gox.c`) — needs a targeted look at
  `file_format.c` (or wherever those functions are actually defined in the
  goxel repo) before Milestone 1 can be written correctly. Don't guess at
  the tiling scheme (e.g. "4×4 grid of 16×16 z-slices") without confirming
  it against source — getting it wrong would silently produce
  mirrored/rotated/scrambled voxel data.

### Milestone 2 — voxel → Height/Normals/AO renderer (`Scripts/voxel_render.py`)
Orthographic rasterizer matching the game's fixed dimetric projection (same
95×47-per-tile convention `conv.py` already assumes). For each visible voxel
face nearest the camera per output pixel:
- **Normals**: trivial and exact — voxel faces are axis-aligned, so this is a
  lookup (no shading computation needed), encoded as an RGB normal map.
- **Height**: depth/elevation of the visible surface, encoded per SMX/SLD
  convention.
- **AmbientOcclusion**: approximate via neighboring-voxel occlusion counts
  (cheap raycast or 26-neighbor check), not full path tracing.

Critical checkpoint before scaling: render one already-completed building
(e.g. a 1x1 with no animation frames), run it through the *same* crop/resize
math from `Scripts/conv.py:replace_semi_transparent_pixels`, and diff its
silhouette/proportions against the existing `files-png-processed` output for
that building. If camera params (FOV, angle, distance, output resolution)
don't line up, iterate on the renderer's camera constants until they do — do
this on 2-3 buildings across different tile sizes (1x1, 2x2, 4x4) before
trusting it for the full set.

### Milestone 3 — Decal/Background layers
Per readme, still required layers with no current source data. Start as flat
transparent/empty layers (many building sprites likely don't need painted
decals or a background plate) and confirm via a real DESpriteTool conversion
that empty layers are accepted, rather than assuming.

### Milestone 4 — player-color repaint + PSD assembly (`Scripts/build_psd.py`)
- Parse `_palettes/playercolor_default.pal` (JASC-PAL, already confirmed
  format: header, count, then `R G B` lines — ramp 0 rows 0-15 = reference
  ramp).
- Reuse the existing player-color pixel selection logic from
  `Scripts/conv.py` (the green-pixel heuristic) to get a boolean mask, then
  repaint those Diffuse pixels using ramp-0 shades chosen by local brightness,
  instead of flat green.
- Reuse the existing damage-decal placement logic from `conv.py` to build the
  `Damage` layer instead of the flat `_dmg.png`.
- Assemble the 7-layer PSD per frame with `pytoshop`: Diffuse (with white-on-
  black layer mask from the existing crop/alpha), Damage (clipping=True),
  AmbientOcclusion (clipping=True), Decal, Background, Height, Normals.
  Write as `name_0000.psd`, `name_0001.psd` for animated buildings (reuse the
  existing "duplicate PNG for animation frames" convention noted in
  `Scripts/readme`).

### Milestone 5 — DESpriteTool automation (`Scripts/build_sld.py`)
Script `wine DESpriteTool.exe <folder>` (matching `convert_psd.bat`'s
pattern) against a `buildings/` staging folder built by Milestone 4, using
the existing `settings.json`/`buildings/settings.json` overrides already
shipped with the tool (no changes needed there). Confirm real `.sld` output
appears and is a plausible size/structure.

### Milestone 6 — wire into existing pipeline
Extend `DIRS.py` with any new path constants needed (e.g. a
`files-psd`/`files-sld` staging dir under `MAIN`), and once SLD output is
verified in-game, decide whether `rename.py`'s distribution step needs an
`.sld`-aware variant alongside its current `.smx` copying.

## Verification

- Milestone 1: unit-check parsed voxel counts/bounding boxes against known
  `.gox` files by hand.
- Milestone 2: pixel/silhouette alignment diff against existing
  `files-png-processed` outputs, on buildings across multiple tile sizes.
- Milestone 4/5: run one real building end-to-end through
  `wine DESpriteTool.exe`, confirm it emits `.sld` without errors.
- Final: install the resulting `.sld` into the mod folder
  (`DIRS.AOEMODS`) in place of the current `.smx` for one test building and
  confirm it renders correctly in-game before converting the rest of the set.

## Open items to resolve empirically during implementation (not assumable now)

- Exact `BL16` 64×64 sub-voxel pixel layout (which of the 4×4×4 tiling
  conventions Goxel uses) — confirm against the real encode/decode source
  (`file_format.c` or wherever `img_write_to_mem`/`img_read_from_mem` are
  actually implemented in the goxel repo, not `gox.c` itself) when writing
  Milestone 1. This is exactly where research was cut off — pick it back up
  here first.
- Whether any real `.gox` file in `files-gox/` has a non-identity layer
  `mat`, which the reference C reader does not apply to block placement —
  verify against actual files before assuming identity transform always
  holds.
- Goxel's exact camera projection constants for the existing renders — reverse
  -engineer from known building silhouettes in Milestone 2.
- Whether DESpriteTool tolerates empty Decal/Background layers, and the exact
  accepted format/bit-depth for Height/Normals — confirm by running a real
  test conversion early (Milestone 5) rather than late.
