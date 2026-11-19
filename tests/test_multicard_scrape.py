"""Multi-card account: each card gets its own balance, history and monthly spend.

Needs requests/bs4/lxml (skipped otherwise). Loads the integration modules
without running the package __init__ (which imports Home Assistant).
"""
import importlib
import sys
import types
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("lxml")
pytest.importorskip("requests")

_PKG = "easypass_pkg"
if _PKG not in sys.modules:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "easypass_th")]
    sys.modules[_PKG] = pkg
scraper_mod = importlib.import_module(f"{_PKG}.scraper")
const = importlib.import_module(f"{_PKG}.const")

TOLL, TOPUP = "ผ่านทาง", "เติมเงิน"

# Shape of /get-all on a multi-card account: shared CustomerID (A…), per-card AccountNumber (B…).
GET_ALL = {
    "easyPassCardsData": {"data": [
        {"SmartcardID": "S1", "PlateNo": "1กก 1111", "PlateProvince": "กรุงเทพมหานคร",
         "AC_Balance": "200.00", "CustomerID": "A100", "AccountNumber": "B1"},
        {"SmartcardID": "S2", "PlateNo": "2ขข 2222", "PlateProvince": "นนทบุรี",
         "AC_Balance": "1,085.50", "CustomerID": "A100", "AccountNumber": "B2"},
    ]},
    "easyPassCardsDataDropdown": [
        {"SmartcardID": "S1", "Reward_Point": "1509"},
        {"SmartcardID": "S2", "Reward_Point": "320"},
    ],
}

USAGE = {
    "B1": [  # 1 Oct toll (outside "this month"), 2 Nov tolls, 1 Nov top-up
        ("31/10/2026 20:45:58", TOLL, "60.00"),
        ("01/11/2026 10:11:03", TOLL, "50.00"),
        ("14/11/2026 16:12:11", TOPUP, "100.00"),
        ("15/11/2026 10:42:58", TOLL, "10.00"),
    ],
    "B2": [
        ("03/11/2026 07:55:40", TOLL, "1,200.00"),
        ("18/11/2026 08:05:12", TOLL, "20.00"),
    ],
}


class _Resp:
    def __init__(self, url, text="", data=None):
        self.url, self.text, self._data, self.headers = url, text, data, {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _Session:
    def __init__(self):
        self.usage_calls = []

    def get(self, url, params=None, **_):
        if url == const.CARD_LIST_URL:
            return _Resp(url, '<html><head><meta name="csrf-token" content="tok"></head></html>')
        if url == const.CARD_API_URL:
            # Page 2 repeats page 1, which stops pagination.
            return _Resp(url, data=GET_ALL)
        raise AssertionError(url)

    def post(self, url, data=None, **_):
        assert url == const.USAGE_API_URL
        self.usage_calls.append((data["cust_acct_id"], data["start_date"], data["end_date"]))
        rows = [
            {"row_id": i + 1, "txn_date": d, "txn_desc": desc, "txn_amt": amt,
             "txn_balance": "0", "location": "x"}
            for i, (d, desc, amt) in enumerate(USAGE[data["cust_acct_id"]])
        ]
        return _Resp(url, data={"data": {"tag_usage": rows}})


@pytest.fixture
def scraped(monkeypatch):
    monkeypatch.setattr(scraper_mod, "_bangkok_today", lambda: date(2026, 11, 19))
    s = scraper_mod.EasyPassScraper("u", "p")
    s._session = _Session()
    cards = s._scrape_cards(history_days=30)
    return s._session, {c.serial_number: c for c in cards}


def test_both_cards_parsed_with_own_balance_and_points(scraped):
    _, cards = scraped
    assert set(cards) == {"S1", "S2"}
    assert cards["S1"].balance == 200.0 and cards["S2"].balance == 1085.5
    assert cards["S1"].reward_points == 1509 and cards["S2"].reward_points == 320
    assert sum(c.balance for c in cards.values()) == 1285.5  # what the dashboard total shows


def test_usage_fetched_per_card_account_number(scraped):
    session, _ = scraped
    assert sorted(session.usage_calls) == [
        ("B1", "2026-11-01", "2026-11-19"),
        ("B2", "2026-11-01", "2026-11-19"),
    ]


def test_history_and_monthly_spend_are_per_card(scraped):
    _, cards = scraped
    s1, s2 = cards["S1"], cards["S2"]
    assert s1.monthly_toll_spend == 60.0 and len(s1.month_tolls) == 2  # Oct toll excluded
    assert s2.monthly_toll_spend == 1220.0 and len(s2.month_tolls) == 2  # "1,200.00" parsed
    assert [t.txn_date[:10] for t in s1.history] == ["01/11/2026", "14/11/2026", "15/11/2026"]
    assert all(t.txn_date[:10] != "31/10/2026" for t in s2.history)
    assert s1.monthly_toll_spend + s2.monthly_toll_spend == 1280.0  # dashboard month total
