"""Discover all sensor/bus mappings from a live HYMER Connect SCU.

Connects to the EHG cloud via SignalR, subscribes to all PIA sensor data,
and builds a complete (bus_id, sensor_id) → value mapping table.
Cross-references with the known SENSOR_MAP and APK LightCircuit names.

Usage:
    Set environment variables:
        HYMER_USERNAME=your@email.com
        HYMER_PASSWORD=yourpassword
        HYMER_EHG_REFRESH_TOKEN=eyJraWQ...  (from mitmproxy capture)
    
    Then run:
        python discover_sensors.py [--duration 120]

    The script collects data for --duration seconds (default: 120),
    then prints a complete mapping table with mapped/unmapped status.

.AUTHOR Jan Tiedemann
.DATE 2026
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import argparse
from collections import defaultdict
from typing import Any

# Add parent directory to path so we can import the integration modules
# We import only standalone modules (api, pia_decoder, signalr_client, const)
# NOT __init__.py which requires homeassistant
_integration_dir = os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'hymer_connect')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components'))

# Prevent __init__.py from loading (it imports homeassistant)
import importlib
import types
# Create a dummy hymer_connect package that doesn't trigger __init__.py
hymer_pkg = types.ModuleType('hymer_connect')
hymer_pkg.__path__ = [os.path.abspath(_integration_dir)]
hymer_pkg.__package__ = 'hymer_connect'
sys.modules['hymer_connect'] = hymer_pkg

import aiohttp
from hymer_connect.api import HymerConnectApi
from hymer_connect.signalr_client import HymerSignalRClient
from hymer_connect.pia_decoder import SENSOR_MAP, decode_pia_payload
from hymer_connect.const import API_BASE_URL


class SensorDiscovery:
    """Discovers all available sensors from the SCU."""

    def __init__(self):
        self.all_sensors: dict[tuple[int, int], list[Any]] = defaultdict(list)
        self.sensor_types: dict[tuple[int, int], set[str]] = defaultdict(set)
        self.message_count = 0
        self.start_time = 0.0

    def on_sensor_update(self, sensor_data: dict[str, Any]) -> None:
        """Collect all sensor data from the decoded PIA responses.
        
        The pia_decoder names unmapped sensors as 'busN_sM' — we extract
        the bus_id and sensor_id from those keys to track them.
        """
        self.message_count += 1
        for key, value in sensor_data.items():
            if value is None:
                continue
            # Check if this is a mapped or unmapped sensor
            # Unmapped sensors have keys like 'bus43_s1'
            import re
            m = re.match(r'bus(\d+)_s(\d+)', key)
            if m:
                bus_id, sensor_id = int(m.group(1)), int(m.group(2))
                self.all_sensors[(bus_id, sensor_id)].append(value)
                self.sensor_types[(bus_id, sensor_id)].add(type(value).__name__)
            else:
                # Mapped sensor — reverse-lookup from SENSOR_MAP
                for (bus, sid), (name, _, _) in SENSOR_MAP.items():
                    if name == key:
                        self.all_sensors[(bus, sid)].append(value)
                        self.sensor_types[(bus, sid)].add(type(value).__name__)
                        break

    def print_results(self) -> None:
        """Print the complete sensor mapping table."""
        elapsed = time.monotonic() - self.start_time
        
        print("\n" + "=" * 90)
        print("  HYMER Connect SCU Sensor Discovery Results")
        print("  Duration: %.0f seconds, Messages received: %d" % (elapsed, self.message_count))
        print("  Total unique (bus_id, sensor_id) pairs: %d" % len(self.all_sensors))
        print("=" * 90)

        # Group by bus_id
        by_bus: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for key in sorted(self.all_sensors.keys()):
            by_bus[key[0]].append(key)

        mapped_count = 0
        unmapped_count = 0

        for bus_id in sorted(by_bus.keys()):
            sensors = by_bus[bus_id]
            print("\n  ── Bus %d ──" % bus_id)

            for key in sensors:
                bus, sid = key
                values = self.all_sensors[key]
                types = self.sensor_types[key]
                
                # Check if mapped
                mapped = SENSOR_MAP.get(key)
                if mapped:
                    name, unit, transform = mapped
                    status = "✅ MAPPED"
                    mapped_count += 1
                else:
                    name = "???"
                    unit = None
                    status = "❌ UNMAPPED"
                    unmapped_count += 1

                # Show latest value and type
                latest = values[-1] if values else "?"
                type_str = ", ".join(types) if types else "?"
                unit_str = " %s" % unit if unit else ""

                print("    (%2d, %2d)  %-35s  %s  value=%s%s  type=%s  samples=%d" % (
                    bus, sid, name, status, latest, unit_str, type_str, len(values)
                ))

        print("\n" + "-" * 90)
        print("  Summary: %d mapped, %d unmapped, %d total" % (
            mapped_count, unmapped_count, mapped_count + unmapped_count
        ))
        print("=" * 90)


async def main():
    parser = argparse.ArgumentParser(description="Discover HYMER Connect SCU sensors")
    parser.add_argument("--duration", type=int, default=120,
                        help="Collection duration in seconds (default: 120)")
    args = parser.parse_args()

    # Get credentials from environment
    username = os.environ.get("HYMER_USERNAME", "")
    password = os.environ.get("HYMER_PASSWORD", "")
    refresh_token = os.environ.get("HYMER_EHG_REFRESH_TOKEN", "")

    if not username or not password:
        print("ERROR: Set HYMER_USERNAME and HYMER_PASSWORD environment variables")
        print("  e.g.: $env:HYMER_USERNAME='your@email.com'")
        print("        $env:HYMER_PASSWORD='yourpassword'")
        sys.exit(1)

    if not refresh_token:
        # Try reading from file
        token_file = os.path.join(os.path.dirname(__file__), "captured_ehg_token.txt")
        if os.path.exists(token_file):
            refresh_token = open(token_file).read().strip()
            print("Loaded refresh token from %s" % token_file)

    if not refresh_token:
        print("WARNING: No EHG refresh token — sensor data will be limited")
        print("  Set HYMER_EHG_REFRESH_TOKEN or run the capture script first")

    discovery = SensorDiscovery()

    async with aiohttp.ClientSession() as session:
        # Authenticate
        print("Connecting to EHG cloud...")
        api = HymerConnectApi(session)
        await api.authenticate(username, password)
        print("Authenticated successfully")

        # Get vehicle info
        vehicles = await api.get_ehg_vehicles()
        if not vehicles:
            print("ERROR: No vehicles found")
            sys.exit(1)

        vehicle = vehicles[0]
        vehicle_urn = vehicle.get("urn", "")
        print("Vehicle: %s (URN: %s)" % (vehicle.get("name", "?"), vehicle_urn))

        # Get SCU URN
        scc_vehicles = await api.get_vehicles()
        scu_urn = ""
        for v in scc_vehicles:
            scu_urn = v.get("smartUnitUrn", "")
            if scu_urn:
                break
        print("SCU: %s" % scu_urn)

        # Connect SignalR
        print("Connecting to SignalR...")
        client = HymerSignalRClient(
            api=api,
            session=session,
            vehicle_urn=vehicle_urn,
            scu_urn=scu_urn,
            ehg_refresh_token=refresh_token,
            on_sensor_update=discovery.on_sensor_update,
        )

        await client.connect()
        print("Connected! Collecting sensor data for %d seconds..." % args.duration)
        print("(Toggle lights, doors, etc. to discover more sensors)")

        discovery.start_time = time.monotonic()

        # Listen for data
        listen_task = asyncio.ensure_future(client.listen())
        
        try:
            await asyncio.sleep(args.duration)
        except KeyboardInterrupt:
            print("\nStopping early...")

        # Stop
        await client.stop()
        
        # Print results
        discovery.print_results()


if __name__ == "__main__":
    asyncio.run(main())
