# dmx_export

Export a Rhino 8 scene to a **DMX package** (overview CSV + JSON pivot + `venue.glb`) via a Grasshopper GhPython3 component. Includes a companion script to import fixtures into BlenderDMX.

> Project language is English. All code, comments, docs, and commit messages are in English.

## Prerequisites

- **Rhino >= 8.3** (embedded CPython 3 on the Grasshopper side + `Rhino.FileIO.FileGltf` API for programmatic .glb export).
- A Rhino scene with:
  * **Fixtures** — Block Instances on sub-layers of `LIGHTS::*` (one sub-layer per group: `LIGHTS::B200-INT`, `LIGHTS::WELLFIT`, ...). Each instance carries user attributes `id`, `gdtf`, `mode`.
  * **Venue** — any geometry on the `VENUE` layer (or `VENUE::*`). Exported as-is to .glb with a -90° X rotation to compensate for the glTF Y-up to Blender Z-up axis swap.

For BlenderDMX import:

- **Blender 4.5+** with the [BlenderDMX addon](https://blenderdmx.eu/) installed.
- GDTF profiles referenced in fixture attributes must be imported into BlenderDMX's profile cache beforehand.

A sample scene is bundled at [`starting_scene.3dm`](starting_scene.3dm) — open it in Rhino 8 to try the export without building a layer hierarchy from scratch.

## Layer convention

```
LIGHTS              (parent layer)
├── B200-INT        (sub-layer, fixtures BI-01 to BI-04)
├── B200-EXT        (sub-layer, fixtures BE-01, BE-03)
├── WELLFIT         (sub-layer, fixtures WN-01 to WN-04)
├── AX3             (empty for now)
└── W600            (empty for now)
VENUE               (venue geometry)
```

The **order of sub-layers in Rhino** determines the DMX address allocation order. Within each sub-layer, fixtures are sorted alphabetically by `id`.

### User attributes per block instance

| Key        | Example                                      | Required |
|------------|----------------------------------------------|----------|
| `id`       | `BI-01`                                      | yes      |
| `gdtf`     | `AKER@Wash_RGBW_7C@Second_version.gdtf`      | yes      |
| `mode`     | `8 CH User- Calibrated 16 Bit`               | yes      |
| `channels` | `7`                                          | yes      |

The `gdtf` value is the **filename on disk** in BlenderDMX's profile cache (not the display name shown in the dropdown).

The `mode` value is the **exact DMX mode name** as written in the GDTF file (it can contain spaces, hyphens, colons — e.g. `"Mode 6CH"`, `"2: RGBW"`). It is passed through unchanged to BlenderDMX's `add_fixture(mode=...)`, so it must match the GDTF mode string verbatim.

The `channels` value is the **channel count for the selected mode**, as an integer. Used for DMX address auto-assignment.

## Installation

**Quick path** — open [`dmx_export.ghx`](dmx_export.ghx) in Grasshopper. The definition already embeds the GhPython3 component, its script, all the inputs, the Button for `run`, and the output Panels.

**Manual path** (if you prefer to rebuild the component from scratch):

1. Open Grasshopper inside Rhino 8.
2. Drop a **GhPython3** component (*Script > Python 3*).
3. Paste the contents of [`dmx_export.py`](dmx_export.py) into the component editor.
4. Add the inputs (right-click on the component, `+`):

    | Name            | Type | Details                                      |
    |-----------------|------|----------------------------------------------|
    | `folder`        | str  | Panel with the output **folder** path        |
    | `run`           | bool | **Button** — writes CSV + JSON + GLB package |
    | `layer_root`    | str  | Panel, defaults to `LIGHTS`                  |
    | `start_address` | int  | Panel, defaults to `1`                       |
    | `dmx_universe`  | int  | Panel, defaults to `1`                       |
    | `export_venue`  | bool | Toggle, defaults to `True`                   |

5. Add the outputs `lines`, `count`, `log`.

> The `.ghx` is the versioned Grasshopper definition (XML, diff-friendly). The binary `.gh` variant is intentionally kept out of the repo.

## Usage

1. Wire a Panel to `lines` to preview the CSV rows.
2. Check `count` (number of detected fixtures) and `log` (per-layer breakdown + written paths).
3. Click **`run`** — files produced in `folder`:
   - `dmx_overview.csv` — human-readable patch table
   - `dmx_overview.json` — pivot file for BlenderDMX import (and future Chataigne import)
   - `venue.glb` — venue geometry with -90° X pre-rotation for correct Blender import

## BlenderDMX import

1. Open a fresh Blender scene with BlenderDMX enabled.
2. Ensure the GDTF profiles referenced in the JSON are already in BlenderDMX's cache.
3. Open the Scripting workspace, paste [`blender/import_to_blenderdmx.py`](blender/import_to_blenderdmx.py).
4. Adjust `JSON_PATH` at the top of the script.
5. Click **Run Script**.

The script creates each fixture with the correct GDTF profile, DMX address, name, position, and orientation (via Target placement along the forward vector).

## Output format

### CSV

```
id;layer;gdtf;mode;channels;X;Y;Z;fX;fY;fZ;universe;address
BI-01;B200-INT;AKER@Wash_RGBW_7C@Second_version.gdtf;8 CH User- Calibrated 16 Bit;7;-14.726;-16.510;0.000;0.000;0.000;1.000;1;1
```

### JSON

```json
{
  "metadata": {
    "version": "0.5.0",
    "units": "meters",
    "layer_root": "LIGHTS"
  },
  "fixtures": [
    {
      "id": "BI-01",
      "layer": "B200-INT",
      "gdtf": "AKER@Wash_RGBW_7C@Second_version.gdtf",
      "mode": "8 CH User- Calibrated 16 Bit",
      "channels": 7,
      "position": [-14.726, -16.510, 0.0],
      "forward": [0.0, 0.0, 1.0],
      "dmx": { "universe": 1, "address": 1 }
    }
  ]
}
```

## DMX address auto-assignment

Addresses are assigned sequentially across a single universe:

1. Sub-layers under `LIGHTS` are iterated **in Rhino's layer panel order** (`SortIndex`).
2. Within each sub-layer, fixtures are sorted **alphabetically by `id`**.
3. Each fixture occupies N channels, read from its `channels` user attribute.
4. The next fixture starts at the previous fixture's address + channel count.

The channel count per fixture is read from the `channels` user attribute on the block instance. It must match the channel count of the GDTF mode selected via the `mode` attribute (no cross-check is performed against the GDTF file).

## Forward vector convention

The block definition's local +Z axis is the **beam direction** (`FORWARD_LOCAL = (0, 0, 1)`). When a block instance is rotated in Rhino, the forward vector is transformed accordingly and written to the JSON.

In BlenderDMX, the forward vector is used to position the fixture's **Target** empty (at `position + forward * 5m`), which the fixture automatically aims at.

## Axis conventions

Rhino and Blender both use right-handed Z-up coordinate systems. Fixture positions and forward vectors transfer directly between them (set via `obj.location` in Blender Python, bypassing glTF axis conversion).

The `venue.glb` requires a **-90° X pre-rotation** because Rhino's `FileGltf.Write` with `MapZToY=False` produces a non-standard Z-up glTF, which Blender's importer then incorrectly swaps (assuming Y-up). The pre-rotation compensates for this double conversion.

## Limitations

- Single DMX universe only (production will support multi-universe).
- Channel count per fixture is user-supplied via the `channels` attribute (no automatic derivation from the GDTF file — a typo will produce a wrong patch).
- No fixture rotation export beyond forward vector (no roll).
- `venue.glb` pre-rotation is hardcoded at -90° X.
- No `.glb` export per fixture model (BlenderDMX uses GDTF geometry directly).

## Related repos

- [`aker-dev/holophonix_export`](https://github.com/aker-dev/holophonix_export) — same pattern, exports speakers to Holophonix.
- `aker-dev/dmx_chataigne_import` (planned) — reads `dmx_overview.json` inside Chataigne.
