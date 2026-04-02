"""API client for HYMER Connect."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    AUTH_GRANT_TYPE_PASSWORD,
    AUTH_GRANT_TYPE_REFRESH,
    ENDPOINT_ACCOUNTS_ME,
    ENDPOINT_AUTH,
    ENDPOINT_MOBILE_CONFIG,
    ENDPOINT_RV_TWIN_SYNC,
    ENDPOINT_SERVICE_CATALOGUE,
    ENDPOINT_SENSORS,
    ENDPOINT_SIUS,
    ENDPOINT_VEHICLES,
    HEADER_ACCESS_TOKEN,
    HEADER_LOCALE,
    HEADER_REMOTE_TOKEN,
    HEADER_SCU_URN,
    OAUTH2_CLIENT_ID,
    OAUTH2_CLIENT_SECRET,
)

_LOGGER = logging.getLogger(__name__)


class HymerConnectApiError(Exception):
    """Base exception for API errors."""


class HymerConnectAuthError(HymerConnectApiError):
    """Authentication error."""


class HymerConnectApi:
    """Client for the HYMER Connect cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        brand: str = "hymer",
        locale: str = "en",
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._brand = brand
        self._locale = locale
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._base_url = API_BASE_URL

    @property
    def authenticated(self) -> bool:
        """Return True if we have an access token."""
        return self._access_token is not None

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """Set auth tokens directly (from stored config)."""
        self._access_token = access_token
        self._refresh_token = refresh_token

    def _auth_headers(self) -> dict[str, str]:
        """Build headers with authentication."""
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "HymerConnect-HA/0.1.0",
            HEADER_LOCALE: self._locale,
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
            headers[HEADER_ACCESS_TOKEN] = self._access_token
        if self._refresh_token:
            headers[HEADER_REMOTE_TOKEN] = self._refresh_token
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request."""
        url = f"{self._base_url}{endpoint}"
        req_headers = self._auth_headers()
        if headers:
            req_headers.update(headers)

        try:
            async with self._session.request(
                method, url, headers=req_headers, data=data, json=json_data
            ) as resp:
                if resp.status == 401:
                    if self._refresh_token:
                        await self._refresh_access_token()
                        return await self._request(
                            method, endpoint, data=data, json_data=json_data, headers=headers
                        )
                    raise HymerConnectAuthError("Authentication failed")
                if resp.status == 403:
                    raise HymerConnectAuthError("Access forbidden")
                if resp.status >= 400:
                    text = await resp.text()
                    raise HymerConnectApiError(
                        f"API error {resp.status}: {text[:200]}"
                    )
                if resp.content_type and "json" in resp.content_type:
                    return await resp.json()
                return {}
        except aiohttp.ClientError as err:
            raise HymerConnectApiError(f"Connection error: {err}") from err

    async def authenticate(self, username: str, password: str) -> dict[str, str]:
        """Authenticate using OAuth2 ROPC with HTTP Basic client auth."""
        import base64
        from urllib.parse import quote

        url = f"{self._base_url}{ENDPOINT_AUTH}"
        client_creds = base64.b64encode(
            f"{OAUTH2_CLIENT_ID}:{OAUTH2_CLIENT_SECRET}".encode()
        ).decode()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {client_creds}",
        }
        data = (
            f"grant_type={AUTH_GRANT_TYPE_PASSWORD}"
            f"&username={quote(username, safe='')}"
            f"&password={quote(password, safe='')}"
        )
        try:
            async with self._session.request(
                "POST", url, headers=headers, data=data
            ) as resp:
                _LOGGER.debug("Auth response status: %s", resp.status)
                if resp.status == 401:
                    raise HymerConnectAuthError(
                        "Invalid email or password"
                    )
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.error("Auth error %s: %s", resp.status, text[:200])
                    raise HymerConnectApiError(
                        f"Auth error {resp.status}: {text[:200]}"
                    )
                result = await resp.json()
                if "access_token" in result:
                    self._access_token = result["access_token"]
                    self._refresh_token = result.get("refresh_token")
                    return {
                        "access_token": self._access_token,
                        "refresh_token": self._refresh_token or "",
                    }
                raise HymerConnectAuthError(
                    "No access_token in auth response"
                )
        except aiohttp.ClientError as err:
            raise HymerConnectApiError(f"Connection error: {err}") from err

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using OAuth2 refresh_token grant."""
        import base64
        from urllib.parse import quote

        if not self._refresh_token:
            raise HymerConnectAuthError("No refresh token available")
        url = f"{self._base_url}{ENDPOINT_AUTH}"
        client_creds = base64.b64encode(
            f"{OAUTH2_CLIENT_ID}:{OAUTH2_CLIENT_SECRET}".encode()
        ).decode()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {client_creds}",
        }
        data = (
            f"grant_type={AUTH_GRANT_TYPE_REFRESH}"
            f"&refresh_token={quote(self._refresh_token, safe='')}"
        )
        try:
            async with self._session.request(
                "POST", url, headers=headers, data=data
            ) as resp:
                if resp.status >= 400:
                    raise HymerConnectAuthError("Token refresh failed")
                result = await resp.json()
                if "access_token" in result:
                    self._access_token = result["access_token"]
                    self._refresh_token = result.get(
                        "refresh_token", self._refresh_token
                    )
                    return
        except aiohttp.ClientError as err:
            raise HymerConnectApiError(f"Connection error: {err}") from err
        raise HymerConnectAuthError("Token refresh failed")

    async def get_mobile_config(self) -> dict[str, Any]:
        """Get mobile app configuration."""
        return await self._request("GET", ENDPOINT_MOBILE_CONFIG, headers={"Brand": self._brand})

    async def get_service_catalogue(self) -> dict[str, Any]:
        """Get service catalogue."""
        return await self._request("GET", ENDPOINT_SERVICE_CATALOGUE)

    async def get_account(self) -> dict[str, Any]:
        """Get current account info."""
        return await self._request("GET", "/api/v2/accounts/me")

    async def get_vehicles(self) -> list[Any]:
        """Get list of vehicles (assets)."""
        result = await self._request("GET", "/api/v2/assets?page=0&size=100")
        if isinstance(result, dict) and "content" in result:
            return result["content"]
        if isinstance(result, list):
            return result
        return [result]

    async def get_vehicle(self, asset_id: int) -> dict[str, Any]:
        """Get single vehicle asset details."""
        return await self._request("GET", f"/api/v2/assets/{asset_id}")

    async def get_vehicle_shadow(self, asset_id: int) -> dict[str, Any]:
        """Get vehicle shadow (current state/properties)."""
        return await self._request("GET", f"/api/v2/assets/{asset_id}/shadow")

    async def get_service_catalogue(self) -> dict[str, Any]:
        """Get service catalogue."""
        return await self._request(
            "GET", "/api/service-catalogue/services"
        )

    async def get_vehicle_status(self) -> dict[str, Any]:
        """Get aggregated vehicle status.

        Fetches vehicles and their properties from the v2 API.
        """
        data: dict[str, Any] = {}
        try:
            vehicles = await self.get_vehicles()
            if vehicles:
                data["vehicles"] = vehicles
                vehicle = vehicles[0]
                data["vehicle"] = vehicle
                data["properties"] = vehicle.get("properties", {})

                asset_id = vehicle.get("id")
                if asset_id:
                    try:
                        shadow = await self.get_vehicle_shadow(asset_id)
                        data["shadow"] = shadow
                        if isinstance(shadow, dict) and "properties" in shadow:
                            data["properties"].update(shadow["properties"])
                    except HymerConnectApiError:
                        _LOGGER.debug("Could not fetch vehicle shadow")
        except HymerConnectApiError as err:
            _LOGGER.debug("Could not fetch vehicles: %s", err)

        try:
            account = await self.get_account()
            data["account"] = account
        except HymerConnectApiError:
            _LOGGER.debug("Could not fetch account info")

        return data
