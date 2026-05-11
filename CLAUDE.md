# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (`custom_components/easypass_th`) that scrapes the Thailand Easy Pass website (`https://thaieasypass.exat.co.th`) and exposes card balance/info as HA sensor entities.

## Development setup

Install scraper dependencies outside HA for standalone testing:

```bash
pip install requests beautifulsoup4 lxml
```

Test the scraper directly (no HA required):

```python
# from repo root
from custom_components.easypass_th.scraper import EasyPassScraper
scraper = EasyPassScraper("your_username", "your_password")
card = scraper.fetch_card()
print(card)
scraper.close()
```

Deploy to HA by copying `custom_components/easypass_th/` into the HA config `custom_components/` directory and restarting HA. HA auto-installs pip requirements from `manifest.json` on first load.

## Architecture

```
Config Flow (UI)  →  config entry (stores credentials)
                          │
                   EasyPassCoordinator          ← coordinator.py
                   (DataUpdateCoordinator)
                   polls every 30 min
                          │
                   run_in_executor              ← never block the event loop
                          │
                   EasyPassScraper              ← scraper.py
                   (requests + bs4)
                          │
                   EasyPassCard (dataclass)     ← models.py
                          │
              ┌───────────┴──────────────┐
         6 CoordinatorEntity sensors     ← sensor.py
```

**Key data flow:** Coordinator calls `scraper.fetch_card()` in a thread executor. The scraper maintains a `requests.Session` across calls (cookie persistence). On session expiry the scraper raises `EasyPassSessionExpiredError`, auto-retries login up to `MAX_LOGIN_RETRIES` times, then raises `EasyPassConnectionError` if retries are exhausted. Auth errors raise `EasyPassAuthError` → coordinator converts this to `ConfigEntryAuthFailed` → HA stops polling and shows a re-auth notification.

## The one file you will need to adapt

**`scraper.py` — specifically `_parse_card()` and the URLs in `const.py`.**

The CSS selectors in `_parse_card()` are intelligent guesses for a typical ASP.NET site. Before the integration works you must:

1. Log into `https://thaieasypass.exat.co.th` with DevTools → Network open
2. Confirm the actual login POST URL and form field names (currently assumed: `POST /Account/Login` with fields `UserName`, `Password`, `__RequestVerificationToken`)
3. Find the actual URL of the card info page (currently assumed: `GET /Card/CardInfo`)
4. Inspect the HTML of each data field and update the `soup.find(id=...)` / `soup.select_one(...)` calls in `_parse_card()`
5. Update `LOGIN_URL`, `DASHBOARD_URL`, `CARD_INFO_URL` in `const.py` if different

Everything else (coordinator, sensors, config flow) is stable and does not need site-specific changes.

## Sensor entities

All sensors live under one HA device per config entry. Unique IDs use `{entry_id}_{sensor_key}`. The `SENSOR_*` constants in `const.py` are the single source of truth for keys, display names, and icons.

| Sensor key    | Source field                     | Unit |
|---------------|----------------------------------|------|
| `balance`     | `EasyPassCard.balance`           | THB  |
| `license`     | `EasyPassCard.license_plate`     | —    |
| `serial`      | `EasyPassCard.serial_number`     | —    |
| `last_update` | `EasyPassCard.last_transaction_date` | — |
| `last_topup`  | `EasyPassCard.last_topup_amount` | THB  |
| `owner`       | `EasyPassCard.owner_name`        | —    |

## HA error lifecycle

| Scraper raises           | Coordinator converts to        | HA behaviour                          |
|--------------------------|-------------------------------|---------------------------------------|
| `EasyPassAuthError`      | `ConfigEntryAuthFailed`       | Stop polling; show re-auth UI         |
| `EasyPassConnectionError`| `UpdateFailed`                | Mark unavailable; retry next interval |
| `EasyPassSessionExpiredError` | (internal; auto-retried) | Transparent re-login                 |
| Any on first boot        | `ConfigEntryNotReady`         | HA retries setup with back-off        |

## Dashboard & automation

See `dashboard_examples.yaml` for Mushroom card, gauge, entities card, and low-balance automation examples.
