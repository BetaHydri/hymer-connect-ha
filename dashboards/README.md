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
