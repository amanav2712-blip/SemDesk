import streamlit as st
import pandas as pd
from datetime import date
import datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page to view this module.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="Task Manager", layout="wide")
st.title("Auto Prioritized Task Manager")
st.markdown("Add assignments and let the algorithm rank what you should work on first.")

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT id FROM courses WHERE username = %s", (active_user,))
available_courses = [row['id'] for row in cursor.fetchall()] # type: ignore

with st.expander("➕ Add a New Task", expanded=True):
    if not available_courses:
        st.warning("You need to add courses in the Timetable tab before adding tasks!")
    else:
        with st.form("add_task_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                task_course = st.selectbox("Course", available_courses)
                task_title = st.text_input("Task Description (e.g., Assignment 1)")
            with col2:
                task_deadline = st.date_input("Deadline Date", min_value=date.today(), format="DD/MM/YYYY")
                task_deadline_time = st.time_input("Deadline Time", value=datetime.time(23, 59))
            with col3:
                task_importance = st.slider("Importance (1-Low, 5-High)", 1, 5, 3)
            with col4:
                task_hours = st.number_input("Estimated Hours", min_value=0.5, step=0.5, value=2.0)

            if st.form_submit_button("Save Task"):
                if task_title:
                    sql = """INSERT INTO tasks (username, course_id, title, deadline, deadline_time, importance, est_hours)
                             VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql, (active_user, str(task_course), task_title, task_deadline, task_deadline_time, task_importance, task_hours))
                    conn.commit()
                    st.success("Task added!")
                    st.rerun()
                else:
                    st.error("Please enter a task description.")

st.subheader("Your Priority Queue")
cursor.execute("SELECT id, course_id, title, deadline, deadline_time, importance, est_hours, status FROM tasks WHERE status = 'Pending' AND username = %s", (active_user,))
tasks = cursor.fetchall()

if tasks:
    df = pd.DataFrame(tasks)

    import datetime as dt_module

    def get_days_left(row):
        d = row['deadline']
        t = row.get('deadline_time')
        if not t:
            t_obj = dt_module.time(23, 59)
        elif hasattr(t, 'seconds'):
            t_obj = dt_module.time(t.seconds // 3600, (t.seconds % 3600) // 60)
        else:
            t_obj = t
        comb = dt_module.datetime.combine(d, t_obj)
        diff_hours = (comb - dt_module.datetime.now()).total_seconds() / 3600.0
        return max(diff_hours / 24.0, 0.05)

    df['days_left'] = df.apply(get_days_left, axis=1)
    df['Priority_Score'] = (df['importance'] * 10) + (df['est_hours'] * 5) / df['days_left']

    df = df.sort_values(by='Priority_Score', ascending=False)

    display_df = df[['course_id', 'title', 'est_hours', 'importance', 'Priority_Score']].copy()
    display_df['Priority_Score'] = display_df['Priority_Score'].round(1)

    def format_deadline_display(row):
        d = row['deadline']
        t = row.get('deadline_time')
        d_str = d.strftime('%d/%m/%y') if hasattr(d, 'strftime') else str(d)
        if t:
            t_str = f"{t.seconds // 3600:02d}:{(t.seconds % 3600) // 60:02d}" if hasattr(t, 'seconds') else t.strftime('%H:%M')
            return f"{d_str} {t_str}"
        return d_str

    display_df['Deadline'] = df.apply(format_deadline_display, axis=1)
    display_df = display_df[['course_id', 'title', 'Deadline', 'est_hours', 'importance', 'Priority_Score']]
    display_df.columns = ['Course', 'Task', 'Deadline', 'Est. Hours', 'Importance', 'Priority Score']

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("### 🏁 Mark Task Complete")
    colA, colB = st.columns([3, 1])
    with colA:
        task_options = {}
        for row in tasks:
            d_fmt = format_deadline_display(row)
            task_options[f"[{row['course_id']}] {row['title']} (Due: {d_fmt})"] = row['id']
        task_to_complete = st.selectbox("Select a task to complete:", options=list(task_options.keys()))
    with colB:
        st.write("")
        st.write("")
        if st.button("Mark Complete"):
            task_id = task_options[task_to_complete]
            cursor.execute("UPDATE tasks SET status = 'Completed' WHERE id = %s AND username = %s", (str(task_id), active_user))
            conn.commit()
            st.success("Task completed! Refreshing...")
            st.rerun()
else:
    st.info("No pending tasks. You're all caught up!")

cursor.close()
conn.close()
