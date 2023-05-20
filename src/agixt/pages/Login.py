import streamlit as st
import auth_libs.Redirect as redir
import bcrypt
from auth_libs.Cfig import Cfig
from auth_libs.Users import (
    load_users,
    save_user_data,
    configure_auth_settings,
    check_admin_configured,
)
import os

CFIG = Cfig()
CONFIG_FILE = "config.yaml"

if (
    not st.session_state.get("logged_in")
    and os.path.exists(CONFIG_FILE)
    and (
        CFIG.load_config()["auth_setup_config"] == "None"
        or CFIG.load_config()["auth_setup_config"] == None
        or CFIG.load_config()["auth_setup_config"] is None
        or CFIG.load_config()["auth_setup_config"] == "null"
        or CFIG.load_config()["auth_setup_config"] == "No Login"
    )
):
    st.session_state["logged_in"] = True
    st.session_state["prof_redir"] = False

# Check if the user is logged in
if st.session_state.get("logged_in") and st.session_state["prof_redir"]:
    # Redirect to the login page if so
    redir.nav_page("Profile")


# Login form
def login_form():
    """
    Renders the login form.
    """
    st.write("Please log in")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    user_data = load_users()

    if st.button("Login"):
        for user in user_data["users"]:
            if user["email"] == email:
                if bcrypt.checkpw(
                    password.encode("utf-8"), user["password_hash"].encode("utf-8")
                ):
                    st.success("Login successful!")
                    st.session_state["logged_in"] = True
                    st.session_state["email"] = email
                    st.experimental_rerun()  # Redirect to UI
                    break
        else:
            st.error("Incorrect email or password.")


# Check if admin configuration is needed
if not check_admin_configured():
    configure_auth_settings()
    st.stop()

# Render the login form
login_form()
