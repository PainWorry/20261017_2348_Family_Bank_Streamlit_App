"""
Google Sheets Synchronization Engine for Family Bank Application.
Automatically mirrors all transactions and account summaries to a target Google Spreadsheet.
Ensures zero data loss on Streamlit Community Cloud and allows Dad to view live records in Google Sheets.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import streamlit as st

# Safe optional imports for Google APIs
try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GOOGLE_DEPS = True
except ImportError:
    HAS_GOOGLE_DEPS = False


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

TRANSACTIONS_HEADERS = [
    "Transaction ID",
    "Timestamp",
    "Member ID",
    "Member Name",
    "Type",
    "Amount (THB)",
    "Status",
    "Reviewed By",
    "Reviewed At",
    "Notes",
    "Bank Info"
]

BALANCES_HEADERS = [
    "Member ID",
    "Member Name",
    "Confirmed Balance (THB)",
    "Pending Deposits (THB)",
    "Total Lifetime Deposited (THB)",
    "Total Lifetime Withdrawn (THB)",
    "Last Synced"
]


class GoogleSheetsSyncEngine:
    def __init__(self):
        self.client: Optional[Any] = None
        self.spreadsheet: Optional[Any] = None
        self.sheet_name: str = ""
        self.configured: bool = False
        self.error_message: Optional[str] = None
        self._initialize()

    def _initialize(self):
        if not HAS_GOOGLE_DEPS:
            self.error_message = "gspread or google-auth package not installed."
            return

        secrets_obj = getattr(st, "secrets", {})
        
        # Look for gcp service account credentials in st.secrets
        # Standard Streamlit formats: st.secrets["gcp_service_account"] or st.secrets["connections"]["gsheets"]
        sa_creds = None
        spreadsheet_target = None

        if "connections" in secrets_obj and "gsheets" in secrets_obj["connections"]:
            cfg = secrets_obj["connections"]["gsheets"]
            spreadsheet_target = cfg.get("spreadsheet") or cfg.get("url") or cfg.get("spreadsheet_url")
            # Can be service account dict or raw values
            if "service_account" in cfg:
                sa_creds = cfg["service_account"]
            elif "private_key" in cfg:
                sa_creds = cfg

        if not sa_creds and "gcp_service_account" in secrets_obj:
            sa_creds = dict(secrets_obj["gcp_service_account"])
            spreadsheet_target = secrets_obj.get("google_sheet_url") or secrets_obj.get("spreadsheet_name") or "Family_Bank_Vault_Ledger"

        if not sa_creds:
            self.error_message = "Google Service Account credentials not found in .streamlit/secrets.toml."
            return

        try:
            creds = Credentials.from_service_account_info(sa_creds, scopes=SCOPES)
            self.client = gspread.authorize(creds)

            # Open target spreadsheet by URL, ID, or Title
            if spreadsheet_target and spreadsheet_target.startswith("https://"):
                self.spreadsheet = self.client.open_by_url(spreadsheet_target)
            elif spreadsheet_target:
                try:
                    self.spreadsheet = self.client.open(spreadsheet_target)
                except Exception:
                    self.spreadsheet = self.client.open_by_key(spreadsheet_target)
            else:
                self.spreadsheet = self.client.open("Family_Bank_Vault_Ledger")

            self.sheet_name = self.spreadsheet.title
            self._ensure_worksheets()
            self.configured = True
            self.error_message = None
        except Exception as e:
            self.configured = False
            self.error_message = f"Failed to connect to Google Sheets: {str(e)}"

    def _ensure_worksheets(self):
        """Ensures that required worksheets exist with standard header rows."""
        if not self.spreadsheet:
            return

        existing_titles = [ws.title for ws in self.spreadsheet.worksheets()]

        # 1. Transactions Ledger Sheet
        if "Transactions_Ledger" not in existing_titles:
            ws_tx = self.spreadsheet.add_worksheet(title="Transactions_Ledger", rows=1000, cols=15)
            ws_tx.append_row(TRANSACTIONS_HEADERS)
        else:
            ws_tx = self.spreadsheet.worksheet("Transactions_Ledger")
            first_row = ws_tx.row_values(1)
            if not first_row:
                ws_tx.append_row(TRANSACTIONS_HEADERS)

        # 2. Account Balances Sheet
        if "Account_Balances" not in existing_titles:
            ws_bal = self.spreadsheet.add_worksheet(title="Account_Balances", rows=20, cols=10)
            ws_bal.append_row(BALANCES_HEADERS)
        else:
            ws_bal = self.spreadsheet.worksheet("Account_Balances")
            first_row = ws_bal.row_values(1)
            if not first_row:
                ws_bal.append_row(BALANCES_HEADERS)

    def is_active(self) -> bool:
        return self.configured and self.spreadsheet is not None

    def sync_all(self, transactions: List[Any], summaries: List[Any], users_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """Performs full synchronization of transactions and balances to Google Sheets."""
        if not self.is_active():
            return False, self.error_message or "Google Sheets sync is not configured."

        try:
            # 1. Sync Transactions
            ws_tx = self.spreadsheet.worksheet("Transactions_Ledger")
            tx_rows = [TRANSACTIONS_HEADERS]
            for t in transactions:
                member_name = users_dict.get(t.user_id, {}).get("display_name", t.user_id)
                tx_rows.append([
                    t.tx_id,
                    t.created_at,
                    t.user_id,
                    member_name,
                    t.tx_type,
                    float(t.amount),
                    t.status,
                    t.reviewed_by or "",
                    t.reviewed_at or "",
                    t.notes or "",
                    t.bank_info or ""
                ])
            ws_tx.clear()
            ws_tx.update(values=tx_rows, range_name="A1")

            # 2. Sync Balances
            ws_bal = self.spreadsheet.worksheet("Account_Balances")
            bal_rows = [BALANCES_HEADERS]
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for s in summaries:
                bal_rows.append([
                    s.user_id,
                    s.display_name,
                    float(s.confirmed_balance),
                    float(s.pending_deposits),
                    float(s.total_deposited),
                    float(s.total_withdrawn),
                    now_str
                ])
            ws_bal.clear()
            ws_bal.update(values=bal_rows, range_name="A1")

            return True, f"Successfully synced {len(transactions)} records to Google Sheet: '{self.sheet_name}'"
        except Exception as e:
            return False, f"Google Sheet sync error: {str(e)}"


# Singleton Google Sheets Sync Engine
_gsheet_engine: Optional[GoogleSheetsSyncEngine] = None

def get_gsheets_sync() -> GoogleSheetsSyncEngine:
    global _gsheet_engine
    if _gsheet_engine is None:
        _gsheet_engine = GoogleSheetsSyncEngine()
    return _gsheet_engine
