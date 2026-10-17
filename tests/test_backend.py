"""
Unit tests for Family Bank backend engine, storage, and authentication.
"""

import unittest
import tempfile
from pathlib import Path

from auth_manager import verify_password, DEFAULT_USERS
from storage import SQLiteLedger
from models import TransactionType, TransactionStatus


class TestFamilyBankBackend(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_bank.db"
        self.slips_dir = Path(self.temp_dir.name) / "slips"
        self.ledger = SQLiteLedger(db_path=self.db_path, slips_dir=self.slips_dir)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_default_passwords(self):
        # Verify Dad default credentials
        dad_hash = DEFAULT_USERS["dad"]["password_hash"]
        self.assertTrue(verify_password("dad1234", dad_hash))
        self.assertFalse(verify_password("wrong_password", dad_hash))

        # Verify Member default credentials
        m1_hash = DEFAULT_USERS["member1"]["password_hash"]
        self.assertTrue(verify_password("pass1234", m1_hash))
        self.assertFalse(verify_password("wrong_password", m1_hash))

    def test_deposit_and_approval_workflow(self):
        # 1. Member 1 submits 1,000 THB deposit
        slip_bytes = b"fake-slip-image-content"
        slip_uri = self.ledger.save_slip_image(slip_bytes, "test_slip.jpg", "tx_001")
        self.assertTrue(slip_uri.startswith("data:image/jpeg;base64,"))

        tx_id = self.ledger.create_transaction(
            user_id="member1",
            tx_type=TransactionType.DEPOSIT.value,
            amount=1000.0,
            slip_data_uri=slip_uri,
            notes="Initial allowance deposit",
            status=TransactionStatus.PENDING.value
        )
        self.assertTrue(tx_id.startswith("tx_"))

        # Verify initial pending state
        sums = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums["member1"].confirmed_balance, 0.0)
        self.assertEqual(sums["member1"].pending_deposits, 1000.0)

        # 2. Dad approves the deposit
        updated = self.ledger.update_transaction_status(
            tx_id=tx_id,
            new_status=TransactionStatus.APPROVED.value,
            reviewer_id="dad"
        )
        self.assertTrue(updated)

        # Verify confirmed balance updated
        sums_after = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums_after["member1"].confirmed_balance, 1000.0)
        self.assertEqual(sums_after["member1"].pending_deposits, 0.0)
        self.assertEqual(sums_after["member1"].total_deposited, 1000.0)

    def test_withdrawal_with_slip(self):
        # Seed initial confirmed deposit
        self.ledger.create_transaction(
            user_id="member2",
            tx_type=TransactionType.DEPOSIT.value,
            amount=2000.0,
            status=TransactionStatus.APPROVED.value,
            reviewed_by="dad"
        )

        # Record withdrawal payout of 500 THB with payout slip
        payout_bytes = b"dad-payout-transfer-slip"
        payout_uri = self.ledger.save_slip_image(payout_bytes, "payout.png", "tx_payout_001")
        self.assertTrue(payout_uri.startswith("data:image/png;base64,"))

        self.ledger.create_transaction(
            user_id="member2",
            tx_type=TransactionType.WITHDRAWAL.value,
            amount=500.0,
            slip_data_uri=payout_uri,
            notes="Books and materials",
            status=TransactionStatus.APPROVED.value,
            reviewed_by="dad"
        )

        # Verify balance deduction
        sums = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums["member2"].confirmed_balance, 1500.0)
        self.assertEqual(sums["member2"].total_deposited, 2000.0)
        self.assertEqual(sums["member2"].total_withdrawn, 500.0)

    def test_vault_metrics(self):
        # Member 1 deposits 500
        self.ledger.create_transaction(
            user_id="member1",
            tx_type=TransactionType.DEPOSIT.value,
            amount=500.0,
            status=TransactionStatus.APPROVED.value
        )
        # Member 3 deposits 300
        self.ledger.create_transaction(
            user_id="member3",
            tx_type=TransactionType.DEPOSIT.value,
            amount=300.0,
            status=TransactionStatus.APPROVED.value
        )
        metrics = self.ledger.get_vault_metrics(DEFAULT_USERS)
        self.assertEqual(metrics["total_vault_confirmed"], 800.0)
        self.assertEqual(metrics["member_count"], 3)


if __name__ == "__main__":
    unittest.main()
