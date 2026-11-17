"""Browser continuity with opaque cookies and server-side session expiry."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

import streamlit as st
from streamlit.components.v1 import declare_component

COOKIE_NAME = "proevira_session"
IDLE_SECONDS = int(os.getenv("WEB_SESSION_IDLE_MINUTES", "30")) * 60
STORE_PATH = Path(os.getenv("WEB_SESSION_STORE", str(Path(__file__).parent / ".sessions.sqlite3")))
AUTH_KEYS = ("auth_token", "user_role", "user_email", "user_uid", "municipio_id")
_cookie = declare_component("proevira_session_cookie", path=str(Path(__file__).parent / "session_cookie"))


@contextmanager
def _db():
    db = sqlite3.connect(STORE_PATH, timeout=10)
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL, last_seen REAL NOT NULL, expires REAL NOT NULL)")
            yield db
    finally:
        db.close()


def _digest(sid):
    return hashlib.sha256(sid.encode()).hexdigest()


def create_session(payload, now=None):
    now = time.time() if now is None else now
    # Only inspect the expiry of the token returned by a successful API login.
    # Authorization and signature verification remain the backend's responsibility.
    part = payload["auth_token"].split(".")[1]
    expires = float(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))["exp"])
    sid = secrets.token_urlsafe(32)
    with _db() as db:
        db.execute("DELETE FROM sessions WHERE expires <= ? OR last_seen <= ?", (now, now - IDLE_SECONDS))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (_digest(sid), json.dumps(payload), now, expires))
    return sid


def load_session(sid, *, touch=True, now=None):
    now = time.time() if now is None else now
    if not isinstance(sid, str) or len(sid) != 43:
        return None
    with _db() as db:
        row = db.execute("SELECT payload, last_seen, expires FROM sessions WHERE id = ?", (_digest(sid),)).fetchone()
        if not row:
            return None
        payload, last_seen, expires = row
        if now - last_seen >= IDLE_SECONDS or now >= expires:
            db.execute("DELETE FROM sessions WHERE id = ?", (_digest(sid),))
            return None
        if touch:
            db.execute("UPDATE sessions SET last_seen = ? WHERE id = ?", (now, _digest(sid)))
    return json.loads(payload)


def revoke_session(sid):
    if isinstance(sid, str) and len(sid) == 43:
        with _db() as db:
            db.execute("DELETE FROM sessions WHERE id = ?", (_digest(sid),))


def remember_login():
    previous = st.session_state.get("_browser_session_id") or st.context.cookies.get(COOKIE_NAME)
    revoke_session(previous)
    payload = {key: st.session_state.get(key) for key in AUTH_KEYS}
    st.session_state["_browser_session_id"] = create_session(payload)
    st.session_state["_browser_session_checked"] = True
    st.session_state.pop("_clear_session_cookie", None)


def forget_login():
    sid = st.session_state.pop("_browser_session_id", None) or st.context.cookies.get(COOKIE_NAME)
    revoke_session(sid)
    st.session_state["_browser_session_checked"] = True
    st.session_state["_clear_session_cookie"] = True
    st.session_state["_reset_navigation"] = True
    for key in (*AUTH_KEYS, "auth_view", "user_name"):
        st.session_state.pop(key, None)


def _expire():
    from api_client import api
    api.logout()
    st.session_state["_session_expired"] = True


def restore_browser_session():
    if st.session_state.pop("_reset_navigation", False):
        st.session_state.pop("main_navigation", None)
    if not st.session_state.get("_browser_session_checked"):
        st.session_state["_browser_session_checked"] = True
        sid = st.context.cookies.get(COOKIE_NAME)
        if sid and not st.session_state.get("auth_token"):
            payload = load_session(sid)
            if payload:
                st.session_state.update(payload)
                st.session_state["_browser_session_id"] = sid
                st.session_state.pop("main_navigation", None)
            else:
                st.session_state["_clear_session_cookie"] = True
                st.session_state["_session_expired"] = True

    sid = st.session_state.get("_browser_session_id")
    if sid and not load_session(sid):
        _expire()
        sid = None
    if st.session_state.get("_clear_session_cookie"):
        _cookie(name=COOKIE_NAME, value="", max_age=0, key="session_cookie", default=None)
    elif sid:
        _cookie(name=COOKIE_NAME, value=sid, max_age=86400, key="session_cookie", default=None)


@st.fragment(run_every=60)
def watch_session_expiry():
    # Timer checks never extend the inactivity window.
    sid = st.session_state.get("_browser_session_id")
    if sid and not load_session(sid, touch=False):
        _expire()
        st.rerun(scope="app")
