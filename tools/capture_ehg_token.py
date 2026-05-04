"""Capture the EHG Remote Access Refresh Token from the Hymer Connect app.

This mitmproxy addon scans ALL intercepted HTTP traffic for the EHG refresh
token (ett=access-refresh).  It uses generic JWT regex scanning across request
bodies, response bodies, headers, and WebSocket messages — so it works
regardless of which API endpoint or JSON key the token appears in.

Usage:
    1. Install mitmproxy:  pip install mitmproxy
    2. Run this script:    mitmdump -s capture_ehg_token.py --listen-port 8080
    3. Set your phone's Wi-Fi proxy to <PC_IP>:8080
    4. Install the mitmproxy CA cert: open http://mitm.it on the phone
    5. Open the Hymer Connect app (patched APK with cert pinning disabled)
    6. The token will be printed and saved automatically

The script auto-exits after capturing the token.

.AUTHOR Jan Tiedemann
.DATE 2026
"""

from __future__ import annotations

import base64
import json
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from mitmproxy import ctx, http

# Target: POST /api/ehg/v1/vehicles/{urn}/remoteAccessToken
TARGET_PATH = "/remoteAccessToken"
# Alternative: look for the token in WebSocket UpdateTokens messages
SIGNALR_HOSTS = {"ehg-prod-signalr.service.signalr.net"}

# Regex to find JWT-like strings (header.payload.signature, each base64url-encoded)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

OUTPUT_DIR = Path(__file__).parent / "traces"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = OUTPUT_DIR / "captured_ehg_token.txt"
BASIC_AUTH_FILE = OUTPUT_DIR / "captured_oauth_basic_auth.txt"

# OAuth /token endpoint path — matches both production and SCC endpoints.
OAUTH_TOKEN_PATH = "/oauth/token"

_BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ✅  EHG REFRESH TOKEN CAPTURED SUCCESSFULLY!                   ║
║                                                                  ║
║   The token has been saved to:                                   ║
║   {path:<55s}  ║
║                                                                  ║
║   Copy this token into your HYMER Connect integration config     ║
║   in Home Assistant under "EHG Remote Access Refresh Token".     ║
║                                                                  ║
║   You can now:                                                   ║
║   1. Close this proxy (Ctrl+C)                                   ║
║   2. Remove the proxy settings from your phone's Wi-Fi           ║
║   3. Uninstall the patched APK and reinstall the original app    ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

_BANNER_BASIC = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ✅  OAUTH BASIC-AUTH HEADER CAPTURED SUCCESSFULLY!             ║
║                                                                  ║
║   The header has been saved to:                                  ║
║   {path:<55s}  ║
║                                                                  ║
║   Copy the header into the HYMER Connect integration             ║
║   reconfigure or options dialog under                            ║
║   "OAuth client header".                                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""


def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload of a JWT without verification."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def _is_refresh_token(token: str) -> bool:
    """Check if a JWT is an EHG remote access refresh token (ett=access-refresh)."""
    payload = _decode_jwt_payload(token)
    return payload.get("ett") == "access-refresh"


def _find_refresh_token(text: str) -> str | None:
    """Scan text for any JWT whose payload has ett=access-refresh."""
    if not text:
        return None
    for match in JWT_RE.finditer(text):
        token = match.group(0)
        if _is_refresh_token(token):
            return token
    return None


def _save_token(token: str) -> None:
    """Save the captured token and print success banner."""
    TOKEN_FILE.write_text(token, encoding="utf-8")

    payload = _decode_jwt_payload(token)
    vehicle = payload.get("urn", "unknown")
    client_id = payload.get("client_id", "unknown")

    print("\n" + "=" * 70)
    print(_BANNER.format(path=str(TOKEN_FILE)))
    print(f"   Vehicle:   {vehicle}")
    print(f"   Client ID: {client_id} (phone BLE MAC)")
    print(f"   Token type: {payload.get('ett', 'unknown')}")
    print(f"   Token length: {len(token)} chars")
    print(f"   Starts with: {token[:50]}...")
    print("=" * 70)
    print(f"\n   TOKEN:\n\n{token}\n")
    print("=" * 70)


class EhgTokenCapture:
    """mitmproxy addon that captures the EHG refresh token and OAuth header."""

    def __init__(self):
        self._found = False
        self._basic_found = False

    def _maybe_save_basic_auth(self, flow: http.HTTPFlow) -> None:
        """If this request looks like the OAuth /token call, save its Basic header.

        Captured separately from the refresh token because the EHG mobile app
        sends both in the same login flow but in different requests.
        """
        if self._basic_found:
            return
        if OAUTH_TOKEN_PATH not in flow.request.path:
            return
        auth = flow.request.headers.get("Authorization", "")
        if not auth.lower().startswith("basic "):
            return
        BASIC_AUTH_FILE.write_text(auth, encoding="utf-8")
        self._basic_found = True
        ctx.log.info(f"\U0001f3af Captured OAuth Basic-auth header from {flow.request.pretty_url}")
        print("\n" + "=" * 70)
        print(_BANNER_BASIC.format(path=str(BASIC_AUTH_FILE)))
        print(f"   HEADER:\n\n{auth}\n")
        print("=" * 70)

    def request(self, flow: http.HTTPFlow) -> None:
        """Intercept HTTP requests to find the remoteAccessToken call."""
        # Always opportunistically harvest the Basic-auth header even if the
        # refresh token has already been captured.
        self._maybe_save_basic_auth(flow)

        if self._found:
            return

        # Fast path: POST /remoteAccessToken — request body contains the token
        if (
            flow.request.method == "POST"
            and TARGET_PATH in flow.request.pretty_url
        ):
            try:
                body = flow.request.get_text()
                if body:
                    data = json.loads(body)
                    token = data.get("token", "")
                    if token and _is_refresh_token(token):
                        ctx.log.info(
                            f"🎯 Found refresh token in POST {flow.request.pretty_url}"
                        )
                        _save_token(token)
                        self._found = True
                        return
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # Generic scan: search for JWTs in any request body
        try:
            body = flow.request.get_text()
            token = _find_refresh_token(body)
            if token:
                ctx.log.info(
                    f"🎯 Found refresh token in request body of {flow.request.method} {flow.request.pretty_url}"
                )
                _save_token(token)
                self._found = True
                return
        except (ValueError, UnicodeDecodeError):
            pass

        # Generic scan: search for JWTs in request headers
        for name, value in flow.request.headers.items():
            token = _find_refresh_token(value)
            if token:
                ctx.log.info(
                    f"🎯 Found refresh token in request header '{name}' of {flow.request.pretty_url}"
                )
                _save_token(token)
                self._found = True
                return

    def response(self, flow: http.HTTPFlow) -> None:
        """Also check responses for tokens (e.g., during initial BLE pairing)."""
        if self._found:
            return

        if not flow.response or not flow.response.content:
            return

        # Generic scan: search for JWTs in response body
        try:
            text = flow.response.get_text()
            token = _find_refresh_token(text)
            if token:
                ctx.log.info(
                    f"🎯 Found refresh token in response body from {flow.request.pretty_url}"
                )
                _save_token(token)
                self._found = True
                return
        except (ValueError, UnicodeDecodeError):
            pass

        # Generic scan: search for JWTs in response headers
        for name, value in flow.response.headers.items():
            token = _find_refresh_token(value)
            if token:
                ctx.log.info(
                    f"🎯 Found refresh token in response header '{name}' from {flow.request.pretty_url}"
                )
                _save_token(token)
                self._found = True
                return

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        """Check WebSocket messages for UpdateTokens containing the token."""
        if self._found:
            return

        if not flow.websocket:
            return

        msg = flow.websocket.messages[-1]
        if not msg.is_text:
            return

        # SignalR uses \x1e as record separator
        for part in msg.text.split("\x1e"):
            part = part.strip()
            if not part:
                continue

            # Fast path: try structured SignalR parsing
            try:
                parsed = json.loads(part)
                if parsed.get("target") == "UpdateTokens":
                    args = parsed.get("arguments", [])
                    if args and isinstance(args[0], dict):
                        ehg_token = args[0].get("ehgAccessToken", "")
                        if ehg_token and _is_refresh_token(ehg_token):
                            ctx.log.info("🎯 Found refresh token in UpdateTokens WebSocket message")
                            _save_token(ehg_token)
                            self._found = True
                            return
            except json.JSONDecodeError:
                pass

            # Generic scan: search for JWTs in raw WebSocket message text
            token = _find_refresh_token(part)
            if token:
                ctx.log.info("🎯 Found refresh token in WebSocket message")
                _save_token(token)
                self._found = True
                return


addons = [EhgTokenCapture()]
