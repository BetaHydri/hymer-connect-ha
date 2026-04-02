"""Constants for HYMER Connect integration."""

DOMAIN = "hymer_connect"
MANUFACTURER = "Erwin Hymer Group"

API_BASE_URL = "https://smartrv.erwinhymergroup.com"
API_BASE_URL_SCC = "https://scc-api.smartrv.erwinhymergroup.com"
API_BASE_URL_RVTWIN = "https://scc-rvtwin.smartrv.erwinhymergroup.com"

# Auth endpoint
ENDPOINT_AUTH = "/api/v2/oauth/token"
OAUTH2_CLIENT_ID = "OAUTH2_CLIENT"
OAUTH2_CLIENT_SECRET = "OAUTH2_CLIENT"

# API endpoints
ENDPOINT_MOBILE_CONFIG = "/api/mobile-config"
ENDPOINT_SERVICE_CATALOGUE = "/api/service-catalogue/services"
ENDPOINT_ACCOUNTS = "/api/ehg/v1/accounts"
ENDPOINT_ACCOUNTS_ME = "/api/ehg/v1/accounts/me"
ENDPOINT_VEHICLES = "/api/ehg/v1/vehicles"
ENDPOINT_SIUS = "/api/ehg/v1/sius"
ENDPOINT_SENSORS = "/api/ehg/v1/sensors"
ENDPOINT_RV_TWIN_SYNC = "/api/rv-twin/sensors/sync"
ENDPOINT_PUSH_NOTIFICATIONS = "/api/push-notifications/subscriptions/scu"
ENDPOINT_LEGAL_DOCS = "/api/ehg/v1/legal-docs"
ENDPOINT_FIRMWARES = "/api/ehg/v1/firmwares/sius"
ENDPOINT_REGISTRATIONS = "/api/ehg/v1/registrations"

# Auth
AUTH_GRANT_TYPE_PASSWORD = "password"
AUTH_GRANT_TYPE_REFRESH = "refresh_token"

# Headers
HEADER_ACCESS_TOKEN = "SCC-CsNgAccessToken"
HEADER_REMOTE_TOKEN = "SCC-CsNgRemoteToken"
HEADER_LOCALE = "SCC-Locale"
HEADER_PIN_CODE = "SCC-PinCode"
HEADER_SCU_URN = "SCC-ScuUrn"

# Brands
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
CONF_SIU_URN = "siu_urn"

# Platforms
PLATFORMS = ["sensor", "binary_sensor"]
