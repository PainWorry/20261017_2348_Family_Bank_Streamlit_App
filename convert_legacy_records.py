"""
Converter script for transforming legacy family money CSV into standardized Family Bank records.
Parses multi-column monthly ledger into unified chronological transactions for:
- Irene
- Herren
- Prim
"""

import csv
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "legacy_kids_money.csv"
OUTPUT_CSV = BASE_DIR / "standardized_family_ledger.csv"

MONTH_MAP = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
}

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


def clean_num(val):
    if not val:
        return 0.0
    val = str(val).replace(",", "").strip()
    try:
        return float(val)
    except Exception:
        return 0.0


def convert():
    with open(INPUT_CSV, mode="r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    # Determine year for each row
    years = {}
    curr_year = 2017
    for r_idx in range(2, len(rows)):
        m_str = rows[r_idx][0].strip() if rows[r_idx] else ""
        if not m_str:
            continue
        if r_idx > 2 and m_str == "Jan":
            curr_year += 1
        marker = rows[r_idx][13].strip() if len(rows[r_idx]) > 13 else ""
        if marker.isdigit():
            curr_year = int(marker)
        years[r_idx] = (m_str, curr_year)

    transactions = []

    # 1. Starting Balances (Row 2, Jun 2017)
    starting_data = [
        ("irene", "Irene", clean_num(rows[2][4])),
        ("herren", "Herren", clean_num(rows[2][8])),
        ("prim", "Prim", clean_num(rows[2][12]))
    ]
    for uid, name, bal in starting_data:
        if bal > 0:
            transactions.append({
                "Transaction ID": f"legacy_{uid}_20170601_start",
                "Timestamp": "2017-06-01 00:00:00",
                "Member ID": uid,
                "Member Name": name,
                "Type": "DEPOSIT",
                "Amount (THB)": f"{bal:.2f}",
                "Status": "APPROVED",
                "Reviewed By": "Dad",
                "Reviewed At": "2017-06-01 00:00:00",
                "Notes": "Initial Starting Balance (Jun 2017)",
                "Bank Info": ""
            })

    # 2. Subsequent Monthly Entries (Row 3 to 107)
    for r_idx in range(3, 108):
        if r_idx not in years:
            continue
        m_str, year = years[r_idx]
        month_num = MONTH_MAP.get(m_str, "01")
        date_str = f"{year}-{month_num}-01 10:00:00"
        row = rows[r_idx]

        # --- IRENE ---
        rate_irene = clean_num(row[1]) if len(row) > 1 else 0.0
        fridge_irene = clean_num(row[2]) if len(row) > 2 else 0.0
        dw_irene = clean_num(row[3]) if len(row) > 3 else 0.0
        bal_irene = clean_num(row[4]) if len(row) > 4 else 0.0

        if bal_irene > 0 or rate_irene > 0 or fridge_irene > 0 or dw_irene != 0:
            if rate_irene > 0:
                transactions.append({
                    "Transaction ID": f"legacy_irene_{year}{month_num}_interest",
                    "Timestamp": date_str,
                    "Member ID": "irene",
                    "Member Name": "Irene",
                    "Type": "DEPOSIT",
                    "Amount (THB)": f"{rate_irene:.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": f"Monthly Interest 3% ({m_str} {year})",
                    "Bank Info": ""
                })
            if fridge_irene > 0:
                transactions.append({
                    "Transaction ID": f"legacy_irene_{year}{month_num}_fridge",
                    "Timestamp": date_str,
                    "Member ID": "irene",
                    "Member Name": "Irene",
                    "Type": "DEPOSIT",
                    "Amount (THB)": f"{fridge_irene:.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": f"Monthly Allowance ตู้เย็น ({m_str} {year})",
                    "Bank Info": ""
                })
            if dw_irene != 0:
                tx_type = "DEPOSIT" if dw_irene > 0 else "WITHDRAWAL"
                tx_note = f"Deposit ฝาก ({m_str} {year})" if dw_irene > 0 else f"Withdrawal ถอน ({m_str} {year})"
                transactions.append({
                    "Transaction ID": f"legacy_irene_{year}{month_num}_dw",
                    "Timestamp": date_str,
                    "Member ID": "irene",
                    "Member Name": "Irene",
                    "Type": tx_type,
                    "Amount (THB)": f"{abs(dw_irene):.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": tx_note,
                    "Bank Info": ""
                })

        # --- HERREN ---
        rate_herren = clean_num(row[5]) if len(row) > 5 else 0.0
        fridge_herren = clean_num(row[6]) if len(row) > 6 else 0.0
        dw_herren = clean_num(row[7]) if len(row) > 7 else 0.0
        bal_herren = clean_num(row[8]) if len(row) > 8 else 0.0

        if bal_herren > 0 or rate_herren > 0 or fridge_herren > 0 or dw_herren != 0:
            if rate_herren > 0:
                transactions.append({
                    "Transaction ID": f"legacy_herren_{year}{month_num}_interest",
                    "Timestamp": date_str,
                    "Member ID": "herren",
                    "Member Name": "Herren",
                    "Type": "DEPOSIT",
                    "Amount (THB)": f"{rate_herren:.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": f"Monthly Interest 3% ({m_str} {year})",
                    "Bank Info": ""
                })
            if fridge_herren > 0:
                transactions.append({
                    "Transaction ID": f"legacy_herren_{year}{month_num}_fridge",
                    "Timestamp": date_str,
                    "Member ID": "herren",
                    "Member Name": "Herren",
                    "Type": "DEPOSIT",
                    "Amount (THB)": f"{fridge_herren:.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": f"Monthly Allowance ตู้เย็น ({m_str} {year})",
                    "Bank Info": ""
                })
            if dw_herren != 0:
                tx_type = "DEPOSIT" if dw_herren > 0 else "WITHDRAWAL"
                tx_note = f"Deposit ฝาก ({m_str} {year})" if dw_herren > 0 else f"Withdrawal ถอน ({m_str} {year})"
                transactions.append({
                    "Transaction ID": f"legacy_herren_{year}{month_num}_dw",
                    "Timestamp": date_str,
                    "Member ID": "herren",
                    "Member Name": "Herren",
                    "Type": tx_type,
                    "Amount (THB)": f"{abs(dw_herren):.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": tx_note,
                    "Bank Info": ""
                })

        # --- PRIM ---
        rate_prim = clean_num(row[9]) if len(row) > 9 else 0.0
        dw_prim = clean_num(row[10]) if len(row) > 10 else 0.0
        bal_prim = clean_num(row[12]) if len(row) > 12 else 0.0

        if bal_prim > 0 or rate_prim > 0 or dw_prim != 0:
            if rate_prim > 0:
                transactions.append({
                    "Transaction ID": f"legacy_prim_{year}{month_num}_interest",
                    "Timestamp": date_str,
                    "Member ID": "prim",
                    "Member Name": "Prim",
                    "Type": "DEPOSIT",
                    "Amount (THB)": f"{rate_prim:.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": f"Monthly Interest 3% ({m_str} {year})",
                    "Bank Info": ""
                })
            if dw_prim != 0:
                tx_type = "DEPOSIT" if dw_prim > 0 else "WITHDRAWAL"
                tx_note = f"Deposit ฝาก ({m_str} {year})" if dw_prim > 0 else f"Withdrawal ถอน ({m_str} {year})"
                transactions.append({
                    "Transaction ID": f"legacy_prim_{year}{month_num}_dw",
                    "Timestamp": date_str,
                    "Member ID": "prim",
                    "Member Name": "Prim",
                    "Type": tx_type,
                    "Amount (THB)": f"{abs(dw_prim):.2f}",
                    "Status": "APPROVED",
                    "Reviewed By": "Dad",
                    "Reviewed At": date_str,
                    "Notes": tx_note,
                    "Bank Info": ""
                })

    # Sort transactions chronologically
    transactions.sort(key=lambda x: x["Timestamp"])

    # Write to standardized CSV
    with open(OUTPUT_CSV, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(transactions)

    print(f"Successfully generated standardized CSV: {OUTPUT_CSV}")
    print(f"Total Transactions Parsed: {len(transactions)}")

    # Print summary per member
    for m in ["irene", "herren", "prim"]:
        m_txs = [t for t in transactions if t["Member ID"] == m]
        dep = sum(float(t["Amount (THB)"]) for t in m_txs if t["Type"] == "DEPOSIT")
        wth = sum(float(t["Amount (THB)"]) for t in m_txs if t["Type"] == "WITHDRAWAL")
        print(f"[{m.upper()}] Deposits={dep:,.2f}, Withdrawals={wth:,.2f}, Net Balance={dep - wth:,.2f}")


if __name__ == "__main__":
    convert()
