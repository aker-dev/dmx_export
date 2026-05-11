# DMX Export — GhPython3 component (Rhino 8.3+, Python 3)
#
# GhPython component setup:
#   Inputs:
#     folder         (str,  Item Access) — output folder (CSV + JSON + .glb)
#     run            (bool, Item Access) — button, writes package
#     layer_root     (str,  Item Access) — fixtures layer prefix, defaults to "LIGHTS"
#     start_address  (int,  Item Access) — first DMX address, defaults to 1
#     dmx_universe   (int,  Item Access) — DMX universe, defaults to 1
#     export_venue   (bool, Item Access) — writes venue.glb when True (default True)
#   Outputs:
#     lines  — list of CSV lines (header included), for preview
#     count  — number of exported fixtures
#     log    — diagnostics (groups + written paths)
#
# Behavior: scans every Block Instance whose full layer path starts with
# "<layer_root>::", reads user attributes (id, gdtf, mode, channels), sorts
# by layer order then by id (alphabetical), auto-assigns DMX addresses from
# the per-block `channels` attribute, extracts position (meters) and forward
# vector from the block's InstanceXform, then if `run` is True writes into
# `folder`:
#   - dmx_overview.csv    (human-readable patch table)
#   - dmx_overview.json   (pivot for BlenderDMX and Chataigne)
#   - venue.glb           (geometry of the VENUE layer, -90 deg X pre-rotated)
#
# Forward vector convention: FORWARD_LOCAL = +Z in the block definition's
# local frame (beam points up when the block is unrotated).
#
# Venue GLB axis compensation: -90 deg X rotation applied before export to
# counteract the glTF Y-up to Blender Z-up swap that occurs on import.

import os
import json
import math
import Rhino

VENUE_ROOT     = "VENUE"
VENUE_GLB_NAME = "venue.glb"
CSV_NAME       = "dmx_overview.csv"
JSON_NAME      = "dmx_overview.json"

FORWARD_LOCAL = (0.0, 0.0, 1.0)

VENUE_XFORM = Rhino.Geometry.Transform.Rotation(
    math.radians(-90),
    Rhino.Geometry.Vector3d.XAxis,
    Rhino.Geometry.Point3d.Origin,
)

doc = Rhino.RhinoDoc.ActiveDoc


# ---------- GLB helpers (from holophonix_export, + transform support) ----------

def collect_objects_on_layer(doc, root):
    """Object IDs whose layer FullPath equals `root` OR starts with `root::`."""
    ids = []
    for obj in doc.Objects:
        layer = doc.Layers[obj.Attributes.LayerIndex]
        fp = layer.FullPath
        if fp == root or fp.startswith(root + "::"):
            ids.append(obj.Id)
    return ids


def _gltf_options():
    opts = Rhino.FileIO.FileGltfWriteOptions()
    opts.MapZToY = False
    opts.ExportMaterials = True
    opts.UseDisplayColorForUnsetMaterials = True
    opts.CullBackfaces = True
    opts.ExportLayers = False
    return opts


def _resolve_display_color(source_doc, rh_obj):
    attrs = rh_obj.Attributes
    if attrs.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromObject:
        return attrs.ObjectColor
    return source_doc.Layers[attrs.LayerIndex].Color


def _add_with_color(tmp_doc, rh_obj, color, transform=None):
    attrs = rh_obj.Attributes.Duplicate()
    attrs.ObjectColor = color
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromLayer
    attrs.MaterialIndex = -1
    attrs.LayerIndex = 0
    geom = rh_obj.Geometry
    if transform is not None:
        geom = geom.Duplicate()
        geom.Transform(transform)
    tmp_doc.Objects.Add(geom, attrs)


def _create_tmp_doc(source_doc):
    tmp = Rhino.RhinoDoc.CreateHeadless(None)
    tmp.AdjustModelUnitSystem(source_doc.ModelUnitSystem, False)
    return tmp


def export_glb(source_doc, object_ids, output_path, transform=None):
    """Export objects as binary .glb. Optional transform applied to geometry."""
    if not object_ids:
        return False
    tmp = _create_tmp_doc(source_doc)
    try:
        for oid in object_ids:
            obj = source_doc.Objects.FindId(oid)
            if obj is not None:
                _add_with_color(tmp, obj, _resolve_display_color(source_doc, obj), transform)
        return Rhino.FileIO.FileGltf.Write(output_path, tmp, _gltf_options())
    finally:
        tmp.Dispose()


# ---------- main ----------

layer_root_name = layer_root if layer_root else "LIGHTS"
start_addr      = int(start_address) if start_address is not None else 1
universe        = int(dmx_universe)  if dmx_universe  is not None else 1
export_venue_v  = True if export_venue is None else bool(export_venue)

unit_scale = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Meters)

log_lines = []
fixtures  = []
lines     = []
count     = 0

root_idx = doc.Layers.FindByFullPath(layer_root_name, -1)
if root_idx < 0:
    log_lines.append("ERROR: layer '{}' not found".format(layer_root_name))
else:
    root_layer = doc.Layers[root_idx]

    sub_layers = [l for l in doc.Layers
                  if l.ParentLayerId == root_layer.Id and not l.IsDeleted]
    sub_layers.sort(key=lambda l: l.SortIndex)

    addr = start_addr

    for sub in sub_layers:
        instances = [o for o in doc.Objects
                     if not o.IsDeleted
                     and o.Attributes.LayerIndex == sub.LayerIndex
                     and o.ObjectType == Rhino.DocObjects.ObjectType.InstanceReference]

        items = []
        for obj in instances:
            a = obj.Attributes
            items.append({
                "obj":      obj,
                "id":       a.GetUserString("id")       or "",
                "gdtf":     a.GetUserString("gdtf")     or "",
                "mode":     a.GetUserString("mode")     or "",
                "channels": a.GetUserString("channels") or "",
            })

        items.sort(key=lambda i: i["id"])

        layer_count = 0
        for it in items:
            if not it["id"]:
                log_lines.append("WARN: instance without 'id' on '{}', skipped".format(sub.Name))
                continue

            try:
                channels = int(it["channels"])
                if channels <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                log_lines.append("WARN: missing/invalid 'channels' attribute on {}, skipped".format(it["id"]))
                continue

            xform = it["obj"].InstanceXform

            pt = Rhino.Geometry.Point3d(0, 0, 0)
            pt.Transform(xform)

            fwd = Rhino.Geometry.Vector3d(*FORWARD_LOCAL)
            fwd.Transform(xform)
            fwd.Unitize()

            fixtures.append({
                "id":       it["id"],
                "layer":    sub.Name,
                "gdtf":     it["gdtf"],
                "mode":     it["mode"],
                "channels": channels,
                "position": [pt.X * unit_scale, pt.Y * unit_scale, pt.Z * unit_scale],
                "forward":  [fwd.X, fwd.Y, fwd.Z],
                "dmx": {"universe": universe, "address": addr},
            })
            addr += channels
            layer_count += 1

        log_lines.append("{}: {} fixtures".format(sub.Name, layer_count))

    lines.append("id;layer;gdtf;mode;channels;X;Y;Z;fX;fY;fZ;universe;address")
    for f in fixtures:
        fw = f["forward"]
        lines.append("{};{};{};{};{};{:.3f};{:.3f};{:.3f};{:.3f};{:.3f};{:.3f};{};{}".format(
            f["id"], f["layer"], f["gdtf"], f["mode"], f["channels"],
            f["position"][0], f["position"][1], f["position"][2],
            fw[0], fw[1], fw[2],
            f["dmx"]["universe"], f["dmx"]["address"],
        ))
    count = len(fixtures)

    if run and folder:
        folder_resolved = os.path.expanduser(folder)
        try:
            if not os.path.isdir(folder_resolved):
                os.makedirs(folder_resolved)

            csv_path  = os.path.join(folder_resolved, CSV_NAME)
            json_path = os.path.join(folder_resolved, JSON_NAME)

            with open(csv_path, "w") as f:
                f.write("\n".join(lines))
            log_lines.append("wrote {}".format(csv_path))

            package = {
                "metadata": {
                    "version":    "0.5.0",
                    "units":      "meters",
                    "layer_root": layer_root_name,
                },
                "fixtures": fixtures,
            }
            with open(json_path, "w") as f:
                json.dump(package, f, indent=2)
            log_lines.append("wrote {}".format(json_path))

            if export_venue_v:
                venue_ids = collect_objects_on_layer(doc, VENUE_ROOT)
                if venue_ids:
                    venue_path = os.path.join(folder_resolved, VENUE_GLB_NAME)
                    if export_glb(doc, venue_ids, venue_path, VENUE_XFORM):
                        log_lines.append("wrote {}".format(venue_path))
                    else:
                        log_lines.append("FAILED venue.glb")
                else:
                    log_lines.append("SKIP venue.glb: no geometry on '{}'".format(VENUE_ROOT))
            else:
                log_lines.append("SKIP venue.glb (export_venue=False)")

        except Exception as e:
            log_lines.append("ERROR writing files: {}".format(e))
    else:
        log_lines.append("idle (run={}, folder={!r})".format(run, folder))

log = "\n".join(log_lines)
