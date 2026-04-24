# HYMER Connect Dashboard

A ready-to-use, mobile-friendly Lovelace dashboard is shipped with this integration as [`hymer_connect.yaml`](./hymer_connect.yaml). It uses **only stock Home Assistant tile cards** — no HACS frontend cards required.

## Installation

1. Copy or link [`hymer_connect.yaml`](./hymer_connect.yaml) into your Home Assistant config
2. **Settings → Dashboards → + Add dashboard → From YAML file**, point it at the file
   *or* paste the contents into a new dashboard via **Edit dashboard → Raw configuration editor**
3. Open the dashboard — all entities resolve automatically because the integration uses stable, predictable entity IDs (`sensor.hymer_*`, `light.hymer_*`, etc.)

> **Prerequisite**: Home Assistant 2022.11+ for tile card support.

## Dashboard Tabs (9 views)

| Tab | Content |
|-----|---------|
| **Overview** | Battery + water gauges, quick toggles (12V, pump, lock, SCU), thermostat, map |
| **Energy** | Solar production, charge phase, charger active, BMS metrics |
| **Power** | Battery details, 12V/main switch, BMS pack, solar power |
| **Climate** | Truma thermostat, fan speed, energy source select, boiler mode, fridge cooling step |
| **Water** | Fresh + grey water gauges, water pump, EBL diagnostic card |
| **Vehicle** | Model info, fuel/AdBlue, odometer, distance to service, outside temperature, ignition, fuel consumption + range |
| **Doors** | Driver/passenger door state, lock state, parking brake, chassis flags |
| **Lights** | All 8 interior lights + LED bar + the two native SCU group lights |
| **GPS** | Map, coordinates, altitude, satellites, signal quality, heading |
| **System** | SCU + Truma firmware, LTE/BT telemetry, tyre pressure, **SCU restart button** |

## Light Entities (provided by the integration)

Entity IDs are predictable and brand-agnostic — no per-install suffix is needed.

| Entity ID | Light | Features |
|-----------|-------|----------|
| `light.hymer` | Outside LED bar (bus 25) | On/Off, Brightness |
| `light.hymer_living_ceiling` | Living ceiling | On/Off, Brightness |
| `light.hymer_living_ambient` | Living ambient | On/Off, Brightness, Color Temp |
| `light.hymer_kitchen` | Kitchen | On/Off, Brightness, Color Temp |
| `light.hymer_seating_overhead` | Seating overhead | On/Off, Brightness |
| `light.hymer_bedroom_ambient` | Bedroom ambient | On/Off, Brightness, Color Temp |
| `light.hymer_night_light` | Night light | On/Off, Brightness |
| `light.hymer_bathroom_ceiling` | Bathroom ceiling | On/Off, Brightness |
| `light.hymer_bedroom_overhead` | Bedroom overhead | On/Off, Brightness |
| `light.hymer_wohnen_all_lights` | **Native SCU group**: All Wohnen (bus 24) | On/Off, Brightness, Color Temp |
| `light.hymer_privat_all_lights` | **Native SCU group**: All Privat (bus 27) | On/Off, Brightness, Color Temp |

> **Native SCU light groups (since v2.26.0)**: The two `*_all_lights` entities are not Home Assistant `light.group` helpers — they map directly onto the SCU bus 24/27 hardware group endpoints, the same ones the EHG app uses. They are reliable and respond instantly. You do **not** need to create your own HA light groups.

## 12V Main Switch — Availability Guard

When the **12V main switch** is turned off, all light entities and the water pump switch become **unavailable** in Home Assistant. Tile cards automatically gray them out and disable interaction — this prevents sending commands to components that won''t respond without habitation power.

| Entity | 12V Off | 12V On |
|--------|---------|--------|
| All lights (interior + LED bar + groups) | Grayed / unavailable | Active |
| Water pump | Grayed / unavailable | Active |
| 12V main switch | **Always active** | Active |
| Fridge (mode + ECO) | **Always active** | Active |
| Boiler | **Always active** | Active |
| Truma heater | **Always active** | Active |

> The fridge, boiler, and heater operate independently of the habitation 12V circuit.

## Energy Dashboard Integration

The HA [Energy dashboard](https://www.home-assistant.io/docs/energy/) requires sensors with specific attributes ([FAQ](https://www.home-assistant.io/docs/energy/faq/#troubleshooting-missing-entities)):

| Attribute | Power sensors | Energy sensors |
|-----------|--------------|----------------|
| `device_class` | `power` | `energy` |
| `state_class` | `measurement` | `total_increasing` |
| `unit_of_measurement` | `W` or `kW` | `Wh` or `kWh` |

The integration provides **power** sensors (W) but not energy sensors (kWh) — convert with HA''s built-in [Riemann Sum](https://www.home-assistant.io/integrations/integration/) helper.

### Creating a Solar Energy sensor (kWh)

**Option A: HA UI (recommended)**

1. **Settings → Devices & Services → Helpers**
2. **+ Create Helper → Integration - Riemann sum integral sensor**
3. Configure:
   - **Input sensor**: `sensor.hymer_solar_power`
   - **Integration method**: Left Riemann sum
   - **Metric prefix**: `k`
   - **Time unit**: Hours
   - **Name**: Hymer Solar Energy

The resulting `sensor.hymer_solar_energy` will have `device_class: energy`, `state_class: total_increasing`, `unit: kWh` — ready for the Energy dashboard.

**Option B: configuration.yaml**

```yaml
sensor:
  - platform: integration
    source: sensor.hymer_solar_power
    name: Hymer Solar Energy
    unique_id: hymer_solar_energy
    unit_prefix: k
    unit_time: h
    method: left
```

### Adding to the Energy Dashboard

1. **Energy** (sidebar) → **Configure**
2. Under **Solar Panels**, click **Add solar production**
3. Select `sensor.hymer_solar_energy`

> The Energy dashboard needs several hours of data before charts populate. Allow at least 24 hours after setup.

### Power sensors ready for Individual Devices

Already correctly attributed (`device_class: power`, `state_class: measurement`):

| Sensor | Unit | Description |
|--------|------|-------------|
| `sensor.hymer_solar_power` | W | Solar output (voltage × current) |
| `sensor.hymer_heater_electric_power` | W | Truma electric element (0/900/1800 W) |

## Stale CAN sensor workarounds

The Hymer SCU caches the last value received from the Mercedes CAN bus. When the engine is turned off, the CAN bus goes silent without sending a final "off" update, so a few sensors hold stale values (e.g. `binary_sensor.hymer_engine` stays `on` while parked).

### Corrected engine running template

Add this template to `configuration.yaml` (or a packages file):

```yaml
template:
  - binary_sensor:
      - name: "Hymer Engine Running (Corrected)"
        unique_id: hymer_engine_running_corrected
        device_class: running
        icon: mdi:engine
        state: >
          {% set ignition = states('sensor.hymer_ignition_state') %}
          {% set engine_raw = is_state('binary_sensor.hymer_engine_running', 'on') %}
          {% if ignition in ['Off', 'Accessory'] %}
            false
          {% else %}
            {{ engine_raw }}
          {% endif %}
        availability: >
          {{ states('sensor.hymer_ignition_state') not in ['unknown', 'unavailable'] }}
```

| Condition | Result |
|-----------|--------|
| Ignition is `Off` or `Accessory` | Engine forced to **Off** |
| Otherwise | Uses raw `binary_sensor.hymer_engine_running` |

Then in your dashboard:

```yaml
# Before (shows stale "on" while parked)
- entity: binary_sensor.hymer_engine_running
  name: Engine Running

# After (correctly shows "off" when ignition is off)
- entity: binary_sensor.hymer_engine_running_corrected
  name: Engine Running
```

> **Tip**: hide the original raw `binary_sensor.hymer_engine_running` via **Settings → Devices & Services → Entities** so it does not clutter the UI.

### Known stale CAN sensors without an obvious override

| Sensor | Why no override |
|--------|-----------------|
| **DPF Status** | Binary status (`Normal`/`Regeneration`), not a soot percentage. `Normal` is correct most of the time; only changes during an active regeneration cycle. The Mercedes service-menu soot percentage is a different CAN signal not exposed by the SCU. |
| **Coolant Temperature** | Drops gradually after engine off; the cached value goes stale slowly but a hard override is not appropriate. |

## Dynamic Slot Discovery (v2.34.0+)

The integration auto-creates a generic, **disabled-by-default** diagnostic sensor (`Discovered bus N slot M`) for every PIA `(bus, slot)` pair the SCU reports that is not already in the named-sensor map.

Useful especially for **non-HYMER EHG brands** (Eriba, Bürstner, Dethleffs, LMC, Niesmann+Bischoff, Sunlight, Carado, Laika, FreeOnTour) where the slot map may have gaps. See the main [README](../README.md#-dynamic-slot-discovery-v2340) for details and how to contribute mappings back upstream.
