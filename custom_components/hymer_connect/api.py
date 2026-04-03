"""API client for HYMER Connect."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    API_BASE_URL,
    API_BASE_URL_APPCOMM,
    API_BASE_URL_SCC,
    APP_VERSION,
    AUTH_GRANT_TYPE_PASSWORD,
    AUTH_GRANT_TYPE_REFRESH,
    ENDPOINT_ACCOUNTS_ME,
    ENDPOINT_AUTH,
    ENDPOINT_CONFIRMATION_TOKEN,
    ENDPOINT_CONFIG_BRANDS,
    ENDPOINT_RV_TWIN_VEHICLES,
    ENDPOINT_SERVICE_CATALOGUE,
    HEADER_ACCESS_TOKEN,
    HEADER_BRAND,
    HEADER_EHG_BRAND,
    HEADER_LOCALE,
    OAUTH2_BASIC_AUTH,
    SIGNALR_NEGOTIATE_PATH,
    USER_AGENT,
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
        locale: str = "de-DE",
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._brand = brand
        self._locale = locale
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def access_token(self) -> str | None:
        """Return the current access token."""
        return self._access_token

    @property
    def authenticated(self) -> bool:
        """Return True if we have an access token."""
        return self._access_token is not None

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """Set auth tokens directly (from stored config)."""
        self._access_token = access_token
        self._refresh_token = refresh_token

    @staticmethod
    def _basic_auth_header() -> str:
        """Return the pre-computed Basic auth header for OAuth2."""
        return OAUTH2_BASIC_AUTH

    def _main_api_headers(self) -> dict[str, str]:
        """Build headers for the main API (smartrv.erwinhymergroup.com)."""
        headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
            HEADER_EHG_BRAND: f"{self._brand.capitalize()}/{APP_VERSION}",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _scc_api_headers(self) -> dict[str, str]:
        """Build headers for the SCC API (scc-api.smartrv.erwinhymergroup.com)."""
        headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
            HEADER_BRAND: self._brand,
            HEADER_LOCALE: self._locale,
        }
        if self._access_token:
            headers[HEADER_ACCESS_TOKEN] = self._access_token
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        *,
        data: str | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request."""
        try:
            async with self._session.request(
                method, url, headers=headers, data=data, json=json_data
            ) as resp:
                if resp.status == 401:
                    if self._refresh_token:
                        await self._refresh_access_token()
                        if headers and HEADER_ACCESS_TOKEN in headers:
                            headers[HEADER_ACCESS_TOKEN] = self._access_token
                        elif headers and "Authorization" in headers:
                            headers["Authorization"] = f"Bearer {self._access_token}"
                        return await self._request(
                            method, url, data=data, json_data=json_data, headers=headers
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

    # --- Authentication ---

    async def authenticate(self, username: str, password: str) -> dict[str, str]:
        """Authenticate using OAuth2 ROPC with HTTP Basic client auth."""
        url = f"{API_BASE_URL}{ENDPOINT_AUTH}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self._basic_auth_header(),
            "User-Agent": USER_AGENT,
            HEADER_EHG_BRAND: f"{self._brand.capitalize()}/{APP_VERSION}",
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
                    raise HymerConnectAuthError("Invalid email or password")
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
                raise HymerConnectAuthError("No access_token in auth response")
        except aiohttp.ClientError as err:
            raise HymerConnectApiError(f"Connection error: {err}") from err

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using OAuth2 refresh_token grant."""
        if not self._refresh_token:
            raise HymerConnectAuthError("No refresh token available")
        url = f"{API_BASE_URL}{ENDPOINT_AUTH}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self._basic_auth_header(),
            "User-Agent": USER_AGENT,
        }
        data = (
            f"grant_type={AUTH_GRANT_TYPE_REFRESH}"
            f"&refresh_token={quote(self._refresh_token, safe='.-_~')}"
        )
        try:
            async with self._session.request(
                "POST", url, headers=headers, data=data
            ) as resp:
                _LOGGER.debug("Token refresh status: %s", resp.status)
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.warning(
                        "Token refresh failed %s: %s", resp.status, text[:200]
                    )
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

    # --- Main API ---

    async def get_account(self) -> dict[str, Any]:
        """Get current account info."""
        url = f"{API_BASE_URL}{ENDPOINT_ACCOUNTS_ME}"
        return await self._request("GET", url, headers=self._main_api_headers())

    async def get_confirmation_token(self) -> dict[str, Any]:
        """Get a confirmation token for remote access."""
        url = f"{API_BASE_URL}{ENDPOINT_CONFIRMATION_TOKEN}"
        return await self._request("POST", url, headers=self._main_api_headers())

    async def get_vehicle_by_token(self, ehg_token: str) -> dict[str, Any]:
        """Get vehicle info using an activation/owner token."""
        url = f"{API_BASE_URL}/api/ehg/v1/vehicles/byToken"
        headers = self._main_api_headers()
        headers["ehg-token"] = ehg_token
        return await self._request("GET", url, headers=headers)

    # --- SCC API ---

    async def get_vehicles(self) -> list[Any]:
        """Get list of vehicles from the RV-Twin API."""
        url = f"{API_BASE_URL_SCC}{ENDPOINT_RV_TWIN_VEHICLES}"
        result = await self._request("GET", url, headers=self._scc_api_headers())
        if isinstance(result, list):
            return result
        return [result]

    async def get_vehicle(self, vehicle_id: int) -> dict[str, Any]:
        """Get single vehicle details including tanks."""
        url = f"{API_BASE_URL_SCC}{ENDPOINT_RV_TWIN_VEHICLES}/{vehicle_id}"
        return await self._request("GET", url, headers=self._scc_api_headers())

    async def get_brand_details(self) -> dict[str, Any]:
        """Get brand configuration details."""
        url = f"{API_BASE_URL_SCC}{ENDPOINT_CONFIG_BRANDS}"
        return await self._request("GET", url, headers=self._scc_api_headers())

    async def get_service_catalogue(self) -> dict[str, Any]:
        """Get available services."""
        url = f"{API_BASE_URL_SCC}{ENDPOINT_SERVICE_CATALOGUE}"
        return await self._request("GET", url, headers=self._scc_api_headers())

    # --- SignalR Negotiate ---

    async def signalr_negotiate(self) -> dict[str, Any]:
        """Negotiate a SignalR connection to the datahub."""
        url = f"{API_BASE_URL_APPCOMM}{SIGNALR_NEGOTIATE_PATH}?negotiateVersion=1"
        headers = {
            "Content-Type": "text/plain;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "X-SignalR-User-Agent": (
                "Microsoft SignalR/6.0 "
                "(6.0.25; Unknown OS; Browser; Unknown Runtime Version)"
            ),
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
            headers[HEADER_ACCESS_TOKEN] = self._access_token
        return await self._request("POST", url, headers=headers, data="")

    # --- Aggregated Data ---

    async def get_vehicle_status(self) -> dict[str, Any]:
        """Get aggregated vehicle status from the SCC REST API."""
        data: dict[str, Any] = {}

        try:
            vehicles = await self.get_vehicles()
            _LOGGER.debug("Fetched %d vehicles", len(vehicles) if vehicles else 0)
            if vehicles:
                data["vehicles"] = vehicles
                vehicle = vehicles[0]
                data["vehicle"] = vehicle
                data["vehicle_id"] = vehicle.get("id")
                data["vin"] = vehicle.get("vin")
                data["name"] = vehicle.get("name")
                data["model"] = vehicle.get("model")
                data["model_group"] = vehicle.get("modelGroup")
                data["model_year"] = vehicle.get("modelYear")
                data["scu_urn"] = vehicle.get("smartUnitUrn")
                data["type_id"] = vehicle.get("typeId")

                vehicle_id = vehicle.get("id")
                if vehicle_id:
                    try:
                        details = await self.get_vehicle(vehicle_id)
                        data["vehicle_details"] = details
                        data["tanks"] = details.get("tanks", [])
                    except HymerConnectApiError:
                        _LOGGER.debug("Could not fetch vehicle details")
        except HymerConnectAuthError:
            raise
        except HymerConnectApiError as err:
            _LOGGER.warning("Could not fetch vehicles: %s", err)

        try:
            account = await self.get_account()
            data["account"] = account
        except HymerConnectApiError:
            _LOGGER.debug("Could not fetch account info")

        _LOGGER.debug(
            "Vehicle status keys: %s, model=%s, vin=%s",
            list(data.keys()),
            data.get("model"),
            data.get("vin"),
        )
        return data
