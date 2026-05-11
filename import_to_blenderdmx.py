# BlenderDMX Import — reads dmx_overview.json, creates fixtures in BlenderDMX.
#
# Usage:
#   1. Open a fresh Blender scene with BlenderDMX addon enabled.
#   2. Ensure GDTF profiles referenced in the JSON are in BlenderDMX's cache.
#   3. Open the Scripting workspace, paste this script.
#   4. Adjust JSON_PATH below.
#   5. Click Run Script.
#
# The script creates each fixture via bpy.ops.dmx.add_fixture, then:
#   - Sets DMX address on the first break.
#   - Renames the fixture and its Blender Collection to the fixture id.
#   - Positions all root objects (Body, 2D symbol, Text) at the fixture location.
#   - Positions the Target empty along the forward vector (5m from body) so the
#     fixture aims in the correct direction.

import bpy
import json
import os

JSON_PATH = os.path.expanduser("~/Desktop/blender_out/dmx_overview.json")
TARGET_DISTANCE = 5.0

with open(JSON_PATH) as f:
    package = json.load(f)

dmx = bpy.context.scene.dmx
created = 0

for fx in package["fixtures"]:
    before = len(dmx.fixtures)

    bpy.ops.dmx.add_fixture(
        profile=fx["gdtf"],
        user_fixture_name=fx["id"],
        mode=fx["mode"],
        units=1,
    )

    if len(dmx.fixtures) <= before:
        print("WARN: add_fixture didn't add a fixture for {}".format(fx["id"]))
        continue

    new_fixture = dmx.fixtures[-1]

    # DMX address on the first break
    if len(new_fixture.dmx_breaks) > 0:
        new_fixture.dmx_breaks[0].universe = fx["dmx"]["universe"]
        new_fixture.dmx_breaks[0].address  = fx["dmx"]["address"]

    # Rename fixture and its Collection
    new_fixture.name = fx["id"]
    if new_fixture.collection:
        new_fixture.collection.name = fx["id"]

    # Position body + orient via Target
    if new_fixture.collection:
        position = tuple(fx["position"])
        fwd = fx.get("forward")

        for obj in new_fixture.collection.all_objects:
            if obj.parent is None:
                if obj.type == "EMPTY" and "Target" in obj.name and fwd:
                    obj.location = (
                        position[0] + fwd[0] * TARGET_DISTANCE,
                        position[1] + fwd[1] * TARGET_DISTANCE,
                        position[2] + fwd[2] * TARGET_DISTANCE,
                    )
                else:
                    obj.location = position

    created += 1

print("Imported {}/{} fixtures".format(created, len(package["fixtures"])))
