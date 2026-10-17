"""
Family Bank Streamlit Web Application
A mobile-friendly, role-based family savings and deposit management portal.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from models import TransactionType, TransactionStatus
from auth_manager import FamilyBankAuth
from storage import get_ledger

# Page setup
st.set_page_config(
    page_title="Family Bank Vault",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for clean, high-contrast banking aesthetics
st.markdown("""
<style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-approved {
        background-color: #dcfce7;
        color: #166534;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-pending {
        background-color: #fef9c3;
        color: #854d0e;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-rejected {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

auth = FamilyBankAuth()
ledger = get_ledger()

# Google Sheets Sync Engine
from gsheets_sync import get_gsheets_sync
gs_engine = get_gsheets_sync()

# Verify authentication gate
if not auth.render_login_ui():
    st.stop()

# Authenticated session context
current_user = auth.get_current_user()
user_id = current_user["user_id"]
role = current_user["role"]
display_name = current_user["display_name"]
users_dict = auth.users

# Top Header & Account Bar
head_col1, head_col2 = st.columns([3, 1])
with head_col1:
    st.title("Family Bank Vault")
    role_label = "Administrator (Dad)" if role == "admin" else "Family Member Account"
    sync_status_text = f"Connected to Google Sheet: **{gs_engine.sheet_name}**" if gs_engine.is_active() else "Google Sheet Sync: Local Engine (Ready to connect)"
    st.caption(f"Authenticated as: **{display_name}** | Access Level: `{role_label}` | {sync_status_text}")
with head_col2:
    st.write("")
    if st.button("Sign Out", use_container_width=True):
        auth.logout()

st.divider()

# ==========================================
# ADMIN VIEW (DAD)
# ==========================================
if role == "admin":
    metrics = ledger.get_vault_metrics(users_dict)
    
    # Vault Summary KPI Cards
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(
            label="Total Vault Balance (Confirmed)",
            value=f"{metrics['total_vault_confirmed']:,.2f} THB"
        )
    with kpi2:
        st.metric(
            label="Pending Deposit Approvals",
            value=f"{metrics['pending_count']} pending",
            delta=f"{metrics['total_vault_pending']:,.2f} THB" if metrics['total_vault_pending'] > 0 else None
        )
    with kpi3:
        st.metric(
            label="Total Lifetime Deposits",
            value=f"{metrics['total_vault_deposited']:,.2f} THB"
        )
    with kpi4:
        st.metric(
            label="Total Payouts / Withdrawals",
            value=f"{metrics['total_vault_withdrawn']:,.2f} THB"
        )

    admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs([
        "Pending Approvals",
        "Record Payout / Withdrawal",
        "Member Passbooks",
        "Full Audit Ledger"
    ])

    # 1. PENDING APPROVALS TAB
    with admin_tab1:
        st.subheader("Incoming Deposit Approvals")
        st.caption("Review uploaded bank transfer slips and confirm deposits into the family vault.")
        
        pending_txs = ledger.get_transactions(status=TransactionStatus.PENDING.value)
        if not pending_txs:
            st.info("No pending deposits requiring approval. All records are currently reconciled.")
        else:
            for tx in pending_txs:
                sender_name = users_dict.get(tx.user_id, {}).get("display_name", tx.user_id)
                with st.expander(f"Pending Deposit: {sender_name} - {tx.amount:,.2f} THB ({tx.created_at})", expanded=True):
                    col_det, col_slip = st.columns([1, 1])
                    with col_det:
                        st.write(f"**Member**: {sender_name} (`{tx.user_id}`)")
                        st.write(f"**Claimed Amount**: `{tx.amount:,.2f} THB`")
                        st.write(f"**Submission Time**: {tx.created_at}")
                        st.write(f"**Member Note**: {tx.notes or 'None provided'}")
                        
                        st.write("---")
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if st.button("Approve Deposit", key=f"app_{tx.tx_id}", use_container_width=True, type="primary"):
                                ledger.update_transaction_status(tx.tx_id, TransactionStatus.APPROVED.value, reviewer_id=user_id)
                                st.success(f"Approved {tx.amount:,.2f} THB deposit for {sender_name}.")
                                st.rerun()
                        with btn_col2:
                            reject_reason = st.text_input("Rejection note", key=f"rej_note_{tx.tx_id}", placeholder="Reason for voiding")
                            if st.button("Reject & Void", key=f"rej_{tx.tx_id}", use_container_width=True):
                                ledger.update_transaction_status(
                                    tx.tx_id,
                                    TransactionStatus.REJECTED.value,
                                    reviewer_id=user_id,
                                    admin_notes=reject_reason or "Verification failed"
                                )
                                st.warning(f"Deposit rejected for {sender_name}.")
                                st.rerun()

                    with col_slip:
                        st.write("**Attached Transfer Slip Proof**:")
                        if tx.slip_path:
                            st.image(tx.slip_path, caption=f"Slip for {tx.amount:,.2f} THB", use_container_width=True)
                        else:
                            st.error("No transfer slip attached to this transaction record.")

    # 2. RECORD PAYOUT / WITHDRAWAL TAB
    with admin_tab2:
        st.subheader("Process Member Withdrawal / Payout")
        st.caption("Execute a payout to a family member and attach the bank transfer confirmation slip.")
        
        member_options = {uid: u["display_name"] for uid, u in users_dict.items() if u.get("role") == "member"}
        summaries = {s.user_id: s for s in ledger.get_account_summaries(users_dict)}

        with st.form("admin_payout_form", clear_on_submit=True):
            sel_member = st.selectbox(
                "Select Member for Payout",
                options=list(member_options.keys()),
                format_func=lambda x: member_options[x]
            )
            
            member_summary = summaries.get(sel_member)
            current_avail = member_summary.confirmed_balance if member_summary else 0.0
            st.info(f"Current Available Confirmed Balance for {member_options[sel_member]}: **{current_avail:,.2f} THB**")

            payout_amount = st.number_input(
                "Payout Amount (THB)",
                min_value=1.0,
                max_value=max(1.0, float(current_avail)),
                value=min(100.0, float(current_avail)),
                step=50.0
            )
            payout_note = st.text_input("Payout Reason / Memo", placeholder="e.g. Tuition fee, emergency expense, cash request")
            
            payout_slip = st.file_uploader(
                "Attach Bank Transfer Payout Slip (Mandatory)",
                type=["png", "jpg", "jpeg", "webp"],
                key="admin_payout_slip"
            )
            
            submit_payout = st.form_submit_button("Record & Confirm Payout", use_container_width=True, type="primary")

            if submit_payout:
                if not payout_slip:
                    st.error("Transfer slip attachment is mandatory for recording withdrawals.")
                elif payout_amount <= 0:
                    st.error("Payout amount must be greater than zero.")
                elif payout_amount > current_avail:
                    st.error(f"Cannot withdraw {payout_amount:,.2f} THB; exceeds available balance of {current_avail:,.2f} THB.")
                else:
                    file_bytes = payout_slip.read()
                    data_uri = ledger.save_slip_image(file_bytes, payout_slip.name, f"payout_{sel_member}")
                    
                    ledger.create_transaction(
                        user_id=sel_member,
                        tx_type=TransactionType.WITHDRAWAL.value,
                        amount=payout_amount,
                        slip_data_uri=data_uri,
                        notes=payout_note or "Withdrawal payout processed by Dad",
                        status=TransactionStatus.APPROVED.value,
                        reviewed_by=user_id
                    )
                    st.success(f"Payout of {payout_amount:,.2f} THB recorded for {member_options[sel_member]} with attached transfer slip.")
                    st.rerun()

    # 3. MEMBER PASSBOOKS TAB
    with admin_tab3:
        st.subheader("Family Member Account Balances")
        summaries_list = ledger.get_account_summaries(users_dict)
        
        sum_cols = st.columns(len(summaries_list) or 1)
        for idx, s in enumerate(summaries_list):
            with sum_cols[idx]:
                st.markdown(f"### {s.display_name}")
                st.write(f"Confirmed Balance: **{s.confirmed_balance:,.2f} THB**")
                st.write(f"Pending Deposits: `{s.pending_deposits:,.2f} THB`")
                st.write(f"Total Deposited: `{s.total_deposited:,.2f} THB`")
                st.write(f"Total Withdrawn: `{s.total_withdrawn:,.2f} THB`")
                st.write("---")

        st.subheader("Member Transaction Filter")
        inspect_member = st.selectbox(
            "Filter Ledger by Member",
            options=["ALL"] + list(member_options.keys()),
            format_func=lambda x: "All Family Members" if x == "ALL" else member_options[x]
        )
        
        filtered_txs = ledger.get_transactions(user_id=None if inspect_member == "ALL" else inspect_member)
        if not filtered_txs:
            st.info("No transactions found for the selected member.")
        else:
            table_data = []
            for t in filtered_txs:
                table_data.append({
                    "Date": t.created_at,
                    "Member": users_dict.get(t.user_id, {}).get("display_name", t.user_id),
                    "Type": t.tx_type,
                    "Amount (THB)": f"{t.amount:,.2f}",
                    "Status": t.status,
                    "Notes": t.notes or "",
                    "Has Slip": "Yes" if t.slip_path else "No"
                })
            st.dataframe(pd.DataFrame(table_data), use_container_width=True)

    # 4. FULL AUDIT LEDGER TAB
    with admin_tab4:
        st.subheader("Complete Master Ledger & CSV Export")
        all_transactions = ledger.get_transactions()
        if not all_transactions:
            st.info("The ledger is currently empty.")
        else:
            df_rows = []
            for t in all_transactions:
                df_rows.append({
                    "Transaction ID": t.tx_id,
                    "Timestamp": t.created_at,
                    "Member ID": t.user_id,
                    "Member Name": users_dict.get(t.user_id, {}).get("display_name", t.user_id),
                    "Type": t.tx_type,
                    "Amount (THB)": t.amount,
                    "Status": t.status,
                    "Reviewed By": t.reviewed_by or "",
                    "Reviewed At": t.reviewed_at or "",
                    "Notes": t.notes or ""
                })
            df_export = pd.DataFrame(df_rows)
            st.dataframe(df_export, use_container_width=True)
            
            csv_bytes = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Full Ledger (CSV)",
                data=csv_bytes,
                file_name=f"family_bank_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.write("---")
        st.subheader("Google Sheets Mirror & Synchronization")
        if gs_engine.is_active():
            st.success(f"Google Sheet Live Mirror is ACTIVE: '{gs_engine.sheet_name}'")
            if st.button("Force Synchronize Master Ledger to Google Sheet Now", use_container_width=True, type="primary"):
                txs = ledger.get_transactions()
                sums = ledger.get_account_summaries(users_dict)
                ok, msg = gs_engine.sync_all(txs, sums, users_dict)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        else:
            st.warning("Google Sheet sync is running in Local Storage mode.")
            with st.expander("How to connect your Google Sheet for Streamlit Cloud Deployment"):
                st.markdown("""
                To enable live synchronization to Google Sheets:
                1. Create a Google Cloud Service Account with **Google Sheets API** and **Google Drive API** enabled.
                2. Share your target Google Spreadsheet with the service account client email (e.g. `service-account@...iam.gserviceaccount.com`) as **Editor**.
                3. In Streamlit Cloud **App Settings -> Secrets** (or locally in `.streamlit/secrets.toml`), paste:
                ```toml
                [connections.gsheets]
                spreadsheet = "https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit"

                [gcp_service_account]
                type = "service_account"
                project_id = "your-project-id"
                private_key_id = "..."
                private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
                client_email = "your-service-account@your-project.iam.gserviceaccount.com"
                client_id = "..."
                ```
                Once configured, every transaction is mirrored instantly to the Google Sheet.
                """)

        st.write("---")
        st.subheader("Import Historical Records (Google Sheet / Excel / CSV)")
        st.caption("Bring in your existing family deposit/withdrawal records so you don't start from zero.")

        imp_col1, imp_col2 = st.columns(2)

        # 1. Pull from connected Google Sheet
        with imp_col1:
            st.markdown("#### Option A: Pull from Google Sheet")
            st.write("Read existing records directly from the `Transactions_Ledger` sheet.")
            if gs_engine.is_active():
                if st.button("Pull Records from Google Sheet Now", use_container_width=True):
                    records, msg = gs_engine.fetch_transactions_from_sheet()
                    if records:
                        imported = ledger.import_transactions(records, reviewer_id=user_id)
                        st.success(f"Successfully imported {imported} new historical records from Google Sheet!")
                        st.rerun()
                    else:
                        st.info(f"No records found: {msg}")
            else:
                st.info("Google Sheet is not connected yet. Connect credentials in secrets to pull directly.")

        # 2. Upload Excel / CSV file
        with imp_col2:
            st.markdown("#### Option B: Upload Old Excel / CSV File")
            uploaded_old_file = st.file_uploader(
                "Upload your existing family Excel (.xlsx, .csv)",
                type=["xlsx", "xls", "csv"],
                key="old_excel_uploader"
            )
            if uploaded_old_file:
                try:
                    if uploaded_old_file.name.endswith(".csv"):
                        df_old = pd.read_csv(uploaded_old_file)
                    else:
                        df_old = pd.read_excel(uploaded_old_file)
                    
                    st.write(f"Previewing {len(df_old)} rows from uploaded file:")
                    st.dataframe(df_old.head(3), use_container_width=True)

                    if st.button("Confirm & Import Excel Records into Vault", use_container_width=True, type="primary"):
                        records_list = df_old.to_dict(orient="records")
                        imported = ledger.import_transactions(records_list, reviewer_id=user_id)
                        st.success(f"Successfully imported {imported} historical transactions into the family vault!")
                        st.rerun()
                except Exception as ex:
                    st.error(f"Error reading file: {str(ex)}")

# ==========================================
# MEMBER VIEW (CHILD 1, 2, OR 3)
# ==========================================
else:
    # Fetch member-specific account summary
    summaries = {s.user_id: s for s in ledger.get_account_summaries(users_dict)}
    my_summary = summaries.get(user_id)
    my_confirmed = my_summary.confirmed_balance if my_summary else 0.0
    my_pending = my_summary.pending_deposits if my_summary else 0.0
    my_withdrawn = my_summary.total_withdrawn if my_summary else 0.0

    # Member KPI Cards
    mk1, mk2, mk3 = st.columns(3)
    with mk1:
        st.metric(
            label="My Confirmed Savings Balance",
            value=f"{my_confirmed:,.2f} THB"
        )
    with mk2:
        st.metric(
            label="My Pending Deposits (Awaiting Dad)",
            value=f"{my_pending:,.2f} THB"
        )
    with mk3:
        st.metric(
            label="My Total Withdrawn",
            value=f"{my_withdrawn:,.2f} THB"
        )

    mem_tab1, mem_tab2, mem_tab3 = st.tabs([
        "Deposit Money",
        "Request Withdrawal",
        "My Passbook & Slips"
    ])

    # 1. DEPOSIT MONEY TAB
    with mem_tab1:
        st.subheader("Record New Deposit")
        st.caption("Upload your bank transfer slip after transferring money to Dad. Once Dad reviews the slip, your confirmed balance will update.")

        with st.form("member_deposit_form", clear_on_submit=True):
            deposit_amount = st.number_input(
                "Deposit Amount (THB)",
                min_value=1.0,
                value=500.0,
                step=50.0
            )
            deposit_notes = st.text_input("Deposit Note / Purpose", placeholder="e.g. October monthly savings, Part-time pay")
            slip_upload = st.file_uploader(
                "Attach Bank Transfer Slip (Mandatory)",
                type=["png", "jpg", "jpeg", "webp"],
                key="mem_deposit_slip"
            )

            submit_deposit = st.form_submit_button("Submit Deposit for Verification", use_container_width=True, type="primary")

            if submit_deposit:
                if not slip_upload:
                    st.error("Bank transfer slip attachment is mandatory to verify your deposit.")
                elif deposit_amount <= 0:
                    st.error("Deposit amount must be greater than zero.")
                else:
                    file_bytes = slip_upload.read()
                    data_uri = ledger.save_slip_image(file_bytes, slip_upload.name, f"dep_{user_id}")
                    
                    ledger.create_transaction(
                        user_id=user_id,
                        tx_type=TransactionType.DEPOSIT.value,
                        amount=deposit_amount,
                        slip_data_uri=data_uri,
                        notes=deposit_notes or "Deposit submitted by member",
                        status=TransactionStatus.PENDING.value
                    )
                    st.success(f"Deposit of {deposit_amount:,.2f} THB submitted successfully! It is now pending verification by Dad.")
                    st.rerun()

    # 2. REQUEST WITHDRAWAL TAB
    with mem_tab2:
        st.subheader("Request Money Withdrawal")
        st.caption("Request to withdraw funds from your confirmed balance. Dad will transfer the money to your bank account and upload the payout slip.")

        with st.form("member_withdrawal_form", clear_on_submit=True):
            st.info(f"Available Balance: **{my_confirmed:,.2f} THB**")
            req_amount = st.number_input(
                "Requested Amount (THB)",
                min_value=1.0,
                max_value=max(1.0, float(my_confirmed)),
                value=min(100.0, float(my_confirmed)),
                step=50.0
            )
            bank_destination = st.text_input("Destination Account", placeholder="Bank Name & Account Number or PromptPay ID")
            req_notes = st.text_input("Reason for Withdrawal", placeholder="e.g. Buying textbooks, monthly rent")

            submit_req = st.form_submit_button("Submit Withdrawal Request", use_container_width=True)

            if submit_req:
                if req_amount <= 0:
                    st.error("Withdrawal amount must be greater than zero.")
                elif req_amount > my_confirmed:
                    st.error(f"Cannot request {req_amount:,.2f} THB; exceeds your confirmed balance of {my_confirmed:,.2f} THB.")
                elif not bank_destination:
                    st.error("Please provide your destination bank account or PromptPay ID.")
                else:
                    ledger.create_transaction(
                        user_id=user_id,
                        tx_type=TransactionType.WITHDRAWAL.value,
                        amount=req_amount,
                        notes=f"{req_notes} | Target: {bank_destination}",
                        bank_info=bank_destination,
                        status=TransactionStatus.PENDING.value
                    )
                    st.success(f"Withdrawal request for {req_amount:,.2f} THB sent to Dad for processing.")
                    st.rerun()

    # 3. MY PASSBOOK & SLIPS TAB
    with mem_tab3:
        st.subheader("My Transaction History & Attached Slips")
        my_txs = ledger.get_transactions(user_id=user_id)

        if not my_txs:
            st.info("No transaction records found for your account.")
        else:
            for tx in my_txs:
                if tx.status == TransactionStatus.APPROVED.value:
                    status_badge = "<span class='badge-approved'>APPROVED</span>"
                elif tx.status == TransactionStatus.PENDING.value:
                    status_badge = "<span class='badge-pending'>PENDING</span>"
                else:
                    status_badge = "<span class='badge-rejected'>REJECTED</span>"

                sign = "+" if tx.tx_type == TransactionType.DEPOSIT.value else "-"
                header_text = f"{tx.created_at} | {tx.tx_type}: {sign}{tx.amount:,.2f} THB ({tx.status})"
                
                with st.expander(header_text, expanded=(tx.status == TransactionStatus.PENDING.value)):
                    col_t1, col_t2 = st.columns([1, 1])
                    with col_t1:
                        st.markdown(f"Status: {status_badge}", unsafe_allow_html=True)
                        st.write(f"**Transaction ID**: `{tx.tx_id}`")
                        st.write(f"**Amount**: `{sign}{tx.amount:,.2f} THB`")
                        st.write(f"**Notes**: {tx.notes or 'None'}")
                        if tx.reviewed_at:
                            st.write(f"**Reviewed by Dad at**: {tx.reviewed_at}")
                    with col_t2:
                        if tx.slip_path:
                            st.write("**Attached Transfer Slip**:")
                            st.image(tx.slip_path, caption=f"Slip for {tx.amount:,.2f} THB", use_container_width=True)
                        else:
                            st.caption("No slip attached.")
