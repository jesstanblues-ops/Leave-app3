from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3, os
from datetime import datetime
import config, smtplib

DB_PATH = "/data/leave.db"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback-secret")

# ---------------- Database ----------------
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
            entitlement REAL,
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

    if seed_needed:
        for emp in config.EMPLOYEES:
            c.execute(
                "INSERT OR IGNORE INTO employees (name, role, join_date, entitlement, current_balance) VALUES (?, ?, ?, ?, ?)",
                (emp.get('name'), emp.get('role','Staff'), emp.get('join_date'),
                 emp.get('entitlement') if emp.get('entitlement') is not None else None,
                 emp.get('entitlement') if emp.get('entitlement') is not None else 0)
            )
        conn.commit()
    conn.close()

# ---------------- Email helper ----------------
def send_email(subject, body, to=None):
    if not getattr(config, 'ENABLE_EMAIL', False):
        return
    try:
        smtp_server = getattr(config, 'SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = getattr(config, 'SMTP_PORT', 587)
        sender = config.ADMIN_EMAIL
        password = os.environ.get('EMAIL_PASSWORD')
        if not password:
            print('EMAIL_PASSWORD not set, skipping send_email')
            return
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender, password)
        msg = f"Subject: {subject}\n\n{body}"
        server.sendmail(sender, to or sender, msg)
        server.quit()
    except Exception as e:
        print('Email error:', e)

# ---------------- Routes ----------------
@app.route('/')
def home():
    return redirect(url_for('apply_leave'))

@app.route("/download_excel")
def download_excel():
    import pandas as pd
    from flask import send_file

    conn = get_db()
    rows = conn.execute("""
        SELECT employee_name, leave_type, start_date, end_date, days, status, reason, applied_on
        FROM leave_requests
        ORDER BY applied_on DESC
    """).fetchall()
    conn.close()

    if not rows:
        flash("No leave records found.", "warning")
        return redirect(url_for("admin_dashboard"))

    df = pd.DataFrame(rows, columns=[
        "Employee Name", "Leave Type", "Start Date", "End Date",
        "Days", "Status", "Reason", "Applied On"
    ])

    file_path = "leave_records.xlsx"
    df.to_excel(file_path, index=False)

    return send_file(
        file_path,
        as_attachment=True,
        download_name="leave_records.xlsx"
    )


@app.route('/balance/<name>')
def balance(name):
    conn = get_db()
    row = conn.execute('SELECT current_balance FROM employees WHERE name=?', (name,)).fetchone()
    conn.close()
    return jsonify({'balance': round(row['current_balance'],2) if row and row['current_balance'] is not None else 0})

@app.route('/apply', methods=['GET','POST'])
def apply_leave():
    conn = get_db()
    employees = conn.execute('SELECT name FROM employees ORDER BY name').fetchall()
    conn.close()
    if request.method == 'POST':
        emp = request.form['employee']
        ltype = request.form['leave_type']
        try:
            s = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            e = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        except:
            flash('Invalid dates', 'danger')
            return redirect(url_for('apply_leave'))
        half = request.form.get('half') == 'yes' or request.form.get('half') == 'on'
        days = (e - s).days + 1
        if days < 0:
            flash('End date must be on/after start date', 'danger')
            return redirect(url_for('apply_leave'))
        if half:
            days -= 0.5
        reason = request.form.get('reason','')

        conn = get_db()
        conn.execute("""INSERT INTO leave_requests (employee_name, leave_type, start_date, end_date, days, status, reason, applied_on)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                     (emp, ltype, s.isoformat(), e.isoformat(), days, 'Pending', reason, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        # notify admin
        send_email('New Leave Request', f"{emp} applied for {days} days ({ltype}).")
        flash('Leave request sent', 'success')
        return redirect(url_for('apply_leave'))

    return render_template('apply_leave.html', employees=employees)

@app.route('/history/<name>')
def history(name):
    conn = get_db()
    leaves = conn.execute('SELECT * FROM leave_requests WHERE employee_name=? ORDER BY applied_on DESC', (name,)).fetchall()
    conn.close()
    return render_template('history.html', leaves=leaves, name=name)

# Admin login
@app.route('/admin_login', methods=['GET','POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        pw = request.form.get('password')
        correct = os.environ.get('ADMIN_PASSWORD')
        if pw and correct and pw == correct:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        error = 'Incorrect password'
    return render_template('admin_login.html', error=error)

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    conn = get_db()
    leaves = conn.execute('SELECT * FROM leave_requests ORDER BY applied_on DESC').fetchall()
    emps = conn.execute('SELECT * FROM employees ORDER BY name').fetchall()
    conn.close()
    return render_template('admin_dashboard.html', leaves=leaves, employees=emps)

@app.route('/approve/<int:lid>')
def approve(lid):
    conn = get_db()
    lr = conn.execute('SELECT * FROM leave_requests WHERE id=?', (lid,)).fetchone()
    if lr and lr['status'] == 'Pending':
        conn.execute("UPDATE leave_requests SET status='Approved' WHERE id=?", (lid,))
        conn.execute("UPDATE employees SET current_balance = current_balance - ? WHERE name=?", (lr['days'], lr['employee_name']))
        conn.commit()
        # email notify to claycorp177
        send_email('Leave Approved', f"{lr['employee_name']}'s leave ({lr['start_date']} → {lr['end_date']}) APPROVED.", to='claycorp177@gmail.com')
    conn.close()
    flash('Leave approved', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/reject/<int:lid>')
def reject(lid):
    conn = get_db()
    lr = conn.execute('SELECT * FROM leave_requests WHERE id=?', (lid,)).fetchone()
    if lr:
        conn.execute("UPDATE leave_requests SET status='Rejected' WHERE id=?", (lid,))
        conn.commit()
        send_email('Leave Rejected', f"{lr['employee_name']}'s leave ({lr['start_date']} → {lr['end_date']}) REJECTED.", to='claycorp177@gmail.com')
    conn.close()
    flash('Leave rejected', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/update_entitlement', methods=['POST'])
def update_entitlement():
    name = request.form.get('name')
    new_ent = request.form.get('entitlement')
    try:
        ent_val = float(new_ent)
    except:
        ent_val = None
    conn = get_db()
    conn.execute('UPDATE employees SET entitlement=? WHERE name=?', (ent_val, name))
    conn.commit()
    conn.close()
    flash('Entitlement updated', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route("/update_balance", methods=["POST"])
def update_balance():
    name = request.form.get('name')
    new_bal = request.form.get('balance')

    try:
        bal_val = float(new_bal)
    except:
        flash('Invalid balance value', 'danger')
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    conn.execute(
        'UPDATE employees SET current_balance=? WHERE name=?',
        (bal_val, name)
    )
    conn.commit()
    conn.close()

    flash('Balance updated', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route("/add_employee", methods=["POST"])
def add_employee():
    name = request.form.get("name")
    join_date = request.form.get("join_date")
    entitlement = request.form.get("entitlement")
    role = "Staff"

    if not name or not join_date:
        flash("Name and join date required", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        ent_val = float(entitlement)
    except:
        ent_val = 0

    conn = get_db()
    conn.execute("""
        INSERT INTO employees (name, role, join_date, entitlement, current_balance)
        VALUES (?, ?, ?, ?, ?)
    """, (name, role, join_date, ent_val, ent_val))
    conn.commit()
    conn.close()

    flash("Employee added successfully!", "success")
    return redirect(url_for("admin_dashboard"))
    
@app.route("/delete_employee", methods=["POST"])
def delete_employee():
    name = request.form.get("name")

    conn = get_db()
    conn.execute("DELETE FROM employees WHERE name=?", (name,))
    conn.commit()
    conn.close()

    flash(f"Employee {name} removed.", "info")
    return redirect(url_for("admin_dashboard"))



# ---------------- Bootstrap DB on startup ----------------
with app.app_context():
    init_db()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')
