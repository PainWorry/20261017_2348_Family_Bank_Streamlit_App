# Family Bank Vault (Streamlit Web Application)

A mobile-friendly, secure family banking and deposit recording web application designed to replace manual Excel bookkeeping. Built with Streamlit, Python, and Google Sheets integration.

---

## Key Capabilities

- **Mobile First Experience**: Upload transfer slips directly from mobile phone camera or image gallery without opening a computer.
- **Role-Based Access Control**:
  - **Dad (Admin)**: Full vault overview, pending deposit approval inbox, withdrawal payout execution, member balance passbooks, and complete audit ledger.
  - **3 Family Members**: Personal dashboard, confirmed balance, pending verification tracker, deposit recording with slip attachment, and withdrawal requests.
- **Two-Stage Verification Ledger**: Deposits are held in `PENDING` status with attached transfer slips until Dad reviews the slip and clicks **Approve** (or **Reject** with a reason).
- **Mandatory Withdrawal Slips**: All payouts/withdrawals recorded by Dad require attaching a bank transfer receipt as verifiable proof of remittance.
- **Dual-Engine Persistence**:
  - **Local Mode**: Runs instantly using SQLite (`family_bank.db`) and local upload directories (`uploads/slips/`).
  - **Cloud Mode**: Seamlessly mirrors every transaction and balance update to **Google Sheets** (`Transactions_Ledger` & `Account_Balances` worksheets) when credentials are provided in `.streamlit/secrets.toml` or Streamlit Community Cloud Secrets.
- **F5 Reload Immunity**: Cookie-backed session persistence ensures mobile devices don't log out when switching apps or refreshing.

---

## Default Accounts & Passwords

The system comes pre-configured with 4 accounts:

| Role | Account ID | Display Name | Initial Password / PIN |
|---|---|---|---|
| Admin | `dad` | Dad (Bank Admin) | `dad1234` |
| Member | `member1` | Member 1 | `pass1234` |
| Member | `member2` | Member 2 | `pass1234` |
| Member | `member3` | Member 3 | `pass1234` |

*Passwords can be customized or added in `.streamlit/secrets.toml`. Use `python hash_tool.py` to generate new salted Bcrypt hashes.*

---

## Local Development & Testing

1. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

2. **Run tests**:
   ```powershell
   python -m unittest discover -s tests -p "test_*.py"
   ```

3. **Launch the application**:
   ```powershell
   streamlit run app.py
   ```

---

## Google Sheets Synchronization Setup (Streamlit Community Cloud)

To enable live mirroring of the family bank ledger to Google Sheets:

1. Create a Google Cloud Service Account in the Google Cloud Console.
2. Enable both **Google Sheets API** and **Google Drive API**.
3. Create a Google Spreadsheet titled `Family_Bank_Vault_Ledger` (or any custom name) and share it with the service account client email as **Editor**.
4. In Streamlit Cloud **App Settings -> Secrets** (or `.streamlit/secrets.toml` locally), paste:

```toml
[connections.gsheets]
spreadsheet = "https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit"

[gcp_service_account]
type = "service_account"
project_id = "your-gcp-project"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-gcp-project.iam.gserviceaccount.com"
client_id = "..."
```

---

## Streamlit Community Cloud 1-Click Deployment

This repository is structured for zero-configuration 1-click deployment on Streamlit Community Cloud:
- Entrypoint: `app.py`
- Pinned Runtime: `.python-version` (3.12)
- Dependencies: `requirements.txt`
