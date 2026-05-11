# Changelog

## [0.5.0] — 2026-05-12

### Added
- GhPython3 component: export fixtures from Rhino `LIGHTS::*` layers to `dmx_overview.csv` + `dmx_overview.json`.
- Auto DMX address assignment: by layer order, then alphabetical `id` within each layer.
- Forward vector extraction from block instance orientation (`FORWARD_LOCAL = +Z`).
- Venue GLB export from `VENUE` layer with -90° X pre-rotation for Blender axis compensation.
- BlenderDMX import script (`blender/import_to_blenderdmx.py`): creates fixtures with correct GDTF profile, DMX address, name, position, and orientation via Target placement.
- User attributes on Rhino block instances: `id`, `gdtf`, `mode`.
- `CHANNEL_MAP` hardcoded for POC (AKER Wash RGBW 7C + BlenderDMX RysyParLED).
