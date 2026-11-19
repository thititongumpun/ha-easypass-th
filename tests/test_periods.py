import importlib.util
from datetime import date, datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "easypass_models",
    Path(__file__).resolve().parents[1] / "custom_components" / "easypass_th" / "models.py",
)
models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(models)

TOLL, TOPUP = "ผ่านทาง", "เติมเงิน"


def _t(d, desc, amt):
    return models.EasyPassTransaction(txn_date=d, txn_desc=desc, txn_amt=amt)


def test_history_start():
    hs = models.history_start
    assert hs(30, date(2026, 11, 19)) == date(2026, 11, 1)
    assert hs(90, date(2026, 11, 19)) == date(2026, 9, 1)
    assert hs(90, date(2026, 1, 31)) == date(2025, 11, 1)
    assert hs(90, date(2026, 2, 28)) == date(2025, 12, 1)
    assert hs(7, date(2026, 11, 19)) == date(2026, 11, 12)


def test_txn_datetime():
    assert _t("24/10/2026 09:32:03", TOLL, 1).txn_datetime == datetime(2026, 10, 24, 9, 32, 3)
    assert _t("24/10/2569 09:32:03", TOLL, 1).txn_datetime.year == 2026
    assert _t("", TOLL, 1).txn_datetime is None
    assert _t("garbage", TOLL, 1).txn_datetime is None


def test_screenshot_regression():
    tolls = [("24/10/2026", 50), ("24/10/2026", 50), ("24/10/2026", 10), ("24/10/2026", 15),
             ("31/10/2026", 60), ("01/11/2026", 50), ("01/11/2026", 10), ("14/11/2026", 60),
             ("15/11/2026", 50), ("15/11/2026", 10)]
    txns = [_t(d + " 10:00:00", TOLL, a) for d, a in tolls]
    txns += [_t("24/10/2026 10:00:00", TOPUP, 100), _t("14/11/2026 10:00:00", TOPUP, 100)]
    card = models.EasyPassCard(
        usage_history=txns, month_start=date(2026, 11, 1), history_start=date(2026, 11, 1)
    )
    assert card.monthly_toll_spend == 180.0
    assert len(card.month_tolls) == 5
    assert len(card.history) == 6


def test_last_day_of_31_day_month():
    card = models.EasyPassCard(
        usage_history=[_t("31/10/2026 23:59:59", TOLL, 20)], month_start=date(2026, 10, 1)
    )
    assert card.monthly_toll_spend == 20.0


def test_defaults():
    assert models.EasyPassCard().history == []
    t = _t("01/11/2026", TOLL, 1)
    assert models.EasyPassCard(usage_history=[t]).history == [t]
