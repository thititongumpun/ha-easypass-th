"""
Live integration test — hits the real Easy Pass website.

Usage:
    set EASYPASS_USER=your@email.com
    set EASYPASS_PASS=yourpassword
    python test_live.py

Or just run it and it will prompt for credentials.
"""

import json
import os
import sys
import types
from datetime import date
from getpass import getpass

# ---------------------------------------------------------------------------
# Stub homeassistant so integration modules import standalone
# ---------------------------------------------------------------------------
def _stub_ha():
    mods = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.config_entries": types.ModuleType("homeassistant.config_entries"),
        "homeassistant.const": types.ModuleType("homeassistant.const"),
        "homeassistant.core": types.ModuleType("homeassistant.core"),
        "homeassistant.exceptions": types.ModuleType("homeassistant.exceptions"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.update_coordinator": types.ModuleType("homeassistant.helpers.update_coordinator"),
        "homeassistant.helpers.entity": types.ModuleType("homeassistant.helpers.entity"),
        "homeassistant.helpers.entity_platform": types.ModuleType("homeassistant.helpers.entity_platform"),
        "homeassistant.components": types.ModuleType("homeassistant.components"),
        "homeassistant.components.sensor": types.ModuleType("homeassistant.components.sensor"),
    }
    mods["homeassistant.const"].CONF_USERNAME = "username"
    mods["homeassistant.const"].CONF_PASSWORD = "password"

    class _Meta(type):
        def __getitem__(cls, item): return cls

    class _CoordEntity(metaclass=_Meta):
        def __init__(self, coordinator): self.coordinator = coordinator
        def async_on_remove(self, cb): pass

    class _DUC(metaclass=_Meta):
        def __init__(self, *a, **kw): pass

    class _DeviceInfo(dict): pass
    class _SensorEntity: pass
    class _SDC: MONETARY = "monetary"
    class _SSC: TOTAL = "total"

    mods["homeassistant.config_entries"].ConfigEntry = type("ConfigEntry", (), {})
    mods["homeassistant.config_entries"].ConfigFlow = object
    mods["homeassistant.core"].HomeAssistant = object
    mods["homeassistant.helpers.update_coordinator"].CoordinatorEntity = _CoordEntity
    mods["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = _DUC
    mods["homeassistant.helpers.update_coordinator"].UpdateFailed = Exception
    mods["homeassistant.helpers.entity"].DeviceInfo = _DeviceInfo
    mods["homeassistant.helpers.entity_platform"].AddEntitiesCallback = type(None)
    mods["homeassistant.components.sensor"].SensorEntity = _SensorEntity
    mods["homeassistant.components.sensor"].SensorDeviceClass = _SDC
    mods["homeassistant.components.sensor"].SensorStateClass = _SSC
    mods["homeassistant.exceptions"].ConfigEntryAuthFailed = Exception
    mods["homeassistant.exceptions"].ConfigEntryNotReady = Exception

    for name, mod in mods.items():
        sys.modules[name] = mod

_stub_ha()

# ---------------------------------------------------------------------------
# Now import the integration
# ---------------------------------------------------------------------------
sys.path.insert(0, ".")
from custom_components.easypass_th.const import (
    CARD_API_URL,
    CARD_LIST_URL,
    LOGIN_POST_URL,
    LOGIN_URL,
    REQUEST_TIMEOUT_SECONDS,
    SESSION_USER_AGENT,
    USAGE_API_URL,
)
from custom_components.easypass_th.scraper import (
    EasyPassAuthError,
    EasyPassConnectionError,
    EasyPassScraper,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sep(title=""):
    width = 70
    if title:
        print(f"\n{'─' * 3} {title} {'─' * (width - len(title) - 5)}")
    else:
        print("─" * width)

def _pp(data):
    """Pretty-print JSON data."""
    print(json.dumps(data, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# Patched scraper that prints raw responses
# ---------------------------------------------------------------------------

class DebugScraper(EasyPassScraper):
    """Subclass that prints raw API responses before parsing."""

    def _scrape_card(self):
        assert self._session is not None

        # Step 1: GET card list page for CSRF
        page_resp = self._session.get(
            CARD_LIST_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        page_resp.raise_for_status()

        if self._is_login_page(page_resp.url, page_resp.text):
            from custom_components.easypass_th.scraper import EasyPassSessionExpiredError
            raise EasyPassSessionExpiredError()

        csrf_token = self._extract_csrf_meta(page_resp.text)
        print(f"  CSRF token  : {csrf_token[:20]}…" if csrf_token else "  CSRF token  : (none)")

        # Step 2: GET /eservice/easypasscardlist/get-all
        api_resp = self._session.get(
            CARD_API_URL,
            params={"_token": csrf_token, "page": 1},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": CARD_LIST_URL,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        api_resp.raise_for_status()
        data = api_resp.json()

        _sep("RAW RESPONSE: get-all")
        _pp(data)

        # Parse card
        card = self._parse_card(data)

        # Step 3: usage history
        if card.cust_acct_id and csrf_token:
            today = date.today()
            start_date = today.replace(day=1).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")

            payload = {
                "cust_acct_id": card.cust_acct_id,
                "start_date": start_date,
                "end_date": end_date,
                "language": "th",
                "flag": "card_history_search",
                "_token": csrf_token,
                "choice": "",
            }
            usage_resp = self._session.post(
                USAGE_API_URL,
                data=payload,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": CARD_LIST_URL,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            usage_resp.raise_for_status()
            usage_data = usage_resp.json()

            _sep(f"RAW RESPONSE: usage ({start_date} → {end_date})")
            _pp(usage_data)

            card.usage_history = self._fetch_usage(card.cust_acct_id, csrf_token)
        else:
            _sep("usage history skipped")
            print(f"  cust_acct_id is empty — field not found in get-all response")
            print(f"  Fix: check get-all JSON above and update _parse_card() in scraper.py")

        return card


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    username = os.environ.get("EASYPASS_USER") or input("Email   : ").strip()
    password = os.environ.get("EASYPASS_PASS") or getpass("Password: ")

    scraper = DebugScraper(username, password)

    _sep("LOGIN")
    print(f"  Logging in as {username} …")

    try:
        card = scraper.fetch_card()
    except EasyPassAuthError as e:
        print(f"\n[ERROR] Authentication failed: {e}")
        return 1
    except EasyPassConnectionError as e:
        print(f"\n[ERROR] Connection failed: {e}")
        return 1
    finally:
        scraper.close()

    _sep("PARSED CARD")
    print(f"  serial_number        : {card.serial_number}")
    print(f"  license_plate        : {card.license_plate}")
    print(f"  balance              : {card.balance} THB")
    print(f"  owner_name           : {card.owner_name}")
    print(f"  mflow_message        : {card.mflow_message}")
    print(f"  cust_acct_id         : {card.cust_acct_id!r}  ← must be non-empty for usage history")
    print(f"  last_transaction_date: {card.last_transaction_date}")
    print(f"  last_topup_amount    : {card.last_topup_amount}")

    _sep("PARSED USAGE HISTORY")
    if card.usage_history:
        print(f"  {len(card.usage_history)} transactions\n")
        print(f"  {'#':<4} {'Date':<22} {'Type':<12} {'Amount':>8}  {'Balance':>10}  Location")
        print(f"  {'─'*4} {'─'*22} {'─'*12} {'─'*8}  {'─'*10}  {'─'*30}")
        for t in card.usage_history:
            print(f"  {t.row_id:<4} {t.txn_date:<22} {t.txn_desc:<12} {t.txn_amt:>8.2f}  {t.txn_balance:>10.2f}  {t.location}")
        print()
        print(f"  Monthly toll spend   : {card.monthly_toll_spend:.2f} THB")
        if card.last_toll:
            print(f"  Last toll location   : {card.last_toll.location} ({card.last_toll.txn_date})")
        if card.last_topup:
            print(f"  Last top-up          : {card.last_topup.txn_amt:.2f} THB ({card.last_topup.txn_date})")
    else:
        print("  No transactions returned.")
        print("  Possible reasons:")
        print("    1. cust_acct_id is empty (fix field mapping — see note above)")
        print("    2. No transactions in the current month date range")

    _sep()
    return 0


if __name__ == "__main__":
    sys.exit(main())
