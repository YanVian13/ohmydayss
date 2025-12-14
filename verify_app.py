# verify_app.py — versi lengkap dengan Admin Panel + Password + Statistik + Log
import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session
from common import get_sheet
from jinja2 import TemplateNotFound

# === KONFIGURASI ===
BASEDIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASEDIR, "templates")
STATIC_DIR = os.path.join(BASEDIR, "static")
DB_PATH = os.path.join(BASEDIR, "data.db")
LOG_PATH = os.path.join(BASEDIR, "scan_log.txt")

ADMIN_PASSWORD = "admin123"  # ubah sesuai kebutuhanmu
SECRET_KEY = "supersecretkey"  # wajib untuk session

# === SETUP APP ===
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = SECRET_KEY
app.config["TEMPLATES_AUTO_RELOAD"] = True


# === UTILITAS DATABASE ===
def get_conn():
    return sqlite3.connect(DB_PATH)


def log_scan(code, status):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {code} - {status}\n")


def verify_code(code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT code, valid, used, last_used FROM codes WHERE code=?", (code,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"status": "invalid", "msg": "Kode tidak ditemukan."}

    _, valid, used, last_used = row
    now = datetime.now()

    if not valid:
        conn.close()
        return {"status": "invalid", "msg": "Kode tidak valid."}

    if used and last_used:
        try:
            last_dt = datetime.strptime(last_used, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last_dt = None
        if last_dt and now - last_dt < timedelta(hours=24):
            conn.close()
            return {"status": "used", "msg": "Kode sudah digunakan dalam 24 jam terakhir."}

    cur.execute(
        "UPDATE codes SET used=1, last_used=? WHERE code=?",
        (now.strftime("%Y-%m-%d %H:%M:%S"), code),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "msg": "Tiket valid. Selamat datang!"}


# === ROUTES ===
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan_choice")
def scan_choice():
    return render_template("scan_choice.html")


@app.route("/scan")
def verify():
    token = request.args.get("token") or request.args.get("id")
    if not token:
        return render_template(
            "verify_result.html",
            status="error",
            message="Tidak ada kode QR yang dikirim.",
            code="(kosong)",
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    result = verify_code(token)
    log_scan(token, result["status"])
    return render_template(
        "verify_result.html",
        status=result["status"],
        message=result["msg"],
        code=token,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/check", methods=["GET", "POST"])
def check_ticket():
    result = None

    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()

        try:
            sheet = get_sheet()
            records = sheet.get_all_records()
        except Exception as e:
            return f"Error membaca data: {e}"

        for r in records:
            if str(r.get("Kode Unik", "")).strip().upper() == code:
                result = {
                    "valid": True,
                    "code": "qr_" + code,
                    "name": r.get("Nama Peserta"),
                    "email": r.get("Email"),
                    "sent_at": r.get("Waktu Kirim"),
                    "used_at": r.get("Nomor HP"),
                    "status": r.get("Status"),
                }
                break

        if not result:
            result = {"valid": False, "code": code}

    return render_template("check_ticket.html", result=result)


@app.route("/reset", methods=["GET", "POST"])
def reset():
    """Reset kode sesuai permintaan admin"""
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_conn()
    cur = conn.cursor()

    mode = request.args.get("mode", "expired")  # expired = >24 jam, all = semua
    if mode == "all":
        cur.execute("UPDATE codes SET used=0, last_used=NULL")
        message = "Semua kode berhasil direset."
    else:
        cur.execute("UPDATE codes SET used=0 WHERE used=1 AND last_used < datetime('now','-24 hours')")
        message = "Kode yang digunakan >24 jam telah direset."

    conn.commit()
    conn.close()
    return render_template("reset.html", message=message)
    
@app.route("/delete_valid", methods=["POST"])
def delete_valid():
    """Hapus semua tiket valid dari database"""
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM codes WHERE valid=1")
    deleted_rows = cur.rowcount
    conn.commit()
    conn.close()

    message = f"✅ Berhasil menghapus {deleted_rows} tiket valid dari database."
    return render_template("reset.html", message=message)



# === ADMIN PANEL ===
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    # Jika sudah login
    if session.get("is_admin"):
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_panel"))
        else:
            return render_template("admin.html", login=True, error="Password salah!")

    return render_template("admin.html", login=True)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin/panel")
def admin_panel():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    # Statistik dari database
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM codes")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM codes WHERE valid=1")
    valid = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM codes WHERE used=1")
    used = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM codes WHERE used=0")
    unused = cur.fetchone()[0]
    conn.close()

    stats = {
        "total": total,
        "valid": valid,
        "used": used,
        "unused": unused,
    }

    # Baca 20 baris terakhir dari log scanner
    logs = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            logs = lines[-20:] if len(lines) > 20 else lines

    return render_template("admin.html", login=False, stats=stats, logs=logs)


# === JALANKAN SERVER ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
