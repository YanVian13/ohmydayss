# verify_app.py
from flask import Flask, render_template, request
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)

DB_PATH = "data.db"
LOG_PATH = "scan_log.txt"

def get_conn():
    return sqlite3.connect(DB_PATH)

def verify_code(code):
    """Memeriksa validitas kode di database"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT code, valid, used, last_used FROM codes WHERE code=?", (code,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return {"status": "invalid", "msg": "Kode tidak ditemukan"}

    _, valid, used, last_used = row

    if not valid:
        conn.close()
        return {"status": "invalid", "msg": "Kode tidak valid"}

    now = datetime.now()
    try:
        last_used_dt = datetime.strptime(last_used, "%Y-%m-%d %H:%M:%S") if last_used else None
    except ValueError:
        last_used_dt = None

    # Jika sudah pernah digunakan dalam 24 jam
    if used and last_used_dt and now - last_used_dt < timedelta(hours=24):
        conn.close()
        return {"status": "used", "msg": "Kode sudah digunakan dalam 24 jam terakhir"}

    # Jika valid dan belum digunakan dalam 24 jam
    cur.execute(
        "UPDATE codes SET used=?, last_used=?, used_by=? WHERE code=?",
        (1, now.strftime("%Y-%m-%d %H:%M:%S"), "scanner", code),
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "msg": "Tiket valid. Selamat datang!"}


def log_scan(code, status):
    """Menyimpan log hasil scan ke file"""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{ts}] {code} - {status}\n")


@app.route("/")
def index():
    """Halaman utama — menu pilihan"""
    return render_template("index.html")


@app.route("/scan_choice")
def scan_choice():
    """Halaman untuk memilih metode scanning"""
    return render_template("scan_choice.html")


@app.route("/verify")
def verify():
    """Verifikasi QR Code"""
    code = request.args.get("token")
    if not code:
        return render_template("verify_result.html", status="error", message="Tidak ada kode QR yang dikirim")

    result = verify_code(code)
    log_scan(code, result["status"])

    # render halaman hasil verifikasi dengan template
    return render_template(
        "verify_result.html",
        status=result["status"],
        message=result["msg"],
        code=code,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route("/scan")
def scan_alias():
    """Alias agar URL /scan?id=... bisa diproses layaknya /verify?token=..."""
    code = request.args.get("id")
    if not code:
        return render_template("verify_result.html", status="error", message="Kode QR tidak ditemukan.")

    # Gunakan fungsi verify_code yang sama
    result = verify_code(code)
    log_scan(code, result["status"])

    return render_template(
        "verify_result.html",
        status=result["status"],
        message=result["msg"],
        code=code,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )



@app.route("/reset", methods=["GET", "POST"])
def reset():
    """Mereset status 'used' jika sudah lebih dari 24 jam"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE codes SET used=0 WHERE used=1 AND last_used < datetime('now','-24 hours')")
    conn.commit()
    conn.close()

    message = "✅ Semua kode yang digunakan lebih dari 24 jam telah direset."
    return render_template("reset.html", message=message)



if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
