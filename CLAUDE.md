# CLAUDE.md

Context file for Claude Code sessions on this repo.

## Project

`aker-dev/dmx_export` — Rhino 8 → DMX package (CSV + JSON + venue.glb) → BlenderDMX import.

Part of the S·O·S lighting pipeline. Sister repo to `aker-dev/holophonix_export` (same conventions).

## Architecture

```
Rhino 3D (LIGHTS::* layers, block instances with user attributes)
    │
    └─ GhPython3 component (dmx_export.py)
         │
         ├─ dmx_overview.csv   (human-readable)
         ├─ dmx_overview.json  (pivot for downstream consumers)
         └─ venue.glb          (3D venue geometry, -90° X pre-rotated)
                │
                └─ BlenderDMX import (blender/import_to_blenderdmx.py)
                     └─ Fixtures placed, named, addressed, oriented via Target
```

## Conventions

- **Language**: English (code, comments, docs, commits).
- **Grasshopper**: `.ghx` versioned (XML, diff-friendly). No `.gh` binary.
- **Sample scene**: `starting_scene.3dm` bundled for testing.
- **Rhino API**: use `Rhino.RhinoDoc.ActiveDoc`, NOT `scriptcontext.doc` (proxy doc issue in GhPython3).
- **Path expansion**: always `os.path.expanduser()` for tilde paths.
- **Units**: positions in meters (auto-converted from doc units via `RhinoMath.UnitScale`).

## Layer hierarchy

```
LIGHTS::*   — fixture block instances (one sub-layer per group)
VENUE::*    — venue geometry for GLB export
```

Layer order under LIGHTS determines DMX address allocation order.

## User attributes on fixture block instances

- `id` (string): fixture identifier, e.g. "BI-01". Drives DMX sort order (alpha).
- `gdtf` (string): GDTF filename on disk, e.g. "AKER@Wash_RGBW_7C@Second_version.gdtf".
- `mode` (string): exact GDTF mode name, passed through verbatim to BlenderDMX (e.g. "8 CH User- Calibrated 16 Bit", "Mode 6CH", "2: RGBW").
- `channels` (int as string): channel count for the selected mode. Drives DMX address auto-assignment.

## Key constants

- `FORWARD_LOCAL = (0, 0, 1)` — beam direction in block's local frame (+Z = up).
- `VENUE_XFORM` — -90° rotation around X applied to venue geometry before GLB export.

## BlenderDMX specifics

- Operator: `bpy.ops.dmx.add_fixture(profile=, user_fixture_name=, mode=, units=1)`.
- `profile` parameter = GDTF filename on disk (not the display name with spaces).
- Fixture orientation controlled via **Target** empty, not Body rotation. Target positioned at `position + forward * 5m`.
- DMX address set post-creation via `dmx.fixtures[-1].dmx_breaks[0].universe/address`.
- Collection rename: `new_fixture.name = id` AND `new_fixture.collection.name = id`.

## Known issues

- `channels` is user-supplied (no cross-check against the GDTF file). A typo will produce a wrong DMX patch. Future work: parse the GDTF zip and derive the channel count from `(gdtf, mode)`.
- Single universe only.
- No roll component in orientation (forward vector only, no up vector).
- venue.glb -90° X rotation is a workaround for MapZToY=False + Blender Y/Z swap.
