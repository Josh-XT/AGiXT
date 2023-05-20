import streamlit as st
import auth_libs.Redirect as redir
import bcrypt
from auth_libs.Users import load_users, save_user_data

# Check if the user is logged in
if st.session_state.get("logged_in"):
    # Redirect to the Profile page if so
    redir.nav_page("Profile")


def registration_form():
    st.write("Registration Form")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    user_data = load_users()

    if st.button("Register"):
        if password == confirm_password:
            if email not in [user["email"] for user in user_data["users"]]:
                hashed_password = bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt()
                )
                user_data["users"].append(
                    {"email": email, "password_hash": hashed_password.decode("utf-8")}
                )
                save_user_data(user_data)
                st.success("Registration successful!")
                st.experimental_rerun()  # Redirect to UI
            else:
                st.error("Email already registered.")
        else:
            st.error("Passwords do not match.")

    st.stop()


registration_form()
