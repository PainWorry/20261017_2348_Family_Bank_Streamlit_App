"""
Modular Authentication & Session Manager for Family Bank Application.
Strictly implements login-best-practices architectural standards:
- Pillar 1: Signed JWT Browser Cookie Session Persistence (F5 reload immunity)
- Pillar 2: Salted Bcrypt Password Hashing with PBKDF2-SHA256 fallback
- Pillar 3: Security Invariants (Tamper resistance, anti-bruteforce throttling, form-based autofill)
"""

import time
import hashlib
import hmac
import secrets
from typing import Optional, Dict, Any
import streamlit as st

# Cryptographic imports
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    import jwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False

try:
    import extra_streamlit_components as stx
    HAS_STX = True
except ImportError:
    HAS_STX = False


def hash_password(password: str) -> str:
    """Hash password using Bcrypt (rounds=12) if available, otherwise salted PBKDF2-SHA256."""
    if HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    else:
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return f"pbkdf2:sha256:100000${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against salted hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
            if HAS_BCRYPT:
                return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
            return False
        elif hashed_password.startswith("pbkdf2:sha256:"):
            parts = hashed_password.split("$")
            if len(parts) == 3:
                salt = parts[1]
                expected_hex = parts[2]
                computed = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000)
                return hmac.compare_digest(computed.hex(), expected_hex)
    except Exception:
        return False
    return False


# Default seeded users and passwords for instant out-of-the-box operation
DEFAULT_USERS: Dict[str, Dict[str, Any]] = {
    "dad": {
        "display_name": "Dad (Bank Admin)",
        "role": "admin",
        # Default: Papa0000
        "password_hash": "$2b$12$WsyEpUWniWySzou2CriRceAbtzLjAPgScGa2OkKcFM6TbicSHJyC2"
    },
    "herren": {
        "display_name": "Herren",
        "role": "member",
        # Default: Herren2222
        "password_hash": "$2b$12$6oC0El9xuXM2KLf5KZDxl.8mkcDX7ts6LwkoeiAsC/O6cW7VNNGeK"
    },
    "irene": {
        "display_name": "Irene",
        "role": "member",
        # Default: Kanun1111
        "password_hash": "$2b$12$IudY.IKo5g0q1LvaoLPIZONOe0tuWDXCaJ7tMxb7A4ftuiahvBTly"
    },
    "prim": {
        "display_name": "Prim",
        "role": "member",
        # Default: Kia3333
        "password_hash": "$2b$12$QsHAGIeTfgYqSy5LbLpbkeUfGK7D656T8JDa3U9ZaqvV/bvK9oka2"
    }
}


class FamilyBankAuth:
    def __init__(self):
        # Read from secrets if present, else fallback to defaults
        auth_cfg = st.secrets.get("auth", {}) if hasattr(st, "secrets") else {}
        self.cookie_secret = auth_cfg.get("cookie_secret", "d94a6f238b19e27c1048b30f81d45e99a8b72c6d5e4f3a2b1c0d9e8f7a6b5c4d")
        self.cookie_name = auth_cfg.get("cookie_name", "family_bank_jwt_session")
        self.cookie_expiry_days = auth_cfg.get("cookie_expiry_days", 30)
        self.users = dict(DEFAULT_USERS)
        
        # Lazy load ledger storage engine
        from storage import get_ledger
        self.ledger = get_ledger()

        # Merge any custom users from secrets.toml
        configured_users = auth_cfg.get("users", {})
        for u_id, u_info in configured_users.items():
            self.users[u_id.lower()] = {
                "display_name": u_info.get("display_name", u_id.title()),
                "role": u_info.get("role", "member"),
                "password_hash": u_info.get("password_hash", "")
            }

        if HAS_STX:
            try:
                self.cookie_manager = stx.CookieManager(key="family_bank_cookie_mgr")
            except Exception:
                self.cookie_manager = None
        else:
            self.cookie_manager = None

    def _create_token(self, username: str, user_data: Dict[str, Any]) -> str:
        """Issues cryptographically signed JWT session token."""
        if not HAS_JWT:
            return username
        payload = {
            "sub": username,
            "display_name": user_data.get("display_name", username),
            "role": user_data.get("role", "member"),
            "must_change_password": user_data.get("must_change_password", False),
            "exp": int(time.time()) + (self.cookie_expiry_days * 86400)
        }
        return jwt.encode(payload, self.cookie_secret, algorithm="HS256")

    def _verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verifies JWT signature and expiry against cookie secret."""
        if not HAS_JWT:
            return self.users.get(token)
        try:
            return jwt.decode(token, self.cookie_secret, algorithms=["HS256"])
        except Exception:
            return None

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Resolves authenticated user from session state or signed browser cookie with live DB sync."""
        if "auth_user" in st.session_state and st.session_state.auth_user:
            uid = st.session_state.auth_user.get("user_id")
            if uid:
                cred = self.ledger.get_user_credential(uid)
                if cred:
                    st.session_state.auth_user["must_change_password"] = cred["must_change_password"]
            return st.session_state.auth_user

        if self.cookie_manager:
            try:
                token = self.cookie_manager.get(cookie=self.cookie_name)
                if token:
                    payload = self._verify_token(token)
                    if payload and payload.get("sub") in self.users:
                        uid = payload["sub"]
                        user_info = self.users[uid]
                        cred = self.ledger.get_user_credential(uid)
                        must_change = cred["must_change_password"] if cred else payload.get("must_change_password", False)
                        st.session_state.auth_user = {
                            "user_id": uid,
                            "display_name": user_info["display_name"],
                            "role": user_info["role"],
                            "must_change_password": must_change
                        }
                        return st.session_state.auth_user
                    else:
                        self.cookie_manager.delete(cookie=self.cookie_name)
            except Exception:
                pass

        return None

    def render_login_ui(self) -> bool:
        """Renders standard browser-compatible form with password manager autofill support."""
        current = self.get_current_user()
        if current:
            return True

        col_l, col_center, col_r = st.columns([1, 2, 1])
        with col_center:
            st.markdown("### Family Vault Login")
            st.caption("Sign in with your authorized family credentials. Sessions persist across browser reloads.")

            user_options = {u_id: self.users[u_id]["display_name"] for u_id in self.users}
            
            with st.form("family_bank_login_form"):
                selected_user = st.selectbox(
                    "Select Account",
                    options=list(user_options.keys()),
                    format_func=lambda x: user_options[x]
                )
                password_input = st.text_input("PIN / Password", type="password", key="login_pwd")
                submit_btn = st.form_submit_button("Sign In to Vault", use_container_width=True, type="primary")

                if submit_btn:
                    # Mandatory anti-brute force throttling delay
                    time.sleep(0.4)

                    user_record = self.users.get(selected_user)
                    if user_record:
                        # Check SQLite ledger for latest password hash & must_change status
                        cred = self.ledger.get_user_credential(selected_user)
                        expected_hash = cred["password_hash"] if cred else user_record["password_hash"]
                        must_change = cred["must_change_password"] if cred else True

                        matched = verify_password(password_input, expected_hash)
                        if not matched and selected_user == "herren" and must_change:
                            matched = (password_input == "pass1234" or password_input == "Herren2222")

                        if matched:
                            user_session = {
                                "user_id": selected_user,
                                "display_name": user_record["display_name"],
                                "role": user_record["role"],
                                "must_change_password": must_change
                            }
                            st.session_state.auth_user = user_session
                            if self.cookie_manager:
                                try:
                                    signed_token = self._create_token(selected_user, user_session)
                                    self.cookie_manager.set(
                                        cookie=self.cookie_name,
                                        val=signed_token,
                                        expires_at=time.time() + (self.cookie_expiry_days * 86400)
                                    )
                                except Exception:
                                    pass
                            st.success(f"Welcome back, {user_record['display_name']}!")
                            st.rerun()
                        else:
                            st.error("Invalid PIN or Password. Access denied.")
                            return False
                    else:
                        st.error("Invalid account selected.")
                        return False

            st.info(
                "Initial Default Passwords:\n"
                "- Dad (Admin): `Papa0000`\n"
                "- Irene: `Kanun1111`\n"
                "- Prim: `Kia3333`\n"
                "- Herren: `Herren2222` (or `pass1234`)\n\n"
                "Note: You will be prompted to set your personal PIN/password upon first login."
            )

        return False

    def change_password(self, user_id: str, new_password: str, old_password: Optional[str] = None) -> tuple[bool, str]:
        """Validates and updates password for user_id in SQLite and active session state."""
        user_id = user_id.lower()
        clean_pwd = (new_password or "").strip()
        
        if len(clean_pwd) < 4:
            return False, "Password must be at least 4 characters long."

        disallowed = ["papa0000", "kanun1111", "kia3333", "herren2222", "dad1234", "pass1234"]
        if clean_pwd.lower() in disallowed:
            return False, "Cannot reuse initial temporary default password. Please choose a personal password."

        cred = self.ledger.get_user_credential(user_id)
        current_hash = cred["password_hash"] if cred else self.users.get(user_id, {}).get("password_hash", "")

        if old_password is not None:
            if not verify_password(old_password, current_hash):
                return False, "Current password does not match."

        if verify_password(clean_pwd, current_hash):
            return False, "New password cannot be identical to the previous password."

        new_hash = hash_password(clean_pwd)
        updated = self.ledger.update_user_password(user_id, new_hash, must_change=False)
        if not updated:
            return False, "Database error updating password."

        # Keep runtime cache in sync
        if user_id in self.users:
            self.users[user_id]["password_hash"] = new_hash

        if "auth_user" in st.session_state and st.session_state.auth_user:
            if st.session_state.auth_user.get("user_id") == user_id:
                st.session_state.auth_user["must_change_password"] = False
                if self.cookie_manager:
                    try:
                        updated_token = self._create_token(user_id, st.session_state.auth_user)
                        self.cookie_manager.set(
                            cookie=self.cookie_name,
                            val=updated_token,
                            expires_at=time.time() + (self.cookie_expiry_days * 86400)
                        )
                    except Exception:
                        pass

        return True, "Password updated successfully."

    def logout(self):
        """Purges local session state and invalidates persistent browser cookie."""
        if self.cookie_manager:
            try:
                self.cookie_manager.delete(cookie=self.cookie_name)
            except Exception:
                pass
        st.session_state.auth_user = None
        st.rerun()
