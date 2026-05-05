# Tools

Only the items listed below are shipped with the repository. Everything else
under `tools/` (including local trace artifacts under `tools/traces/`) is
gitignored.

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
expects remain valid. The converter understands both the **legacy flat
schema** (early Dan-extractor releases) and the **v1.0.16+ wrapped schema**
(current). If the upstream project publishes a formal schema, adjust
`SCHEMA_MAP` and the `_normalize_*` helpers at the top of
[`convert_dan_metadata.py`](convert_dan_metadata.py) in one place.

### End-to-end workflow (validated 2026-05-05 against Dan-extractor v1.0.16)

Follow these steps to generate a `<brand>.json` overlay for your vehicle.
**Everything happens locally on your machine** — nothing is uploaded, and
none of the intermediate files may be committed back to this repo.

#### Prerequisites

* **Python 3.11+** on PATH (`python --version`). 3.14 is fine.
* **Git** to clone Dan's extractor.
* **A lawfully obtained EHG APK** for your vehicle's brand (`com.ehg.hymerconnect`,
  `com.ehg.dethleffsconnect`, `com.ehg.eribaconnect`, etc.). Confirm the
  package name on the official Google Play listing before downloading from a
  trusted mirror. The current EHG APK ships a **Hermes bytecode** bundle
  (~14 MB `index.android.bundle`).
* **Hermes decompiler** — install [`hermes-dec`](https://pypi.org/project/hermes-dec/)
  0.1.3 (the version Dan validated against; supports HBC v51–v99 including
  the v96 the current EHG APK ships):

  ```pwsh
  pip install hermes-dec==0.1.3
  ```

  This puts `hbc-decompiler.exe` (Windows) or `hbc-decompiler` (Linux/macOS)
  on PATH. Verify with `Get-Command hbc-decompiler` / `which hbc-decompiler`.
* **Disk space**: Hermes decompilation expands the 14 MB bytecode bundle to
  an ~80 MB pseudo-JS file in a temp work directory.
* **Time**: full decompile + extract takes a few minutes on a modern laptop.

#### Steps

1. **Clone Dan's extractor** to a local-only working folder (do **not** put
   it inside this repo's `tools/` tree if you intend to commit anything
   afterwards):

   ```pwsh
   git clone --depth 1 https://github.com/dan-simms1/hymer-connect-ha.git C:\work\dan-extractor
   cd C:\work\dan-extractor
   ```

2. **Run the metadata extraction** against your local APK, pointing at the
   `hbc-decompiler` from step Prerequisites:

   ```pwsh
   python scripts\prepare_runtime_metadata.py `
       --apk-path       C:\path\to\com.ehg.<brand>connect.apk `
       --hbc-decompiler (Get-Command hbc-decompiler).Source `
       --zip-out        C:\work\dan-extractor\runtime_metadata.zip
   ```

   This produces a `generated_data\` directory next to the script with eight
   JSON files (`sensor_labels.json`, `component_kinds.json`,
   `control_catalog.json`, `coverage_audit.json`, `vehicle_catalog.json`,
   `support_matrix.json`, `scenario_catalog.json`, `oauth_client.json`) plus
   a transfer zip.

   > **Windows users:** if the extractor crashes part-way with
   > `UnicodeDecodeError: 'charmap' codec can't decode byte 0x90`, edit the
   > two `bundle_path.open()` calls in `scripts/generate_cleanroom_registry.py`
   > and add `encoding="utf-8", errors="replace"`. Re-run with
   > `--bundle-js <work_dir>/runtime_metadata/bundle.js` to skip the slow
   > decompile step. (Reported upstream.)
   >
   > **Sensitive output:** `generated_data\oauth_client.json` contains the
   > app's OAuth client Basic-auth header. Treat it like a password — keep
   > it local, never commit, never share.

3. **Run this converter** against the extracted directory:

   ```pwsh
   python tools\convert_dan_metadata.py convert `
       --input  C:\work\dan-extractor\source\runtime_metadata\generated_data `
       --output custom_components\hymer_connect\sensor_maps\<brand>.json `
       --brand  <brand>
   ```

   The summary line will report how many sensors / lights / switches /
   climate markers it emitted.

4. **Curate the output** before opening a PR — see the next section.

5. **Clean up** the extractor work directory once you are done. The
   metadata, the pseudo-JS bundle, and `oauth_client.json` must never leave
   your machine.

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
| `kind` in {fridge, heater, boiler, ac, truma_heater, heater_neo, air_conditioner} | **not** auto-emitted; a `_climate_templates_required` marker is written instead — hand-port from `sensor_maps/hymer.json` |

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

The generated file is a **starting point**, not a final overlay. Treat it as a
candidate list of every (bus, slot) the EHG app *knows about* across the entire
brand catalog — your specific vehicle's SCU will only actually emit a subset,
and may map a different `kind` to a given bus number than the brand catalog
suggests. A typical converter output is 5–10× larger than the curated overlay
it should become.

#### Why curation is mandatory

The extractor reads the EHG app's *generic* vehicle / component catalog. Your
SCU's runtime behaviour is the only authoritative source of truth for:

* **which bus numbers actually exist** on your vehicle (the catalog lists every
  bus the app could ever encounter across all brands and model years),
* **what `kind` of component lives on each bus** (the catalog default may be
  generic where your SCU exposes a brand-specific module — e.g. a bus listed as
  generic `light` may actually drive a switch pad on your model),
* **which slot ids carry meaningful values** vs. firmware-reserved padding,
* **what units / scaling** the SCU actually transmits (the catalog often lists
  the *protocol* unit; the SCU may report a divided / converted value).

#### Recommended curation workflow

1. **Capture a live SCU dump** with the vehicle's 12 V on, using
   [`discover_sensors.py`](discover_sensors.py) for at least 120 seconds:

   ```pwsh
   python tools\discover_sensors.py --duration 120 > my_vehicle_dump.txt
   ```

2. **Cross-reference**: for every `(bus, sid)` in the generated overlay,
   confirm the same key appears in your live dump. **Delete every entry your
   SCU does not emit.** This is by far the largest cleanup step.

3. **Verify `kind` per bus**: open the live dump and compare the value pattern
   on each bus against the converter's `_climate_templates_required` markers
   and `kind` assumptions. If your vehicle has a Truma heater on bus 58 and the
   converter put a marker on bus 31 instead, **remove the wrong-bus marker and
   add the right-bus marker** before hand-porting the climate template.

4. **Re-name entities** to match the conventions in
   [`base.json`](../custom_components/hymer_connect/sensor_maps/base.json) and
   [`hymer.json`](../custom_components/hymer_connect/sensor_maps/hymer.json)
   (lower_snake_case, brand-prefix only when ambiguous, units in
   `unit_of_measurement` not in the name).

5. **Refine `device_class` / `state_class` / `icon`** — the converter only
   applies the few unambiguous unit-to-class mappings (V/A/W/°C/km/L/bar/kPa).
   Percent, ratios, durations, counts, and enum-strings need a manual review.

6. **Fill in `_climate_templates_required` markers by hand** using the
   `truma_heater` / `fridge` blocks in `hymer.json` as a template. The
   converter intentionally never auto-emits raw climate slots because guessing
   the wrong `target_temperature` or `mode` mapping for a heater is a safety
   issue.

7. **Validate switch write semantics**: any switch entry carrying
   `_inferred_from_platform` was synthesized from the v1.0.16+ control catalog
   shape, which only tells us "this slot is a switch" — not the actual on/off
   protocol values. Test each switch carefully against the EHG app's behaviour
   on a stationary vehicle before relying on it in an automation.

8. **Run the integration locally** with your edited overlay (drop it into
   `custom_components/hymer_connect/sensor_maps/<brand>.json`, restart Home
   Assistant) and confirm every entity gets a non-`unknown` value within ~60 s
   of 12 V on.

9. **Strip the converter header keys** (`_generated_by`, `_source_vehicle_id`,
   `_doc`, `_inferred_from_platform` markers) once you are satisfied — they
   are useful during curation but should not ship in the final overlay.

10. **Open a PR** with the curated `<brand>.json` only. Do **not** include the
    raw converter output, the extractor metadata directory, or any
    `oauth_client.json` file.

### Credits

This converter consumes the metadata extraction tooling shipped with
[**HYMER Connect Metadata Edition**](https://github.com/dan-simms1/hymer-connect-ha)
by [@dan-simms1](https://github.com/dan-simms1) — a sibling Home Assistant
integration that uses the same EHG cloud stack with a metadata-driven
approach. This repository ships only the converter; it does not redistribute
any APK-derived data or vendor credentials. Users supply their own
extraction output locally before running the converter.
