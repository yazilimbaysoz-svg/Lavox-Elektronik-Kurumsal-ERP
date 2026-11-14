from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Callable, ParamSpec, TypeVar

from .database import database

P = ParamSpec("P")
T = TypeVar("T")

VALID_ROLES = ("Admin", "Cashier", "Technician")

TC_KIMLIK_PATTERN = re.compile(r"^[1-9][0-9]{10}$")
PHONE_PATTERN = re.compile(r"^(\+90|0)?5[0-9]{9}$")


class SecurityError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class AuthorizationError(SecurityError):
    def __init__(self, detail: str = "Insufficient privileges for this action.") -> None:
        super().__init__(403, detail)


class AuthenticationError(SecurityError):
    def __init__(self, detail: str = "Invalid credentials.") -> None:
        super().__init__(401, detail)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210000)
    return salt + ":" + derived.hex()


def verify_password(password: str, stored: str) -> bool:
    salt, derived_hex = stored.split(":", 1)
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210000)
    return secrets.compare_digest(computed.hex(), derived_hex)


def mask_tc_kimlik(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not TC_KIMLIK_PATTERN.match(digits):
        return "***"
    return digits[:3] + "******" + digits[-2:]


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not PHONE_PATTERN.match(digits):
        return "***"
    normalized = digits[-10:]
    return normalized[:3] + "******" + normalized[-2:]


def mask_email(value: str) -> str:
    if not value or "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return masked_local + "@" + domain


def kvkk_mask(value: str, field_type: str) -> str:
    if not value:
        return value
    if field_type == "tc_kimlik":
        return mask_tc_kimlik(value)
    if field_type == "phone":
        return mask_phone(value)
    if field_type == "email":
        return mask_email(value)
    return "***"


def timestamp_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def require_role(*allowed_roles: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    for role in allowed_roles:
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            current_user = kwargs.pop("current_user", None)
            if current_user is None and args:
                current_user = args[-1] if isinstance(args[-1], dict) else None
            if current_user is None:
                raise AuthorizationError("No authenticated user context provided.")
            user_role = current_user.get("role") if isinstance(current_user, dict) else None
            if user_role not in allowed_roles:
                raise AuthorizationError(
                    f"Role '{user_role}' is not authorized. Required: {', '.join(allowed_roles)}."
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


def audit_action(action: str, table_name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    if action not in ("CREATE", "UPDATE", "DELETE"):
        raise ValueError(f"Invalid audit action: {action}")

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            current_user = kwargs.pop("current_user", None)
            if current_user is None and args:
                current_user = args[-1] if isinstance(args[-1], dict) else None
            user_id = current_user.get("id") if isinstance(current_user, dict) else None
            ip_address = kwargs.pop("ip_address", None)

            record_id_value = kwargs.get("record_id") or kwargs.get("id")
            old_values = kwargs.pop("old_values", None)
            new_values = kwargs.pop("new_values", None)

            result = func(*args, **kwargs)

            if isinstance(result, dict):
                record_id_value = record_id_value or result.get("id") or result.get("record_id")
                old_values = old_values or result.get("old_values")
                new_values = new_values or result.get("new_values")

            with database() as connection:
                connection.execute(
                    """
                    INSERT INTO audit_logs
                        (user_id, action, table_name, record_id, old_values, new_values, timestamp, ip_address)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        action,
                        table_name,
                        int(record_id_value) if record_id_value is not None else None,
                        json.dumps(old_values, ensure_ascii=False) if old_values is not None else None,
                        json.dumps(new_values, ensure_ascii=False) if new_values is not None else None,
                        timestamp_now(),
                        ip_address,
                    ),
                )

            return result

        return wrapper

    return decorator


def authenticate_user(username: str, password: str, ip_address: str | None = None) -> dict[str, Any]:
    with database() as connection:
        row = connection.execute(
            """
            SELECT id, username, email, password_hash, role, is_active
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if row is None:
        raise AuthenticationError("User not found.")
    user = dict(row)
    if not user["is_active"]:
        raise AuthenticationError("User account is disabled.")
    stored_hash = user["password_hash"]
    if not verify_password(password, stored_hash):
        raise AuthenticationError("Invalid password.")
    with database() as connection:
        connection.execute(
            """
            INSERT INTO audit_logs
                (user_id, action, table_name, record_id, old_values, new_values, timestamp, ip_address)
            VALUES (?, 'LOGIN', 'users', ?, NULL, NULL, ?, ?)
            """,
            (user["id"], user["id"], timestamp_now(), ip_address),
        )
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
    }
