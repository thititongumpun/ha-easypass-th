# Thailand Easy Pass – HA Integration: Implementation Plan

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Home Assistant Core                │
│                                                     │
│  Config Entry  ──►  __init__.py                     │
│       │               │                             │
│       │               ▼                             │
│  Config Flow    EasyPassCoordinator                 │
│  (UI setup)     (polls every 30 min)                │
│                        │                           │
│                        │ async_add_executor_job     │
│                        ▼                           │
│               Thread Pool Executor                  │
│                        │                           │
│                        ▼                           │
│               EasyPassScraper                       │
│               (requests + bs4)                      │
│                        │                           │
│               ┌────────┘                           │
│               ▼                                     │
│        EasyPassCard (model)                         │
│               │                                     │
│       ┌───────┴────────────────────────┐           │
│       ▼       ▼        ▼       ▼       ▼           │
│  Balance  License  Serial  LastTrans  LastTopup     │
│  Sensor   Sensor   Sensor  Sensor     Sensor        │
└─────────────────────────────────────────────────────┘
```

## 2. File Structure

```
custom_components/
└── easypass_th/
    ├── __init__.py          # Integration entry-point (setup/unload)
    ├── manifest.json        # Integration metadata + pip requirements
    ├── const.py             # All constants, URLs, keys
    ├── models.py            # EasyPassCard dataclass
    ├── scraper.py           # requests + bs4 web scraper (ADAPT THIS)
    ├── coordinator.py       # DataUpdateCoordinator (polling engine)
    ├── config_flow.py       # Config Flow UI (setup + re-auth)
    ├── sensor.py            # All sensor entity classes
    ├── icons.json           # MDI icon mappings
    └── translations/
        ├── en.json          # English UI strings
        └── th.json          # Thai UI strings
```

## 3. Entity Model

| Entity ID                         | Unit | Device Class | State Class  | Source Field                |
|-----------------------------------|------|-------------|-------------|------------------------------|
| `sensor.easy_pass_balance`        | THB  | monetary    | total       | `EasyPassCard.balance`       |
| `sensor.easy_pass_license`        | —    | —           | —           | `EasyPassCard.license_plate` |
| `sensor.easy_pass_serial`         | —    | —           | —           | `EasyPassCard.serial_number` |
| `sensor.easy_pass_last_update`    | —    | —           | —           | `EasyPassCard.last_transaction_date` |
| `sensor.easy_pass_last_topup`     | THB  | monetary    | total       | `EasyPassCard.last_topup_amount` |
| `sensor.easy_pass_owner`          | —    | —           | —           | `EasyPassCard.owner_name`    |

## 4. Data Flow

```
[HA starts]
     │
     ▼
async_setup_entry()
     │
     ▼
EasyPassCoordinator created
     │
     ▼
async_config_entry_first_refresh()  ← raises ConfigEntryNotReady on failure
     │
     ▼
_async_update_data()
     │
     ▼
run_in_executor → EasyPassScraper.fetch_card()
     │
     ├── if no session: _do_login()
     │       ├── GET login page → extract CSRF token
     │       └── POST credentials → check for success
     │
     └── _scrape_card()
             ├── GET /Card/CardInfo
             ├── detect session expiry (redirect to login)
             └── _parse_card() → EasyPassCard

EasyPassCard returned → stored in coordinator.data
     │
     ▼
All CoordinatorEntity sensors auto-refresh
```

## 5. Step-by-Step Implementation Order

### Step 1 – Inspect the real website (CRITICAL)

Before touching any code, do this manually:

1. Open `https://thaieasypass.exat.co.th` in Chrome/Firefox
2. Open DevTools → Network tab
3. Log in and observe:
   - What URL is the login POST sent to?
   - What form fields are in the POST body?
   - Is there a hidden `__RequestVerificationToken` or similar field?
   - What cookies are set after login?
4. Navigate to the card info page and observe:
   - What is the URL?
   - Right-click → Inspect on each data field (balance, serial, etc.)
   - Note the HTML element `id` or `class` for each field
5. Update `const.py` (URLs) and `scraper.py` (CSS selectors) accordingly

### Step 2 – Install dependencies

Add to your HA `custom_components` and restart. HA will auto-install from
`manifest.json` requirements on first load.

For local testing outside HA:
```bash
pip install requests beautifulsoup4 lxml
```

### Step 3 – Test the scraper standalone

```python
# test_scraper.py  (run outside HA to debug HTML parsing)
from custom_components.easypass_th.scraper import EasyPassScraper

scraper = EasyPassScraper("your_username", "your_password")
card = scraper.fetch_card()
print(card)
scraper.close()
```

### Step 4 – Copy to HA

Copy `custom_components/easypass_th/` to your HA config directory.

### Step 5 – Restart HA + add integration

Settings → Integrations → Add → search "Thailand Easy Pass"

### Step 6 – Verify entities

Developer Tools → States → filter "easy_pass"

## 6. Authentication & Session Cookie Handling

```
HOW ASP.NET SESSION COOKIES WORK (typical Thai gov sites)
----------------------------------------------------------

1. GET /Account/Login
   ← Server sets:  .AspNet.ApplicationCookie (session ID)
                   __RequestVerificationToken (CSRF cookie)
   ← HTML contains: <input type="hidden" name="__RequestVerificationToken" value="abc123">

2. POST /Account/Login
   → Body: UserName=xxx&Password=yyy&__RequestVerificationToken=abc123
   ← If success: redirect 302 to /Home/Index
                 Server updates .AspNet.ApplicationCookie
   ← If failure: 200 OK back on /Account/Login with error message

3. GET /Card/CardInfo
   → Cookies: .AspNet.ApplicationCookie (auto-sent by requests.Session)
   ← If session valid: 200 with card HTML
   ← If session expired: 302 redirect to /Account/Login
      → We detect this and raise EasyPassSessionExpiredError
      → Coordinator catches it and re-logs in
```

## 7. Error Handling Strategy

| Error                     | Where Caught          | HA Behaviour                        |
|--------------------------|----------------------|-------------------------------------|
| Auth failure (bad creds) | Coordinator          | `ConfigEntryAuthFailed` → HA shows re-auth notification, stops polling |
| Connection error         | Coordinator          | `UpdateFailed` → entity goes unavailable, retried next interval |
| Session expired          | Scraper (auto-retry) | Transparent re-login, max 3 attempts |
| HTML parse failure       | Scraper (warning log)| Returns partial EasyPassCard; sensors show None |
| First setup failure      | `__init__.py`        | `ConfigEntryNotReady` → HA retries setup with back-off |

## 8. Polling & Coordinator Explained

```
DataUpdateCoordinator calls _async_update_data() every 30 minutes.
  │
  ├── On SUCCESS: stores result in coordinator.data
  │              calls async_write_ha_state() on all subscribed entities
  │
  └── On FAILURE: sets coordinator.last_exception
                  entities auto-set available=False
                  HA retries at next interval

Sensors inherit CoordinatorEntity which:
  - Subscribes to coordinator in async_added_to_hass()
  - Unsubscribes in async_will_remove_from_hass()
  - Never polls independently
```

## 9. Security Considerations

| Concern                    | Mitigation                                                      |
|---------------------------|------------------------------------------------------------------|
| Credential storage         | Stored in HA config entry (encrypted by HA's secret manager)   |
| Credentials in logs        | Never log username/password (only log username at DEBUG level)  |
| HTML injection             | BeautifulSoup uses lxml parser; never eval scraped content      |
| Session token leakage      | Stored in requests.Session (in-process RAM only)                |
| MITM                       | requests verifies SSL by default                                |
| Scraper detection          | Uses realistic User-Agent + natural request headers             |

## 10. Testing Strategy

### Unit tests (pytest)

```python
# tests/test_scraper.py
from unittest.mock import patch, MagicMock
from custom_components.easypass_th.scraper import EasyPassScraper

def test_parse_card_extracts_balance(sample_html):
    scraper = EasyPassScraper("u", "p")
    card = scraper._parse_card(sample_html)
    assert card.balance == 1234.50

def test_login_loop_protection(mock_session):
    # Make login always redirect back to login page
    mock_session.get.return_value.url = "/Account/Login"
    scraper = EasyPassScraper("u", "wrong_pass")
    with pytest.raises(EasyPassAuthError):
        scraper.fetch_card()
```

### Integration smoke test (inside HA)

1. Add integration via UI
2. Check Developer Tools → States for all 6 sensor entities
3. Check Developer Tools → Logs for any ERROR/WARNING from `easypass_th`
4. Disconnect network → verify sensors go unavailable (not crash)
5. Reconnect → verify sensors recover at next poll

---

## Future Enhancements

### A – Official API (if discovered)
Replace `scraper.py` with an `api.py` module that:
- Uses `aiohttp.ClientSession` directly (no executor needed)
- Calls JSON endpoints instead of HTML parsing
- No BS4 dependency needed

Keep `models.py` and everything above unchanged.

### B – Cloudflare Protection
If EXAT adds Cloudflare:
- Option 1: Use `cloudscraper` library (drop-in replacement for `requests`)
- Option 2: Use Playwright/Selenium in executor for JS challenge solving
- Option 3: Route through a residential proxy

### C – CAPTCHA Handling
- Login CAPTCHAs: Use 2captcha/anti-captcha service via their API
- Add `CONF_CAPTCHA_API_KEY` to config_flow
- In `_do_login()`: detect CAPTCHA, solve via API, inject solution

### D – TOTP / MFA Future-Proofing
Config Flow already supports multi-step via `async_step_totp`:
```python
async def async_step_totp(self, user_input=None):
    # Add a second step to collect TOTP code
    # Store it temporarily, not in config entry
```

The scraper's `_do_login()` can POST the TOTP to a secondary endpoint
after the initial credential POST.

### E – Multiple Cards
Current design supports 1 card per config entry.
For multiple cards, extend `EasyPassCard` to a list:
- `coordinator.data = {DATA_CARDS: [card1, card2]}`
- Sensor platform iterates the list and creates entities per card
- Each entity's `unique_id` includes the card's serial number
