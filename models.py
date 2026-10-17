"""
Data models and enumeration schemas for Family Bank Web Application.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class TransactionType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    ADJUSTMENT = "ADJUSTMENT"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class User:
    user_id: str
    display_name: str
    role: str
    password_hash: str


@dataclass
class Transaction:
    tx_id: str
    user_id: str
    tx_type: str
    amount: float
    slip_path: Optional[str] = None
    status: str = TransactionStatus.PENDING.value
    created_at: str = ""
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    notes: Optional[str] = None
    bank_info: Optional[str] = None


@dataclass
class AccountSummary:
    user_id: str
    display_name: str
    confirmed_balance: float
    pending_deposits: float
    total_deposited: float
    total_withdrawn: float
