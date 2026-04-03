"""Constants for HYMER Connect integration."""

DOMAIN = "hymer_connect"
MANUFACTURER = "Erwin Hymer Group"

# --- Base URLs ---
API_BASE_URL = "https://smartrv.erwinhymergroup.com"
API_BASE_URL_SCC = "https://scc-api.smartrv.erwinhymergroup.com"
API_BASE_URL_RVTWIN = "https://scc-rvtwin.smartrv.erwinhymergroup.com"
API_BASE_URL_APPCOMM = "https://scc-appcomm.smartrv.erwinhymergroup.com"

# --- OAuth2 Authentication ---
ENDPOINT_AUTH = "/api/v2/oauth/token"
OAUTH2_CLIENT_ID = "ehg-prod-mobile-app-technical-user"
OAUTH2_CLIENT_SECRET = "Z{?z:+7mQa5v@oee5]%dE^U*qx8}Yr(al5xSTh-9,D]bn<;8Vo8u<g%s\u00dc-(N3%y"
AUTH_GRANT_TYPE_PASSWORD = "password"
AUTH_GRANT_TYPE_REFRESH = "refresh_token"

# --- Main API Endpoints ---
ENDPOINT_ACCOUNTS_ME = "/api/ehg/v1/accounts/me"
ENDPOINT_VEHICLES_BY_TOKEN = "/api/ehg/v1/vehicles/byToken"
ENDPOINT_CONFIRMATION_TOKEN = "/api/ehg/v1/accounts/confirmationToken"

# --- SCC API Endpoints ---
ENDPOINT_RV_TWIN_VEHICLES = "/api/rv-twin/vehicles"
ENDPOINT_CONFIG_MENU = "/api/config/menu"
ENDPOINT_CONFIG_BRANDS = "/api/config/brands/details"
ENDPOINT_SERVICE_CATALOGUE = "/api/service-catalogue/services"
ENDPOINT_PUSH_NOTIFICATIONS = "/api/push-notifications/subscriptions/scu"
ENDPOINT_PUSH_DEVICE_REG = "/api/push-notifications/devices"

# --- SignalR ---
SIGNALR_NEGOTIATE_PATH = "/datahub/negotiate"
SIGNALR_HUB_NAME = "datahub"

# --- Headers ---
HEADER_ACCESS_TOKEN = "scc-csngaccesstoken"
HEADER_BRAND = "scc-brand"
HEADER_LOCALE = "scc-locale"
HEADER_APP_VERSION = "scc-appversion"
HEADER_EHG_BRAND = "ehg-smart-caravan-brand"

# --- App Version ---
APP_VERSION = "2.10.14"
USER_AGENT = "okhttp/4.10.0"

# --- Brands ---
BRANDS = {
    "hymer": "HYMER",
    "buerstner": "Bürstner",
    "dethleffs": "Dethleffs",
    "eriba": "Eriba",
    "lmc": "LMC",
    "niesmann-bischoff": "Niesmann+Bischoff",
    "sunlight": "Sunlight",
    "carado": "Carado",
    "laika": "Laika",
    "freeontour": "FreeOnTour",
}

# Default scan interval (seconds)
DEFAULT_SCAN_INTERVAL = 60

# Config keys
CONF_BRAND = "brand"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_VEHICLE_URN = "vehicle_urn"
CONF_SCU_URN = "scu_urn"
CONF_VEHICLE_ID = "vehicle_id"

# Platforms
PLATFORMS = ["sensor", "binary_sensor"]
