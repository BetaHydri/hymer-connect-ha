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
          {% set ignition = states('sensor.hymer_hymer_connect_hymer_6') %}
          {% set locked = is_state('binary_sensor.hymer_hymer_connect_hymer_lock', 'on') %}
          {% set engine_raw = is_state('binary_sensor.hymer_hymer_connect_hymer_betriebszustand', 'on') %}
          {% if ignition in ['Off', 'Accessory'] or locked %}
            false
          {% else %}
            {{ engine_raw }}
          {% endif %}
        availability: >
          {{ states('sensor.hymer_hymer_connect_hymer_6') not in ['unknown', 'unavailable'] }}
```

**How it works:**

| Condition | Result |
|-----------|--------|
| Ignition is "Off" or "Accessory" | Engine forced to **Off** |
| Vehicle is locked | Engine forced to **Off** |
| Otherwise | Uses the raw `engine_running` value |

Then replace the entity in your dashboard:

```yaml
# Before
- entity: binary_sensor.hymer_hymer_connect_hymer_betriebszustand
  name: Engine Running

# After
- entity: binary_sensor.hymer_engine_running_corrected
  name: Engine Running
```

### Corrected speed, RPM, and engine torque templates

The same caching issue affects driving sensors. Speed, RPM, and engine
torque keep their last CAN value after the engine is turned off
(for example, showing 73 km/h and 1670 RPM while parked).

These can be created either via `configuration.yaml` or via the HA UI
(**Settings > Devices & Services > Helpers > Template**).

> **Important:** When creating template sensors via the HA UI, you must
> use compact single-line templates. The multiline YAML `>` format
> causes whitespace in the output, making numeric sensors show
> "Unknown" (Unbekannt).

#### Option A: HA UI helpers (recommended)

Create each sensor via **Settings > Helpers > + Create Helper >
Template > Template a sensor**. Use the following single-line
templates:

**Hymer Speed (Corrected):**

- Unit of measurement: `km/h`
- Device class: Speed
- State template:

```jinja
{% if states('sensor.hymer_hymer_connect_hymer_6') in ['Off', 'Accessory'] %}0{% else %}{{ states('sensor.hymer_hymer_connect_hymer_geschwindigkeit') }}{% endif %}
```

**Hymer RPM (Corrected):**

- Unit of measurement: `rpm`
- State template:

```jinja
{% if states('sensor.hymer_hymer_connect_hymer_6') in ['Off', 'Accessory'] %}0{% else %}{{ states('sensor.hymer_hymer_connect_hymer_5') }}{% endif %}
```

**Hymer Engine Torque (Corrected):**

- Unit of measurement: `%`
- State template:

```jinja
{% if states('sensor.hymer_hymer_connect_hymer_6') in ['Off', 'Accessory'] %}0{% else %}{{ states('sensor.hymer_hymer_connect_hymer_25') }}{% endif %}
```

**Availability template** (same for all three):

```jinja
{{ states('sensor.hymer_hymer_connect_hymer_6') not in ['unknown', 'unavailable'] }}
```

#### Option B: configuration.yaml

If you prefer YAML configuration, add these to your
`configuration.yaml`. Note the compact template format without extra
whitespace:

```yaml
template:
  - sensor:
      - name: "Hymer Speed (Corrected)"
        unique_id: hymer_speed_corrected
        device_class: speed
        unit_of_measurement: "km/h"
        icon: mdi:speedometer
        state: "{% if states('sensor.hymer_hymer_connect_hymer_6') in ['Off', 'Accessory'] %}0{% else %}{{ states('sensor.hymer_hymer_connect_hymer_geschwindigkeit') }}{% endif %}"
        availability: "{{ states('sensor.hymer_hymer_connect_hymer_6') not in ['unknown', 'unavailable'] }}"

      - name: "Hymer RPM (Corrected)"
        unique_id: hymer_rpm_corrected
        unit_of_measurement: "rpm"
        icon: mdi:engine
        state: "{% if states('sensor.hymer_hymer_connect_hymer_6') in ['Off', 'Accessory'] %}0{% else %}{{ states('sensor.hymer_hymer_connect_hymer_5') }}{% endif %}"
        availability: "{{ states('sensor.hymer_hymer_connect_hymer_6') not in ['unknown', 'unavailable'] }}"

      - name: "Hymer Engine Torque (Corrected)"
        unique_id: hymer_engine_torque_corrected
        unit_of_measurement: "%"
        icon: mdi:engine
        state: "{% if states('sensor.hymer_hymer_connect_hymer_6') in ['Off', 'Accessory'] %}0{% else %}{{ states('sensor.hymer_hymer_connect_hymer_25') }}{% endif %}"
        availability: "{{ states('sensor.hymer_hymer_connect_hymer_6') not in ['unknown', 'unavailable'] }}"
```

Then replace the entities in your dashboard:

| Original entity | Corrected entity |
|-----------------|------------------|
| `sensor.hymer_hymer_connect_hymer_geschwindigkeit` | `sensor.hymer_speed_corrected` |
| `sensor.hymer_hymer_connect_hymer_5` | `sensor.hymer_rpm_corrected` |
| `sensor.hymer_hymer_connect_hymer_25` | `sensor.hymer_engine_torque_corrected` |

> **Tip:** You can hide the original stale entities via
> **Settings > Devices & Services > Entities** (toggle "Visible" off)
> so they do not clutter your UI.

### Known stale CAN sensors without workaround

Some CAN bus sensors are cached by the SCU but cannot be corrected
with a simple template override because their value is meaningful even
when the engine is off:

| Sensor | Why no override |
|--------|-----------------|
| **DPF Status** | Soot load level persists after engine shutdown. The cached value may be outdated (for example, `0%` while the Mercedes service menu shows ~33%), but forcing it to `0` would not be correct either. This value only updates while the engine is running. The unit has been corrected to `%` in the integration (v2.6+). |
| **Coolant Temperature** | Temperature drops gradually; the cached value becomes stale over time but a hard override is not appropriate. |
