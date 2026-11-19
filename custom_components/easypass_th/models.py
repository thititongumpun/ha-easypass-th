"""Data models for Thailand Easy Pass integration."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional


def history_start(history_days: int, today: date) -> date:
    """First day included for a history option: 30 = this month, 90 = this month + 2 before."""
    if history_days == 30:
        return today.replace(day=1)
    if history_days == 90:
        year, month = today.year, today.month - 2
        if month < 1:
            month += 12
            year -= 1
        return date(year, month, 1)
    return today - timedelta(days=history_days)


@dataclass
class EasyPassTransaction:
    """A single toll or top-up transaction from the usage history API."""

    row_id: int = 0
    location: str = ""
    txn_date: str = ""
    txn_desc: str = ""      # "ผ่านทาง" = toll, "เติมเงิน" = top-up
    txn_amt: float = 0.0
    txn_balance: float = 0.0

    @property
    def txn_datetime(self) -> Optional[datetime]:
        """Parse txn_date ("dd/mm/YYYY HH:MM:SS"); Buddhist-era years are converted to CE."""
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(self.txn_date.strip(), fmt)
            except ValueError:
                continue
            return dt.replace(year=dt.year - 543) if dt.year > 2400 else dt
        return None

    @property
    def is_toll(self) -> bool:
        return self.txn_desc == "ผ่านทาง"

    @property
    def is_topup(self) -> bool:
        return self.txn_desc == "เติมเงิน"


@dataclass
class EasyPassCard:
    """Represents a single Easy Pass card/account."""

    serial_number: str = ""
    balance: Optional[float] = None
    license_plate: str = ""
    owner_name: str = ""
    mflow_message: str = ""         # easyPassPlusData.mflowRegisterMessage
    last_transaction_date: str = ""
    last_topup_amount: Optional[float] = None
    cust_acct_id: str = ""          # account ID used for usage history API
    usage_history: list = field(default_factory=list)  # list[EasyPassTransaction]
    reward_points: Optional[int] = None                # easyPassCardsDataDropdown.Reward_Point
    history_start: Optional[date] = None   # first day of the selected history window
    month_start: Optional[date] = None     # 1st of the current month (Bangkok time)

    raw_html_snippet: str = field(default="", repr=False)

    def is_valid(self) -> bool:
        """Return True if the card has the minimum required data."""
        return bool(self.serial_number or self.license_plate)

    @property
    def history(self) -> list:
        """Transactions inside the selected history window (unparseable dates are kept)."""
        if self.history_start is None:
            return list(self.usage_history)
        return [
            t for t in self.usage_history
            if t.txn_datetime is None or t.txn_datetime.date() >= self.history_start
        ]

    @property
    def month_tolls(self) -> list:
        """Toll transactions dated in the current calendar month."""
        if self.month_start is None:
            return []
        return [
            t for t in self.usage_history
            if t.is_toll and t.txn_datetime and t.txn_datetime.date() >= self.month_start
        ]

    @property
    def monthly_toll_spend(self) -> float:
        """Sum of toll charges from the 1st of the current month through today."""
        return sum(t.txn_amt for t in self.month_tolls)

    @property
    def last_toll(self) -> Optional["EasyPassTransaction"]:
        """Most recent toll transaction, or None."""
        tolls = [t for t in self.usage_history if t.is_toll]
        return tolls[-1] if tolls else None

    @property
    def last_topup(self) -> Optional["EasyPassTransaction"]:
        """Most recent top-up transaction, or None."""
        topups = [t for t in self.usage_history if t.is_topup]
        return topups[-1] if topups else None
