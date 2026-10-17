"""
Password Hashing Utility for Family Bank App.
Generates Bcrypt and PBKDF2 hashes for .streamlit/secrets.toml.
Run: python hash_tool.py
"""

import getpass
import hashlib
import secrets

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


def generate_hash():
    print("=== Family Bank Credential Generator ===")
    pwd1 = getpass.getpass("Enter password/PIN to hash: ")
    pwd2 = getpass.getpass("Confirm password/PIN: ")

    if pwd1 != pwd2:
        print("Error: Passwords do not match.")
        return

    if HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=12)
        h = bcrypt.hashpw(pwd1.encode("utf-8"), salt).decode("utf-8")
        print("\nGenerated Bcrypt Hash:")
        print(f'password_hash = "{h}"')
    else:
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac("sha256", pwd1.encode("utf-8"), salt.encode("utf-8"), 100000)
        h = f"pbkdf2:sha256:100000${salt}${key.hex()}"
        print("\nGenerated PBKDF2 Hash:")
        print(f'password_hash = "{h}"')


if __name__ == "__main__":
    generate_hash()
