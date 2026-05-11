"""
Web scraper for thaieasypass.exat.co.th.

Runs in a thread-pool executor so it never blocks the HA event loop.
All network I/O uses requests.Session with cookie persistence.

HOW SESSION WORKS
-----------------
1. GET login page → capture __RequestVerificationToken (ASP.NET anti-forgery).
2. POST credentials + token → server sets auth cookies.
3. Subsequent GETs carry cookies automatically via requests.Session.
4. On expiry the server redirects back to /Account/Login → we detect this
   and raise SessionExpiredError so the coordinator can re-authenticate.

ADAPTING THE SELECTORS
-----------------------
If the site layout changes, only this file needs updating.
Run `python -c "from scraper import EasyPassScraper; ..."` standalone to debug.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .const import (
    BASE_URL,
    CARD_API_URL,
    CARD_LIST_URL,
    LOGIN_POST_URL,
    LOGIN_URL,
    MAX_LOGIN_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    SESSION_USER_AGENT,
    USAGE_API_URL,
)
from .models import EasyPassCard, EasyPassTransaction

_LOGGER = logging.getLogger(__name__)


class EasyPassAuthError(Exception):
    """Raised when credentials are rejected."""


class EasyPassSessionExpiredError(Exception):
    """Raised when the session has expired and needs re-login."""


class EasyPassConnectionError(Exception):
    """Raised on network / timeout failures."""


class EasyPassScraper:
    """Stateful scraper that maintains a logged-in requests.Session."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session: Optional[requests.Session] = None
        self._login_attempts = 0

    # ------------------------------------------------------------------
    # Public API (called from executor thread by coordinator)
    # ------------------------------------------------------------------

    def fetch_cards(self) -> list[EasyPassCard]:
        """
        Return all cards for the account.  Automatically logs in on first call
        or re-logs in after session expiry (up to MAX_LOGIN_RETRIES).
        """
        for attempt in range(MAX_LOGIN_RETRIES):
            try:
                if self._session is None:
                    self._do_login()
                return self._scrape_cards()
            except EasyPassSessionExpiredError:
                _LOGGER.info(
                    "Session expired (attempt %d/%d), re-logging in.",
                    attempt + 1,
                    MAX_LOGIN_RETRIES,
                )
                self._session = None
            except EasyPassAuthError:
                raise  # Bad credentials – no point retrying
            except Exception as exc:
                _LOGGER.warning("fetch_cards attempt %d failed: %s", attempt + 1, exc)
                self._session = None
                if attempt == MAX_LOGIN_RETRIES - 1:
                    raise EasyPassConnectionError(str(exc)) from exc
                time.sleep(2 ** attempt)  # 1 s, 2 s back-off

        raise EasyPassConnectionError("Max login retries exceeded.")

    def close(self) -> None:
        """Release the underlying session."""
        if self._session:
            self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": SESSION_USER_AGENT,
                "Accept-Language": "th,en;q=0.9",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/webp,*/*;q=0.8"
                ),
            }
        )
        return session

    def _do_login(self) -> None:
        """Perform a fresh login, storing auth cookies in self._session."""
        _LOGGER.debug("Logging in as %s", self._username)
        session = self._make_session()

        # Step 1: GET login page to harvest anti-CSRF token
        try:
            resp = session.get(
                LOGIN_URL,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EasyPassConnectionError(f"Cannot reach login page: {exc}") from exc

        csrf_token = self._extract_csrf(resp.text)
        if not csrf_token:
            _LOGGER.warning(
                "No CSRF token found on login page – proceeding without it. "
                "The site may have changed its HTML."
            )

        # Step 2: POST via AJAX to /eservice/login (jQuery XHR, returns JSON)
        payload = {
            "_token": csrf_token or "",
            "user_name": self._username,
            "password": self._password,
        }
        try:
            resp = session.post(
                LOGIN_POST_URL,
                data=payload,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": LOGIN_URL,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EasyPassConnectionError(f"Login POST failed: {exc}") from exc

        # Step 3: Parse JSON response
        try:
            result = resp.json()
            _LOGGER.debug("Login response JSON: %s", result)
        except Exception:
            # Unexpected non-JSON response — treat as failure
            raise EasyPassConnectionError(
                f"Login returned unexpected content-type: {resp.headers.get('Content-Type')}"
            )

        # The JS at line 944 redirects to /eservice/easypasscardlist on success.
        # Common JSON shapes: {"status":"success"}, {"redirect":"..."}, {"error":"..."}
        status = result.get("status") or result.get("Status") or ""
        error_msg = result.get("message") or result.get("error") or result.get("msg") or ""

        if str(status).lower() in ("success", "ok", "true", "1") or result.get("redirect"):
            _LOGGER.debug("Login successful (status=%r).", status)
        elif error_msg:
            _LOGGER.error("Login rejected by server: %s", error_msg)
            raise EasyPassAuthError(f"Invalid credentials: {error_msg}")
        else:
            # Dump the full response so we can adapt
            _LOGGER.error("Unrecognised login response: %s", result)
            raise EasyPassAuthError(f"Login failed – unexpected response: {result}")

        self._session = session
        self._login_attempts = 0
        _LOGGER.debug("Login successful.")

    def _scrape_cards(self) -> list[EasyPassCard]:
        """
        Fetch all cards via the JSON API.

        Step 1: GET the card list page to pick up a fresh CSRF token from
                the <meta name="csrf-token"> tag (Laravel refreshes it per session).
        Step 2: GET /eservice/easypasscardlist/get-all with that token.
                Returns JSON: { easyPassCardsDataDropdown: [...], easyPassCardsData: {...} }
        """
        assert self._session is not None

        # Step 1: get fresh CSRF token from the card list page
        try:
            page_resp = self._session.get(
                CARD_LIST_URL,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            page_resp.raise_for_status()
        except requests.RequestException as exc:
            raise EasyPassConnectionError(f"Cannot reach card list page: {exc}") from exc

        if self._is_login_page(page_resp.url, page_resp.text):
            raise EasyPassSessionExpiredError()

        csrf_token = self._extract_csrf_meta(page_resp.text)
        _LOGGER.debug("Card page CSRF token: %s…", csrf_token[:10] if csrf_token else "NONE")

        # Step 2: call the JSON API
        try:
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
        except requests.RequestException as exc:
            raise EasyPassConnectionError(f"Card API request failed: {exc}") from exc

        try:
            data = api_resp.json()
        except Exception as exc:
            raise EasyPassConnectionError(
                f"Card API returned non-JSON ({api_resp.headers.get('Content-Type')}): {exc}"
            ) from exc

        _LOGGER.debug("Card API response keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))
        cards = self._parse_cards(data)

        # Fetch usage history for each card that has a cust_acct_id
        for card in cards:
            if card.cust_acct_id and csrf_token:
                card.usage_history = self._fetch_usage(card.cust_acct_id, csrf_token)

        return cards

    # ------------------------------------------------------------------
    # Parsing helpers  –– ADAPT THESE to match actual site HTML
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_csrf(html: str) -> str:
        """Extract _token from a login form input."""
        soup = BeautifulSoup(html, "lxml")
        token_el = soup.find("input", {"name": "_token"})
        return token_el["value"] if token_el else ""

    @staticmethod
    def _extract_csrf_meta(html: str) -> str:
        """Extract CSRF token from Laravel <meta name='csrf-token'> tag."""
        soup = BeautifulSoup(html, "lxml")
        meta = soup.find("meta", {"name": "csrf-token"})
        return meta["content"] if meta else ""

    @staticmethod
    def _is_login_page(url: str, html: str) -> bool:
        """Heuristic: are we back on the login page?
        Must NOT match the card page — every Laravel page has name="_token" in a meta tag.
        Only the login page has the user_name input field in a form.
        """
        return (
            'type="text" id="user_name"' in html
            or 'name="user_name" placeholder=' in html
        )

    def _fetch_usage(self, cust_acct_id: str, csrf_token: str) -> list:
        """
        POST to /eservice/easypasscardlist/usage to get transaction history.

        Fetches from the 1st of the current month through today.
        Returns list[EasyPassTransaction] sorted oldest-first (as the API returns).
        """
        from datetime import date
        today = date.today()
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        payload = {
            "cust_acct_id": cust_acct_id,
            "start_date": start_date,
            "end_date": end_date,
            "language": "th",
            "flag": "card_history_search",
            "_token": csrf_token,
            "choice": "",
        }

        try:
            resp = self._session.post(
                USAGE_API_URL,
                data=payload,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": CARD_LIST_URL,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            _LOGGER.warning("Usage history fetch failed: %s", exc)
            return []

        tag_usage: list = (data.get("data") or {}).get("tag_usage") or []
        transactions = []
        for item in tag_usage:
            try:
                txn = EasyPassTransaction(
                    row_id=int(item.get("row_id", 0)),
                    location=item.get("location", ""),
                    txn_date=item.get("txn_date", ""),
                    txn_desc=item.get("txn_desc", ""),
                    txn_amt=float(str(item.get("txn_amt", 0)).replace(",", "") or 0),
                    txn_balance=float(str(item.get("txn_balance", 0)).replace(",", "") or 0),
                )
                transactions.append(txn)
            except (ValueError, TypeError) as exc:
                _LOGGER.debug("Skipping malformed transaction row: %s — %s", item, exc)

        _LOGGER.debug("Fetched %d transactions for %s", len(transactions), cust_acct_id)
        return transactions

    @staticmethod
    def _parse_balance(text: str) -> Optional[float]:
        """Parse a Thai-formatted number like '1,234.56' to float."""
        text = text.replace(",", "").strip()
        match = re.search(r"[\d.]+", text)
        return float(match.group()) if match else None

    def _parse_cards(self, data: dict) -> list[EasyPassCard]:
        """
        Parse the JSON response from /eservice/easypasscardlist/get-all.

        All records in easyPassCardsData.data are returned (one per card).

        Fields mapped:
            SmartcardID                        → serial_number
            PlateNo + PlateProvince            → license_plate
            Title + Given_Name + Family_Name   → owner_name
            AC_Balance                         → balance
            easyPassPlusData.mflowRegisterMessage → mflow_message
        """
        raw_cards: list = (data.get("easyPassCardsData") or {}).get("data") or []
        if not raw_cards:
            _LOGGER.warning("Card API returned no cards. Keys: %s", list(data.keys()))
            return []

        results: list[EasyPassCard] = []
        for d in raw_cards:
            card = EasyPassCard()
            card.serial_number = d.get("SmartcardID", "")
            card.license_plate = (
                d.get("PlateNo", "") + " " + d.get("PlateProvince", "")
            ).strip()
            card.balance = EasyPassScraper._parse_balance(str(d.get("AC_Balance", "") or ""))
            card.owner_name = (
                f"{d.get('Title', '')}{d.get('Given_Name', '')} {d.get('Family_Name', '')}"
            ).strip()
            card.mflow_message = (
                (d.get("easyPassPlusData") or {}).get("mflowRegisterMessage", "")
            )
            card.cust_acct_id = d.get("CustomerID", "")

            if not card.is_valid():
                _LOGGER.warning("Parsed card has no serial or license plate. Entry: %s", d)
            else:
                results.append(card)
                _LOGGER.debug("Parsed card: %s", card)

        # Reward points from the parallel dropdown list (index matches card position)
        dropdown: list = data.get("easyPassCardsDataDropdown") or []
        for i, card in enumerate(results):
            if i < len(dropdown):
                raw_points = dropdown[i].get("Reward_Point")
                try:
                    card.reward_points = int(raw_points) if raw_points is not None else None
                except (ValueError, TypeError):
                    card.reward_points = None

        _LOGGER.debug("Total cards parsed: %d", len(results))
        return results
