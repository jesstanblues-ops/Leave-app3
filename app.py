from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
from datetime import datetime
import config, requests, json
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-secret")


# ============================================================
#  POSTGRESQL CONNECTION
# ============================================================
def get_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise Exception("DATABASE_URL missing in Render environment")

    conn = psycopg2.connect(
        db_url,
        sslmode="require",
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn


# ============================================================
#  INITIALIZE DATABASE
# ============================================================
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            role TEXT,
            join_date TEXT,
            entitlement REAL,
            current_balance REAL DEFAULT 0
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id SERIAL PRIMARY KEY,
            employee_name TEXT,
            leave_type TEXT,
            start_date TEXT,
            end_date TEXT,
            days REAL,
            status TEXT,
            reason TEXT,
            applied_on TEXT
        );
    """)

    conn.commit()

    # Seed data only if empty
    cur.execute("SELECT COUNT(*) AS c FROM employees")
    if cur.fetchone()["c"] == 0:
        for emp in config.EMPLOYEES:
            cur.execute("""
                INSERT INTO employees (name, role, join_date, entitlement, current_balance)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (name) DO NOTHING;
            """, (
                emp["name"],
                emp.get("role", "Staff"),
                emp["join_date"],
                emp.get("entitlement"),
                emp.get("entitlement") or 0
            ))
        conn.commit()

    cur.close()
    conn.close()


# ============================================================
#  EMAIL (BREVO API)
# ============================================================
def send_email(subject, body, to):
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        print("BREVO_API_KEY missing — skipping email")
        return

    url = "https://api.brevo.com/v3/smtp/email"

    payload = {
        "sender": {
            "name": "Leave System",
            "email": "jessetan.ba@gmail.com"  # MUST BE VERIFIED IN BREVO
        },
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": f"<p>{body}</p>"
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        print("Brevo response:", r.status_code, r.text)
    except Exception as e:
        print("Email send error:", e)


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def home():
    return redirect(url_for("apply_leave"))
# ==========================================
# DOWNLOAD EXCEL (MULTI-SHEET EXPORT)
# ==========================================
@app.route("/download_excel")
def download_excel():
    import pandas as pd
    from flask import send_file
    from openpyxl import Workbook

    conn = get_db()
    cur = conn.cursor()

    # ---------------------------
    # SHEET 1 — Leave Records
    # ---------------------------
    cur.execute("""
        SELECT employee_name, leave_type, start_date, end_date, days, status, reason, applied_on
        FROM leave_requests
        ORDER BY applied_on DESC
    """)
    leave_rows = cur.fetchall()
    df_leaves = pd.DataFrame(leave_rows)

    # ---------------------------
    # SHEET 2 — Employee Balances
    # ---------------------------
    cur.execute("""
        SELECT name, entitlement, current_balance
        FROM employees
        ORDER BY name
    """)
    emp_rows = cur.fetchall()
    df_employees = pd.DataFrame(emp_rows)

    conn.close()

    # ---------------------------
    # Create Excel with 2 sheets
    # ---------------------------
    file_path = "leave_export.xlsx"

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df_leaves.to_excel(writer, sheet_name="Leave Records", index=False)
        df_employees.to_excel(writer, sheet_name="Balances", index=False)

    return send_file(
        file_path,
        as_attachment=True,
        download_name="leave_records.xlsx"
    )

@app.route("/balance/<name>")
def balance(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT current_balance FROM employees WHERE name=%s", (name,))
    row = cur.fetchone()
    conn.close()
    return jsonify({"balance": float(row["current_balance"]) if row else 0})


@app.route("/apply", methods=["GET", "POST"])
def apply_leave():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM employees ORDER BY name")
    employees = cur.fetchall()
    conn.close()

    if request.method == "POST":
        emp = request.form["employee"]
        ltype = request.form["leave_type"]

        try:
            s = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
            e = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        except:
            flash("Invalid dates", "danger")
            return redirect(url_for("apply_leave"))

        half = request.form.get("half") == "on"
        days = (e - s).days + 1
        if half:
            days -= 0.5

        reason = request.form.get("reason", "")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO leave_requests (employee_name, leave_type, start_date, end_date, days, status, reason, applied_on)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (emp, ltype, s.isoformat(), e.isoformat(), days, "Pending", reason, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        send_email(
            "New Leave Request",
            f"{emp} applied for {days} days ({ltype}).",
            to="jessetan.ba@gmail.com"
        )

        flash("Leave request submitted", "success")
        return redirect(url_for("apply_leave"))

    return render_template("apply_leave.html", employees=employees)


@app.route("/history/<name>")
def history(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM leave_requests WHERE employee_name=%s ORDER BY applied_on DESC", (name,))
    leaves = cur.fetchall()
    conn.close()
    return render_template("history.html", leaves=leaves, name=name)


# ============================================================
# ADMIN AUTH
# ============================================================
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password")
        if pw == os.environ.get("ADMIN_PASSWORD"):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Incorrect password"
    return render_template("admin_login.html", error=error)


@app.route("/admin_logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Logged out", "info")
    return redirect(url_for("admin_login"))


# ============================================================
# ADMIN DASHBOARD
# ============================================================
@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM leave_requests ORDER BY applied_on DESC")
    leaves = cur.fetchall()

    cur.execute("SELECT * FROM employees ORDER BY name")
    employees = cur.fetchall()

    conn.close()
    return render_template("admin_dashboard.html", leaves=leaves, employees=employees)


# ============================================================
# RENAME EMPLOYEE (FIXED FOR POSTGRES)
# ============================================================
@app.route("/update_employee_name", methods=["POST"])
def update_employee_name():
    old_name = request.form.get("old_name")
    new_name = request.form.get("new_name")

    if not new_name:
        flash("New name cannot be empty", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("UPDATE employees SET name=%s WHERE name=%s", (new_name, old_name))
        cur.execute("UPDATE leave_requests SET employee_name=%s WHERE employee_name=%s", (new_name, old_name))
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Rename failed: {e}", "danger")
    finally:
        conn.close()

    flash(f"Employee renamed: {old_name} → {new_name}", "success")
    return redirect(url_for("admin_dashboard"))


# ============================================================
# APPROVE / REJECT LEAVE
# ============================================================
@app.route("/approve/<int:lid>")
def approve(lid):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM leave_requests WHERE id=%s", (lid,))
    lr = cur.fetchone()

    if lr and lr["status"] == "Pending":
        cur.execute("UPDATE leave_requests SET status='Approved' WHERE id=%s", (lid,))
        cur.execute("UPDATE employees SET current_balance=current_balance-%s WHERE name=%s",
                    (lr["days"], lr["employee_name"]))
        conn.commit()

        send_email(
            "Leave Approved",
            f"{lr['employee_name']}'s leave ({lr['start_date']} → {lr['end_date']}) approved.",
            to="claycorp177@gmail.com",
        )

    conn.close()
    flash("Leave approved", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/reject/<int:lid>")
def reject(lid):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM leave_requests WHERE id=%s", (lid,))
    lr = cur.fetchone()

    if lr:
        cur.execute("UPDATE leave_requests SET status='Rejected' WHERE id=%s", (lid,))
        conn.commit()

        send_email(
            "Leave Rejected",
            f"{lr['employee_name']}'s leave ({lr['start_date']} → {lr['end_date']}) rejected.",
            to="claycorp177@gmail.com",
        )

    conn.close()
    flash("Leave rejected", "info")
    return redirect(url_for("admin_dashboard"))


# ============================================================
# UPDATE ENTITLEMENT / BALANCE
# ============================================================
@app.route("/update_entitlement", methods=["POST"])
def update_entitlement():
    name = request.form["name"]
    ent = request.form["entitlement"]

    try:
        ent_val = float(ent)
    except:
        ent_val = None

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE employees SET entitlement=%s WHERE name=%s", (ent_val, name))
    conn.commit()
    conn.close()

    flash("Entitlement updated", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/update_balance", methods=["POST"])
def update_balance():
    name = request.form["name"]
    bal = request.form["balance"]

    try:
        bal_val = float(bal)
    except:
        flash("Invalid balance", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE employees SET current_balance=%s WHERE name=%s", (bal_val, name))
    conn.commit()
    conn.close()

    flash("Balance updated", "success")
    return redirect(url_for("admin_dashboard"))


# ============================================================
# ADD / DELETE EMPLOYEE
# ============================================================
@app.route("/add_employee", methods=["POST"])
def add_employee():
    name = request.form.get("name")
    join_date = request.form.get("join_date")
    entitlement = request.form.get("entitlement")

    if not name or not join_date:
        flash("Name & join date required", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        ent_val = float(entitlement)
    except:
        ent_val = 0

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO employees (name, role, join_date, entitlement, current_balance)
        VALUES (%s,%s,%s,%s,%s)
    """, (name, "Staff", join_date, ent_val, ent_val))
    conn.commit()
    conn.close()

    flash("Employee added", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/delete_employee", methods=["POST"])
def delete_employee():
    name = request.form["name"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM employees WHERE name=%s", (name,))
    conn.commit()
    conn.close()

    flash(f"{name} removed", "info")
    return redirect(url_for("admin_dashboard"))


# ============================================================
# TEST EMAIL
# ============================================================
@app.route("/test_email")
def test_email():
    send_email(
        "Test Email",
        "If you received this, email is working!",
        to="jessetan.ba@gmail.com"
    )
    return "Test email sent. Check logs."

# ============================================================
# SIMPLE MONTHLY CALENDAR API
# ============================================================
@app.route("/calendar")
def calendar_api():
    month = request.args.get("month")  # format: YYYY-MM

    if not month:
        return jsonify({"error": "month=YYYY-MM required"}), 400

    try:
        year, mon = map(int, month.split("-"))
    except:
        return jsonify({"error": "Invalid month format"}), 400

    # Start + End of month
    start_month = datetime(year, mon, 1).date()
    if mon == 12:
        end_month = datetime(year + 1, 1, 1).date()
    else:
        end_month = datetime(year, mon + 1, 1).date()

    conn = get_db()
    cur = conn.cursor()

    # Fetch approved leaves that touch that month
    cur.execute("""
        SELECT employee_name, leave_type, start_date, end_date
        FROM leave_requests
        WHERE status='Approved'
          AND NOT (end_date < %s OR start_date >= %s)
    """, (start_month.isoformat(), end_month.isoformat()))

    rows = cur.fetchall()
    conn.close()

    # Build the output
    calendar = {}

    for r in rows:
        s = datetime.strptime(r["start_date"], "%Y-%m-%d").date()
        e = datetime.strptime(r["end_date"], "%Y-%m-%d").date()

        current = max(s, start_month)
        last = min(e, end_month)

        while current < last:
            d = current.isoformat()
            if d not in calendar:
                calendar[d] = []

            calendar[d].append({
                "name": r["employee_name"],
                "type": r["leave_type"]
            })

            current = current.replace(day=current.day + 1)

    return jsonify(calendar)
# ============================================================
# SIMPLE HTML CALENDAR VIEW
# ============================================================
@app.route("/calendar_view")
def calendar_view():
    return render_template("calendar_view.html")



# ============================================================
# INIT DB ON START
# ============================================================
with app.app_context():
    init_db()


# ============================================================
# RUN LOCAL
# ============================================================
if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0")
