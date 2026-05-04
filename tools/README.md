# Tools

Most files under `tools/` are local reverse-engineering scratchpads (mitmproxy
output, logcat dumps, dex extracts, APK inspection scripts, captured packets,
…) and are gitignored. Local trace artifacts produced by the scripts below
live under [`tools/traces/`](traces/) which is also gitignored. Only the items
listed in the table are shipped with the repository.

## Shipped scripts at a glance

| Script | Purpose | Run as |
| --- | --- | --- |
| [`Start-EhgTokenCapture.ps1`](Start-EhgTokenCapture.ps1) | One-click PowerShell wrapper around the mitmproxy capture: checks prerequisites (Python, mitmproxy, Node.js, apk-mitm), starts the proxy, prints connection instructions, and exits when the token + OAuth header are captured. **Use this on Windows.** | `pwsh tools\Start-EhgTokenCapture.ps1` |
| [`capture_ehg_token.py`](capture_ehg_token.py) | mitmproxy addon that scans intercepted HTTP/WebSocket traffic for the EHG Remote Access Refresh Token (`ett=access-refresh`) **and** the OAuth `Authorization: Basic <…>` client header. Saves both to `traces/captured_ehg_token.txt` / `traces/captured_oauth_basic_auth.txt` and auto-exits. **Use this directly on Linux/macOS.** | `mitmdump -s tools/capture_ehg_token.py --listen-port 8080` |
| [`discover_sensors.py`](discover_sensors.py) | Connects to the EHG cloud via SignalR using your captured token, subscribes to all PIA sensor data for a configurable window (default 120 s), and prints a complete `(bus_id, sensor_id) → value` table cross-referenced with the known sensor map. **Use this to identify unmapped slots on a non-S600 vehicle** before opening a brand-overlay PR. | `python tools/discover_sensors.py --duration 120` |
| [`convert_dan_metadata.py`](convert_dan_metadata.py) | Converts a *local* EHG runtime-metadata extraction directory (produced by [@dan-simms1's upstream extractor](https://github.com/dan-simms1/hymer-connect-ha)) into a starting `sensor_maps/<brand>.json` overlay. Detailed below. | `python tools/convert_dan_metadata.py self-test` |

The two capture scripts are alternatives — use the PowerShell wrapper on
Windows, or invoke the Python addon directly on Linux/macOS. Both write to
the same `traces/captured_*.txt` files.

## `convert_dan_metadata.py` — Brand overlay generator

Converts a **local** EHG runtime-metadata extraction directory — produced by
[HYMER Connect Metadata Edition](https://github.com/dan-simms1/hymer-connect-ha)
by [@dan-simms1](https://github.com/dan-simms1) — into a
[`sensor_maps/<brand>.json`](../custom_components/hymer_connect/sensor_maps/)
overlay file. This is intended for users whose vehicle is **not** a HYMER
Grand Canyon S 600 / S 700 (sub-brands such as Bürstner, Carado, Dethleffs,
Eriba variants, LMC, Laika, Niesmann+Bischoff, Sunlight, Freeontour, …) where
`hymer.json` does not match.

### Provenance rules

1. **You** lawfully obtain the EHG APK / bundle.
2. **You** run the upstream extractor's `prepare_runtime_metadata.py` locally
   (see
   [HYMER Connect Metadata Edition](https://github.com/dan-simms1/hymer-connect-ha))
   to produce a metadata directory containing `sensor_labels.json`,
   `component_kinds.json`, `control_catalog.json`, `coverage_audit.json`, and
   (optionally) `support_matrix.json` / `vehicle_catalog.json`.
3. **You** run this converter against that local directory to emit a brand
   overlay.
4. **Neither** the input metadata nor `oauth_client.json` may be committed to
   this repo. The `.gitignore` already blocks the common file names, but
   please double-check before opening a PR.

### Pin to a released tag of the upstream extractor

The upstream metadata format is reasonably stable but is not a public API.
Pin your extraction to a
[released tag](https://github.com/dan-simms1/hymer-connect-ha/releases)
rather than the upstream `main` branch so the field names this converter
expects remain valid. If the upstream project publishes a formal schema,
adjust `SCHEMA_MAP` at the top of
[`convert_dan_metadata.py`](convert_dan_metadata.py) in one place.

### Conservative emission policy

The converter intentionally emits a minimal, safe subset of the source
metadata:

| Coverage class | Output |
| --- | --- |
| `known_read_only` | `sensor` or `binary_sensor` (datatype-driven) |
| `known_writable` + `kind=light` | `lights` section |
| `known_writable` + `control_catalog` entry | `switches` section |
| `inferred` | skipped (or emitted with `enabled: false` if `--include-inferred`) |
| `suppressed` | always skipped |
| `kind` in {fridge, heater, boiler, ac} | **not** auto-emitted; a `_climate_templates_required` marker is written instead — hand-port from `sensor_maps/hymer.json` |

### Usage

```pwsh
# 1. Verify the converter logic on synthetic in-memory fixtures.
python tools\convert_dan_metadata.py self-test

# 2. Convert your own local extraction.
python tools\convert_dan_metadata.py convert `
    --input  C:\path\to\your\local\dan_metadata `
    --output custom_components\hymer_connect\sensor_maps\<brand>.json `
    --brand  <brand> `
    --vehicle-id <optional support_matrix key>
```

`--include-inferred` re-enables the conservative-skip behaviour for inferred
slots: they are emitted with `enabled: false` and `_inferred: true` so a
maintainer can review and promote individual entries.

### Reviewing the output before merging

The generated file is a **starting point**, not a final overlay:

* Re-name auto-generated entity ids to match the conventions in
  [`base.json`](../custom_components/hymer_connect/sensor_maps/base.json) and
  [`hymer.json`](../custom_components/hymer_connect/sensor_maps/hymer.json).
* Refine `device_class` / `icon` choices — the converter only applies the few
  unambiguous unit-to-class mappings.
* Fill in any `_climate_templates_required` entries by hand using the
  `truma_heater` / `fridge` blocks in `hymer.json` as a template.
* Test on a real vehicle (12 V on for passive sensors) before opening a PR.
* Strip the `_generated_by` and `_source_vehicle_id` header keys once you have
  curated the file.

### Credits

This converter consumes the metadata extraction tooling shipped with
[**HYMER Connect Metadata Edition**](https://github.com/dan-simms1/hymer-connect-ha)
by [@dan-simms1](https://github.com/dan-simms1) — a sibling Home Assistant
integration that uses the same EHG cloud stack with a metadata-driven
approach. This repository ships only the converter; it does not redistribute
any APK-derived data or vendor credentials. Users supply their own
extraction output locally before running the converter.
