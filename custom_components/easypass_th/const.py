"""Constants for the Thailand Easy Pass integration."""

DOMAIN = "easypass_th"
MANUFACTURER = "EXAT (การทางพิเศษแห่งประเทศไทย)"

# --- Website URLs ---
BASE_URL = "https://member-thaieasypass.exat.co.th"
LOGIN_URL = BASE_URL + "/"                      # GET – login page (harvests _token)
LOGIN_POST_URL = f"{BASE_URL}/eservice/login"   # POST – AJAX login endpoint
CARD_LIST_URL = f"{BASE_URL}/eservice/easypasscardlist"          # GET – page (for CSRF token)
CARD_API_URL = f"{BASE_URL}/eservice/easypasscardlist/get-all"   # GET – JSON API
CARD_INFO_URL = CARD_API_URL
USAGE_API_URL = f"{BASE_URL}/eservice/easypasscardlist/usage"    # POST – transaction history

# --- Config entry keys ---
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# --- Coordinator ---
DEFAULT_SCAN_INTERVAL_MINUTES = 30
MAX_LOGIN_RETRIES = 3

# --- Request settings ---
REQUEST_TIMEOUT_SECONDS = 30
SESSION_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# --- Sensor unique ID suffixes ---
SENSOR_BALANCE = "balance"
SENSOR_LICENSE = "license"
SENSOR_SERIAL = "serial"
SENSOR_LAST_UPDATE = "last_update"
SENSOR_LAST_TOPUP = "last_topup"
SENSOR_OWNER = "owner"
SENSOR_MFLOW = "mflow_status"
SENSOR_MONTHLY_SPEND = "monthly_spend"
SENSOR_LAST_TOLL_LOCATION = "last_toll_location"
SENSOR_REWARD_POINTS = "reward_points"

# --- Sensor display names ---
SENSOR_NAMES = {
    SENSOR_BALANCE:            "Easy Pass Balance",
    SENSOR_LICENSE:            "Easy Pass License Plate",
    SENSOR_SERIAL:             "Easy Pass Card Serial",
    SENSOR_LAST_UPDATE:        "Easy Pass Last Transaction",
    SENSOR_LAST_TOPUP:         "Easy Pass Last Top-up",
    SENSOR_OWNER:              "Easy Pass Account Owner",
    SENSOR_MFLOW:              "Easy Pass M-Flow Status",
    SENSOR_MONTHLY_SPEND:      "Easy Pass Monthly Spend",
    SENSOR_LAST_TOLL_LOCATION: "Easy Pass Last Toll Location",
    SENSOR_REWARD_POINTS:      "Easy Pass Reward Points",
}

# --- Icons ---
SENSOR_ICONS = {
    SENSOR_BALANCE:            "mdi:cash",
    SENSOR_LICENSE:            "mdi:car",
    SENSOR_SERIAL:             "mdi:card-account-details",
    SENSOR_LAST_UPDATE:        "mdi:calendar-clock",
    SENSOR_LAST_TOPUP:         "mdi:cash-plus",
    SENSOR_OWNER:              "mdi:account",
    SENSOR_MFLOW:              "mdi:highway",
    SENSOR_MONTHLY_SPEND:      "mdi:cash-multiple",
    SENSOR_LAST_TOLL_LOCATION: "mdi:map-marker",
    SENSOR_REWARD_POINTS:      "mdi:star-circle",
}

# --- Error strings ---
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_UNKNOWN = "unknown"
ERROR_SESSION_EXPIRED = "session_expired"
