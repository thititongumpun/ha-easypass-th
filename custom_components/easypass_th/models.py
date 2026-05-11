"""Data models for Thailand Easy Pass integration."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EasyPassCard:
    """Represents a single Easy Pass card/account."""

    serial_number: str = ""
    balance: Optional[float] = None
    license_plate: str = ""
    owner_name: str = ""
    mflow_message: str = ""     # easyPassPlusData.mflowRegisterMessage
    last_transaction_date: str = ""
    last_topup_amount: Optional[float] = None

    raw_html_snippet: str = field(default="", repr=False)

    def is_valid(self) -> bool:
        """Return True if the card has the minimum required data."""
        return bool(self.serial_number or self.license_plate)
