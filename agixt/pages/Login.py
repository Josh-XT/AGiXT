import streamlit as st
import bcrypt
from auth_libs.Cfig import Cfig
from auth_libs.Users import (
    load_users,
    save_user_data,
    configure_auth_settings,
    check_admin_configured,
)
from auth_libs.Users import check_auth_status

check_auth_status()
CFIG = Cfig()


# Login form
def login_form():
    """
    Renders the login form.
    """
    if CFIG.load_config()["auth_setup_config"] == "No Login":
        st.write("Login Is Not Enabled")
        st.stop()

    user_data = load_users()
    if user_data == "Reload":
        st.experimental_rerun()

    st.write("Please log in")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

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
