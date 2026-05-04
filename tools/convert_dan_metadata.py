"""Convert an EHG runtime-metadata extraction directory into a hymer-connect-ha
brand overlay JSON (sensor_maps/<brand>.json).

The input is produced by an external EHG metadata extractor such as
`HYMER Connect Metadata Edition` by @dan-simms1
(https://github.com/dan-simms1/hymer-connect-ha) -- see tools/README.md.
This converter is independent: it reads that local extraction output and
emits a brand overlay; it does not redistribute any APK-derived data.

Pipeline:

    user APK  --(upstream prepare_runtime_metadata.py)-->  local metadata dir
                                                           (NOT committed to git)
    local metadata dir  --(this converter)-->  sensor_maps/<brand>.json
                                                (reviewable patch)

Conservative emission policy:

    * Read-only slots                       -> sensor / binary_sensor (auto)
    * component_kinds[bus] == "light"       -> lights section          (auto)
    * Writable slot AND support_matrix says
      "known_writable" AND control_catalog
      has explicit write semantics          -> switches section        (auto)
    * Writable but only "inferred"          -> emitted with
                                               "enabled": false and
                                               "_inferred": true       (opt-in)
    * Suppressed in coverage_audit          -> skipped
    * Climate / fridge / boiler / heater    -> NOT auto-emitted; a
                                               "_climate_templates_required"
                                               marker block is added so the
                                               maintainer hand-ports them
                                               from hymer.json.

Schema posture: the upstream metadata format is reasonably stable but is NOT
a public API. ALL field-name lookups are funneled through SCHEMA_MAP at the
top of this file so we can re-tune to a future formal schema in one place.

Use --self-test to run an in-memory round-trip with synthetic fixtures (no
real APK-derived data is needed or accepted in this repo).

Author: Jan Tiedemann
Date:   2026
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# SCHEMA_MAP -- single source of truth for upstream-side field names.
#
# Field names below are the documented or strongly-implied names from the
# upstream extractor's output. Adjust here when a formal schema is published.
# ---------------------------------------------------------------------------

SCHEMA_MAP: dict[str, dict[str, str]] = {
    # sensor_labels.json: per-slot label/decode metadata.
    # Expected shape:
    #   { "<bus>,<sid>": {"name": ..., "datatype": ..., "unit": ..., "mode": ...} }
    "sensor_labels": {
        "name": "name",
        "datatype": "datatype",   # bool | uint8 | uint16 | int16 | float | string
        "unit": "unit",           # SI unit string ("V", "A", "%", "°C", ...) or null
        "mode": "mode",           # read | write | read_write
        "transform": "transform", # optional: div10 / div100 / div1000 / div3600
    },
    # component_kinds.json: per-bus component classification.
    # Expected shape:
    #   { "<bus>": {"kind": "light"|"switch"|"fridge"|"heater"|"boiler"|"sensor"|...} }
    "component_kinds": {
        "kind": "kind",
    },
    # control_catalog.json: per-(bus,sid) write semantics.
    # Expected shape:
    #   { "<bus>,<sid>": {"write_type": ..., "on_value": ..., "off_value": ...} }
    "control_catalog": {
        "write_type": "write_type",   # bool | str | uint
        "on_value": "on_value",
        "off_value": "off_value",
        "read_path": "read_path",     # optional dotted path under signalr_sensors
    },
    # coverage_audit.json: per-(bus,sid) coverage classification.
    # Expected shape:
    #   { "<bus>,<sid>": "known_read_only"|"known_writable"|"inferred"|"suppressed" }
    "coverage_audit": {
        # Values are leaf strings; nothing to remap. Listed for documentation.
    },
    # support_matrix.json: per-vehicle / per-slot support flags.
    # Expected shape:
    #   { "<vehicle_id>": { "<bus>,<sid>": "known_writable"|"known_read_only"|... } }
    "support_matrix": {
        # Same as coverage_audit but vehicle-scoped.
    },
    # vehicle_catalog.json: brand/model directory.
    # Expected shape:
    #   { "<vehicle_id>": {"brand": ..., "model": ..., "buses": [..]} }
    # Buses list is informational only -- NOT authoritative; the SCU's runtime
    # behaviour wins.
    "vehicle_catalog": {
        "brand": "brand",
        "model": "model",
        "buses": "buses",
    },
}

# Coverage classes used in coverage_audit.json / support_matrix.json.
COV_KNOWN_RO   = "known_read_only"
COV_KNOWN_RW   = "known_writable"
COV_INFERRED   = "inferred"
COV_SUPPRESSED = "suppressed"

# Component kinds we treat specially.
KIND_LIGHT      = "light"
KIND_SWITCH     = "switch"
KIND_FRIDGE     = "fridge"
KIND_HEATER     = "heater"
KIND_BOILER     = "boiler"
KIND_AC         = "ac"
CLIMATE_KINDS   = {KIND_FRIDGE, KIND_HEATER, KIND_BOILER, KIND_AC}

# Datatype -> HA platform/device_class/state_class heuristics.
# These are intentionally minimal; brand maintainers can refine post-conversion.
DATATYPE_PLATFORM: dict[str, dict[str, Any]] = {
    "bool":   {"platform": "binary_sensor"},
    "uint8":  {"platform": "sensor", "state_class": "measurement"},
    "uint16": {"platform": "sensor", "state_class": "measurement"},
    "int16":  {"platform": "sensor", "state_class": "measurement"},
    "float":  {"platform": "sensor", "state_class": "measurement"},
    "string": {"platform": "sensor"},
}

# Unit -> device_class hints. Conservative; only obvious mappings.
# Units intentionally omitted (e.g. "%") have no unambiguous device_class.
UNIT_DEVICE_CLASS: dict[str, str] = {
    "V":  "voltage",
    "A":  "current",
    "W":  "power",
    "Wh": "energy",
    "°C": "temperature",
    "°F": "temperature",
    "km": "distance",
    "L":  "volume_storage",
    "bar": "pressure",
    "kPa": "pressure",
    "h":  "duration",
}

# Default light SID convention used by hymer.json: 1=on/off, 2=brightness, 3=color_temp.
LIGHT_SID_ONOFF      = 1
LIGHT_SID_BRIGHTNESS = 2
LIGHT_SID_COLOR_TEMP = 3


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ExtractionMetadata:
    """In-memory view of an upstream extractor's local output directory."""

    sensor_labels:    dict[str, dict[str, Any]] = field(default_factory=dict)
    component_kinds:  dict[str, dict[str, Any]] = field(default_factory=dict)
    control_catalog:  dict[str, dict[str, Any]] = field(default_factory=dict)
    coverage_audit:   dict[str, str]            = field(default_factory=dict)
    support_matrix:   dict[str, dict[str, str]] = field(default_factory=dict)
    vehicle_catalog:  dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ConvertStats:
    sensors_emitted:       int = 0
    binary_sensors_emitted:int = 0
    lights_emitted:        int = 0
    switches_emitted:      int = 0
    inferred_disabled:     int = 0
    suppressed_skipped:    int = 0
    climate_markers:       int = 0
    unknown_kind:          int = 0


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

REQUIRED_FILES = (
    "sensor_labels.json",
    "component_kinds.json",
    "control_catalog.json",
    "coverage_audit.json",
)

OPTIONAL_FILES = (
    "support_matrix.json",
    "vehicle_catalog.json",
)


def load_metadata(meta_dir: Path) -> ExtractionMetadata:
    """Load an upstream extractor's output from a local directory.

    Required files raise FileNotFoundError; optional files default to {}.
    """
    if not meta_dir.is_dir():
        raise FileNotFoundError(f"Metadata directory not found: {meta_dir}")

    def _load(name: str, *, required: bool) -> Any:
        path = meta_dir / name
        if not path.is_file():
            if required:
                raise FileNotFoundError(f"Required metadata file missing: {path}")
            return {}
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    md = ExtractionMetadata(
        sensor_labels   = _load("sensor_labels.json",   required=True),
        component_kinds = _load("component_kinds.json", required=True),
        control_catalog = _load("control_catalog.json", required=True),
        coverage_audit  = _load("coverage_audit.json",  required=True),
        support_matrix  = _load("support_matrix.json",  required=False),
        vehicle_catalog = _load("vehicle_catalog.json", required=False),
    )
    _validate_required_fields(md)
    return md


def _validate_required_fields(md: ExtractionMetadata) -> None:
    """Validate the minimal field set we depend on; fail loudly on gaps."""
    name_key     = SCHEMA_MAP["sensor_labels"]["name"]
    datatype_key = SCHEMA_MAP["sensor_labels"]["datatype"]
    kind_key     = SCHEMA_MAP["component_kinds"]["kind"]

    missing_name: list[str] = []
    for slot, entry in md.sensor_labels.items():
        if not isinstance(entry, dict):
            raise ValueError(f"sensor_labels[{slot!r}] is not an object")
        if name_key not in entry:
            missing_name.append(slot)
        # datatype is allowed to be missing; we'll fall back to string-typed sensor.
        _ = datatype_key  # documented dependency

    if missing_name:
        head = ", ".join(missing_name[:5])
        raise ValueError(
            f"sensor_labels.json: {len(missing_name)} entries lack required "
            f"'{name_key}' field (e.g. {head})"
        )

    for bus, entry in md.component_kinds.items():
        if not isinstance(entry, dict):
            raise ValueError(f"component_kinds[{bus!r}] is not an object")
        if kind_key not in entry:
            raise ValueError(
                f"component_kinds[{bus!r}] missing required '{kind_key}' field"
            )


# ---------------------------------------------------------------------------
# Conversion logic
# ---------------------------------------------------------------------------

def convert(
    md: ExtractionMetadata,
    *,
    brand: str,
    vehicle_id: str | None = None,
    include_inferred: bool = False,
) -> tuple[dict[str, Any], ConvertStats]:
    """Convert metadata into a sensor_maps overlay dict.

    Args:
        md: parsed metadata.
        brand: lower-case brand slug (e.g. "buerstner").
        vehicle_id: optional support_matrix key to scope writability decisions.
        include_inferred: if True, emit inferred slots with enabled=false instead
            of skipping them. Default False (strict-conservative).
    """
    stats = ConvertStats()
    overlay: dict[str, Any] = {
        "_comment": (
            f"{brand} brand overlay generated by tools/convert_dan_metadata.py "
            "from a LOCAL EHG runtime-metadata extraction. Not committed as "
            "APK-derived data; review and prune before merging."
        ),
        "_generated_by": "convert_dan_metadata.py",
        "_source_vehicle_id": vehicle_id or "unspecified",
        "_doc": (
            "Auto-generated entries are conservative: read-only slots only by "
            "default. Switches require explicit known_writable + control_catalog "
            "entry. Climate/fridge/boiler are NOT auto-emitted; see "
            "_climate_templates_required."
        ),
        "sensors":  {},
        "lights":   {},
        "switches": {},
        "_climate_templates_required": [],
    }

    # Per-vehicle support map (optional).
    vehicle_support: dict[str, str] = {}
    if vehicle_id and vehicle_id in md.support_matrix:
        vehicle_support = md.support_matrix[vehicle_id]

    # Build per-bus light grouping first so we can emit `lights` properly.
    light_buses: dict[str, list[tuple[int, dict[str, Any]]]] = {}

    name_key     = SCHEMA_MAP["sensor_labels"]["name"]
    datatype_key = SCHEMA_MAP["sensor_labels"]["datatype"]
    unit_key     = SCHEMA_MAP["sensor_labels"]["unit"]
    mode_key     = SCHEMA_MAP["sensor_labels"]["mode"]
    transform_key= SCHEMA_MAP["sensor_labels"]["transform"]
    kind_key     = SCHEMA_MAP["component_kinds"]["kind"]

    # Track which buses we've already inserted a climate marker for.
    climate_marked: set[str] = set()

    for slot, label in sorted(md.sensor_labels.items(), key=_slot_sort_key):
        try:
            bus_str, sid_str = slot.split(",", 1)
            bus = int(bus_str)
            sid = int(sid_str)
        except ValueError:
            # Skip malformed slot keys but keep going.
            continue

        coverage = vehicle_support.get(slot) or md.coverage_audit.get(slot, COV_INFERRED)

        if coverage == COV_SUPPRESSED:
            stats.suppressed_skipped += 1
            continue

        kind_entry = md.component_kinds.get(str(bus), {})
        kind = kind_entry.get(kind_key, "sensor")

        # Climate-class buses get a single placeholder marker, no auto entries.
        if kind in CLIMATE_KINDS:
            if str(bus) not in climate_marked:
                overlay["_climate_templates_required"].append({
                    "bus": bus,
                    "kind": kind,
                    "note": (
                        f"Bus {bus} is a {kind!r} component. Hand-port a template "
                        f"from sensor_maps/hymer.json -> climate section. Do NOT "
                        f"trust auto-generated raw slots for safety-critical "
                        f"controls."
                    ),
                })
                climate_marked.add(str(bus))
                stats.climate_markers += 1
            continue

        name      = label[name_key]
        datatype  = label.get(datatype_key)
        unit      = label.get(unit_key)
        mode      = label.get(mode_key, "read")
        transform = label.get(transform_key)

        # ---- LIGHTS: group SIDs 1/2/3 per bus -------------------------------
        if kind == KIND_LIGHT:
            light_buses.setdefault(str(bus), []).append((sid, label))
            continue

        # ---- SWITCHES: only when writable AND in control_catalog ------------
        ctrl = md.control_catalog.get(slot)
        is_writable = mode in ("write", "read_write") and coverage == COV_KNOWN_RW
        if kind == KIND_SWITCH or (is_writable and ctrl):
            if not ctrl:
                # Writable per coverage but no explicit control semantics --
                # emit as opt-in only.
                if include_inferred:
                    overlay["switches"][slot] = _build_switch(
                        name, ctrl=None, inferred=True
                    )
                    stats.inferred_disabled += 1
                continue
            if not is_writable:
                # Has control entry but coverage doesn't confirm writable --
                # opt-in only.
                if include_inferred:
                    overlay["switches"][slot] = _build_switch(
                        name, ctrl=ctrl, inferred=True
                    )
                    stats.inferred_disabled += 1
                continue
            overlay["switches"][slot] = _build_switch(name, ctrl=ctrl, inferred=False)
            stats.switches_emitted += 1
            continue

        # ---- READ-ONLY SENSORS / BINARY SENSORS -----------------------------
        if coverage == COV_INFERRED and not include_inferred:
            continue

        sensor_entry = _build_sensor(name, datatype, unit, transform)
        if coverage == COV_INFERRED:
            sensor_entry["enabled"] = False
            sensor_entry["_inferred"] = True
            stats.inferred_disabled += 1
        elif sensor_entry.get("platform") == "binary_sensor":
            stats.binary_sensors_emitted += 1
        else:
            stats.sensors_emitted += 1

        overlay["sensors"][slot] = sensor_entry

    # ---- Emit grouped lights ------------------------------------------------
    for bus, slots in sorted(light_buses.items(), key=lambda kv: int(kv[0])):
        sid_map = {sid: lbl for sid, lbl in slots}
        # Use the SID-1 label name as the canonical light name; fall back to any.
        canonical = sid_map.get(LIGHT_SID_ONOFF) or next(iter(sid_map.values()))
        light_entry: dict[str, Any] = {
            "name": canonical[name_key],
            "icon": "mdi:lightbulb",
            "brightness": LIGHT_SID_BRIGHTNESS in sid_map,
            "color_temp": LIGHT_SID_COLOR_TEMP in sid_map,
        }
        overlay["lights"][bus] = light_entry
        stats.lights_emitted += 1

    # Drop empty top-level sections so the diff against base.json is minimal.
    for k in ("sensors", "lights", "switches", "_climate_templates_required"):
        if not overlay[k]:
            del overlay[k]

    return overlay, stats


def _slot_sort_key(item: tuple[str, Any]) -> tuple[int, int]:
    """Sort slot keys '<bus>,<sid>' numerically; malformed keys sort last."""
    try:
        bus, sid = item[0].split(",", 1)
        return (int(bus), int(sid))
    except (ValueError, AttributeError):
        return (10**9, 10**9)


def _build_sensor(
    name: str,
    datatype: str | None,
    unit: str | None,
    transform: str | None,
) -> dict[str, Any]:
    """Build a sensor / binary_sensor entry from upstream-side field values."""
    base = DATATYPE_PLATFORM.get(datatype or "string", {"platform": "sensor"}).copy()
    entry: dict[str, Any] = {"name": name}
    entry.update(base)

    if unit:
        entry["unit"] = unit
        dc = UNIT_DEVICE_CLASS.get(unit)
        if dc:
            entry["device_class"] = dc

    if transform:
        entry["transform"] = transform

    if entry.get("platform") == "binary_sensor":
        # Strip sensor-only keys that don't apply to binary_sensor.
        entry.pop("state_class", None)
        entry.pop("unit", None)
        entry.pop("device_class", None)  # bool device_class is rarely correct from unit

    return entry


def _build_switch(
    name: str,
    *,
    ctrl: dict[str, Any] | None,
    inferred: bool,
) -> dict[str, Any]:
    """Build a switch entry. If `ctrl` is None, emit a stub the user must fill."""
    entry: dict[str, Any] = {
        "name": name,
        "icon": "mdi:toggle-switch",
    }
    wt_key = SCHEMA_MAP["control_catalog"]["write_type"]
    on_key = SCHEMA_MAP["control_catalog"]["on_value"]
    off_key= SCHEMA_MAP["control_catalog"]["off_value"]
    rp_key = SCHEMA_MAP["control_catalog"]["read_path"]

    if ctrl:
        if wt_key in ctrl:
            entry["write_type"] = ctrl[wt_key]
        if on_key in ctrl:
            entry["on_value"] = ctrl[on_key]
            entry["write_on"] = ctrl[on_key]
        if off_key in ctrl:
            entry["write_off"] = ctrl[off_key]
        if rp_key in ctrl:
            entry["read_path"] = ctrl[rp_key]
    else:
        entry["_TODO"] = "control_catalog had no entry; fill write semantics manually."

    if inferred:
        entry["enabled"] = False
        entry["_inferred"] = True

    return entry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_convert(args: argparse.Namespace) -> int:
    md = load_metadata(Path(args.input))
    overlay, stats = convert(
        md,
        brand=args.brand,
        vehicle_id=args.vehicle_id,
        include_inferred=args.include_inferred,
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(overlay, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"Wrote {out_path}", file=sys.stderr)
    print(_format_stats(stats), file=sys.stderr)
    return 0


def _format_stats(s: ConvertStats) -> str:
    return (
        f"  sensors:        {s.sensors_emitted}\n"
        f"  binary_sensors: {s.binary_sensors_emitted}\n"
        f"  lights:         {s.lights_emitted}\n"
        f"  switches:       {s.switches_emitted}\n"
        f"  inferred(off):  {s.inferred_disabled}\n"
        f"  suppressed:     {s.suppressed_skipped}\n"
        f"  climate marks:  {s.climate_markers}"
    )


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="convert_dan_metadata",
        description=(
            "Convert a LOCAL EHG runtime-metadata extraction directory "
            "into a hymer-connect-ha brand overlay JSON. Never run this against "
            "files committed to git -- the input must be your own local APK "
            "extraction output."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("convert", help="Convert a metadata directory.")
    c.add_argument("--input", "-i", required=True,
                   help="Path to your local upstream metadata directory.")
    c.add_argument("--output", "-o", required=True,
                   help="Path to write the overlay JSON (e.g. sensor_maps/buerstner.json).")
    c.add_argument("--brand", "-b", required=True,
                   help="Brand slug for the overlay header (e.g. 'buerstner').")
    c.add_argument("--vehicle-id", default=None,
                   help="Optional support_matrix vehicle id to scope writability.")
    c.add_argument("--include-inferred", action="store_true",
                   help="Emit inferred slots as disabled entries instead of skipping.")
    c.set_defaults(func=_cli_convert)

    s = sub.add_parser("self-test",
                       help="Run an in-memory round-trip with synthetic fixtures.")
    s.set_defaults(func=lambda _a: _self_test())

    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_argparser().parse_args(list(argv) if argv is not None else None)
    return args.func(args)


# ---------------------------------------------------------------------------
# Self-test (synthetic fixtures only -- no APK-derived data in this repo)
# ---------------------------------------------------------------------------

SYNTHETIC_FIXTURES: dict[str, Any] = {
    "sensor_labels": {
        # Read-only universal sensor.
        "1,1": {"name": "odometer", "datatype": "uint16", "unit": "km", "mode": "read"},
        # Boolean read-only -> binary_sensor.
        "3,1": {"name": "main_switch_state", "datatype": "bool", "mode": "read"},
        # Light bus (kind=light) with on/off + brightness.
        "11,1": {"name": "light_living_ceiling", "datatype": "bool", "mode": "read_write"},
        "11,2": {"name": "light_living_ceiling_brightness", "datatype": "uint8",
                 "unit": "%", "mode": "read_write"},
        # Writable switch with control_catalog entry -> switches.
        "34,2": {"name": "fridge_eco_ctrl", "datatype": "bool", "mode": "read_write"},
        # Inferred slot -> skipped unless --include-inferred.
        "99,9": {"name": "mystery_inferred", "datatype": "uint8", "mode": "read"},
        # Suppressed slot -> always skipped.
        "99,99": {"name": "should_not_appear", "datatype": "uint8", "mode": "read"},
        # Climate (heater) bus -> emits marker only.
        "58,8": {"name": "heater_setpoint", "datatype": "uint8", "unit": "°C",
                 "mode": "read_write"},
    },
    "component_kinds": {
        "1":  {"kind": "sensor"},
        "3":  {"kind": "sensor"},
        "11": {"kind": "light"},
        "34": {"kind": "switch"},
        "58": {"kind": "heater"},
        "99": {"kind": "sensor"},
    },
    "control_catalog": {
        "34,2": {"write_type": "bool", "on_value": True, "off_value": False,
                 "read_path": "signalr_sensors.fridge_eco"},
    },
    "coverage_audit": {
        "1,1":   COV_KNOWN_RO,
        "3,1":   COV_KNOWN_RO,
        "11,1":  COV_KNOWN_RW,
        "11,2":  COV_KNOWN_RW,
        "34,2":  COV_KNOWN_RW,
        "99,9":  COV_INFERRED,
        "99,99": COV_SUPPRESSED,
        "58,8":  COV_KNOWN_RW,
    },
    "support_matrix": {},
    "vehicle_catalog": {},
}


def _self_test() -> int:
    """Run conversion against in-memory synthetic fixtures and assert invariants."""
    md = ExtractionMetadata(**SYNTHETIC_FIXTURES)  # type: ignore[arg-type]
    _validate_required_fields(md)

    overlay, stats = convert(md, brand="synthetic", include_inferred=False)

    failures: list[str] = []

    def expect(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # Conservative defaults: inferred and suppressed are absent.
    expect("99,9" not in overlay.get("sensors", {}),
           "inferred slot 99,9 should be skipped without --include-inferred")
    expect("99,99" not in overlay.get("sensors", {}),
           "suppressed slot 99,99 must always be skipped")

    # Read-only sensors are emitted.
    expect("1,1" in overlay.get("sensors", {}),
           "odometer (1,1) should be emitted as sensor")
    expect(overlay["sensors"]["1,1"].get("platform") == "sensor",
           "1,1 should be platform=sensor")
    expect(overlay["sensors"]["1,1"].get("device_class") == "distance",
           "1,1 with unit km should map device_class=distance")

    expect(overlay["sensors"]["3,1"].get("platform") == "binary_sensor",
           "3,1 datatype=bool should map to binary_sensor")
    expect("unit" not in overlay["sensors"]["3,1"],
           "binary_sensor entries should not carry unit")

    # Lights grouped by bus, brightness flag detected.
    expect("11" in overlay.get("lights", {}),
           "bus 11 should appear under lights")
    expect(overlay["lights"]["11"].get("brightness") is True,
           "bus 11 should have brightness=true (sid 2 present)")
    expect(overlay["lights"]["11"].get("color_temp") is False,
           "bus 11 should have color_temp=false (no sid 3)")

    # Switch with control entry emitted with semantics.
    expect("34,2" in overlay.get("switches", {}),
           "writable 34,2 with control_catalog entry should be a switch")
    sw = overlay["switches"]["34,2"]
    expect(sw.get("write_type") == "bool", "switch write_type should be bool")
    expect(sw.get("on_value") is True, "switch on_value should be True")
    expect(sw.get("read_path") == "signalr_sensors.fridge_eco",
           "switch read_path should pass through")

    # Climate bus produces marker, not raw entries.
    markers = overlay.get("_climate_templates_required", [])
    expect(any(m["bus"] == 58 for m in markers),
           "heater bus 58 should produce a climate template marker")
    expect("58,8" not in overlay.get("sensors", {}),
           "heater slot 58,8 must not be auto-emitted as raw sensor")

    # Stats sanity.
    expect(stats.sensors_emitted >= 1, "expected at least one sensor")
    expect(stats.lights_emitted == 1, "expected exactly one light bus")
    expect(stats.switches_emitted == 1, "expected exactly one switch")
    expect(stats.suppressed_skipped == 1, "expected one suppressed skip")
    expect(stats.climate_markers == 1, "expected one climate marker")

    # --include-inferred mode surfaces inferred sensors as disabled.
    overlay2, stats2 = convert(md, brand="synthetic", include_inferred=True)
    expect("99,9" in overlay2.get("sensors", {}),
           "inferred slot 99,9 should appear when --include-inferred is set")
    expect(overlay2["sensors"]["99,9"].get("enabled") is False,
           "inferred sensor must be enabled=false")
    expect(overlay2["sensors"]["99,9"].get("_inferred") is True,
           "inferred sensor must carry _inferred=true marker")
    expect(stats2.inferred_disabled >= 1, "expected at least one inferred entry")

    if failures:
        print("SELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("SELF-TEST PASSED", file=sys.stderr)
    print(_format_stats(stats), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
