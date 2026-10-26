import streamlit as st
import streamlit_authenticator as stauth
import bcrypt
import datetime
import database
import importlib
importlib.reload(database)
from streamlit_calendar import calendar

st.set_page_config(page_title="SemDesk", layout="wide")

#connecting to the database
database.init_db()
conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT username, name, password FROM users")
db_users = cursor.fetchall()

credentials = {"usernames": {}}
for u in db_users:
    credentials["usernames"][u["username"]] = {
        "name": u["name"],
        "password": u["password"]
    }

authenticator = stauth.Authenticate(
    credentials,
    "semdesk_cookie",
    "auth_key",
    cookie_expiry_days=30
)

authenticator.login()

if st.session_state.get("authentication_status"):
    active_user = st.session_state["username"]      # from here onwards for every query we use WHERE username = active_user so that only that user's tasks are visible.

    with st.sidebar:
        st.write(f"Logged in as: **{active_user}**")
        authenticator.logout()

    st.title("SemDesk Dashboard")

    data = database.get_attendance_data(active_user)
    stats = data["stats"]

    cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE username = %s AND status = 'Pending'", (active_user,))
    task_res = cursor.fetchone()
    pending_tasks = task_res["count"] if task_res else 0

    total_held = sum(s["held"] for s in stats.values())
    total_attended = sum(s["attended"] for s in stats.values())
    overall_pct = (total_attended / total_held * 100) if total_held > 0 else 100.0      #overall attendance percentage

    col1, col2, col3 = st.columns(3)
    col1.metric("Overall Attendance", f"{overall_pct:.1f}%", f"{total_attended}/{total_held} classes attended")
    col2.metric("Pending Tasks", str(pending_tasks))
    col3.metric("Enrolled Courses", str(len(stats)))

    st.divider()

    # monthly calendar view
    st.subheader("Monthly Academic Calendar")

    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,listMonth",
        },
        "initialView": "dayGridMonth",
        "navLinks": True,
        "selectable": True,
        "defaultTimedEventDuration": "00:01:00",
        "forceEventDuration": False,
        "nextDayThreshold": "09:00:00",
    }

    custom_css = """
        .fc-daygrid-event {
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 100%;
        }
    """

    calendar(events=data["events"], options=calendar_options, custom_css=custom_css, key="semdesk_calendar_v3")

    # Schedule tasks on specific time slots
    with st.expander("Schedule Appointment or Study Block on Calendar", expanded=False):
        col_sch1, col_sch2 = st.columns([1, 1])
        with col_sch1:
            st.write("**New Scheduled Block**")
            with st.form("schedule_event_form", clear_on_submit=True):
                cursor.execute("SELECT id, course_id, title FROM tasks WHERE username = %s AND status = 'Pending'", (active_user,))
                p_tasks = cursor.fetchall()

                task_options = ["Custom Entry"] + [f"Task: [{t['course_id']}] {t['title']}" for t in p_tasks]   # type: ignore
                selected_source = st.selectbox("Schedule type", task_options)

                if selected_source == "Custom Entry":
                    event_title = st.text_input("Title / Details")
                    category = st.selectbox("Category", ["Appointment", "Study Block", "Personal"])
                else:
                    event_title = selected_source
                    category = "Study Block"

                ev_col_d, ev_col_t1, ev_col_t2 = st.columns(3)
                with ev_col_d:
                    ev_date = st.date_input("Date", value=datetime.date.today(), format="DD/MM/YYYY", key="ev_date_input")
                with ev_col_t1:
                    ev_start = st.time_input("Start Time", value=datetime.time(14, 0), key="ev_st_input")
                with ev_col_t2:
                    ev_end = st.time_input("End Time", value=datetime.time(15, 0), key="ev_et_input")

                if st.form_submit_button("Add to Calendar"):
                    if event_title:
                        cursor.execute(
                            "INSERT INTO scheduled_events (username, title, event_date, start_time, end_time, category) VALUES (%s, %s, %s, %s, %s, %s)",
                            (active_user, event_title, ev_date, ev_start, ev_end, category)
                        )
                        conn.commit()
                        st.success(f"Added '{event_title}' to calendar on {ev_date.strftime('%d/%m/%y')}!")
                        st.rerun()
                    else:
                        st.warning("Please enter a title for the event.")

        with col_sch2:
            st.write("**Your Scheduled Appointments & Blocks**")
            sched_list = data.get("scheduled_events", [])
            if sched_list:
                for ev in sched_list[:6]:
                    c_ev1, c_ev2 = st.columns([3, 1])
                    ev_d_str = ev['event_date'].strftime('%d/%m/%y') if hasattr(ev['event_date'], 'strftime') else str(ev['event_date'])
                    st_fmt = f"{ev['start_time'].seconds // 3600:02d}:{(ev['start_time'].seconds % 3600) // 60:02d}" if hasattr(ev['start_time'], 'seconds') else str(ev['start_time'])[:5]
                    et_fmt = f"{ev['end_time'].seconds // 3600:02d}:{(ev['end_time'].seconds % 3600) // 60:02d}" if hasattr(ev['end_time'], 'seconds') else str(ev['end_time'])[:5]
                    c_ev1.write(f"• **{ev['title']}** ({ev.get('category', 'Event')})\n  *{ev_d_str} • {st_fmt} - {et_fmt}*")
                    if c_ev2.button("Remove", key=f"del_ev_{ev['id']}"):
                        cursor.execute("DELETE FROM scheduled_events WHERE id = %s AND username = %s", (ev['id'], active_user))
                        conn.commit()
                        st.rerun()
            else:
                st.info("No appointments or study blocks scheduled yet.")

    st.divider()

    # Attendance Management
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Log a Bunk (Absence)")
        st.caption("Classes are automatically marked Present according to your timetable. Log here only when you miss a class.")

        if stats:
            bunk_course = st.selectbox("Course", list(stats.keys()), key="bunk_c")
            bunk_date = st.date_input("Date Missed", value=datetime.date.today(), format="DD/MM/YYYY", key="bunk_d")

            bunk_weekday = bunk_date.strftime("%A")
            day_slots = [s for s in data["slots"] if s["course_id"] == bunk_course and s["day_of_week"] == bunk_weekday]

            if day_slots:
                slot_labels = [f"{database.format_time_str(s['start_time'])} - {database.format_time_str(s['end_time'])}" for s in day_slots]
                chosen_idx = st.selectbox("Class Time Slot", range(len(day_slots)), format_func=lambda i: slot_labels[i], key="bunk_slot")
                bunk_time = day_slots[chosen_idx]["start_time"]
            else:
                bunk_time = st.time_input("Class Start Time", value=datetime.time(9, 0), key="bunk_time")
                st.caption(f"No regular timetable slots for {bunk_course} on {bunk_weekday}.")

            if st.button("Record Bunk", key="btn_bunk"):
                cursor.execute(
                    "INSERT INTO absences (username, course_id, absence_date, start_time) VALUES (%s, %s, %s, %s)",
                    (active_user, bunk_course, bunk_date, bunk_time)
                )
                conn.commit()
                time_disp = database.format_time_str(bunk_time)
                st.success(f"Recorded bunk for {bunk_course} ({time_disp}) on {bunk_date.strftime('%d/%m/%y')}")
                st.rerun()
        else:
            st.info("Add courses in the Timetable tab first.")

        # Recent Bunks & Undo
        if data["absences"]:
            st.write("**Recent Logged Bunks**")
            for b in data["absences"][:5]:
                col_b1, col_b2 = st.columns([3, 1])
                b_date_str = b['absence_date'].strftime('%d/%m/%y') if hasattr(b['absence_date'], 'strftime') else str(b['absence_date'])
                time_disp = f" ({database.format_time_str(b['start_time'])})" if b.get('start_time') else ""
                col_b1.write(f"• {b['course_id']} on {b_date_str}{time_disp}")
                if col_b2.button("Undo", key=f"undo_{b['id']}"):
                    cursor.execute("DELETE FROM absences WHERE id = %s AND username = %s", (b['id'], active_user))
                    conn.commit()
                    st.rerun()

    with col_right:
        st.subheader("Live Attendance Status")
        if stats:
            for cid, s in stats.items():
                status_color = "normal" if s["pct"] >= s["target"] else "inverse"
                if s["pct"] >= s["target"]:
                    note = f"Safe to skip {s['safe_to_skip']} classes"
                else:
                    note = f"Must attend next {s['must_attend']} classes"

                st.metric(
                    label=f"{cid} - {s['name']}",
                    value=f"{s['pct']:.1f}% (Target: {s['target']:.0f}%)",
                    delta=f"{s['attended']}/{s['held']} attended • {note}",
                    delta_color=status_color
                )
        else:
            st.info("No courses found. Add courses in the Timetable tab.")

elif st.session_state.get("authentication_status") is False:
    st.error("Username or password is incorrect")

elif st.session_state.get("authentication_status") is None:
    st.divider()
    with st.expander("New student? Create an account"):
        with st.form("register_form"):
            new_name = st.text_input("Full Name")
            new_username = st.text_input("Username").lower().strip()
            new_password = st.text_input("Password", type="password")

            if st.form_submit_button("Register"):
                if not new_username or not new_password:
                    st.warning("Please fill in both username and password.")
                elif new_username in credentials["usernames"]:
                    st.error("Username already taken.")
                else:
                    hashed_pw = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                    cursor.execute(
                        "INSERT INTO users (username, name, password) VALUES (%s, %s, %s)",
                        (new_username, new_name, hashed_pw)
                    )
                    conn.commit()
                    st.success("Account created! Please log in above.")
                    st.rerun()

cursor.close()
conn.close()
