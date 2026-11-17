"""Accounts: sign-up, sign-in and profile changes. Passwords are hashed, never stored."""
from __future__ import annotations

import re

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import User, db
from ..errors import ApiError, Conflict
from ..models import LEVELS

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[A-Za-z]{2,}$")
ROLE_RE = re.compile(r"^[\w .,/&+#()\-]{2,60}$")
COMMON_PASSWORDS = {"password", "password1", "12345678", "123456789", "qwertyuiop", "iloveyou", "11111111",
                    "00000000", "abcdefgh", "letmein1", "welcome1"}

# Compared against when an email is unknown, so "no such user" and "wrong password" take similar time.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def normalize_email(email) -> str:
    return (email or "").strip().lower() if isinstance(email, str) else ""


def _check_password_rules(password) -> str:
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ApiError("Choose a password of 8 to 128 characters.")
    if password.lower() in COMMON_PASSWORDS:
        raise ApiError("That password is too common. Pick something harder to guess.")
    return password


def _clean_name(name) -> str:
    name = (name or "").strip() if isinstance(name, str) else ""
    if not 1 <= len(name) <= 60:
        raise ApiError("Enter your name (up to 60 characters).")
    return name


def register(email, password, name) -> User:
    email = normalize_email(email)
    if not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address.")
    password = _check_password_rules(password)
    name = _clean_name(name)
    if User.query.filter_by(email=email).first():
        raise Conflict("An account with this email already exists. Try signing in.")
    user = User(email=email, name=name, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(email, password) -> User:
    user = User.query.filter_by(email=normalize_email(email)).first()
    ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password if isinstance(password, str) else "")
    if not user or not ok:
        raise ApiError("Incorrect email or password.", 401)
    return user


def sign_in(user: User) -> None:
    session.clear()                      # new session on login: prevents session fixation
    session["uid"] = user.id
    session.permanent = True


def sign_out() -> None:
    session.clear()


def current_user() -> User | None:
    uid = session.get("uid")
    if not uid:
        return None
    user = db.session.get(User, uid)
    if user is None:
        session.clear()                  # the account was deleted
    return user


def update_profile(user: User, name, target_role, level) -> User:
    if name is not None:
        user.name = _clean_name(name)
    if target_role is not None:
        target_role = target_role.strip() if isinstance(target_role, str) else ""
        if target_role and not ROLE_RE.match(target_role):
            raise ApiError("Enter a role such as 'Backend Developer'.")
        user.target_role = target_role
    if level is not None:
        if level not in LEVELS:
            raise ApiError(f"Level must be one of: {', '.join(LEVELS)}.")
        user.level = level
    db.session.commit()
    return user


def change_password(user: User, current, new) -> None:
    if not check_password_hash(user.password_hash, current if isinstance(current, str) else ""):
        raise ApiError("Your current password is incorrect.", 403)
    user.password_hash = generate_password_hash(_check_password_rules(new))
    db.session.commit()


def delete_account(user: User, password) -> None:
    if not check_password_hash(user.password_hash, password if isinstance(password, str) else ""):
        raise ApiError("Password is incorrect.", 403)
    db.session.delete(user)              # interviews and answers are removed with it (cascade)
    db.session.commit()
    session.clear()