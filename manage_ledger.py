"""
Deterministic Family Bank Ledger Manager (Non-LLM).
Pure Python CLI utility to read, inspect, record, and edit transactions
directly in the standardized CSV ledger without any AI or LLM dependency.
"""

import sys
import os
import csv
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent / "standardized_family_ledger.csv"

HEADERS = [
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

MEMBER_MAP = {
    "herren": "Herren",
    "irene": "Irene",
    "prim": "Prim"
}


def load_records(filepath: Path = DEFAULT_LEDGER_PATH) -> List[Dict[str, Any]]:
    """Loads transactions from CSV file."""
    if not filepath.exists():
        print(f"Error: Ledger file not found at {filepath}")
        return []
    
    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_records(records: List[Dict[str, Any]], filepath: Path = DEFAULT_LEDGER_PATH):
    """Saves records back to CSV with backup safeguard."""
    # Write to temporary file first for atomic safety
    temp_file = filepath.with_suffix(".tmp")
    with open(temp_file, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(records)

    # Replace target file
    temp_file.replace(filepath)


def calculate_balances(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Calculates balances per member deterministically."""
    balances = {
        m: {"deposited": 0.0, "withdrawn": 0.0, "net": 0.0}
        for m in MEMBER_MAP
    }

    for r in records:
        m_id = r.get("Member ID", "").strip().lower()
        if m_id not in balances:
            balances[m_id] = {"deposited": 0.0, "withdrawn": 0.0, "net": 0.0}

        status = r.get("Status", "").strip().upper()
        if status != "APPROVED":
            continue

        try:
            amt = float(r.get("Amount (THB)", 0.0))
        except ValueError:
            amt = 0.0

        tx_type = r.get("Type", "").strip().upper()
        if tx_type == "DEPOSIT":
            balances[m_id]["deposited"] += amt
            balances[m_id]["net"] += amt
        elif tx_type == "WITHDRAWAL":
            balances[m_id]["withdrawn"] += amt
            balances[m_id]["net"] -= amt

    return balances


def print_balances(records: List[Dict[str, Any]]):
    """Displays formatted balance table."""
    balances = calculate_balances(records)
    total_net = sum(b["net"] for b in balances.values())
    total_dep = sum(b["deposited"] for b in balances.values())
    total_wth = sum(b["withdrawn"] for b in balances.values())

    print("\n" + "=" * 65)
    print("           FAMILY BANK VAULT - BALANCE SUMMARY")
    print("=" * 65)
    print(f"{'Member':<15} | {'Total Deposited':>15} | {'Total Withdrawn':>15} | {'Net Balance':>15}")
    print("-" * 65)
    for m_id, b in sorted(balances.items()):
        name = MEMBER_MAP.get(m_id, m_id.title())
        print(f"{name:<15} | {b['deposited']:>15,.2f} | {b['withdrawn']:>15,.2f} | {b['net']:>15,.2f}")
    print("-" * 65)
    print(f"{'TOTAL VAULT':<15} | {total_dep:>15,.2f} | {total_wth:>15,.2f} | {total_net:>15,.2f}")
    print("=" * 65 + "\n")


def print_recent(records: List[Dict[str, Any]], limit: int = 15, member_filter: Optional[str] = None):
    """Displays recent transactions."""
    filtered = records
    if member_filter:
        filtered = [r for r in records if r.get("Member ID", "").lower() == member_filter.lower()]

    recent = filtered[-limit:]
    print("\n" + "=" * 80)
    print(f"RECENT TRANSACTIONS ({'All' if not member_filter else member_filter.title()}) - Showing {len(recent)} records")
    print("=" * 80)
    print(f"{'Timestamp':<19} | {'Member':<8} | {'Type':<10} | {'Amount':>10} | {'Notes'}")
    print("-" * 80)
    for r in recent:
        print(f"{r.get('Timestamp', '')[:19]:<19} | {r.get('Member Name', '')[:8]:<8} | {r.get('Type', ''):<10} | {float(r.get('Amount (THB)', 0)):>10,.2f} | {r.get('Notes', '')}")
    print("=" * 80 + "\n")


def add_transaction(
    member_id: str,
    tx_type: str,
    amount: float,
    notes: str = "",
    date_str: Optional[str] = None,
    filepath: Path = DEFAULT_LEDGER_PATH
):
    """Appends a new transaction deterministically."""
    records = load_records(filepath)
    now = datetime.now()
    timestamp = date_str if date_str else now.strftime("%Y-%m-%d %H:%M:%S")
    tx_id = f"tx_{int(now.timestamp())}_{member_id[:3]}"
    member_name = MEMBER_MAP.get(member_id.lower(), member_id.title())

    new_tx = {
        "Transaction ID": tx_id,
        "Timestamp": timestamp,
        "Member ID": member_id.lower(),
        "Member Name": member_name,
        "Type": tx_type.upper(),
        "Amount (THB)": f"{amount:.2f}",
        "Status": "APPROVED",
        "Reviewed By": "Dad",
        "Reviewed At": timestamp,
        "Notes": notes or "Manual entry via CLI",
        "Bank Info": ""
    }

    records.append(new_tx)
    save_records(records, filepath)
    print(f"Success: Added {tx_type.upper()} of {amount:,.2f} THB for {member_name} (ID: {tx_id})")
    print_balances(records)


def edit_transaction(tx_id: str, new_amount: Optional[float] = None, new_note: Optional[str] = None, filepath: Path = DEFAULT_LEDGER_PATH):
    """Edits an existing transaction by ID."""
    records = load_records(filepath)
    found = False
    for r in records:
        if r.get("Transaction ID", "").strip() == tx_id.strip():
            found = True
            if new_amount is not None:
                r["Amount (THB)"] = f"{new_amount:.2f}"
            if new_note is not None:
                r["Notes"] = new_note
            r["Reviewed At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"Updated transaction {tx_id}: Amount={r['Amount (THB)']}, Notes={r['Notes']}")
            break

    if not found:
        print(f"Error: Transaction ID '{tx_id}' not found.")
        return

    save_records(records, filepath)
    print_balances(records)


def interactive_menu(filepath: Path = DEFAULT_LEDGER_PATH):
    """Interactive text menu for managing the ledger without AI."""
    while True:
        records = load_records(filepath)
        print("--- Family Bank Ledger CLI ---")
        print("1. View Balances")
        print("2. View Recent Transactions")
        print("3. Record Deposit (Money In)")
        print("4. Record Withdrawal (Money Out)")
        print("5. Edit Existing Transaction")
        print("6. Exit")
        choice = input("Select option (1-6): ").strip()

        if choice == "1":
            print_balances(records)
        elif choice == "2":
            mem = input("Filter by member (herren/irene/prim or Enter for all): ").strip()
            print_recent(records, limit=20, member_filter=mem if mem else None)
        elif choice == "3":
            mem = input("Member (herren/irene/prim): ").strip().lower()
            try:
                amt = float(input("Deposit Amount (THB): ").strip())
                note = input("Note / Purpose: ").strip()
                add_transaction(mem, "DEPOSIT", amt, note, filepath=filepath)
            except ValueError:
                print("Invalid amount.")
        elif choice == "4":
            mem = input("Member (herren/irene/prim): ").strip().lower()
            try:
                amt = float(input("Withdrawal Amount (THB): ").strip())
                note = input("Reason: ").strip()
                add_transaction(mem, "WITHDRAWAL", amt, note, filepath=filepath)
            except ValueError:
                print("Invalid amount.")
        elif choice == "5":
            tid = input("Enter Transaction ID to edit: ").strip()
            amt_in = input("New Amount (or press Enter to keep): ").strip()
            note_in = input("New Note (or press Enter to keep): ").strip()
            new_amt = float(amt_in) if amt_in else None
            new_note = note_in if note_in else None
            edit_transaction(tid, new_amount=new_amt, new_note=new_note, filepath=filepath)
        elif choice == "6":
            print("Exiting.")
            break
        else:
            print("Invalid choice.")


def main():
    parser = argparse.ArgumentParser(description="Deterministic Family Bank Ledger Editor (Non-LLM)")
    subparsers = parser.add_subparsers(dest="command")

    # Command: balance
    subparsers.add_parser("balance", help="Display current balances")

    # Command: list
    list_p = subparsers.add_parser("list", help="List recent transactions")
    list_p.add_argument("--member", "-m", help="Filter by member (herren/irene/prim)")
    list_p.add_argument("--limit", "-n", type=int, default=15, help="Number of records to show")

    # Command: add
    add_p = subparsers.add_parser("add", help="Add a transaction")
    add_p.add_argument("--member", "-m", required=True, help="Member ID (herren/irene/prim)")
    add_p.add_argument("--type", "-t", required=True, choices=["deposit", "withdrawal"], help="Transaction type")
    add_p.add_argument("--amount", "-a", type=float, required=True, help="Amount in THB")
    add_p.add_argument("--note", help="Description note")
    add_p.add_argument("--date", help="Custom timestamp (YYYY-MM-DD HH:MM:SS)")

    # Command: edit
    edit_p = subparsers.add_parser("edit", help="Edit transaction")
    edit_p.add_argument("--id", required=True, help="Transaction ID")
    edit_p.add_argument("--amount", "-a", type=float, help="New amount in THB")
    edit_p.add_argument("--note", help="New description note")

    # Command: interactive
    subparsers.add_parser("interactive", help="Start interactive text menu")

    args = parser.parse_args()

    if not args.command:
        # Default to interactive if no arguments provided
        interactive_menu()
    elif args.command == "balance":
        print_balances(load_records())
    elif args.command == "list":
        print_recent(load_records(), limit=args.limit, member_filter=args.member)
    elif args.command == "add":
        add_transaction(args.member, args.type, args.amount, args.note or "", args.date)
    elif args.command == "edit":
        edit_transaction(args.id, args.amount, args.note)
    elif args.command == "interactive":
        interactive_menu()


if __name__ == "__main__":
    main()
