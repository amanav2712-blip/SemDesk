import streamlit as st
import numpy as np
import scipy.stats as stats
import plotly.graph_objects as go
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page to view this module.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="GPA & Grade Predictor", layout="wide")
st.title("GPA & Relative Grade Predictor")
st.markdown("Enter exam statistics for each course to calculate percentiles, predicted letter grades, and projected semester SGPA & overall CGPA.")

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

# Grade mapping helper: A, A-, B, B-, C, C-, D, F (10-point scale)
def get_letter_grade(z):
    if z >= 1.5:
        return "A", 10, "green"
    elif z >= 1.0:
        return "A-", 9, "lightgreen"
    elif z >= 0.5:
        return "B", 8, "#3B82F6"
    elif z >= 0.0:
        return "B-", 7, "#0284C7"
    elif z >= -0.5:
        return "C", 6, "#D97706"
    elif z >= -1.0:
        return "C-", 5, "#EA580C"
    elif z >= -1.5:
        return "D", 4, "#E11D48"
    else:
        return "F", 0, "#DC2626"

cursor.execute("SELECT id, name, credits FROM courses WHERE username = %s ORDER BY id", (active_user,))
all_courses = cursor.fetchall()

if not all_courses:
    st.info("Add courses in the **Timetable** tab first.")
    cursor.close()
    conn.close()
    st.stop()

# ----------------- SECTION 1: SEMESTER PROFILE & SGPA / CGPA FORECAST -----------------
st.subheader("Semester Profile & GPA Forecast")

cursor.execute("SELECT current_sem, prev_cgpa FROM academic_settings WHERE username = %s", (active_user,))
sem_data = cursor.fetchone() or {}
curr_sem = int(sem_data.get("current_sem") or 1)
curr_prev_cgpa = float(sem_data.get("prev_cgpa") or 0.0)

with st.expander("Confirm Semester & Prior CGPA", expanded=(curr_prev_cgpa == 0.0 and curr_sem > 1)):
    with st.form("sem_profile_form"):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            input_sem = st.number_input("Current Semester", min_value=1, max_value=8, value=curr_sem, step=1)
        with col_s2:
            prev_label = "Previous Sem SGPA" if input_sem == 2 else "Cumulative CGPA prior to this semester"
            input_prev_cgpa = st.number_input(prev_label, min_value=0.0, max_value=10.0, value=curr_prev_cgpa, step=0.05, disabled=(input_sem == 1))

        if st.form_submit_button("Save Semester Profile"):
            cursor.execute("""
                INSERT INTO academic_settings (username, current_sem, prev_cgpa)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE current_sem=VALUES(current_sem), prev_cgpa=VALUES(prev_cgpa)
            """, (active_user, input_sem, input_prev_cgpa if input_sem > 1 else 0.0))
            conn.commit()
            st.success("Semester profile saved!")
            st.rerun()

# Check all subjects' saved details
cursor.execute("SELECT course_id, my_marks, class_avg, std_dev, max_marks FROM grades WHERE username = %s", (active_user,))
saved_grades_list = cursor.fetchall()
saved_grades_map = {g["course_id"]: g for g in saved_grades_list}

all_saved_records = []
missing_courses = []

for c in all_courses:
    cid = c["id"]
    cr = float(c.get("credits") or 0.0)
    if cid in saved_grades_map:
        g = saved_grades_map[cid]
        mm = float(g["my_marks"])
        ca = float(g["class_avg"])
        sd = float(g["std_dev"])
        mx = float(g.get("max_marks") or 100.0)
        z = (mm - ca) / sd if sd > 0 else 0.0
        grd, pts, clr = get_letter_grade(z)
        all_saved_records.append({
            "Course": cid,
            "Name": c["name"],
            "Credits": cr,
            "Score": f"{mm:g} / {mx:g}",
            "Class Mean": f"{ca:g}",
            "Z-Score": f"{z:.2f}",
            "Predicted Grade": grd,
            "Grade Points": pts,
            "Weighted Points": pts * cr
        })
    else:
        missing_courses.append(cid)

all_saved = len(missing_courses) == 0 and len(all_courses) > 0

if all_saved:
    total_credits = sum(r["Credits"] for r in all_saved_records)
    total_weighted_points = sum(r["Weighted Points"] for r in all_saved_records)

    # GPA formula: sum(grade * credit) / sum(credit)
    if total_credits > 0:
        pred_sgpa = total_weighted_points / total_credits
        sgpa_desc = f"Weighted across {total_credits:g} credits"
    else:
        # Fallback if credits are 0
        pts_list = [r["Grade Points"] for r in all_saved_records]
        pred_sgpa = sum(pts_list) / len(pts_list)
        sgpa_desc = "Unweighted (set credits in Timetable)"

    if curr_sem == 1:
        pred_cgpa = pred_sgpa
        cgpa_delta = None
    else:
        pred_cgpa = ((curr_prev_cgpa * (curr_sem - 1)) + pred_sgpa) / curr_sem
        cgpa_delta = f"{pred_cgpa - curr_prev_cgpa:+.2f} from prior CGPA"

    col_g1, col_g2, col_g3, col_g4 = st.columns(4)
    col_g1.metric("Current Semester", f"Semester {curr_sem}")
    col_g2.metric("Total Credits", f"{total_credits:g}")
    col_g3.metric("Projected SGPA", f"{pred_sgpa:.2f}", sgpa_desc)
    col_g4.metric("Projected CGPA", f"{pred_cgpa:.2f}", delta=cgpa_delta)

    st.write("**Course Grades Summary**")
    display_records = [
        {
            "Course": r["Course"],
            "Name": r["Name"],
            "Credits": f"{r['Credits']:g}",
            "Score": r["Score"],
            "Class Mean": r["Class Mean"],
            "Z-Score": r["Z-Score"],
            "Predicted Grade": r["Predicted Grade"],
            "Grade Points": r["Grade Points"]
        } for r in all_saved_records
    ]
    st.dataframe(pd.DataFrame(display_records), use_container_width=True, hide_index=True)
else:
    st.info(f"Exam statistics saved for **{len(all_saved_records)} / {len(all_courses)}** courses. Enter details for the remaining courses ({', '.join(missing_courses)}) below to calculate your projected SGPA and CGPA.")

st.divider()

st.subheader("Course Exam Statistics & Curve Visualization")

course_ids = [c["id"] for c in all_courses]
selected_course = st.selectbox("Select Course to Enter/View Stats", course_ids)

saved_data = saved_grades_map.get(selected_course)

default_max = float(saved_data['max_marks']) if saved_data and saved_data.get('max_marks') else 100.0
default_marks = float(saved_data['my_marks']) if saved_data else min(75.0, default_max * 0.75)
default_avg = float(saved_data['class_avg']) if saved_data else min(65.0, default_max * 0.65)
default_std = float(saved_data['std_dev']) if saved_data else max(1.0, default_max * 0.1)

with st.form("grade_form"):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        max_marks = st.number_input("Max Marks (Total)", min_value=1.0, value=default_max, step=5.0)
    with col2:
        my_marks = st.number_input("Your Marks", min_value=0.0, max_value=float(max_marks), value=min(default_marks, float(max_marks)), step=1.0)
    with col3:
        class_avg = st.number_input("Class Average (Mean)", min_value=0.0, max_value=float(max_marks), value=min(default_avg, float(max_marks)), step=1.0)
    with col4:
        std_dev = st.number_input("Standard Deviation (σ)", value=default_std, min_value=0.1, step=0.5)

    submitted = st.form_submit_button("Save & Run Prediction")

    if submitted:
        sql = """
        INSERT INTO grades (username, course_id, my_marks, class_avg, std_dev, max_marks)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE my_marks=VALUES(my_marks), class_avg=VALUES(class_avg), std_dev=VALUES(std_dev), max_marks=VALUES(max_marks)
        """
        cursor.execute(sql, (active_user, str(selected_course), my_marks, class_avg, std_dev, max_marks))
        conn.commit()
        st.success(f"Saved statistics for {selected_course}!")
        st.rerun()

if saved_data:
    mm = float(saved_data["my_marks"])
    ca = float(saved_data["class_avg"])
    sd = float(saved_data["std_dev"])
    mx = float(saved_data.get("max_marks") or 100.0)

    lower_bound = 0.0
    upper_bound = mx

    a = (lower_bound - ca) / sd
    b = (upper_bound - ca) / sd

    percentile = stats.truncnorm.cdf(mm, a, b, loc=ca, scale=sd) * 100
    z_score = (mm - ca) / sd

    pred_grade, pts, color = get_letter_grade(z_score)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Your Z-Score", f"{z_score:.2f}")
    c2.metric("Score Percentage", f"{(mm / mx * 100):.1f}%")
    c3.metric("Class Percentile", f"Top {max(0.1, 100 - percentile):.1f}%")
    c4.metric("Predicted Grade", f"{pred_grade} ({pts} pts)")

    st.subheader(f"{selected_course} Relative Grading Curve")

    x = np.linspace(0, mx, 200)
    y = stats.truncnorm.pdf(x, a, b, loc=ca, scale=sd)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Class Distribution', fill='tozeroy', fillcolor='rgba(59, 130, 246, 0.2)'))
    fig.add_vline(x=mm, line_dash="dash", line_color=color, annotation_text=f"You ({mm:g}/{mx:g})", annotation_position="top right")
    fig.add_vline(x=ca, line_width=1, line_color="gray", annotation_text=f"Average ({ca:g})", annotation_position="bottom right")

    fig.update_layout(xaxis_title=f"Marks (out of {mx:g})", yaxis_title="Probability Density", showlegend=False, height=380)
    st.plotly_chart(fig, use_container_width=True)

cursor.close()
conn.close()
