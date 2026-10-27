
from flask import Flask, render_template, request, redirect, url_for, flash
from pathlib import Path
from contextlib import closing
import sqlite3
import re

app = Flask(__name__)
app.secret_key = "change-this-secret-before-deployment"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_db():
    with closing(get_db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL DEFAULT '',
                course TEXT NOT NULL DEFAULT '',
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                fee_amount REAL DEFAULT 0,
                payment_status TEXT DEFAULT 'Pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(students)")
        }

        additions = {
            "name": "TEXT NOT NULL DEFAULT ''",
            "course": "TEXT NOT NULL DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "email": "TEXT DEFAULT ''",
            "fee_amount": "REAL DEFAULT 0",
            "payment_status": "TEXT DEFAULT 'Pending'",
            "created_at": "TEXT",
        }

        for column, definition in additions.items():
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE students ADD COLUMN {column} {definition}"
                )

        conn.execute("""
            UPDATE students
            SET payment_status = 'Pending'
            WHERE payment_status IS NULL OR payment_status = ''
        """)
        conn.execute("""
            UPDATE students SET fee_amount = 0
            WHERE fee_amount IS NULL
        """)
        conn.commit()


@app.template_filter("digits")
def digits(value):
    return re.sub(r"\D", "", value or "")


@app.route("/")
def home():
    search = request.args.get("search", "").strip()

    with closing(get_db()) as conn:
        if search:
            pattern = f"%{search}%"
            students = conn.execute("""
                SELECT * FROM students
                WHERE name LIKE ? OR course LIKE ?
                   OR phone LIKE ? OR email LIKE ?
                ORDER BY id DESC
            """, (pattern, pattern, pattern, pattern)).fetchall()
        else:
            students = conn.execute("""
                SELECT * FROM students ORDER BY id DESC
            """).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]

        paid = conn.execute("""
            SELECT COUNT(*) FROM students
            WHERE payment_status = 'Paid'
        """).fetchone()[0]

        pending = conn.execute("""
            SELECT COUNT(*) FROM students
            WHERE payment_status = 'Pending'
        """).fetchone()[0]

        total_fees = conn.execute("""
            SELECT COALESCE(SUM(fee_amount), 0) FROM students
        """).fetchone()[0]

        paid_fees = conn.execute("""
            SELECT COALESCE(SUM(fee_amount), 0) FROM students
            WHERE payment_status = 'Paid'
        """).fetchone()[0]

    return render_template(
        "index.html",
        students=students,
        search=search,
        total=total,
        paid=paid,
        pending=pending,
        total_fees=total_fees,
        paid_fees=paid_fees,
    )


@app.route("/add", methods=["GET", "POST"])
def add_student():
    # Direct browser visits to /add redirect instead of returning 405.
    if request.method == "GET":
        flash("Use the registration form to add a student.", "info")
        return redirect(url_for("home"))

    name = request.form.get("name", "").strip()
    course = request.form.get("course", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    fee_text = request.form.get("fee_amount", "0").strip()
    status = request.form.get("payment_status", "Pending")

    if not name or not course:
        flash("Student name and course are required.", "error")
        return redirect(url_for("home"))

    if len(name) > 120 or len(course) > 120:
        flash("Name and course must be 120 characters or fewer.", "error")
        return redirect(url_for("home"))

    if len(phone) > 30 or len(email) > 254:
        flash("Check the phone number or email length.", "error")
        return redirect(url_for("home"))

    try:
        fee = float(fee_text or 0)
        if fee < 0 or fee > 1_000_000_000:
            raise ValueError
    except ValueError:
        flash("Enter a valid, non-negative course fee.", "error")
        return redirect(url_for("home"))

    if status not in ("Paid", "Pending"):
        status = "Pending"

    try:
        with closing(get_db()) as conn:
            conn.execute("""
                INSERT INTO students
                    (name, course, phone, email, fee_amount, payment_status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, course, phone, email, fee, status))
            conn.commit()

        flash(f"{name} was added successfully!", "success")

    except sqlite3.Error:
        app.logger.exception("Database error while adding student")
        flash("Could not save the student. Check the terminal.", "error")

    return redirect(url_for("home"))


@app.route("/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    try:
        with closing(get_db()) as conn:
            cursor = conn.execute(
                "DELETE FROM students WHERE id = ?", (student_id,)
            )
            conn.commit()

        if cursor.rowcount:
            flash("Student record deleted successfully.", "success")
        else:
            flash("Student record was not found.", "error")

    except sqlite3.Error:
        app.logger.exception("Database error while deleting student")
        flash("Could not delete the student.", "error")

    return redirect(url_for("home"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)
