import streamlit as st
import pandas as pd
import datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database
import importlib
importlib.reload(database)

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page first.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="Attendance Analytics", layout="wide")
st.title("Attendance Analytics & Tracker")

data = database.get_attendance_data(active_user)
stats = data["stats"]

if not stats:
    st.info("No courses found. Add courses and timetable in the **Timetable** tab to see your attendance analytics.")
    st.stop()

selected_course = st.selectbox("Select Course", list(stats.keys()))
c_stat = stats[selected_course]

st.divider()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Classes Held So Far", c_stat["held"])
col2.metric("Classes Attended", c_stat["attended"])

pct_color = "normal" if c_stat["pct"] >= c_stat["target"] else "inverse"
col3.metric("Current Attendance", f"{c_stat['pct']:.1f}%", f"Target: {c_stat['target']:.0f}%", delta_color=pct_color)

if c_stat["pct"] >= c_stat["target"]:
    col4.metric("Safe to Skip", f"{c_stat['safe_to_skip']} classes", delta="Buffer available", delta_color="normal")
else:
    col4.metric("Must Attend Next", f"{c_stat['must_attend']} classes", delta="Danger Zone", delta_color="inverse")

# Progress bar
st.write(f"**Attendance Progress vs Cutoff ({c_stat['target']:.0f}%)**")
st.progress(min(1.0, max(0.0, c_stat["pct"] / 100.0)))

st.divider()

col_l, col_r = st.columns([1, 1])

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

with col_l:
    st.subheader(f"Log a Bunk for {selected_course}")
    st.caption("Classes are automatically counted as Present. Record missed classes below:")

    bunk_d = st.date_input("Date Missed", value=datetime.date.today(), format="DD/MM/YYYY", key="att_bunk_d")
    bunk_weekday = bunk_d.strftime("%A")
    day_slots = [s for s in data["slots"] if s["course_id"] == selected_course and s["day_of_week"] == bunk_weekday]

    if day_slots:
        slot_labels = [f"{database.format_time_str(s['start_time'])} - {database.format_time_str(s['end_time'])}" for s in day_slots]
        chosen_idx = st.selectbox("Class Time Slot", range(len(day_slots)), format_func=lambda i: slot_labels[i], key="att_bunk_slot")
        bunk_time = day_slots[chosen_idx]["start_time"]
    else:
        bunk_time = st.time_input("Class Start Time", value=datetime.time(9, 0), key="att_bunk_time")
        st.caption(f"No regular timetable slots for {selected_course} on {bunk_weekday}.")

    if st.button("Record Bunk", key="att_record_bunk"):
        cursor.execute(
            "INSERT INTO absences (username, course_id, absence_date, start_time) VALUES (%s, %s, %s, %s)",
            (active_user, selected_course, bunk_d, bunk_time)
        )
        conn.commit()
        time_disp = database.format_time_str(bunk_time)
        st.success(f"Recorded bunk for {selected_course} ({time_disp}) on {bunk_d.strftime('%d/%m/%y')}")
        st.rerun()

with col_r:
    st.subheader("Logged Bunks History")
    course_bunks = [b for b in data["absences"] if b["course_id"] == selected_course]
    if course_bunks:
        for b in course_bunks:
            b_col1, b_col2 = st.columns([3, 1])
            b_date_str = b['absence_date'].strftime('%d/%m/%y') if hasattr(b['absence_date'], 'strftime') else str(b['absence_date'])
            time_disp = f" at {database.format_time_str(b['start_time'])}" if b.get('start_time') else ""
            b_col1.write(f"• Missed on **{b_date_str}**{time_disp}")
            if b_col2.button("Undo", key=f"att_undo_{b['id']}"):
                cursor.execute("DELETE FROM absences WHERE id = %s AND username = %s", (b['id'], active_user))
                conn.commit()
                st.rerun()
    else:
        st.success("No bunks recorded for this course! 100% attendance maintained.")

st.divider()
st.subheader("All Courses Overview")
overview_rows = []
for cid, s in stats.items():
    overview_rows.append({
        "Course Code": cid,
        "Course Name": s["name"],
        "Held": s["held"],
        "Attended": s["attended"],
        "Bunks": s["bunks"],
        "Attendance %": f"{s['pct']:.1f}%",
        "Target %": f"{s['target']:.0f}%",
        "Status": f"Safe to skip {s['safe_to_skip']}" if s["pct"] >= s["target"] else f"Must attend {s['must_attend']}"
    })
st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

cursor.close()
conn.close()
