import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page to view this module.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="Timetable", layout="wide")
st.title("Course Management")
st.markdown("Add and manage your current semester courses.")

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

with st.expander("Add a New Course", expanded=True):
    with st.form("add_course_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            course_id = st.text_input("Course Code")
            course_name = st.text_input("Course Name")
        with col2:
            target_attendance = st.number_input("Target Attendance (%)", min_value=0.0, max_value=100.0, value=80.0)

        submitted = st.form_submit_button("Save Course")

        if submitted:
            if course_id and course_name:
                try:
                    sql = "INSERT INTO courses (username, id, name, target_attendance) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (active_user, course_id.upper(), course_name, target_attendance))
                    conn.commit()
                    st.success(f"Successfully added {course_id.upper()}!")
                except Exception as e:
                    st.error(f"Error adding course (Does that ID already exist?): {e}")
            else:
                st.warning("Please fill in both the Course Code and Name.")

st.subheader("Current Semester Courses")
cursor.execute("SELECT id as 'Course Code', name as 'Course Name', target_attendance as 'Target Attendance (%)' FROM courses WHERE username = %s", (active_user,))
courses = cursor.fetchall()

if courses:
    st.dataframe(courses, use_container_width=True, hide_index=True)
else:
    st.info("No courses added yet. Use the form above to add your first class!")

cursor.close()
conn.close()
