"""Streamlit login / signup screen that gates access to the main dashboard."""

import streamlit as st

from src.auth.database import (
    authenticate_user,
    create_user,
    get_user_role,
    init_user_db,
    log_auth_event,
    verify_department_id,
)
from src.auth.notifications import send_auth_notifications
from src.config import ADMIN_SECRET_ID, DEFAULT_ROLE

ROLE_CHOICES = ["User", "Department", "Admin"]
SIGNUP_ROLE_CHOICES = ["User", "Department"]
_ROLE_KEY = {"User": "user", "Department": "department", "Admin": "admin"}


def _init_session_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if "user_name" not in st.session_state:
        st.session_state.user_name = None
    if "user_role" not in st.session_state:
        st.session_state.user_role = None


def is_authenticated() -> bool:
    _init_session_state()
    return st.session_state.authenticated


def current_role() -> str:
    """The signed-in user's role ('user' | 'admin' | 'department')."""
    _init_session_state()
    return st.session_state.user_role or DEFAULT_ROLE


def logout() -> None:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.user_name = None
    st.session_state.user_role = None


def _handle_login(
    role_choice: str,
    email: str,
    password: str,
    dept_id: str,
    secret_id: str,
) -> None:
    selected_role = _ROLE_KEY[role_choice]

    if not email or not password:
        st.error("Please enter both email and password.")
        return
    if selected_role == "department" and not dept_id.strip():
        st.error("Department ID is mandatory for Department login.")
        return
    if selected_role == "admin" and not secret_id.strip():
        st.error("Admin Secret ID is mandatory for Admin login.")
        return

    success, message = authenticate_user(email, password)
    if not success:
        log_auth_event(email, None, selected_role, "login", "failed", message)
        st.error(message)
        return

    account_role = get_user_role(email.strip().lower())

    if account_role != selected_role:
        detail = f"Selected '{role_choice}' but account role is '{account_role}'."
        log_auth_event(email, None, selected_role, "login", "failed", detail)
        st.error(
            f"This account isn't registered as {role_choice}. "
            f"Please choose the correct role and try again."
        )
        return

    if selected_role == "department" and not verify_department_id(email, dept_id):
        log_auth_event(
            email, None, selected_role, "login", "failed", "Incorrect Department ID."
        )
        st.error("Incorrect Department ID for this account.")
        return

    if selected_role == "admin" and secret_id.strip() != ADMIN_SECRET_ID:
        log_auth_event(
            email, None, selected_role, "login", "failed", "Incorrect Admin Secret ID."
        )
        st.error("Incorrect Admin Secret ID.")
        return

    st.session_state.authenticated = True
    st.session_state.user_email = email.strip().lower()
    st.session_state.user_name = email.split("@")[0]
    st.session_state.user_role = account_role

    log_auth_event(email, st.session_state.user_name, account_role, "login", "success")

    warnings = send_auth_notifications("login", st.session_state.user_name, email)
    if warnings:
        st.session_state["_notify_warning"] = "; ".join(warnings)

    st.success(message)
    st.rerun()


def _handle_signup(
    role_choice: str,
    full_name: str,
    email: str,
    password: str,
    confirm_password: str,
    dept_id: str,
) -> None:
    selected_role = _ROLE_KEY[role_choice]

    if not full_name or not email or not password:
        st.error("Please fill in all fields.")
        return
    if password != confirm_password:
        st.error("Passwords do not match.")
        return
    if len(password) < 6:
        st.error("Password must be at least 6 characters long.")
        return
    if selected_role == "department" and not dept_id.strip():
        st.error("Department ID is mandatory for Department sign up.")
        return

    success, message = create_user(
        full_name,
        email,
        password,
        role=selected_role,
        dept_id=dept_id if selected_role == "department" else None,
    )
    if success:
        st.session_state.authenticated = True
        st.session_state.user_email = email.strip().lower()
        st.session_state.user_name = full_name.strip()
        st.session_state.user_role = selected_role

        log_auth_event(email, full_name, selected_role, "signup", "success")

        warnings = send_auth_notifications("signup", full_name, email)
        if warnings:
            st.session_state["_notify_warning"] = "; ".join(warnings)

        st.success(message)
        st.rerun()
    else:
        log_auth_event(email, full_name, selected_role, "signup", "failed", message)
        st.error(message)


def render_auth_page() -> None:
    """Render the login/signup page. Call this and stop further rendering
    (i.e. don't render the main app) until is_authenticated() is True."""
    _init_session_state()
    init_user_db()

    st.set_page_config(
        page_title="Pahad Guard — Sign In",
        page_icon="🏔️",
        layout="centered",
    )

    st.title("🏔️ Pahad Guard")
    st.caption("Sign in or create an account to access the landslide risk dashboard.")

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        login_role_choice = st.selectbox(
            "Login as", ROLE_CHOICES, key="login_role_choice"
        )

        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")

            dept_id = ""
            secret_id = ""
            if login_role_choice == "Department":
                dept_id = st.text_input(
                    "Department ID *",
                    key="login_dept_id",
                    help="The Department ID that was set when this account was created.",
                )
            elif login_role_choice == "Admin":
                secret_id = st.text_input(
                    "Admin Secret ID *",
                    type="password",
                    key="login_secret_id",
                    help="The shared administrator secret ID configured for this deployment.",
                )

            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            _handle_login(login_role_choice, email, password, dept_id, secret_id)

        st.caption(
            "Demo logins: admin@pahadguard.com · department@pahadguard.com · "
            "user@pahadguard.com (passwords in the README)"
        )

    with signup_tab:
        signup_role_choice = st.selectbox(
            "Sign up as", SIGNUP_ROLE_CHOICES, key="signup_role_choice"
        )

        with st.form("signup_form"):
            full_name = st.text_input("Full name", key="signup_name")
            email = st.text_input("Email", key="signup_email")

            signup_dept_id = ""
            if signup_role_choice == "Department":
                signup_dept_id = st.text_input(
                    "Department ID *",
                    key="signup_dept_id",
                    help="Choose a Department ID — you'll need to re-enter it on every login.",
                )

            password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input(
                "Confirm password", type="password", key="signup_confirm_password"
            )
            submitted = st.form_submit_button("Create account", use_container_width=True)

        if submitted:
            _handle_signup(
                signup_role_choice,
                full_name,
                email,
                password,
                confirm_password,
                signup_dept_id,
            )

        st.caption(
            "Sign up as **User** or **Department** (Department requires a "
            "Department ID). Admin accounts are granted by an existing "
            "administrator from the Database page."
        )

    warning = st.session_state.pop("_notify_warning", None)
    if warning:
        st.info(
            f"Signed in, but the email notification could not be sent ({warning}). "
            "Check your Brevo configuration in .env."
        )
