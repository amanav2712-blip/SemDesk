import mysql.connector
import streamlit as st

DB_USER = "avnadmin"
DB_PASS = st.secrets["DB_PASS"]
DB_HOST = st.secrets["DB_HOST"]
DB_PORT = 21199
DB_NAME = "defaultdb"

def get_connection():
    return mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
    )

def init_db():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        username VARCHAR(50) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        password VARCHAR(255) NOT NULL
    );
    """
    cursor.execute(create_users_table)

    create_course_table = '''
    CREATE TABLE IF NOT EXISTS courses (
        username VARCHAR(50),
        id VARCHAR(10),
        name VARCHAR(100) UNIQUE NOT NULL,
        target_attendance FLOAT DEFAULT 80.0,
        PRIMARY KEY (username, id)
    );
    '''
    cursor.execute(create_course_table)

    create_tasks_table = '''
    CREATE TABLE IF NOT EXISTS tasks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50),
        course_id VARCHAR(10),
        title VARCHAR(200) NOT NULL,
        deadline DATE NOT NULL,
        importance INT DEFAULT 3,
        est_hours FLOAT DEFAULT 1.0,
        status VARCHAR(20) DEFAULT 'Pending',
        FOREIGN KEY (username, course_id) REFERENCES courses(username, id) ON DELETE CASCADE
    );
    '''
    cursor.execute(create_tasks_table)

    create_attendance_table = """
    CREATE TABLE IF NOT EXISTS attendance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50),
        course_id VARCHAR(10),
        class_date DATE NOT NULL,
        status VARCHAR(10) NOT NULL,
        FOREIGN KEY (username, course_id) REFERENCES courses(username, id) ON DELETE CASCADE
    );
    """
    cursor.execute(create_attendance_table)

    create_grades_table = """
    CREATE TABLE IF NOT EXISTS grades (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50),
        course_id VARCHAR(10) UNIQUE,
        my_marks FLOAT NOT NULL,
        class_avg FLOAT NOT NULL,
        std_dev FLOAT NOT NULL,
        FOREIGN KEY (username, course_id) REFERENCES courses(username, id) ON DELETE CASCADE
    );
    """
    cursor.execute(create_grades_table)

    conn.commit()
    cursor.close()
    conn.close()
