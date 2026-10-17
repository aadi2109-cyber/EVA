"""Make sure env/.env holds a valid JWT_SECRET (the backend rejects short/placeholder ones).

Usage: python scripts/ensure_jwt_secret.py <path-to-env-file>
Exit 0 when a valid secret is in place (generating one if needed), 1 on a bad shell value.
"""
import os
import re
import secrets
import sys


def valid(value: str) -> bool:
    return len(value.encode("utf-8")) >= 32 and not value.lower().startswith("replace-with-")


path = sys.argv[1]

shell_value = os.environ.get("JWT_SECRET")
if shell_value:
    if not valid(shell_value):
        sys.exit("JWT_SECRET in your shell environment is too short or a placeholder; "
                 "unset it (shell values override env/.env).")
    sys.exit(0)

text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
match = re.search(r"^JWT_SECRET=(.*)$", text, re.M)
if match and valid(match.group(1).strip().strip("\"'")):
    sys.exit(0)

line = "JWT_SECRET=" + secrets.token_urlsafe(48)
if match:
    text = re.sub(r"^JWT_SECRET=.*$", lambda _: line, text, count=1, flags=re.M)
else:
    text += ("" if not text or text.endswith("\n") else "\n") + line + "\n"
os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print(">> generated JWT_SECRET in " + path)
