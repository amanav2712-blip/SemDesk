import streamlit as st
import streamlit_authenticator as stauth
import bcrypt
import database

st.set_page_config(page_title="SemDesk", page_icon="🎓")

database.init_db()
conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT * FROM users")
db_users = cursor.fetchall()

credentials = {"usernames": {}}
for u in db_users:
    credentials["usernames"][u["username"]] = { # type: ignore
        "name": u["name"],  # type: ignore
        "password": u["password"]  # type: ignore
    }

authenticator = stauth.Authenticate(
    credentials,
    "semdesk_cookie",
    "auth_key",
    cookie_expiry_days=30
)

authenticator.login()

if st.session_state.get("authentication_status"):
    with st.sidebar:
        authenticator.logout()

    st.title(f'Welcome to SemDesk, {st.session_state["name"]}! 🎓')
    st.markdown("Select a module from the sidebar to manage your semester.")

elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.divider()
    with st.expander("New to SemDesk? Create an Account"):
        with st.form("register_form"):
            new_name = st.text_input("Full Name")
            new_username = st.text_input("Username").lower()
            new_password = st.text_input("Password", type="password")

            if st.form_submit_button("Register"):
                if new_username in credentials["usernames"]:
                    st.error("Username already taken.")
                elif new_username and new_password:
                    hashed_pw = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

                    cursor.execute("INSERT INTO users (username, name, password) VALUES (%s, %s, %s)",
                                    (new_username, new_name, hashed_pw))
                    conn.commit()
                    st.success("Account created! Please log in above.")
                    st.rerun()

cursor.close()
conn.close()
