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
        self.ledger = SQLiteLedger(db_path=self.db_path, slips_dir=self.slips_dir, auto_seed=False)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_default_passwords(self):
        # Verify Dad default credentials
        dad_hash = DEFAULT_USERS["dad"]["password_hash"]
        self.assertTrue(verify_password("Papa0000", dad_hash))
        self.assertFalse(verify_password("wrong_password", dad_hash))

        # Verify Member default credentials
        irene_hash = DEFAULT_USERS["irene"]["password_hash"]
        self.assertTrue(verify_password("Kanun1111", irene_hash))

        prim_hash = DEFAULT_USERS["prim"]["password_hash"]
        self.assertTrue(verify_password("Kia3333", prim_hash))

        herren_hash = DEFAULT_USERS["herren"]["password_hash"]
        self.assertTrue(verify_password("Herren2222", herren_hash))

    def test_deposit_and_approval_workflow(self):
        # 1. Member 1 submits 1,000 THB deposit
        slip_bytes = b"fake-slip-image-content"
        slip_uri = self.ledger.save_slip_image(slip_bytes, "test_slip.jpg", "tx_001")
        self.assertTrue(slip_uri.startswith("data:image/jpeg;base64,"))

        tx_id = self.ledger.create_transaction(
            user_id="irene",
            tx_type=TransactionType.DEPOSIT.value,
            amount=1000.0,
            slip_data_uri=slip_uri,
            notes="Initial allowance deposit",
            status=TransactionStatus.PENDING.value
        )
        self.assertTrue(tx_id.startswith("tx_"))

        # Verify initial pending state
        sums = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums["irene"].confirmed_balance, 0.0)
        self.assertEqual(sums["irene"].pending_deposits, 1000.0)

        # 2. Dad approves the deposit
        updated = self.ledger.update_transaction_status(
            tx_id=tx_id,
            new_status=TransactionStatus.APPROVED.value,
            reviewer_id="dad"
        )
        self.assertTrue(updated)

        # Verify confirmed balance updated
        sums_after = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums_after["irene"].confirmed_balance, 1000.0)
        self.assertEqual(sums_after["irene"].pending_deposits, 0.0)
        self.assertEqual(sums_after["irene"].total_deposited, 1000.0)

    def test_withdrawal_with_slip(self):
        # Seed initial confirmed deposit
        self.ledger.create_transaction(
            user_id="herren",
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
            user_id="herren",
            tx_type=TransactionType.WITHDRAWAL.value,
            amount=500.0,
            slip_data_uri=payout_uri,
            notes="Books and materials",
            status=TransactionStatus.APPROVED.value,
            reviewed_by="dad"
        )

        # Verify balance deduction
        sums = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums["herren"].confirmed_balance, 1500.0)
        self.assertEqual(sums["herren"].total_deposited, 2000.0)
        self.assertEqual(sums["herren"].total_withdrawn, 500.0)

    def test_vault_metrics(self):
        # Irene deposits 500
        self.ledger.create_transaction(
            user_id="irene",
            tx_type=TransactionType.DEPOSIT.value,
            amount=500.0,
            status=TransactionStatus.APPROVED.value
        )
        # Prim deposits 300
        self.ledger.create_transaction(
            user_id="prim",
            tx_type=TransactionType.DEPOSIT.value,
            amount=300.0,
            status=TransactionStatus.APPROVED.value
        )
        metrics = self.ledger.get_vault_metrics(DEFAULT_USERS)
        self.assertEqual(metrics["total_vault_confirmed"], 800.0)
        self.assertEqual(metrics["member_count"], 3)

    def test_import_historical_transactions(self):
        # Simulate old records from Excel/Google Sheet
        old_data = [
            {
                "Transaction ID": "legacy_001",
                "Timestamp": "2026-09-01 10:00:00",
                "Member Name": "Member 1",
                "Type": "DEPOSIT",
                "Amount": 1500.0,
                "Status": "APPROVED",
                "Notes": "Old September deposit"
            },
            {
                "Transaction ID": "legacy_002",
                "Timestamp": "2026-09-15 14:00:00",
                "Member Name": "Member 2",
                "Type": "WITHDRAWAL",
                "Amount": 300.0,
                "Status": "APPROVED",
                "Notes": "Old withdrawal"
            }
        ]
        imported = self.ledger.import_transactions(old_data)
        self.assertEqual(imported, 2)

        sums = {s.user_id: s for s in self.ledger.get_account_summaries(DEFAULT_USERS)}
        self.assertEqual(sums["irene"].confirmed_balance, 1500.0)
        self.assertEqual(sums["herren"].confirmed_balance, -300.0)

        # Test duplicate import rejection
        imported_again = self.ledger.import_transactions(old_data)
        self.assertEqual(imported_again, 0)

    def test_user_credentials_initial_state(self):
        # Verify default users are seeded with must_change_password=True
        dad_cred = self.ledger.get_user_credential("dad")
        self.assertIsNotNone(dad_cred)
        self.assertTrue(dad_cred["must_change_password"])

        herren_cred = self.ledger.get_user_credential("herren")
        self.assertIsNotNone(herren_cred)
        self.assertTrue(herren_cred["must_change_password"])

    def test_update_user_password(self):
        from auth_manager import hash_password
        new_hash = hash_password("MyNewSecretPin999")
        
        # Update Herren's password
        success = self.ledger.update_user_password("herren", new_hash, must_change=False)
        self.assertTrue(success)

        # Verify must_change_password is now False
        cred = self.ledger.get_user_credential("herren")
        self.assertFalse(cred["must_change_password"])
        self.assertTrue(verify_password("MyNewSecretPin999", cred["password_hash"]))
        self.assertFalse(verify_password("pass1234", cred["password_hash"]))

    def test_auto_seed_feature(self):
        # Verify auto_seed=True populates all 410 transactions and computes 1,283,677.10 THB
        seeded_db = Path(self.temp_dir.name) / "seeded_bank.db"
        seeded_ledger = SQLiteLedger(db_path=seeded_db, slips_dir=self.slips_dir, auto_seed=True)
        self.assertEqual(len(seeded_ledger.get_transactions()), 410)
        metrics = seeded_ledger.get_vault_metrics(DEFAULT_USERS)
        self.assertAlmostEqual(metrics["total_vault_confirmed"], 1283677.10, places=2)

    def test_emergency_reset_user_to_default(self):
        # Change password first
        from auth_manager import hash_password
        self.ledger.update_user_password("irene", hash_password("ChangedPass777"), must_change=False)
        self.assertFalse(self.ledger.get_user_credential("irene")["must_change_password"])

        # Execute emergency reset
        self.ledger.reset_user_to_default("irene")
        irene_cred = self.ledger.get_user_credential("irene")
        self.assertTrue(irene_cred["must_change_password"])
        self.assertTrue(verify_password("Kanun1111", irene_cred["password_hash"]))

        # Execute individual reset for dad and prim
        self.ledger.reset_user_to_default("dad")
        self.assertTrue(verify_password("Papa0000", self.ledger.get_user_credential("dad")["password_hash"]))

        self.ledger.reset_user_to_default("prim")
        self.assertTrue(verify_password("Kia3333", self.ledger.get_user_credential("prim")["password_hash"]))


if __name__ == "__main__":
    unittest.main()




