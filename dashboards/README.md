# Dashboard Setup

## Lights Dashboard

The lights dashboard page must be configured manually in Home Assistant.

### Light Entities (provided by the integration)

| Entity | Light | Features |
|--------|-------|----------|
| `light.hymer_*_light_living_ceiling` | Living ceiling | On/Off, Brightness |
| `light.hymer_*_light_living_ambient` | Living ambient | On/Off, Brightness, Color Temp |
| `light.hymer_*_light_kitchen` | Kitchen | On/Off, Brightness, Color Temp |
| `light.hymer_*_light_seating_overhead` | Seating overhead | On/Off, Brightness |
| `light.hymer_*_light_bedroom_ambient` | Bedroom ambient | On/Off, Brightness, Color Temp |
| `light.hymer_*_light_nightlight` | Night light | On/Off, Brightness |
| `light.hymer_*_light_bathroom_ceiling` | Bathroom ceiling | On/Off, Brightness |
| `light.hymer_*_light_bedroom_overhead` | Bedroom overhead | On/Off, Brightness |

> Replace `*` with your integration's unique ID (e.g. `hymer_hymer_connect_hymer`).

### 12V Main Switch — Availability Guard

When the **12V main switch** is turned off, all light entities and the water pump switch become **unavailable** in Home Assistant. Dashboard tile cards automatically gray them out and disable interaction — this prevents sending commands to components that won't respond without habitation power.

| Entity | 12V Off | 12V On |
|--------|---------|--------|
| All lights (ceiling, ambient, kitchen, etc.) | Grayed out / unavailable | Active / controllable |
| Water pump | Grayed out / unavailable | Active / controllable |
| 12V main switch | **Always active** | Active |
| Fridge (mode + ECO) | **Always active** | Active |
| Boiler | **Always active** | Active |
| Truma heater | **Always active** | Active |

> The fridge, boiler, and heater operate independently of the habitation 12V circuit and remain controllable at all times.

### Creating Light Groups (optional)

To control multiple lights at once, create HA light groups:

1. Go to **Settings > Devices & Services > Helpers**
2. Click **+ Create Helper > Group > Light group**
3. Name it (e.g. "All Wohnen") and select the lights to include

**Suggested groups:**

| Group | Lights |
|-------|--------|
| All Wohnen | Living ceiling, Living ambient, Kitchen, Seating overhead |
| All Privat | Bedroom ambient, Night light, Bathroom ceiling, Bedroom overhead |
| All Lights | All 8 lights |

> **Note:** Previous versions (before v2.5.4) included hardware group switches
> (All Wohnen bus 24, All Privat bus 15) as light entities. These were removed
> because they used SCU hardware toggles that behaved unpredictably. HA light
> groups provide reliable, predictable group control.

## Energy Dashboard Integration

The HA [Energy dashboard](https://www.home-assistant.io/docs/energy/) requires sensors with specific attributes to appear in the entity picker ([FAQ](https://www.home-assistant.io/docs/energy/faq/#troubleshooting-missing-entities)):

| Attribute | Power sensors | Energy sensors |
|-----------|--------------|----------------|
| `device_class` | `power` | `energy` |
| `state_class` | `measurement` | `total_increasing` |
| `unit_of_measurement` | `W` or `kW` | `Wh` or `kWh` |

The integration provides **power** sensors (`solar_power` in W, `heater_electric_power` in W) but not energy sensors. The Energy dashboard's **Solar Panels** section requires an energy sensor (kWh).

### Creating a Solar Energy sensor (Riemann Sum)

Use HA's built-in [Integration - Riemann Sum](https://www.home-assistant.io/integrations/integration/) helper to convert `solar_power` (W) into cumulative energy (kWh):

**Option A: HA UI (recommended)**

1. Go to **Settings > Devices & Services > Helpers**
2. Click **+ Create Helper > Integration - Riemann sum integral sensor**
3. Configure:
   - **Input sensor**: `sensor.hymer_solar_power`
   - **Integration method**: Left Riemann sum
   - **Metric prefix**: `k` (kilo)
   - **Time unit**: Hours
   - **Name**: Hymer Solar Energy

The resulting `sensor.hymer_solar_energy` will have `device_class: energy`, `state_class: total_increasing`, and `unit: kWh` — ready for the Energy dashboard.

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

1. Go to **Energy** (sidebar) > **Configure**
2. Under **Solar Panels**, click **Add solar production**
3. Select `sensor.hymer_solar_energy`

> **Note:** The Energy dashboard needs several hours of data before it starts showing charts. Allow at least 24 hours after setup.

### Available power sensors (ready for individual device tracking)

These sensors already have the correct `device_class: power` and `state_class: measurement` attributes and can be used directly under **Individual Devices** in the Energy dashboard:

| Sensor | Unit | Description |
|--------|------|-------------|
| `sensor.hymer_solar_power` | W | Solar panel output (voltage × current) |
| `sensor.hymer_heater_electric_power` | W | Truma heater electric element (0/900/1800W) |

## Stale CAN sensor workarounds

The Hymer SCU caches the last value received from the Mercedes CAN bus.
When the engine is turned off, the CAN bus goes silent without sending
a final "off" update. This causes certain sensors to display stale
values (for example, "Engine Running" stays "On" even though the
vehicle is parked and locked).

### Corrected engine running template

Add the following template binary sensor to your `configuration.yaml`
(or a packages file). It cross-references ignition state and lock
status to override the stale cached engine value.

```yaml
template:
  - binary_sensor:
      - name: "Hymer Engine Running (Corrected)"
        unique_id: hymer_engine_running_corrected
        device_class: running
        icon: mdi:engine
        state: >
          {% set ignition = states('sensor.hymer_ignition') %}
          {% set locked = is_state('binary_sensor.hymer_lock', 'on') %}
          {% set engine_raw = is_state('binary_sensor.hymer_engine', 'on') %}
          {% if ignition in ['Off', 'Accessory'] or locked %}
            false
          {% else %}
            {{ engine_raw }}
          {% endif %}
        availability: >
          {{ states('sensor.hymer_ignition') not in ['unknown', 'unavailable'] }}
```

**How it works:**

| Condition | Result |
|-----------|--------|
| Ignition is "Off" or "Accessory" | Engine forced to **Off** |
| Vehicle is locked | Engine forced to **Off** |
| Otherwise | Uses the raw `engine_running` value |

Then replace the entity in your dashboard:

```yaml
# Before (shows stale "on" while parked)
- entity: binary_sensor.hymer_engine
  name: Engine Running

# After (correctly shows "off" when ignition is off)
- entity: binary_sensor.hymer_engine_running_corrected
  name: Engine Running
```

> **Tip:** You can hide the original stale `binary_sensor.hymer_engine` via
> **Settings > Devices & Services > Entities** (toggle "Visible" off)
> so it does not clutter your UI.

### Speed, RPM, and engine torque — not available on S600

On the Grand Canyon S600, the CAN bus slots that carry speed, RPM,
and engine torque on other models (e.g. S700) are mapped to different
sensors (`fuel_level`, `distance_to_service`). These driving sensors
are **not currently available** in the integration for the S600. If
they are identified and added in a future version, corrected template
sensors (like the engine running template above) should be created to
handle the stale CAN caching issue.

### Known stale CAN sensors without workaround

Some CAN bus sensors are cached by the SCU but cannot be corrected
with a simple template override because their value is meaningful even
when the engine is off:

| Sensor | Why no override |
|--------|-----------------|
| **DPF Status** | A binary status flag (`Normal` / `Regeneration`), not a soot load percentage. The value `0` ("Normal") is correct most of the time — it only changes to `1` ("Regeneration") during an active DPF regeneration cycle. The Mercedes service menu shows the actual soot load percentage, which is a different CAN signal not exposed by the Hymer SCU. |
| **Coolant Temperature** | Temperature drops gradually; the cached value becomes stale over time but a hard override is not appropriate. |
