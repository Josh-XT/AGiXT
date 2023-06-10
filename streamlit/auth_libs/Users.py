import os
import json
import bcrypt
import streamlit as st
from auth_libs.Cfig import Cfig
import auth_libs.Redirect as redir
import logging
import time

CFIG = Cfig()

USER_FILE = "user_data.json"


def load_users():
    """
    Loads the user data from the user file.
    If the user file doesn't exist, triggers the initial user setup.
    Returns the loaded user data.
    """
    if not os.path.exists(USER_FILE):
        # Initial user setup
        st.write("Admin Account Setup")
        admin_email = st.text_input("Enter the admin email")
        admin_password = st.text_input("Enter the admin password", type="password")
        confirm_password = st.text_input("Confirm the admin password", type="password")
        if st.button("Create Admin Account"):
            if admin_password != confirm_password:
                st.error("Password and confirm password do not match.")
            else:
                admin_password_hash = str(
                    bcrypt.hashpw(
                        admin_password.encode("utf-8"), bcrypt.gensalt()
                    ).decode()
                )
                admin_data = {
                    "email": admin_email,
                    "password_hash": admin_password_hash,
                    "admin": True,
                }
                user_data = {"users": [admin_data]}
                save_user_data(user_data)
                config = CFIG.load_config()
                config["admin_email"] = admin_email
                config["config"] = ["", "", "", ""]
                # allow_reg = False
                config["config"][0] = False
                # allow_uac = False
                config["config"][1] = False
                # allow_ucp = False
                config["config"][2] = False
                # allow_uaa = False
                config["config"][3] = False
                CFIG.save_config(config)
                st.success("Admin account created successfully!")
                # Clear session state and redirect to the login page
                st.session_state.clear()
                st.experimental_rerun()
        st.stop()
    else:
        with open(USER_FILE, "r") as file:
            user_data = json.load(file)
    try:
        return user_data
    except:
        return None


def save_user_data(user_data):
    """
    Saves the user data to the user file.
    """
    with open(USER_FILE, "w") as file:
        json.dump(user_data, file, indent=4)


def configure_auth_settings():
    """
    Prompts the admin to configure the authentication settings.
    """
    st.write("Auth/Login Settings Configuration")
    setup_cfg = st.radio(
        "Auth/Login Settings",
        (
            "No Login",
            "Single-User Login",
            "Multi-User Private Registration",
            "Multi-User Public Registration",
        ),
        0,
    )
    if st.button("Build Config"):
        CFIG.set_auth_setup_config(setup_cfg)
        st.success("Auth/Login settings configured!")
        st.experimental_rerun()
    st.stop()


def check_admin_configured():
    """
    Checks if the admin configuration is already done.
    Returns True if configured, False otherwise.
    """
    return CFIG.is_auth_setup_configured()


def logout_button():
    """
    Renders the logout button.
    """
    if st.button("Logout"):
        # Clear session state and redirect to the login page
        st.session_state.clear()
        st.experimental_rerun()  # Redirect to the login page


def check_auth_status():
    # Check if the user is logged in
    if (
        not st.session_state.get("logged_in")
        and os.path.exists("config.yaml")
        and (CFIG.load_config()["auth_setup"] == True)
    ):
        # Redirect to the login page if not
        redir.nav_page("Login")
        logging.info("Not logged in")
    else:
        if CFIG.load_config()["auth_setup"] == True:
            if (
                st.session_state.get("logged_in")
                and st.session_state.get("login_page") == True
            ):
                logging.info("Logged In!")
                redir.nav_page("Profile")
            logout_button()
        elif st.session_state.get("login_page") == "Profile_Page":
            redir.nav_page("Login")
