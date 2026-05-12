#!/usr/bin/env python3
"""
mochi2gdtf.py — Generate BlenderDMX-compatible GDTF files from Chataigne .mochi definitions.

Based on the AKER_Wash_RGBW_7C GDTF template (verified working in BlenderDMX).

Usage:
    python3 mochi2gdtf.py <input.mochi> [--output <output.gdtf>] [--manufacturer <name>]
"""

import json
import zipfile
import uuid
import argparse
import os
import sys


# ─── Channel type mapping: mochi key → GDTF config ───

CHANNEL_MAP = {
    "intensity": {
        "attr": "Dimmer",
        "pretty": "Dim",
        "feature": "Dimmer.Dimmer",
        "physical_unit": "None",
        "activation_group": None,
        "functions": [
            {"name": "Dimmer 1", "attr": "Dimmer", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "strobe": "USE_STROBE_PRESET",  # resolved at build time via --strobe-preset
    "red": {
        "attr": "ColorAdd_R",
        "pretty": "R",
        "feature": "Color.RGB",
        "physical_unit": "ColorComponent",
        "activation_group": "ColorRGB",
        "functions": [
            {"name": "ColorAdd_R 1", "attr": "ColorAdd_R", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "green": {
        "attr": "ColorAdd_G",
        "pretty": "G",
        "feature": "Color.RGB",
        "physical_unit": "ColorComponent",
        "activation_group": "ColorRGB",
        "functions": [
            {"name": "ColorAdd_G 1", "attr": "ColorAdd_G", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "blue": {
        "attr": "ColorAdd_B",
        "pretty": "B",
        "feature": "Color.RGB",
        "physical_unit": "ColorComponent",
        "activation_group": "ColorRGB",
        "functions": [
            {"name": "ColorAdd_B 1", "attr": "ColorAdd_B", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "white": {
        "attr": "ColorAdd_W",
        "pretty": "White",
        "feature": "Color.RGB",
        "physical_unit": "ColorComponent",
        "activation_group": "ColorRGB",
        "functions": [
            {"name": "ColorAdd_W 1", "attr": "ColorAdd_W", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "amber": {
        "attr": "ColorAdd_RY",
        "pretty": "Amber",
        "feature": "Color.RGB",
        "physical_unit": "ColorComponent",
        "activation_group": "ColorRGB",
        "functions": [
            {"name": "ColorAdd_RY 1", "attr": "ColorAdd_RY", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "colorMacro": {
        "attr": "Color1",
        "pretty": "ColorMacro",
        "feature": "Color.RGB",
        "physical_unit": "None",
        "activation_group": None,
        "functions": [
            {"name": "Color1 1", "attr": "Color1", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "cTC": {
        "attr": "CTC",
        "pretty": "CTC",
        "feature": "Color.RGB",
        "physical_unit": "None",
        "activation_group": None,
        "functions": [
            {"name": "CTC 1", "attr": "CTC", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "curve": {
        "attr": "IntensityMode",
        "pretty": "Curve",
        "feature": "Dimmer.Dimmer",
        "physical_unit": "None",
        "activation_group": None,
        "functions": [
            {"name": "IntensityMode 1", "attr": "IntensityMode", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
    "ctrl": {
        "attr": "Control1",
        "pretty": "Ctrl",
        "feature": "Control.Control",
        "physical_unit": "None",
        "activation_group": None,
        "functions": [
            {"name": "Control1 1", "attr": "Control1", "dmx_from": "0/1", "default": "0/1",
             "phys_from": "0.000000", "phys_to": "1.000000"},
        ],
    },
}

CHANNEL_ALIASES = {
    "color macro": "colorMacro",
    "ctc": "cTC",
    "emulated white": "white",
    "rsrvd": "ctrl",
}

# ─── Strobe presets: per-fixture strobe channel definitions ───
# Based on manufacturer PDF DMX charts.

_STROBE_BASE = {
    "attr": "Shutter1",
    "pretty": "Sh1",
    "feature": "Beam.Beam",
    "physical_unit": "None",
    "activation_group": None,
}

_STROBE_EXTRA_ATTRS = [
    {"name": "Shutter1Closed", "pretty": "Closed", "feature": "Beam.Beam",
     "physical_unit": "None", "main_attribute": "Shutter1"},
    {"name": "Shutter1Strobe", "pretty": "Strobe1", "feature": "Beam.Beam",
     "physical_unit": "Frequency", "main_attribute": "Shutter1",
     "sub_physical_units": [
         {"phys_from": "0.000000", "phys_to": "0.000000", "unit": "Time", "type": "Duration"},
         {"phys_from": "1.000000", "phys_to": "1.000000", "unit": "Percent", "type": "TimeOffset"},
     ]},
]

STROBE_PRESETS = {
    # Cameo B200 / W600-SMD — 10 CH mode, channel 2
    # PDF: 0-5 open, 6-10 closed, 11-127 effects, 128-250 strobe <1Hz-20Hz, 251-255 open
    "cameo": {
        **_STROBE_BASE,
        "extra_attrs": _STROBE_EXTRA_ATTRS,
        "functions": [
            {"name": "Open",           "attr": "Shutter1",       "dmx_from": "0/1",   "default": "0/1",
             "phys_from": "1.000000", "phys_to": "1.000000"},
            {"name": "Closed",         "attr": "Shutter1Closed", "dmx_from": "6/1",   "default": "6/1",
             "phys_from": "0.000000", "phys_to": "0.000000"},
            {"name": "Strobe Effects", "attr": "Shutter1Strobe", "dmx_from": "11/1",  "default": "11/1",
             "phys_from": "0.500000", "phys_to": "10.000000"},
            {"name": "Strobe Linear",  "attr": "Shutter1Strobe", "dmx_from": "128/1", "default": "189/1",
             "phys_from": "1.000000", "phys_to": "20.000000"},
            {"name": "Open 2",         "attr": "Shutter1",       "dmx_from": "251/1", "default": "251/1",
             "phys_from": "1.000000", "phys_to": "1.000000"},
        ],
    },

    # Chauvet WELL Fit — 6 Ch mode, channel 6
    # PDF: 0-10 no function (open), 11-255 slow to fast
    "chauvet": {
        **_STROBE_BASE,
        "extra_attrs": _STROBE_EXTRA_ATTRS,
        "functions": [
            {"name": "Open",   "attr": "Shutter1",       "dmx_from": "0/1",  "default": "0/1",
             "phys_from": "1.000000", "phys_to": "1.000000"},
            {"name": "Strobe", "attr": "Shutter1Strobe", "dmx_from": "11/1", "default": "133/1",
             "phys_from": "1.000000", "phys_to": "25.000000"},
        ],
    },

    # Astera AX3 — Profile 12 DIM RGBWS, channel 6
    # PDF: 0-3 off, 4 random fast, 5 random medium, 6 random slow, 7-255 variable 0.4Hz→25Hz
    "astera": {
        **_STROBE_BASE,
        "extra_attrs": _STROBE_EXTRA_ATTRS,
        "functions": [
            {"name": "Open",            "attr": "Shutter1",       "dmx_from": "0/1", "default": "0/1",
             "phys_from": "1.000000", "phys_to": "1.000000"},
            {"name": "Strobe Random",   "attr": "Shutter1Strobe", "dmx_from": "4/1", "default": "5/1",
             "phys_from": "5.000000", "phys_to": "15.000000"},
            {"name": "Strobe Variable", "attr": "Shutter1Strobe", "dmx_from": "7/1", "default": "131/1",
             "phys_from": "0.400000", "phys_to": "25.000000"},
        ],
    },
}

# Auto-detect strobe preset from manufacturer name
MANUFACTURER_STROBE_MAP = {
    "cameo": "cameo",
    "chauvet": "chauvet",
    "astera": "astera",
}


def parse_mochi(filepath):
    """Parse .mochi, return fixture name + ordered channel keys from fixtureType."""
    with open(filepath) as f:
        data = json.load(f)
    fixture_name = "Unknown"
    channels = []
    for ft in data.get("fixtureType", []):
        fixture_name = ft.get("niceName", fixture_name)
        for item in ft.get("containers", {}).get("channels", {}).get("items", []):
            params = {p["controlAddress"]: p["value"] for p in item.get("parameters", [])}
            path = params.get("/channelType", "")
            channels.append(path.rstrip("/").split("/")[-1] if path else "unknown")
    return fixture_name, channels


def resolve(key, strobe_preset=None):
    """Resolve mochi key to GDTF config."""
    if key in CHANNEL_MAP:
        val = CHANNEL_MAP[key]
        if val == "USE_STROBE_PRESET":
            if strobe_preset and strobe_preset in STROBE_PRESETS:
                return STROBE_PRESETS[strobe_preset]
            print(f"  ⚠ No strobe preset specified, using 'cameo' default", file=sys.stderr)
            return STROBE_PRESETS["cameo"]
        return val
    lo = key.lower()
    if lo in CHANNEL_ALIASES:
        return CHANNEL_MAP[CHANNEL_ALIASES[lo]]
    for k in CHANNEL_MAP:
        if k.lower() == lo:
            val = CHANNEL_MAP[k]
            if val == "USE_STROBE_PRESET":
                if strobe_preset and strobe_preset in STROBE_PRESETS:
                    return STROBE_PRESETS[strobe_preset]
                return STROBE_PRESETS["cameo"]
            return val
    print(f"  ⚠ Unknown '{key}' → generic Control", file=sys.stderr)
    return CHANNEL_MAP["ctrl"]


def build_xml(fixture_name, channels, manufacturer, strobe_preset=None):
    """Build description.xml string matching BlenderDMX format."""

    resolved = [(k, resolve(k, strobe_preset)) for k in channels]

    # Deduplicate attrs
    seen = {}
    deduped = []
    for key, cfg in resolved:
        attr = cfg["attr"]
        if attr in seen:
            seen[attr] += 1
            cfg = {**cfg, "attr": f"{attr}_{seen[attr]}",
                   "functions": [
                       {**fn, "name": fn["name"].replace(attr, f"{attr}_{seen[attr]}"),
                        "attr": fn["attr"] if fn["attr"] != attr else f"{attr}_{seen[attr]}"}
                       for fn in cfg["functions"]
                   ]}
        else:
            seen[attr] = 1
        deduped.append((key, cfg))
    resolved = deduped

    # Collect features & activation groups
    features = {}
    act_groups = set()
    for _, cfg in resolved:
        fg, feat = cfg["feature"].split(".")
        features.setdefault(fg, set()).add(feat)
        if cfg.get("activation_group"):
            act_groups.add(cfg["activation_group"])

    fid = str(uuid.uuid4()).upper()
    short = fixture_name.split("(")[0].strip()[:15]
    n = len(channels)
    identity = "{1.000000,0.000000,0.000000,0.000000}{0.000000,1.000000,0.000000,0.000000}{0.000000,0.000000,1.000000,0.000000}{0,0,0,1}"
    beam_pos = "{1.000000,0.000000,0.000000,0.000000}{0.000000,1.000000,0.000000,0.000000}{0.000000,0.000000,1.000000,-0.048022}{0,0,0,1}"

    L = []
    w = L.append

    w('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>')
    w('<GDTF DataVersion="1.2">')
    w('')
    w(f'  <FixtureType CanHaveChildren="No" Description="Auto-generated from .mochi — {n}ch" FixtureTypeID="{fid}" LongName="{fixture_name}" Manufacturer="{manufacturer}" Name="{short}" RefFT="" ShortName="{short[:10]}" Thumbnail="" ThumbnailOffsetX="0" ThumbnailOffsetY="0">')

    # ── AttributeDefinitions ──
    w('    <AttributeDefinitions>')
    w('      <ActivationGroups>')
    for ag in sorted(act_groups):
        w(f'        <ActivationGroup Name="{ag}"/>')
    w('      </ActivationGroups>')

    w('      <FeatureGroups>')
    for fg in features:
        w(f'        <FeatureGroup Name="{fg}" Pretty="{fg}">')
        for feat in sorted(features[fg]):
            w(f'          <Feature Name="{feat}"/>')
        w(f'        </FeatureGroup>')
    w('      </FeatureGroups>')

    w('      <Attributes>')
    seen_a = set()
    for _, cfg in resolved:
        a = cfg["attr"]
        if a not in seen_a:
            seen_a.add(a)
            ag = f' ActivationGroup="{cfg["activation_group"]}"' if cfg.get("activation_group") else ""
            w(f'        <Attribute{ag} Feature="{cfg["feature"]}" Name="{a}" PhysicalUnit="{cfg["physical_unit"]}" Pretty="{cfg["pretty"]}"/>')
        for extra in cfg.get("extra_attrs", []):
            if extra["name"] not in seen_a:
                seen_a.add(extra["name"])
                ma = f' MainAttribute="{extra["main_attribute"]}"' if extra.get("main_attribute") else ""
                subs = extra.get("sub_physical_units", [])
                if subs:
                    w(f'        <Attribute Feature="{extra["feature"]}"{ma} Name="{extra["name"]}" PhysicalUnit="{extra["physical_unit"]}" Pretty="{extra["pretty"]}">')
                    for su in subs:
                        w(f'          <SubPhysicalUnit PhysicalFrom="{su["phys_from"]}" PhysicalTo="{su["phys_to"]}" PhysicalUnit="{su["unit"]}" Type="{su["type"]}"/>')
                    w('        </Attribute>')
                else:
                    w(f'        <Attribute Feature="{extra["feature"]}"{ma} Name="{extra["name"]}" PhysicalUnit="{extra["physical_unit"]}" Pretty="{extra["pretty"]}"/>')
    w('      </Attributes>')
    w('    </AttributeDefinitions>')

    # ── Wheels, PhysicalDescriptions, Models ──
    w('    <Wheels/>')
    w('    <PhysicalDescriptions>')
    w('      <ColorSpace Mode="sRGB" Name=""/>')
    w('      <AdditionalColorSpaces/>')
    w('      <Gamuts/>')
    w('      <Filters/>')
    w('      <Emitters/>')
    w('      <DMXProfiles/>')
    w('      <CRIs/>')
    w('      <Connectors/>')
    w('      <Properties>')
    w('        <OperatingTemperature High="45.000000" Low="-10.000000"/>')
    w('        <Weight Value="5.500000"/>')
    w('        <LegHeight Value="0.000000"/>')
    w('      </Properties>')
    w('    </PhysicalDescriptions>')
    w('    <Models>')
    w('      <Model File="" Height="0.096000" Length="0.385000" Name="body" PrimitiveType="Cube" SVGFrontOffsetX="0.000000" SVGFrontOffsetY="0.000000" SVGOffsetX="0.000000" SVGOffsetY="0.000000" SVGSideOffsetX="0.000000" SVGSideOffsetY="0.000000" Width="0.255000"/>')
    w('      <Model File="" Height="0.005000" Length="0.385000" Name="beam" PrimitiveType="Cube" SVGFrontOffsetX="0.000000" SVGFrontOffsetY="0.000000" SVGOffsetX="0.000000" SVGOffsetY="0.000000" SVGSideOffsetX="0.000000" SVGSideOffsetY="0.000000" Width="0.255000"/>')
    w('    </Models>')

    # ── Geometries ──
    w('    <Geometries>')
    w(f'      <Geometry Model="body" Name="Body" Position="{identity}">')
    w(f'        <Beam BeamAngle="40.000000" BeamRadius="0.050000" BeamType="Wash" ColorRenderingIndex="100" ColorTemperature="6500.000000" FieldAngle="40.000000" LampType="LED" LuminousFlux="18000.000000" Model="beam" Name="Beam" Position="{beam_pos}" PowerConsumption="180.000000" RectangleRatio="1.777700" ThrowRatio="1.000000"/>')
    w('      </Geometry>')
    w('    </Geometries>')

    # ── DMXModes ──
    w('    <DMXModes>')
    w(f'      <DMXMode Description="" Geometry="Body" Name="{n} Channels">')
    w('        <DMXChannels>')

    for offset, (_, cfg) in enumerate(resolved, 1):
        attr = cfg["attr"]
        fn0 = cfg["functions"][0]
        init = f"Beam_{attr}.{attr}.{fn0['name']}"

        w(f'          <DMXChannel DMXBreak="1" Geometry="Beam" Highlight="None" InitialFunction="{init}" Offset="{offset}">')
        w(f'            <LogicalChannel Attribute="{attr}" DMXChangeTimeLimit="0.000000" Master="None" MibFade="0.000000" Snap="No">')
        for fn in cfg["functions"]:
            w(f'              <ChannelFunction Attribute="{fn["attr"]}" CustomName="" DMXFrom="{fn["dmx_from"]}" Default="{fn["default"]}" Max="1.000000" Min="0.000000" Name="{fn["name"]}" OriginalAttribute="" PhysicalFrom="{fn["phys_from"]}" PhysicalTo="{fn["phys_to"]}" RealAcceleration="0.000000" RealFade="0.000000"/>')
        w('            </LogicalChannel>')
        w('          </DMXChannel>')

    w('        </DMXChannels>')
    w('        <Relations/>')
    w('        <FTMacros/>')
    w('      </DMXMode>')
    w('    </DMXModes>')

    w('    <Revisions>')
    w('      <Revision Date="2026-05-12T00:00:00" ModifiedBy="mochi2gdtf" Text="Generated from .mochi" UserID="0"/>')
    w('    </Revisions>')
    w('    <FTPresets/>')
    w('    <Protocols/>')
    w('  </FixtureType>')
    w('')
    w('</GDTF>')

    return "\r\n".join(L)


def mochi_to_gdtf(mochi_path, output_path=None, manufacturer="Custom", strobe_preset=None):
    fixture_name, channels = parse_mochi(mochi_path)

    # Auto-detect strobe preset from manufacturer if not specified
    if strobe_preset is None:
        for mfr_key, preset_name in MANUFACTURER_STROBE_MAP.items():
            if mfr_key.lower() in manufacturer.lower():
                strobe_preset = preset_name
                break

    has_strobe = "strobe" in channels
    print(f"Fixture: {fixture_name}")
    print(f"Channels: {len(channels)}")
    if has_strobe:
        print(f"Strobe preset: {strobe_preset or 'default (cameo)'}")
    for i, k in enumerate(channels, 1):
        c = resolve(k, strobe_preset)
        n_fn = len(c.get("functions", []))
        fn_info = f" ({n_fn} functions)" if n_fn > 1 else ""
        print(f"  {i:2d}. {k:20s} → {c['attr']:20s} (offset {i}){fn_info}")

    xml = build_xml(fixture_name, channels, manufacturer, strobe_preset)

    if not output_path:
        output_path = os.path.splitext(os.path.basename(mochi_path))[0] + ".gdtf"

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("description.xml", xml.encode("utf-8"))

    print(f"\n✓ {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="Chataigne .mochi → BlenderDMX .gdtf")
    p.add_argument("mochi")
    p.add_argument("--output", "-o")
    p.add_argument("--manufacturer", "-m", default="Custom")
    p.add_argument("--strobe-preset", "-s", choices=list(STROBE_PRESETS.keys()),
                   help="Strobe channel ranges (auto-detected from manufacturer if omitted)")
    args = p.parse_args()
    mochi_to_gdtf(args.mochi, args.output, args.manufacturer, args.strobe_preset)


if __name__ == "__main__":
    main()
