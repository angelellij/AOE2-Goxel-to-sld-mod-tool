# Project Handoff: AoE2 PNG → SLD Converter (Python, Linux)

## Goal
Build a **fully scriptable-from-Python** pipeline that turns source PNG files
plus attribute data (anchors/hotspots, etc.) into **game-ready graphics for
Age of Empires II: Definitive Edition** — ideally the modern **SLD** format,
with SLP as an acceptable fallback.

Constraints / preferences:
- Now working on **Linux** (was on Windows).
- Wants to **avoid GUI apps** — the whole thing should be callable from Python
  code with no clicks, so it can be folded into an existing batch pipeline.
- SLP is accepted by the game, but **SLD is preferred** (it's the current
  default format since AoE2DE update 66692).

## Key findings (the important part)

1. **Do NOT reimplement SLX / SLX Studio.**
   - `.slx` is just SLX Studio's own *intermediate text manifest* (CSV-like:
     it indexes PNG frames + attributes). It is **not** what the game reads.
   - The game reads SLP / SMX / SLD. So targeting SLX is a dead end for this goal.

2. **The official game install ships a command-line converter that already does this.**
   - Tool: **`DESpriteTool.exe`**
   - Location: `...\steam\steamapps\common\AoE2DE\Tools_Builds\Sprites\`
   - It converts **SLP and PSD → SMX, SMP, and SLD** (the official encoder the
     devs use, so its SLD output is correct by definition).
   - It's a CLI tool (unlike SLX Studio, which is a GUI app), so it's genuinely
     zero-click and scriptable. Runs on Linux under **Wine**.
   - There is a **readme in that Sprites folder** documenting the exact flags —
     STILL NEEDS TO BE READ (see open items).

3. **No community PNG/PSD → SLD *encoder* exists outside the official tool.**
   - SLD was reverse-engineered by openage (+ SLX Studio author + others) for
     **reading only**.
   - SLD compression is **lossy** (4×4-block texture compression), so a
     hand-rolled encoder would be a large effort AND produce worse output than
     the official tool. Not worth it — use `DESpriteTool.exe`.

## Planned pipeline

Preferred (pending readme confirmation that DESpriteTool takes PNG/PSD directly):

    Python builds layered PNG/PSD  →  DESpriteTool.exe (via subprocess/Wine)  →  SLD

Fallback (if DESpriteTool needs SLP input):

    PNGs + attributes  →  png2slp.py (to be written)  →  DESpriteTool.exe  →  SLD

- `png2slp.py` = a self-contained Python CLI to write a valid `.slp` from PNGs +
  anchor/attribute data. SLP encoding is well documented, lossless, and
  verifiable. This is the only piece that might need to be built by hand.

## Open items / what to gather next

1. **Read `DESpriteTool.exe`'s readme** in
   `...\AoE2DE\Tools_Builds\Sprites\`.
   - Determines the exact CLI flags.
   - Determines whether it accepts **PNG/PSD directly** (→ skip the SLP step
     entirely, simplest pipeline) or requires **SLP input** (→ build `png2slp.py`).

2. **Provide a reference SLP set** to validate any SLP builder against:
   - One example `.slp` (e.g. one SLX Studio previously produced),
   - Its source PNGs,
   - The CSV with the anchor values.
   - Purpose: confirm generated SLP is byte-compatible with a known-good file.

3. **Confirm what the 3 source PNGs are** (very likely: main graphic, shadow,
   and player-color / "d" mask). Needed to pack SLP/layers correctly.

## Notes on the source PNGs (from the wiki)
In the SMX/SLX PNG convention: PNGs suffixed with **"d"** are **masks** — each
pixel's colour decides whether the corresponding pixel is transparent, modified
by player colour, or used as-is. SLD layer order (per openage): main graphics,
shadows, damage mask, player colour.

## Environment
- OS: Linux. Wine required to run `DESpriteTool.exe`.
- Repo access: use **Claude Code** (CLI or desktop Code tab) for direct
  read/write on the project files.

## Immediate next action for the new session
Paste the contents of the Sprites-folder readme so the CLI interface is known,
then decide PNG-direct vs SLP-first and build accordingly.