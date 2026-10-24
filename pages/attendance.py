import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page to view this module.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="Attendance", layout="wide")
st.title("Smart Attendance Tracker")

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT id, target_attendance FROM courses WHERE username = %s", (active_user,))
courses_data = cursor.fetchall()

if not courses_data:
    st.warning("Add courses in the Timetable tab first.")
else:
    course_dict = {str(row['id']): float(row['target_attendance']) for row in courses_data} # type: ignore
    selected_course = st.selectbox("Select Course to Manage", list(course_dict.keys()))
    target_pct = course_dict[selected_course]

    with st.expander("Log Today's Class", expanded=True):
        with st.form("attendance_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                class_date = st.date_input("Date", value=date.today())
            with col2:
                status = st.selectbox("Status", ["Present", "Absent", "Cancelled"])

            if st.form_submit_button("Log Attendance"):
                if status != "Cancelled":
                    sql = "INSERT INTO attendance (username, course_id, class_date, status) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (active_user, selected_course, class_date, str(status)))
                    conn.commit()
                    st.success("Logged successfully!")
                    st.rerun()

    cursor.execute("SELECT class_date, status FROM attendance WHERE course_id = %s AND username = %s ORDER BY class_date ASC", (selected_course, active_user))
    records = cursor.fetchall()

    if records:
        df = pd.DataFrame(records)

        total_classes = len(df)
        present_classes = len(df[df['status'] == 'Present'])
        current_pct = (present_classes / total_classes) * 100

        classes_to_target = (present_classes / (target_pct / 100)) - total_classes

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Classes", total_classes)
        c2.metric("Classes Attended", present_classes)

        pct_color = "normal" if current_pct >= target_pct else "inverse"
        c3.metric("Current Attendance", f"{current_pct:.1f}%", delta=f"{current_pct - target_pct:.1f}% from Target", delta_color=pct_color)

        if classes_to_target >= 1:
            c4.metric("Safe to Skip", f"{int(classes_to_target)} classes", delta="You have a buffer", delta_color="normal")
        elif classes_to_target < 0:
            needed = abs(int(classes_to_target)) + 1
            c4.metric("Must Attend Next", f"{needed} classes", delta="Danger Zone", delta_color="inverse")
        else:
            c4.metric("Safe to Skip", "0 classes", delta="On the edge", delta_color="off")

        st.subheader("Attendance Trend")

        df['is_present'] = df['status'].apply(lambda x: 1 if x == 'Present' else 0)
        df['cumulative_present'] = df['is_present'].cumsum()
        df['cumulative_total'] = range(1, len(df) + 1)
        df['cumulative_pct'] = (df['cumulative_present'] / df['cumulative_total']) * 100

        fig = px.line(df, x='class_date', y='cumulative_pct', markers=True,
                      labels={'class_date': 'Date', 'cumulative_pct': 'Attendance %'})

        fig.add_hline(y=target_pct, line_dash="dash", line_color="red",
                      annotation_text=f"Cutoff ({target_pct}%)", annotation_position="bottom right")

        fig.update_layout(yaxis_range=[0, 105])
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No attendance logged for this course yet.")

cursor.close()
conn.close()
