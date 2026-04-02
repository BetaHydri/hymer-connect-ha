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
        """Authenticate using username and password (OAuth2 ROPC)."""
        data = {
            "grant_type": AUTH_GRANT_TYPE_PASSWORD,
            "username": username,
            "password": password,
        }
        # Try multiple possible auth endpoints
        for endpoint in [
            "/api/ehg/v1/accounts/auth",
            "/api/ehg/v1/token",
            "/api/auth/token",
        ]:
            try:
                result = await self._request(
                    "POST",
                    endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                )
                if isinstance(result, dict) and "access_token" in result:
                    self._access_token = result["access_token"]
                    self._refresh_token = result.get("refresh_token")
                    return {
                        "access_token": self._access_token,
                        "refresh_token": self._refresh_token or "",
                    }
            except HymerConnectApiError:
                continue
        raise HymerConnectAuthError(
            "Could not authenticate. Check credentials and try again."
        )

    async def _refresh_access_token(self) -> None:
        """Refresh the access token."""
        if not self._refresh_token:
            raise HymerConnectAuthError("No refresh token available")
        data = {
            "grant_type": AUTH_GRANT_TYPE_REFRESH,
            "refresh_token": self._refresh_token,
        }
        for endpoint in [
            "/api/ehg/v1/accounts/auth",
            "/api/ehg/v1/token",
            "/api/auth/token",
        ]:
            try:
                result = await self._request(
                    "POST",
                    endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                )
                if isinstance(result, dict) and "access_token" in result:
                    self._access_token = result["access_token"]
                    self._refresh_token = result.get("refresh_token", self._refresh_token)
                    return
            except HymerConnectApiError:
                continue
        raise HymerConnectAuthError("Token refresh failed")

    async def get_mobile_config(self) -> dict[str, Any]:
        """Get mobile app configuration."""
        return await self._request("GET", ENDPOINT_MOBILE_CONFIG, headers={"Brand": self._brand})

    async def get_service_catalogue(self) -> dict[str, Any]:
        """Get service catalogue."""
        return await self._request("GET", ENDPOINT_SERVICE_CATALOGUE)

    async def get_account(self) -> dict[str, Any]:
        """Get current account info."""
        return await self._request("GET", ENDPOINT_ACCOUNTS_ME)

    async def get_vehicles(self) -> list[Any]:
        """Get list of vehicles."""
        result = await self._request("GET", ENDPOINT_VEHICLES)
        if isinstance(result, list):
            return result
        return result.get("vehicles", result.get("items", [result]))

    async def get_sius(self) -> list[Any]:
        """Get list of SIUs (Smart Interface Units)."""
        result = await self._request("GET", ENDPOINT_SIUS)
        if isinstance(result, list):
            return result
        return result.get("sius", result.get("items", [result]))

    async def get_sensors(self, siu_urn: str | None = None) -> dict[str, Any]:
        """Get sensor data."""
        endpoint = ENDPOINT_SENSORS
        headers = {}
        if siu_urn:
            headers[HEADER_SCU_URN] = siu_urn
        return await self._request("GET", endpoint, headers=headers)

    async def get_vehicle_data(self, siu_urn: str | None = None) -> dict[str, Any]:
        """Get full vehicle data via rv-twin sync."""
        headers = {}
        if siu_urn:
            headers[HEADER_SCU_URN] = siu_urn
        return await self._request("GET", ENDPOINT_RV_TWIN_SYNC, headers=headers)

    async def get_vehicle_status(self) -> dict[str, Any]:
        """Get aggregated vehicle status.

        Attempts multiple endpoints and returns the best available data.
        """
        data: dict[str, Any] = {}
        for fetcher_name, fetcher in [
            ("sensors", self.get_sensors),
            ("vehicles", self.get_vehicles),
            ("sius", self.get_sius),
        ]:
            try:
                result = await fetcher()
                data[fetcher_name] = result
            except HymerConnectApiError as err:
                _LOGGER.debug("Could not fetch %s: %s", fetcher_name, err)
        return data
