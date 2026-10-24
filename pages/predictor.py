import streamlit as st
import numpy as np
import scipy.stats as stats
import plotly.graph_objects as go
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import database

if not st.session_state.get("authentication_status"):
    st.warning("Please log in on the Home page to view this module.")
    st.stop()

active_user = st.session_state["username"]

st.set_page_config(page_title="GPA Predictor", layout="wide")
st.title("Relative Grading Predictor")
st.markdown("Enter your midsem stats to calculate your exact class percentile and predicted grade using SciPy.")

conn = database.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT id FROM courses WHERE username = %s", (active_user,))
courses = [row['id'] for row in cursor.fetchall()] # type: ignore

if not courses:
    st.warning("Add courses in the Timetable tab first.")
else:
    selected_course = st.selectbox("Select Course", courses)

    cursor.execute("SELECT my_marks, class_avg, std_dev FROM grades WHERE course_id = %s AND username = %s", (str(selected_course), active_user))
    saved_data = cursor.fetchone()

    default_marks = float(saved_data['my_marks']) if saved_data else 75.0  # type: ignore
    default_avg = float(saved_data['class_avg']) if saved_data else 65.0  # type: ignore
    default_std = float(saved_data['std_dev']) if saved_data else 10.0  # type: ignore

    with st.form("grade_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            my_marks = st.number_input("Your Marks", value=default_marks, step=1.0)
        with col2:
            class_avg = st.number_input("Class Average (Mean)", value=default_avg, step=1.0)
        with col3:
            std_dev = st.number_input("Standard Deviation", value=default_std, min_value=0.1, step=1.0)

        submitted = st.form_submit_button("Run Prediction Algorithm")

        if submitted:
            sql = """
            INSERT INTO grades (username, course_id, my_marks, class_avg, std_dev)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE my_marks=VALUES(my_marks), class_avg=VALUES(class_avg), std_dev=VALUES(std_dev)
            """
            cursor.execute(sql, (active_user, str(selected_course), my_marks, class_avg, std_dev))
            conn.commit()

    # 3. SciPy Math (Truncated Normal Distribution)
        if submitted or saved_data:
            st.divider()

            # 1. Define the absolute boundaries of the exam
            lower_bound = 0.0
            upper_bound = 100.0

            # 2. Calculate the "clip" points for SciPy
            a = (lower_bound - class_avg) / std_dev
            b = (upper_bound - class_avg) / std_dev

            # 3. Calculate exact percentile using Truncated CDF
            percentile = stats.truncnorm.cdf(my_marks, a, b, loc=class_avg, scale=std_dev) * 100

            # We still calculate standard Z-score for the Letter Grade logic
            z_score = (my_marks - class_avg) / std_dev

            if z_score >= 1.5:
                pred_grade, color = "S / A+", "green"
            elif z_score >= 0.5:
                pred_grade, color = "A", "lightgreen"
            elif z_score >= -0.5:
                pred_grade, color = "B", "orange"
            elif z_score >= -1.5:
                pred_grade, color = "C", "red"
            else:
                pred_grade, color = "F", "red"

            # 4. Results Dashboard
            c1, c2, c3 = st.columns(3)
            c1.metric("Your Z-Score", f"{z_score:.2f}")
            c2.metric("Class Percentile", f"Top {100 - percentile:.1f}%")
            c3.metric("Predicted Grade", pred_grade)

            # 5. Plotly Truncated Bell Curve Visualization
            st.subheader("Your Position on the Realistic Grading Curve")

            # Generate X values strictly between 0 and 100
            x = np.linspace(0, 100, 200)

            # Generate Y values using the Truncated Probability Density Function (PDF)
            y = stats.truncnorm.pdf(x, a, b, loc=class_avg, scale=std_dev)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Class Distribution', fill='tozeroy', fillcolor='rgba(100, 150, 250, 0.2)'))
            fig.add_vline(x=my_marks, line_dash="dash", line_color=color, annotation_text=f"You ({my_marks})", annotation_position="top right")
            fig.add_vline(x=class_avg, line_width=1, line_color="gray", annotation_text="Average", annotation_position="bottom right")

            fig.update_layout(xaxis_title="Marks", yaxis_title="Probability Density", showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)

    cursor.close()
    conn.close()
