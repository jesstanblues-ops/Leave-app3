# Insert the full production-ready app.py her# ===========================
#  Leave Management System v3
#  Production-Grade Flask App
# ===========================

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, session
)
import sqlite3, os
from datetime import datetime, date
import config
import smtplib

# -----------------------------
# Flask Setup
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-secret")

DB_PATH = os.path.join(os.getcwd(), "leave.db")


# -----------------------------
# Database Helpers
# -----------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    seed_needed = not os.path.exists(DB_PATH)
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            role TEXT,
            join_date TEXT,
            entitlement INTEGER,
            phone TEXT,
            current_balance REAL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_name TEXT,
            leave_type TEXT,
            start_date TEXT,
            end_date TEXT,
            days REAL,
            status TEXT,
            reason TEXT,
            applied_on TEXT
        )
    """)

    conn.commit()

    # Initial data insertion
    if seed_needed:
        for emp in config.EMPLOYEES:
            conn.execute("""
                INSERT OR IGNORE INTO employees 
                (name, role, join_date, entitlement, phone, current_balance)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (
                emp["name"],
                emp.get("role", "Staff"),
                emp["join_date"],
                emp.get("entitlement"),
                emp.get("phone")
            ))
        conn.commit()

    conn.close()


# -----------------------------
# Leave Accrual Logic (Prorated)
# -----------------------------
def calc_prorated_balance(emp):
    today = date.today()
    year = today.year

    # find accrual pattern
    pattern = next(
        (e["accrual_pattern"] for e in config.EMPLOYEES if e["name"] == emp["name"]),
        None
    )
    if pattern is None:
        pattern = {m: 2 for m in range(1, 13)}

    entitlement = emp["entitlement"]

    join_date = datetime.strptime(emp["join_date"], "%Y-%m-%d").date()
    total = 0.0

    for m in range(1, today.month + 1):
        month_start = date(year, m, 1)
        if month_start < join_date.replace(day=1):
            continue
        if year < config.SYSTEM_START_YEAR:
            continue
        total += float(pattern.get(m, 0))

    if entitlement is not None:
        total = min(total, entitlement)

    return round(total, 2)


def update_all_balances():
    conn = get_db()
    c = conn.cursor()

    for emp in c.execute("SELECT * FROM employees").fetchall():
        new_balance = calc_prorated_balance(emp)
        c.execute("UPDATE employees SET current_balance=? WHERE id=?", (new_balance, emp["id"]))

    conn.commit()
    conn.close()


# -----------------------------
# Email Sending Helper
# -----------------------------
def send_email(subject, body, to=None):
    if not config.ENABLE_EMAIL:
        return

    try:
        smtp_server = getattr(config, "SMTP_SERVER", "smtp.gmail.com")
        smtp_port = getattr(config, "SMTP_PORT", 587)

        sender = config.ADMIN_EMAIL
        password = os.environ.get("EMAIL_PASSWORD")

        if not password:
            print("EMAIL_PASSWORD env variable missing.")
            return

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender, password)
        msg = f"Subject: {subject}\n\n{body}"
        server.sendmail(sender, to or sender, msg)
        server.quit()
        print("Email sent to:", to or sender)

    except Exception as e:
        print("Email error:", e)


# -----------------------------
# Admin Login
# -----------------------------
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password")
        correct = os.environ.get("ADMIN_PASSWORD")

        if pw == correct and correct:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        error = "Incorrect password"

    return render_template("admin_login.html", error=error)


@app.route("/admin_logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out.")
    return redirect(url_for("admin_login"))


# -----------------------------
# Main Routes
# -----------------------------
@app.route("/")
def home():
    return redirect(url_for("apply_leave"))


@app.route("/balance/<name>")
def balance(name):
    conn = get_db()
    row = conn.execute("SELECT current_balance FROM employees WHERE name=?", (name,)).fetchone()
    conn.close()
    return jsonify({"balance": round(row["current_balance"], 2) if row else 0})


@app.route("/apply", methods=["GET", "POST"])
def apply_leave():
    conn = get_db()
    employees = conn.execute("SELECT name FROM employees ORDER BY name").fetchall()
    conn.close()

    if request.method == "POST":
        emp = request.form["employee"]
        ltype = request.form["leave_type"]
        s = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        e = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        half = request.form.get("half") == "yes"
        reason = request.form.get("reason", "")

        days = (e - s).days + 1
        if half:
            days -= 0.5

        conn = get_db()
        bal = conn.execute("SELECT current_balance FROM employees WHERE name=?", (emp,)).fetchone()["current_balance"]
        warning = bal < days

        conn.execute("""
            INSERT INTO leave_requests
            (employee_name, leave_type, start_date, end_date, days, status, reason, applied_on)
            VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?)
        """, (emp, ltype, s.isoformat(), e.isoformat(), days, reason, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        if warning:
            flash(f"Warning: Applying {days} days but only {bal} available.", "warning")
        else:
            flash("Leave request sent.", "success")

        send_email("New Leave Request", f"{emp} applied for {days} days ({ltype}).")

        return redirect(url_for("apply_leave"))

    return render_template("apply_leave.html", employees=employees)


@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    leaves = conn.execute("SELECT * FROM leave_requests ORDER BY applied_on DESC").fetchall()
    emps = conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
    conn.close()

    return render_template("admin_dashboard.html", leaves=leaves, employees=emps)


@app.route("/history/<name>")
def history(name):
    conn = get_db()
    leaves = conn.execute("""
        SELECT * FROM leave_requests
        WHERE employee_name=?
        ORDER BY applied_on DESC
    """, (name,)).fetchall()
    conn.close()
    return render_template("history.html", leaves=leaves, name=name)


@app.route("/approve/<int:lid>")
def approve(lid):
    conn = get_db()
    lr = conn.execute("SELECT * FROM leave_requests WHERE id=?", (lid,)).fetchone()

    if lr and lr["status"] == "Pending":
        conn.execute("UPDATE leave_requests SET status='Approved' WHERE id=?", (lid,))
        conn.execute("""
            UPDATE employees
            SET current_balance = current_balance - ?
            WHERE name=?
        """, (lr["days"], lr["employee_name"]))
        conn.commit()

        send_email(
            "Leave Approved",
            f"{lr['employee_name']}'s leave "
            f"({lr['start_date']} → {lr['end_date']}) "
            f"has been APPROVED.",
            to="claycorp177@gmail.com"
        )

    conn.close()
    flash("Leave approved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/reject/<int:lid>")
def reject(lid):
    conn = get_db()
    lr = conn.execute("SELECT * FROM leave_requests WHERE id=?", (lid,)).fetchone()

    if lr:
        conn.execute("UPDATE leave_requests SET status='Rejected' WHERE id=?", (lid,))
        conn.commit()

        send_email(
            "Leave Rejected",
            f"{lr['employee_name']}'s leave "
            f"({lr['start_date']} → {lr['end_date']}) "
            f"has been REJECTED.",
            to="claycorp177@gmail.com"
        )

    conn.close()
    flash("Leave rejected.", "info")
    return redirect(url_for("admin_dashboard"))


# -----------------------------
# Update Entitlement
# -----------------------------
@app.route("/update_entitlement", methods=["POST"])
def update_entitlement():
    name = request.form["name"]
    new_ent = request.form["entitlement"]

    try:
        ent_val = int(new_ent)
    except:
        ent_val = None

    conn = get_db()
    conn.execute("UPDATE employees SET entitlement=? WHERE name=?", (ent_val, name))
    conn.commit()
    conn.close()

    flash("Entitlement updated.", "info")
    return redirect(url_for("admin_dashboard"))


# -----------------------------
# Bootstrapping (Gunicorn Safe)
# -----------------------------
with app.app_context():
    init_db()
    update_all_balances()


# -----------------------------
# Local Run
# -----------------------------
if __name__ == "__main__":
    init_db()
    update_all_balances()
    app.run(debug=True, host="0.0.0.0")
