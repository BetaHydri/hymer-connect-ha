# The PIA protocol as observed on the wire

This note describes what the SCU<->cloud protocol looks like in practice.
Everything here is derived from mitmproxy captures of a real session
between the HYMER Connect mobile app and the `scc-appcomm` / Azure SignalR
endpoints. Nothing in this file is copied from the app binary; it
documents observable wire behaviour so future contributors can extend
the integration without having to rediscover the format.

## Transport

After the OAuth2 login and a two-step SignalR negotiate (see
`signalr_client.py`), the phone holds one WebSocket to the
`datahub` hub on `ehg-prod-signalr.service.signalr.net`. All live
sensor traffic travels over that single connection as SignalR-framed
JSON messages (record separator `\x1e`), type 1 invocations for
requests/responses and type 3 completions for ack.

Three invocation targets are observed in normal use:

| target | direction | purpose |
|--------|-----------|---------|
| `UpdateTokens` | client→server | authenticate the SignalR session using the short-lived remote-access token |
| `PiaRequest` | client→server | subscribe to sensors, or write a value to one |
| `PiaResponse` | server→client | deliver sensor values from the vehicle |

Every `PiaRequest` and `PiaResponse` carries a single base64 string
argument which is a protobuf-encoded blob.

## Outer wrapper (both directions)

The outer layer is a short header plus a nested payload:

```
field 2 (length-delimited) = wrapper {
    field 1 (varint)             = msg_id        (random per-message ID)
    field 2 (length-delim, utf8) = protocol tag  (e.g. "v0.32.0")
    field 3 (varint)             = epoch seconds
    field 4 (length-delim)       = payload       (sensor write list, or subscription)
}
```

Both subscription and write requests use the same wrapper. The
difference is what sits inside `field 4`.

## Sensor writes (PiaRequest to set a value)

The payload for a write is a list of sensor entries:

```
field 2 (length-delim) = entries {
    field 1 (length-delim) = entry {
        field 1 (varint)         = sensor_id
        field 2 (varint)         = bus_id
        field 3 (varint)         = unsigned int value     [if int]
        field 4 (length-delim)   = UTF-8 string value     [if string]
        field 5 (varint, 0/1)    = bool value             [if bool]
        field 6 (fixed32, LE f32)= IEEE-754 float value   [if float]
        field 7 (varint)         = signed int value       [if signed int]
    }
    field 1 (length-delim) = entry { ... }   # batched writes are allowed
    ...
}
```

Observations (each verified by byte-for-byte comparison with captured
app traffic on a 2025 Grand Canyon S700):

- Exactly one value field is populated per entry. The field number
  picks the datatype.
- Multi-entry payloads are accepted; the app uses them when a UI
  change needs to update more than one slot at once (e.g. changing a
  heater target temperature will also re-send the current energy
  source). Single-entry writes are equally valid.
- The varint in field 5 is `1` or `0`; no other values observed.
- Field 6 is a 32-bit little-endian IEEE-754 float — a write of
  20.0 °C produces bytes `35 00 00 a0 41`. A heater-off sentinel
  of −273.0 has also been observed at this slot.
- Field 4 strings are plain UTF-8; no length prefix beyond the
  standard protobuf length-delimited framing.

`build_sensor_write()` in `pia_decoder.py` implements this encoding
and has unit-tests against the captured hexes.

## Sensor subscriptions (PiaRequest without a value)

The initial subscription PiaRequest carries a nested list of
`(bus, sensor)` pairs only — no value — and asks the SCU to start
streaming those slots. The integration replays the captured subscription
blobs verbatim (`_PIA_REQUESTS` in `pia_decoder.py`); every
bus/sensor pair we ever see in a `PiaResponse` is one the app has
subscribed to.

## Sensor responses (PiaResponse)

The response payload has the same three layers of nesting but the
inner entries additionally carry a timestamp and sometimes a string
bus-name label:

```
entry {
    field 1 (varint)         = sensor_id
    field 2 (varint)         = bus_id
    field 3/4/5/6/7          = value (same mapping as writes)
    field 10 (length-delim)  = bus_name string (optional)
    field 11 (length-delim)  = per-entry metadata (timestamp etc.)
}
```

Unused sensor slots consistently return either:

- `field 3 = uint 100` as a placeholder — the SCU reports "100" on
  brightness and level slots when the underlying circuit/tank isn't
  populated on this vehicle. Reading 100 as a percent would be
  misleading; the integration filters it at decode time where known.
- Float sentinels `3276.8`, `32768.0`, `65535.0`, `6553.5` — these
  decode from 0x7FFF / 0xFFFF integer values; treated as
  "unavailable" by `pia_decoder._FLOAT_SENTINELS`.

## Component (bus) numbers

Every bus_id observed in `PiaResponse` corresponds to a component type
the SCU knows about (chassis signals, EBL electrical block, solar
charge controller, fridge, heater, light circuit, etc.). The same
bus number means the same component across vehicles — different
vehicles just report on different subsets of buses based on what's
actually installed. There is no "this vehicle model → these bus IDs"
table that this integration needs; the SCU simply starts streaming
whatever is present after the initial subscription.

The integration's `SENSOR_MAP` in `pia_decoder.py` records the
(bus, sensor) → (snake_case name, unit, transform) mapping that
yields values consistent with app UI readings. Each entry can be
independently verified by:

1. Running a mitmproxy capture alongside an app session.
2. Changing a single control in the app.
3. Noting which (bus, sensor) entry in the next `PiaResponse`
   changes value and how.

## Commands that aren't sensor writes

Not every SCU action is a sensor write. At least the following are
observed to use a different protobuf message type (`CommandRequestTopic`
in protocol terms, dispatched over a separate transport):

- Real-time mode toggle
- SCU restart (`cold` = true/false)
- Factory reset
- Bluetooth bonding reset
- Telemetry wipe
- Troubleshoot-report upload

Only restart is currently interesting for Home Assistant use; the
rest are either destructive or developer-only. Adding command-topic
support would need a new encoder and a new SignalR invocation target
— this is not yet wired up; a hook is left for it in the coordinator.

## What this implies for contributions

- A new entity for an existing sensor is trivial: find the
  `(bus, sensor)` in `SENSOR_MAP`, wire an entity to the resulting
  `signalr_sensors.<name>` key, done.
- A new control (switch/number/select/button) follows the pattern in
  the switch/number/select/button platforms: the entity knows its
  `(bus, sensor)` pair and calls `build_sensor_write(...)`.
- Finding a previously unmapped slot: look in `PiaResponse`
  decodings for `bus{N}_s{M}` unmapped fallbacks, correlate the value
  trajectory with something physical, and add a line to `SENSOR_MAP`.
