import streamlit as st
import pandas as pd
import datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page first.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="Schedule & Courses", layout="wide")
st.title("Course & Schedule Management")

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

tab_courses, tab_timetable, tab_calendar = st.tabs(["Courses", "Weekly Timetable", "Academic Calendar"])

# ----------------- TAB 1: COURSES -----------------
with tab_courses:
    with st.expander("Add New Course", expanded=False):
        with st.form("add_course_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                course_id = st.text_input("Course Code").strip().upper()
                course_name = st.text_input("Course Name")
            with col2:
                course_credits = st.number_input("Credits", min_value=0.0, max_value=20.0, value=0.0, step=1.0)
            with col3:
                target_att = st.number_input("Target Attendance (%)", min_value=1.0, max_value=100.0, value=80.0, step=1.0)

            if st.form_submit_button("Save Course"):
                if course_id and course_name:
                    try:
                        cursor.execute(
                            "INSERT INTO courses (username, id, name, credits, target_attendance) VALUES (%s, %s, %s, %s, %s)",
                            (active_user, course_id, course_name, course_credits, target_att)
                        )
                        conn.commit()
                        st.success(f"Added {course_id}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not add course: {e}")
                else:
                    st.warning("Please enter both course code and name.")

    cursor.execute("SELECT id as 'Code', name as 'Course Name', credits as 'Credits', target_attendance as 'Target %' FROM courses WHERE username = %s ORDER BY id", (active_user,))
    courses_list = cursor.fetchall()

    if courses_list:
        st.subheader("Your Enrolled Courses")
        st.caption("You can directly edit **Credits** and **Target %** in the table below, then click **Save Course Updates**.")

        courses_df = pd.DataFrame(courses_list)

        edited_courses_df = st.data_editor(
            courses_df,
            column_config={
                "Code": st.column_config.TextColumn("Code", disabled=True),
                "Course Name": st.column_config.TextColumn("Course Name", disabled=True),
                "Credits": st.column_config.NumberColumn("Credits", min_value=0.0, max_value=20.0, step=1.0),
                "Target %": st.column_config.NumberColumn("Target %", min_value=1.0, max_value=100.0, step=1.0),
            },
            hide_index=True,
            use_container_width=True,
            key="courses_editor"
        )

        col_save, col_del = st.columns([1, 1])
        with col_save:
            if st.button("Save Course Updates", type="primary"):
                for _, row in edited_courses_df.iterrows():
                    cursor.execute(
                        "UPDATE courses SET credits = %s, target_attendance = %s WHERE username = %s AND id = %s",
                        (float(row["Credits"]), float(row["Target %"]), active_user, str(row["Code"]))
                    )
                conn.commit()
                st.success("Updated course credits and targets!")
                st.rerun()

        with col_del:
            del_course = st.selectbox("Select course to delete", [c["Code"] for c in courses_list], key="del_c")
            if st.button("Delete Course"):
                cursor.execute("DELETE FROM courses WHERE username = %s AND id = %s", (active_user, del_course))
                cursor.execute("DELETE FROM timetable WHERE username = %s AND course_id = %s", (active_user, del_course))
                cursor.execute("DELETE FROM absences WHERE username = %s AND course_id = %s", (active_user, del_course))
                conn.commit()
                st.success(f"Deleted {del_course}")
                st.rerun()
    else:
        st.info("No courses added yet.")

# ----------------- TAB 2: WEEKLY TIMETABLE -----------------
with tab_timetable:
    cursor.execute("SELECT id, name FROM courses WHERE username = %s ORDER BY id", (active_user,))
    user_courses = cursor.fetchall()

    if not user_courses:
        st.info("Add courses in the 'Courses' tab before creating a timetable.")
    else:
        st.subheader("Weekly Timetable Grid")
        st.caption("Double-click or tap any hour cell to assign or clear a class from the dropdown. Click 'Save Timetable' when done.")

        course_ids = [c["id"] for c in user_courses]
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        hour_labels = [f"{h:02d}:00 - {h+1:02d}:00" for h in range(8, 18)]

        # Build initial grid structure
        grid_data = {"Time": hour_labels}
        for d in days:
            grid_data[d] = [""] * len(hour_labels)

        # Pre-fill with existing timetable from database
        cursor.execute("SELECT course_id, day_of_week, start_time FROM timetable WHERE username = %s", (active_user,))
        existing_slots = cursor.fetchall()
        for slot in existing_slots:
            d = slot["day_of_week"]
            st_val = slot["start_time"]
            st_h = st_val.seconds // 3600 if hasattr(st_val, "seconds") else getattr(st_val, "hour", None)
            if st_h is not None and 8 <= st_h < 18 and d in grid_data:
                row_idx = st_h - 8
                grid_data[d][row_idx] = slot["course_id"]

        grid_df = pd.DataFrame(grid_data)

        # Configure columns with selectboxes
        col_config = {
            "Time": st.column_config.TextColumn("Time", disabled=True),
        }
        for d in days:
            col_config[d] = st.column_config.SelectboxColumn(
                d,
                help=f"Class on {d}",
                options=[""] + course_ids,
                required=False,
            )

        edited_df = st.data_editor(
            grid_df,
            column_config=col_config,
            hide_index=True,
            use_container_width=True,
            disabled=["Time"],
            key="timetable_grid_editor"
        )

        col_save1, col_save2 = st.columns([1, 3])
        with col_save1:
            if st.button("Save Weekly Timetable", type="primary"):
                cursor.execute("DELETE FROM timetable WHERE username = %s", (active_user,))
                insert_count = 0
                for idx, row in edited_df.iterrows():
                    h = 8 + idx
                    st_time = datetime.time(h, 0)
                    et_time = datetime.time(h + 1, 0)
                    for d in days:
                        cid = row.get(d)
                        if cid and str(cid).strip() and str(cid).strip() in course_ids:
                            cursor.execute(
                                "INSERT INTO timetable (username, course_id, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s, %s)",
                                (active_user, str(cid).strip(), d, st_time, et_time)
                            )
                            insert_count += 1
                conn.commit()
                st.success(f"Saved {insert_count} timetable classes successfully!")
                st.rerun()

        with col_save2:
            if st.button("Clear All Timetable Slots"):
                cursor.execute("DELETE FROM timetable WHERE username = %s", (active_user,))
                conn.commit()
                st.warning("Cleared all timetable slots.")
                st.rerun()

# ----------------- TAB 3: ACADEMIC CALENDAR -----------------
with tab_calendar:
    st.subheader("Semester Timeline & Examination Dates")
    st.caption("These dates allow the attendance engine to calculate actual teaching days and pause classes during exams and holidays.")

    cursor.execute("SELECT * FROM academic_settings WHERE username = %s", (active_user,))
    curr_settings = cursor.fetchone() or {}

    today = datetime.date.today()
    def_sem_s = curr_settings.get("sem_start") or today
    def_sem_e = curr_settings.get("sem_end") or (today + datetime.timedelta(days=120))
    def_lwd = curr_settings.get("last_working_day") or (today + datetime.timedelta(days=90))
    def_mid_s = curr_settings.get("midsem_start") or (today + datetime.timedelta(days=45))
    def_mid_e = curr_settings.get("midsem_end") or (today + datetime.timedelta(days=52))
    def_end_s = curr_settings.get("endsem_start") or (today + datetime.timedelta(days=105))
    def_end_e = curr_settings.get("endsem_end") or (today + datetime.timedelta(days=115))

    with st.form("settings_form"):
        c1, c2 = st.columns(2)
        with c1:
            sem_s = st.date_input("Semester Start Date", value=def_sem_s, format="DD/MM/YYYY")
            lwd = st.date_input("Last Working Day (Classes End)", value=def_lwd, format="DD/MM/YYYY", help="The class timetable schedule is no longer valid after this date.")
            mid_s = st.date_input("Midsem Exams Start Date", value=def_mid_s, format="DD/MM/YYYY")
            end_s = st.date_input("Endsem Exams Start Date", value=def_end_s, format="DD/MM/YYYY")
        with c2:
            sem_e = st.date_input("Semester End Date", value=def_sem_e, format="DD/MM/YYYY")
            st.caption("ℹ️ Timetable classes will automatically pause and not be counted after the Last Working Day.")
            mid_e = st.date_input("Midsem Exams End Date", value=def_mid_e, format="DD/MM/YYYY")
            end_e = st.date_input("Endsem Exams End Date", value=def_end_e, format="DD/MM/YYYY")

        if st.form_submit_button("Save Semester Dates"):
            cursor.execute("""
                INSERT INTO academic_settings (username, sem_start, sem_end, last_working_day, midsem_start, midsem_end, endsem_start, endsem_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    sem_start=VALUES(sem_start),
                    sem_end=VALUES(sem_end),
                    last_working_day=VALUES(last_working_day),
                    midsem_start=VALUES(midsem_start),
                    midsem_end=VALUES(midsem_end),
                    endsem_start=VALUES(endsem_start),
                    endsem_end=VALUES(endsem_end)
            """, (active_user, sem_s, sem_e, lwd, mid_s, mid_e, end_s, end_e))
            conn.commit()
            st.success("Semester dates saved!")
            st.rerun()

    st.divider()
    st.subheader("Holidays")

    col_h1, col_h2 = st.columns([1, 1])
    with col_h1:
        with st.form("add_holiday_form", clear_on_submit=True):
            h_name = st.text_input("Holiday Name (e.g. Diwali)")
            h_date = st.date_input("Holiday Date", value=today, format="DD/MM/YYYY")
            if st.form_submit_button("Add Holiday"):
                if h_name:
                    cursor.execute(
                        "INSERT INTO academic_holidays (username, holiday_date, name) VALUES (%s, %s, %s)",
                        (active_user, h_date, h_name)
                    )
                    conn.commit()
                    st.success(f"Added holiday: {h_name}")
                    st.rerun()

    with col_h2:
        cursor.execute("SELECT id, holiday_date, name FROM academic_holidays WHERE username = %s ORDER BY holiday_date", (active_user,))
        holidays = cursor.fetchall()
        if holidays:
            h_df = pd.DataFrame(holidays)
            h_df["Date"] = pd.to_datetime(h_df["holiday_date"]).dt.strftime("%d/%m/%y")
            st.dataframe(h_df[["Date", "name"]].rename(columns={"name": "Holiday"}), use_container_width=True, hide_index=True)
            h_del_map = {f"{(h['holiday_date'].strftime('%d/%m/%y') if hasattr(h['holiday_date'], 'strftime') else h['holiday_date'])} - {h['name']}": h["id"] for h in holidays}
            del_h_label = st.selectbox("Select holiday to remove", list(h_del_map.keys()))
            if st.button("Delete Holiday"):
                cursor.execute("DELETE FROM academic_holidays WHERE id = %s AND username = %s", (h_del_map[del_h_label], active_user))
                conn.commit()
                st.success("Removed holiday!")
                st.rerun()
        else:
            st.info("No holidays added yet.")

cursor.close()
conn.close()
