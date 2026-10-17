"""
Modular Authentication & Session Manager for Family Bank Application.
Follows login-best-practices architectural standards:
- Bcrypt salted password verification with PBKDF2/SHA256 fallback
- Anti-bruteforce throttling
- Form-based login with browser autofill support
- Persistent session state with role-based access control (Admin vs Member)
"""

import time
import hashlib
import hmac
import secrets
from typing import Optional, Dict, Any
import streamlit as st

# Optional cryptographic imports with resilient fallbacks
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    import extra_streamlit_components as stx
    HAS_STX = True
except ImportError:
    HAS_STX = False


def hash_password(password: str) -> str:
    """Hash password using Bcrypt if available, otherwise salted PBKDF2-SHA256."""
    if HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    else:
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return f"pbkdf2:sha256:100000${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hash."""
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
        elif hashed_password.startswith("plain:"):
            # Emergency local plaintext fallback for development only
            return hmac.compare_digest(plain_password, hashed_password.replace("plain:", ""))
    except Exception:
        return False
    return False


# Default seeded users and passwords for instant out-of-the-box operation
DEFAULT_USERS: Dict[str, Dict[str, Any]] = {
    "dad": {
        "display_name": "Dad (Bank Admin)",
        "role": "admin",
        # Default: dad1234
        "password_hash": "$2b$12$A9987hrlN1jnEKzBmXs3leo9qyTgbAmzaTPEGwyZIKBjjX3diHvHi"
    },
    "herren": {
        "display_name": "Herren",
        "role": "member",
        # Default: pass1234
        "password_hash": "$2b$12$KKhZTeF6lTzbFkOAapqAleCt576VYTpzqcHSFJVEFT/F3MDvNXX3C"
    },
    "irene": {
        "display_name": "Irene",
        "role": "member",
        # Default: pass1234
        "password_hash": "$2b$12$KKhZTeF6lTzbFkOAapqAleCt576VYTpzqcHSFJVEFT/F3MDvNXX3C"
    },
    "prim": {
        "display_name": "Prim",
        "role": "member",
        # Default: pass1234
        "password_hash": "$2b$12$KKhZTeF6lTzbFkOAapqAleCt576VYTpzqcHSFJVEFT/F3MDvNXX3C"
    }
}


class FamilyBankAuth:
    def __init__(self):
        # Read from secrets if present, else fallback to defaults
        auth_cfg = st.secrets.get("auth", {}) if hasattr(st, "secrets") else {}
        self.cookie_name = auth_cfg.get("cookie_name", "family_bank_session")
        self.users = dict(DEFAULT_USERS)
        
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

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Resolves authenticated user from session state or cookie."""
        if "auth_user" in st.session_state and st.session_state.auth_user:
            return st.session_state.auth_user

        if self.cookie_manager:
            try:
                cookie_val = self.cookie_manager.get(cookie=self.cookie_name)
                if cookie_val and cookie_val in self.users:
                    user_info = self.users[cookie_val]
                    st.session_state.auth_user = {
                        "user_id": cookie_val,
                        "display_name": user_info["display_name"],
                        "role": user_info["role"]
                    }
                    return st.session_state.auth_user
            except Exception:
                pass

        return None

    def render_login_ui(self) -> bool:
        """Renders responsive login form with user quick-selector and PIN/password input."""
        current = self.get_current_user()
        if current:
            return True

        col_l, col_center, col_r = st.columns([1, 2, 1])
        with col_center:
            st.markdown("### Family Vault Login")
            st.caption("Select your profile and enter your PIN / Password to access your records.")

            user_options = {u_id: self.users[u_id]["display_name"] for u_id in self.users}
            
            with st.form("family_bank_login_form"):
                selected_user = st.selectbox(
                    "Select Account",
                    options=list(user_options.keys()),
                    format_func=lambda x: user_options[x]
                )
                password_input = st.text_input("PIN / Password", type="password", key="login_pwd")
                submit_btn = st.form_submit_button("Sign In to Vault", use_container_width=True)

                if submit_btn:
                    # Anti-brute force throttling delay
                    time.sleep(0.4)

                    user_record = self.users.get(selected_user)
                    if user_record and verify_password(password_input, user_record["password_hash"]):
                        user_session = {
                            "user_id": selected_user,
                            "display_name": user_record["display_name"],
                            "role": user_record["role"]
                        }
                        st.session_state.auth_user = user_session
                        if self.cookie_manager:
                            try:
                                self.cookie_manager.set(
                                    cookie=self.cookie_name,
                                    val=selected_user,
                                    expires_at=time.time() + (30 * 86400)
                                )
                            except Exception:
                                pass
                        st.success(f"Welcome back, {user_record['display_name']}!")
                        st.rerun()
                    else:
                        st.error("Incorrect PIN or Password. Please try again.")
                        return False

            st.info(
                "Initial Test Passwords:\n"
                "- Dad (Admin): `dad1234`\n"
                "- Member 1 / 2 / 3: `pass1234`"
            )

        return False

    def logout(self):
        """Purges session state and clears cookie."""
        if self.cookie_manager:
            try:
                self.cookie_manager.delete(cookie=self.cookie_name)
            except Exception:
                pass
        st.session_state.auth_user = None
        st.rerun()
