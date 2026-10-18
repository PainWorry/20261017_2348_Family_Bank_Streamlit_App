"""
Storage and Ledger Engine for Family Bank Application.
Provides hybrid persistence:
- Default: Local SQLite with file-based slip storage (with base64 fallback for cloud resiliency)
- Cloud ready: Google Sheets / Drive connector hooks via Streamlit secrets
"""

import os
import sqlite3
import base64
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from models import Transaction, AccountSummary, TransactionType, TransactionStatus

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "family_bank.db"
SLIPS_DIR = BASE_DIR / "uploads" / "slips"


class SQLiteLedger:
    def __init__(self, db_path: Path = DB_PATH, slips_dir: Path = SLIPS_DIR, auto_seed: bool = True):
        self.db_path = db_path
        self.slips_dir = slips_dir
        self.slips_dir.mkdir(parents=True, exist_ok=True)
        self.init_db(auto_seed=auto_seed)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self, auto_seed: bool = True):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    tx_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tx_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    slip_path TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    notes TEXT,
                    bank_info TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_credentials (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    must_change_password INTEGER DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

            # Seed default users if not already present
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            default_hashes = {
                "dad": "$2b$12$WsyEpUWniWySzou2CriRceAbtzLjAPgScGa2OkKcFM6TbicSHJyC2",
                "herren": "$2b$12$6oC0El9xuXM2KLf5KZDxl.8mkcDX7ts6LwkoeiAsC/O6cW7VNNGeK",
                "irene": "$2b$12$IudY.IKo5g0q1LvaoLPIZONOe0tuWDXCaJ7tMxb7A4ftuiahvBTly",
                "prim": "$2b$12$QsHAGIeTfgYqSy5LbLpbkeUfGK7D656T8JDa3U9ZaqvV/bvK9oka2",
            }
            for u_id, p_hash in default_hashes.items():
                cursor.execute("""
                    INSERT OR IGNORE INTO user_credentials (user_id, password_hash, must_change_password, updated_at)
                    VALUES (?, ?, 1, ?)
                """, (u_id, p_hash, now_str))
            conn.commit()

        # Auto-seed transactions from standardized_family_ledger.csv on fresh boot (e.g. Streamlit Cloud)
        if auto_seed:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM transactions")
                tx_count = cursor.fetchone()[0]

            if tx_count == 0:
                csv_path = BASE_DIR / "standardized_family_ledger.csv"
                if csv_path.exists():
                    import csv
                    try:
                        with open(csv_path, mode="r", encoding="utf-8") as f:
                            records = list(csv.DictReader(f))
                            if records:
                                self.import_transactions(records)
                    except Exception:
                        pass

    def get_user_credential(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user password hash and must_change_password status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, password_hash, must_change_password, updated_at FROM user_credentials WHERE user_id = ?",
                (user_id.lower(),)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "user_id": row["user_id"],
                    "password_hash": row["password_hash"],
                    "must_change_password": bool(row["must_change_password"]),
                    "updated_at": row["updated_at"]
                }
            return None

    def update_user_password(self, user_id: str, new_password_hash: str, must_change: bool = False) -> bool:
        """Updates user password hash and clears must_change_password flag upon successful change."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_credentials (user_id, password_hash, must_change_password, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    must_change_password = excluded.must_change_password,
                    updated_at = excluded.updated_at
            """, (user_id.lower(), new_password_hash, 1 if must_change else 0, now_str))
            conn.commit()
            return cursor.rowcount > 0

    def reset_user_to_default(self, user_id: str) -> bool:
        """Emergency break-glass reset of a single user credential to official default password."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        default_hashes = {
            "dad": "$2b$12$WsyEpUWniWySzou2CriRceAbtzLjAPgScGa2OkKcFM6TbicSHJyC2",
            "herren": "$2b$12$6oC0El9xuXM2KLf5KZDxl.8mkcDX7ts6LwkoeiAsC/O6cW7VNNGeK",
            "irene": "$2b$12$IudY.IKo5g0q1LvaoLPIZONOe0tuWDXCaJ7tMxb7A4ftuiahvBTly",
            "prim": "$2b$12$QsHAGIeTfgYqSy5LbLpbkeUfGK7D656T8JDa3U9ZaqvV/bvK9oka2",
        }
        uid = user_id.lower().strip()
        p_hash = default_hashes.get(uid, default_hashes["herren"])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_credentials (user_id, password_hash, must_change_password, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    must_change_password = 1,
                    updated_at = excluded.updated_at
            """, (uid, p_hash, now_str))
            conn.commit()
            return True

    def save_slip_image(self, file_bytes: bytes, filename: str, tx_id: str) -> str:
        """Saves uploaded slip to disk and returns relative path and base64 encoded string for fail-safe display."""
        ext = os.path.splitext(filename)[1].lower() or ".jpg"
        safe_name = f"slip_{tx_id}{ext}"
        target_path = self.slips_dir / safe_name
        with open(target_path, "wb") as f:
            f.write(file_bytes)
        
        # Also store small data URI prefix in case the container restarts or for direct rendering
        b64_content = base64.b64encode(file_bytes).decode("utf-8")
        mime = "image/png" if ext == ".png" else "image/jpeg"
        data_uri = f"data:{mime};base64,{b64_content}"
        return data_uri

    def create_transaction(
        self,
        user_id: str,
        tx_type: str,
        amount: float,
        slip_data_uri: Optional[str] = None,
        notes: Optional[str] = None,
        bank_info: Optional[str] = None,
        status: str = TransactionStatus.PENDING.value,
        reviewed_by: Optional[str] = None
    ) -> str:
        import uuid
        tx_id = f"tx_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reviewed_at = now_str if status == TransactionStatus.APPROVED.value else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (
                    tx_id, user_id, tx_type, amount, slip_path,
                    status, created_at, reviewed_at, reviewed_by, notes, bank_info
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx_id, user_id, tx_type, amount, slip_data_uri,
                status, now_str, reviewed_at, reviewed_by, notes, bank_info
            ))
            conn.commit()
        
        # Trigger Google Sheets auto-sync if configured
        self._try_gsheets_sync()
        return tx_id

    def update_transaction_status(self, tx_id: str, new_status: str, reviewer_id: str, admin_notes: Optional[str] = None) -> bool:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if admin_notes:
                cursor.execute("""
                    UPDATE transactions 
                    SET status = ?, reviewed_at = ?, reviewed_by = ?, notes = notes || ' | Admin Note: ' || ?
                    WHERE tx_id = ?
                """, (new_status, now_str, reviewer_id, admin_notes, tx_id))
            else:
                cursor.execute("""
                    UPDATE transactions 
                    SET status = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE tx_id = ?
                """, (new_status, now_str, reviewer_id, tx_id))
            conn.commit()
            success = cursor.rowcount > 0

        if success:
            self._try_gsheets_sync()
        return success

    def import_transactions(self, records: List[Dict[str, Any]], reviewer_id: str = "dad") -> int:
        """Imports transactions from external list or dataframe dicts with duplicate prevention."""
        import uuid
        imported_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for r in records:
                # Resolve transaction ID or generate deterministic hash
                raw_tx_id = str(r.get("Transaction ID") or r.get("tx_id") or "").strip()
                user_id = str(r.get("Member ID") or r.get("user_id") or "").strip().lower()
                
                valid_ids = ["irene", "herren", "prim", "member1", "member2", "member3", "dad"]
                if not user_id or user_id not in valid_ids:
                    member_name = str(r.get("Member Name") or r.get("Member") or r.get("Name") or "").strip().lower()
                    if "herren" in member_name or "2" in member_name or "สอง" in member_name:
                        user_id = "herren"
                    elif "irene" in member_name or "1" in member_name or "หนึ่ง" in member_name:
                        user_id = "irene"
                    elif "prim" in member_name or "3" in member_name or "สาม" in member_name:
                        user_id = "prim"
                    else:
                        user_id = "herren"
                elif user_id == "member1":
                    user_id = "irene"
                elif user_id == "member2":
                    user_id = "herren"
                elif user_id == "member3":
                    user_id = "prim"

                # Resolve transaction type
                raw_type = str(r.get("Type") or r.get("tx_type") or "DEPOSIT").strip().upper()
                if "WITHDRAW" in raw_type or "ถอน" in raw_type or "PAYOUT" in raw_type:
                    tx_type = TransactionType.WITHDRAWAL.value
                else:
                    tx_type = TransactionType.DEPOSIT.value

                # Amount
                try:
                    amount = abs(float(r.get("Amount (THB)") or r.get("Amount") or r.get("amount") or 0.0))
                except Exception:
                    continue

                if amount <= 0:
                    continue

                # Status
                raw_status = str(r.get("Status") or r.get("status") or "APPROVED").strip().upper()
                status = TransactionStatus.APPROVED.value if "APP" in raw_status or "อนุมัติ" in raw_status or "VERIFIED" in raw_status else TransactionStatus.PENDING.value

                timestamp = str(r.get("Timestamp") or r.get("Date") or r.get("created_at") or now_str).strip()
                notes = str(r.get("Notes") or r.get("notes") or "Imported from historical record").strip()
                bank_info = str(r.get("Bank Info") or r.get("bank_info") or "").strip()

                if not raw_tx_id:
                    raw_tx_id = f"imp_{abs(hash(timestamp + user_id + str(amount)))}"

                # Check if exists
                cursor.execute("SELECT 1 FROM transactions WHERE tx_id = ?", (raw_tx_id,))
                if cursor.fetchone():
                    continue

                cursor.execute("""
                    INSERT INTO transactions (
                        tx_id, user_id, tx_type, amount, slip_path,
                        status, created_at, reviewed_at, reviewed_by, notes, bank_info
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    raw_tx_id, user_id, tx_type, amount, None,
                    status, timestamp, timestamp if status == TransactionStatus.APPROVED.value else None,
                    reviewer_id, notes, bank_info
                ))
                imported_count += 1
            conn.commit()

        if imported_count > 0:
            self._try_gsheets_sync()

        return imported_count

    def _try_gsheets_sync(self):
        """Asynchronously or safely trigger Google Sheets sync if credentials exist."""
        try:
            from gsheets_sync import get_gsheets_sync
            from auth_manager import DEFAULT_USERS
            gs = get_gsheets_sync()
            if gs.is_active():
                txs = self.get_transactions()
                summaries = self.get_account_summaries(DEFAULT_USERS)
                gs.sync_all(txs, summaries, DEFAULT_USERS)
        except Exception:
            pass

    def get_transactions(self, user_id: Optional[str] = None, status: Optional[str] = None) -> List[Transaction]:
        query = "SELECT * FROM transactions WHERE 1=1"
        params: List[Any] = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                Transaction(
                    tx_id=r["tx_id"],
                    user_id=r["user_id"],
                    tx_type=r["tx_type"],
                    amount=r["amount"],
                    slip_path=r["slip_path"],
                    status=r["status"],
                    created_at=r["created_at"],
                    reviewed_at=r["reviewed_at"],
                    reviewed_by=r["reviewed_by"],
                    notes=r["notes"],
                    bank_info=r["bank_info"]
                )
                for r in rows
            ]

    def get_account_summaries(self, users_dict: Dict[str, Dict[str, Any]]) -> List[AccountSummary]:
        summaries = []
        all_txs = self.get_transactions()

        # Only summarize member accounts (excluding admin dad from member quota)
        member_ids = [uid for uid, u in users_dict.items() if u.get("role") == "member"]

        for uid in member_ids:
            name = users_dict[uid].get("display_name", uid.title())
            confirmed_balance = 0.0
            pending_deposits = 0.0
            total_deposited = 0.0
            total_withdrawn = 0.0

            for tx in all_txs:
                if tx.user_id == uid:
                    if tx.tx_type == TransactionType.DEPOSIT.value:
                        if tx.status == TransactionStatus.APPROVED.value:
                            confirmed_balance += tx.amount
                            total_deposited += tx.amount
                        elif tx.status == TransactionStatus.PENDING.value:
                            pending_deposits += tx.amount
                    elif tx.tx_type == TransactionType.WITHDRAWAL.value:
                        if tx.status == TransactionStatus.APPROVED.value:
                            confirmed_balance -= tx.amount
                            total_withdrawn += tx.amount
                    elif tx.tx_type == TransactionType.ADJUSTMENT.value:
                        if tx.status == TransactionStatus.APPROVED.value:
                            confirmed_balance += tx.amount

            summaries.append(AccountSummary(
                user_id=uid,
                display_name=name,
                confirmed_balance=confirmed_balance,
                pending_deposits=pending_deposits,
                total_deposited=total_deposited,
                total_withdrawn=total_withdrawn
            ))

        return summaries

    def get_vault_metrics(self, users_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        summaries = self.get_account_summaries(users_dict)
        total_vault_confirmed = sum(s.confirmed_balance for s in summaries)
        total_vault_pending = sum(s.pending_deposits for s in summaries)
        total_vault_deposited = sum(s.total_deposited for s in summaries)
        total_vault_withdrawn = sum(s.total_withdrawn for s in summaries)

        pending_txs = [tx for tx in self.get_transactions(status=TransactionStatus.PENDING.value)]

        return {
            "total_vault_confirmed": total_vault_confirmed,
            "total_vault_pending": total_vault_pending,
            "total_vault_deposited": total_vault_deposited,
            "total_vault_withdrawn": total_vault_withdrawn,
            "pending_count": len(pending_txs),
            "member_count": len(summaries)
        }


# Global Singleton Ledger Instance
_ledger_instance: Optional[SQLiteLedger] = None

def get_ledger() -> SQLiteLedger:
    global _ledger_instance
    if _ledger_instance is None:
        _ledger_instance = SQLiteLedger()
    return _ledger_instance
