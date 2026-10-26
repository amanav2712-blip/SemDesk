import mysql.connector
import streamlit as st
import datetime

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
        database=DB_NAME,
        autocommit=True
    )

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username VARCHAR(50) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        password VARCHAR(255) NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        username VARCHAR(50),
        id VARCHAR(10),
        name VARCHAR(100) NOT NULL,
        credits FLOAT DEFAULT 0.0,
        target_attendance FLOAT DEFAULT 80.0,
        PRIMARY KEY (username, id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS timetable (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL,
        course_id VARCHAR(10) NOT NULL,
        day_of_week VARCHAR(15) NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS absences (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL,
        course_id VARCHAR(10) NOT NULL,
        absence_date DATE NOT NULL,
        start_time TIME
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS academic_settings (
        username VARCHAR(50) PRIMARY KEY,
        sem_start DATE,
        sem_end DATE,
        last_working_day DATE,
        midsem_start DATE,
        midsem_end DATE,
        endsem_start DATE,
        endsem_end DATE,
        current_sem INT DEFAULT 1,
        prev_cgpa FLOAT DEFAULT 0.0
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS academic_holidays (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL,
        holiday_date DATE NOT NULL,
        name VARCHAR(100) NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50),
        course_id VARCHAR(10),
        title VARCHAR(200) NOT NULL,
        deadline DATE NOT NULL,
        deadline_time TIME DEFAULT '23:59:00',
        importance INT DEFAULT 3,
        est_hours FLOAT DEFAULT 1.0,
        status VARCHAR(20) DEFAULT 'Pending'
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL,
        title VARCHAR(200) NOT NULL,
        event_date DATE NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        category VARCHAR(50) DEFAULT 'Appointment'
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grades (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50),
        course_id VARCHAR(10) UNIQUE,
        my_marks FLOAT NOT NULL,
        class_avg FLOAT NOT NULL,
        std_dev FLOAT NOT NULL,
        max_marks FLOAT DEFAULT 100.0
    )""")

    conn.commit()
    cursor.close()
    conn.close()

def format_time_str(t):
    if t is None:
        return ""
    if hasattr(t, "seconds"):
        return f"{t.seconds // 3600:02d}:{(t.seconds % 3600) // 60:02d}"
    if hasattr(t, "hour"):
        return f"{t.hour:02d}:{t.minute:02d}"
    parts = str(t).split(":")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

def normalize_time(t):
    if t is None:
        return None
    if hasattr(t, "seconds"):
        return t.seconds
    if hasattr(t, "hour"):
        return t.hour * 3600 + t.minute * 60 + t.second
    parts = str(t).split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) > 2 else 0)

def get_attendance_data(username):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, name, target_attendance FROM courses WHERE username = %s", (username,))
    courses = {c['id']: c for c in cursor.fetchall()}

    cursor.execute("SELECT * FROM academic_settings WHERE username = %s", (username,))
    settings = cursor.fetchone() or {}

    cursor.execute("SELECT id, holiday_date, name FROM academic_holidays WHERE username = %s ORDER BY holiday_date", (username,))
    holidays_raw = cursor.fetchall()
    holiday_dates = {h['holiday_date']: h['name'] for h in holidays_raw}

    cursor.execute("SELECT id, course_id, day_of_week, start_time, end_time FROM timetable WHERE username = %s ORDER BY start_time", (username,))
    slots = cursor.fetchall()

    cursor.execute("SELECT id, course_id, absence_date, start_time FROM absences WHERE username = %s ORDER BY absence_date DESC", (username,))
    absences_raw = cursor.fetchall()
    bunk_slots = {(a['course_id'], a['absence_date'], normalize_time(a['start_time'])) for a in absences_raw if a['start_time'] is not None}
    bunk_dates_legacy = {(a['course_id'], a['absence_date']) for a in absences_raw if a['start_time'] is None}
    matched_legacy_bunks = set()

    cursor.execute("SELECT id, course_id, title, deadline, deadline_time FROM tasks WHERE username = %s AND status = 'Pending'", (username,))
    tasks = cursor.fetchall()

    cursor.execute("SELECT id, title, event_date, start_time, end_time, category FROM scheduled_events WHERE username = %s ORDER BY event_date, start_time", (username,))
    scheduled_events_raw = cursor.fetchall()

    cursor.close()
    conn.close()

    today = datetime.date.today()
    sem_start = settings.get("sem_start")
    sem_end = settings.get("sem_end")
    lwd = settings.get("last_working_day")
    mid_s = settings.get("midsem_start")
    mid_e = settings.get("midsem_end")
    end_s = settings.get("endsem_start")
    end_e = settings.get("endsem_end")

    stats = {}
    for cid, c in courses.items():
        stats[cid] = {
            "name": c["name"],
            "target": float(c["target_attendance"]),
            "held": 0,
            "bunks": 0,
            "attended": 0,
            "pct": 100.0,
            "safe_to_skip": 0,
            "must_attend": 0,
        }

    calendar_events = []

    for h_date, h_name in holiday_dates.items():
        calendar_events.append({
            "title": f"Holiday: {h_name}",
            "start": str(h_date),
            "allDay": True,
            "color": "#10B981"
        })

    if lwd:
        calendar_events.append({
            "title": "Last Working Day (Classes End)",
            "start": str(lwd),
            "allDay": True,
            "color": "#D97706"
        })

    if mid_s and mid_e:
        calendar_events.append({
            "title": "Midsem Examinations",
            "start": str(mid_s),
            "end": str(mid_e + datetime.timedelta(days=1)),
            "allDay": True,
            "color": "#F59E0B"
        })
    if end_s and end_e:
        calendar_events.append({
            "title": "Endsem Examinations",
            "start": str(end_s),
            "end": str(end_e + datetime.timedelta(days=1)),
            "allDay": True,
            "color": "#8B5CF6"
        })

    for t in tasks:
        d_val = t['deadline']
        tm_val = t.get('deadline_time')
        if tm_val:
            tm_str = f"{tm_val.seconds // 3600:02d}:{(tm_val.seconds % 3600) // 60:02d}" if hasattr(tm_val, 'seconds') else str(tm_val)[:5]
            task_title = f"Due {tm_str}: {t['title']} ({t['course_id']})"
        else:
            task_title = f"Due: {t['title']} ({t['course_id']})"

        calendar_events.append({
            "title": task_title,
            "start": str(d_val),
            "allDay": True,
            "color": "#DC2626"
        })

    for ev in scheduled_events_raw:
        st_s = str(ev["start_time"])
        et_s = str(ev["end_time"])
        start_iso = f"{ev['event_date']}T{st_s if len(st_s) == 8 else '0' + st_s}"
        end_iso = f"{ev['event_date']}T{et_s if len(et_s) == 8 else '0' + et_s}"
        ev_color = "#8B5CF6" if ev.get("category") == "Appointment" else "#06B6D4"
        calendar_events.append({
            "title": f"[{ev.get('category', 'Event')}] {ev['title']}",
            "start": start_iso,
            "end": end_iso,
            "color": ev_color
        })

    teaching_end = lwd if lwd else sem_end

    if sem_start and teaching_end and slots:
        calc_end = min(today, teaching_end)
        view_end = min(teaching_end, today + datetime.timedelta(days=30))

        cur = sem_start
        while cur <= view_end:
            is_exam = (mid_s and mid_e and mid_s <= cur <= mid_e) or (end_s and end_e and end_s <= cur <= end_e)
            is_holiday = cur in holiday_dates

            if not is_exam and not is_holiday:
                weekday = cur.strftime("%A")
                for s in slots:
                    if s["day_of_week"] == weekday:
                        cid = s["course_id"]
                        if cid not in stats:
                            continue

                        st_str = str(s["start_time"])
                        et_str = str(s["end_time"])
                        start_iso = f"{cur}T{st_str if len(st_str) == 8 else '0' + st_str}"
                        end_iso = f"{cur}T{et_str if len(et_str) == 8 else '0' + et_str}"

                        st_sec = normalize_time(s["start_time"])
                        if (cid, cur, st_sec) in bunk_slots:
                            is_bunk = True
                        elif (cid, cur) in bunk_dates_legacy and (cid, cur) not in matched_legacy_bunks:
                            is_bunk = True
                            matched_legacy_bunks.add((cid, cur))
                        else:
                            is_bunk = False

                        if cur <= calc_end:
                            stats[cid]["held"] += 1
                            if is_bunk:
                                stats[cid]["bunks"] += 1
                                calendar_events.append({
                                    "title": f"{cid} (Bunked)",
                                    "start": start_iso,
                                    "end": end_iso,
                                    "color": "#EF4444"
                                })
                            else:
                                calendar_events.append({
                                    "title": f"{cid}",
                                    "start": start_iso,
                                    "end": end_iso,
                                    "color": "#3B82F6"
                                })
                        else:
                            calendar_events.append({
                                "title": f"{cid} (Scheduled)",
                                "start": start_iso,
                                "end": end_iso,
                                "color": "#94A3B8"
                            })

            cur += datetime.timedelta(days=1)

    for cid, s in stats.items():
        s["attended"] = s["held"] - s["bunks"]
        s["pct"] = (s["attended"] / s["held"] * 100) if s["held"] > 0 else 100.0
        target = s["target"] / 100.0

        if s["pct"] >= s["target"]:
            if target > 0:
                s["safe_to_skip"] = max(0, int(s["attended"] / target - s["held"]))
            else:
                s["safe_to_skip"] = 99
        else:
            if target < 1:
                needed = (target * s["held"] - s["attended"]) / (1 - target)
                s["must_attend"] = max(1, int(needed + 0.999))
            else:
                s["must_attend"] = 99

    return {
        "stats": stats,
        "settings": settings,
        "holidays": holidays_raw,
        "slots": slots,
        "absences": absences_raw,
        "events": calendar_events,
        "scheduled_events": scheduled_events_raw,
        "today": today
    }
