"""Data models for Thailand Easy Pass integration."""

from dataclasses import dataclass, field
from typing import Optional


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

    raw_html_snippet: str = field(default="", repr=False)

    def is_valid(self) -> bool:
        """Return True if the card has the minimum required data."""
        return bool(self.serial_number or self.license_plate)

    @property
    def monthly_toll_spend(self) -> float:
        """Sum of toll charges in the fetched usage period."""
        return sum(t.txn_amt for t in self.usage_history if t.is_toll)

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
