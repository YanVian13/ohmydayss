# send_ticket_gui.py (fixed)
import os
import sqlite3
import threading
from datetime import datetime
from tkinter import Tk, Label, Button, Text, END, Scrollbar, Frame, BOTH, RIGHT, Y, LEFT
from html import escape
import random
import time

# local helpers from common.py
from common import sync_from_sheets, get_conn, generate_token, push_code_to_sheet, update_participant_sheet_row

# Gmail API & email
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

# QR generation
import qrcode


def normalize(v):
    return str(v).strip() if v is not None else ""


def is_paid(status):
    return normalize(status).upper() == "PAID"


def upsert_code(conn, token, valid=1, used=0, last_used=None, used_by=None):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(codes)")
    cols_info = [c[1] for c in cur.fetchall()]

    data_map = {
        "code": token,
        "valid": valid,
        "used": used,
        "last_used": last_used,
        "used_by": used_by,
    }

    cols_to_use = [c for c in data_map if c in cols_info]
    values = [data_map[c] for c in cols_to_use]

    placeholders = ",".join(["?"] * len(cols_to_use))
    sql = f"INSERT OR REPLACE INTO codes ({','.join(cols_to_use)}) VALUES ({placeholders})"
    cur.execute(sql, values)
    conn.commit()


# === CONFIG ===
SCOPES_GMAIL = ["https://www.googleapis.com/auth/gmail.send"]
QR_OUT = "output_qr"
os.makedirs(QR_OUT, exist_ok=True)

# put your sending email here (must match the account you authorize via client_secret.json)
SENDER_EMAIL = "youremail@gmail.com"

# Event info (edit as needed)
EVENT_NAME = "CUPO x G-VOZ 2K25"
VENUE = "SMAN 13 Surabaya"
EVENT_DATETIME = "17 Desember 2025, 15:20"


# ====== EMAIL HTML VARIATION FUNCTION ======
def make_email_html(name, token, event=None, venue=None, datetime_str=None):
    name_s = escape(name or "")
    token_s = escape(token or "")
    event_s = escape(event or "")
    venue_s = escape(venue or "")
    datetime_s = escape(datetime_str or "")

    header_lines = []
    if event_s:
        header_lines.append(f"<div class='event'>{event_s}</div>")
    if datetime_s:
        header_lines.append(f"<div class='datetime'>{datetime_s}</div>")
    if venue_s:
        header_lines.append(f"<div class='venue'>{venue_s}</div>")
    header_html = "<br>".join(header_lines)

    templates = [
        """
        <div class="card">
          <h1>🎉 {event}</h1>
          {header}
          <p class="lead">Halo <strong>{name}</strong>,</p>
          <p>Kami sudah menerima pembayaranmu. Berikut tiket digital untuk acara kami.</p>
          <div class="code">Kode: <strong>{token}</strong></div>
          <img src="cid:qrimage" alt="QR Ticket" class="qr">
          <p class="note">Tunjukkan QR ini saat registrasi. Sampai jumpa!</p>
          <div class="sig">— Panitia</div>
        </div>
        """,

        """
        <div class="card">
          <h2>{event}</h2>
          {header}
          <p>Yth. <strong>{name}</strong>,</p>
          <p>Terima kasih atas partisipasi dan pembelian tiket Anda. Detail tiket digital adalah sebagai berikut:</p>
          <div class="code boxed">{token}</div>
          <img src="cid:qrimage" alt="QR Ticket" class="qr">
          <p class="muted">Mohon hadir 15 menit lebih awal. Salam, Panitia.</p>
        </div>
        """,

        """
        <div class="card">
          <h2>🎟️ Tiket Anda</h2>
          {header}
          <p class="lead">Hai <strong>{name}</strong>,</p>
          <img src="cid:qrimage" alt="QR Ticket" class="qr">
          <div style="margin:12px 0;"><span class="btn">Tunjukkan QR saat masuk</span></div>
          <div class="code small">{token}</div>
          <p class="muted">Terima kasih telah membeli tiket.</p>
        </div>
        """,

        """
        <div class="card">
          <h2>Selamat Datang!</h2>
          {header}
          <p>Halo <strong>{name}</strong>, terima kasih sudah bergabung.</p>
          <div class="qr-wrap"><img src="cid:qrimage" alt="QR Ticket" class="qr"></div>
          <p class="instructions">Langkah singkat: simpan email ini & tampilkan QR pada meja registrasi.</p>
          <div class="code">{token}</div>
        </div>
        """,

        """
        <div class="card">
          <h3>{event}</h3>
          {header}
          <p><strong>{name}</strong></p>
          <img src="cid:qrimage" alt="QR Ticket" class="qr">
          <div class="code tiny">{token}</div>
          <p class="muted">Panitia</p>
        </div>
        """,
    ]

    css = """
    <style>
      body { margin:0; padding:0; font-family: Arial, sans-serif; background:#f4f6f8; }
      .wrap { display:flex; align-items:center; justify-content:center; padding:18px; }
      .card {
        width:100%; max-width:520px; background:#fff; border-radius:12px; padding:20px;
        box-shadow:0 8px 22px rgba(12,20,36,0.08); text-align:center; margin:10px auto;
      }
      .card h1, .card h2, .card h3 { margin:6px 0 10px 0; color:#0f172a; }
      .lead { font-size:15px; margin:6px 0; color:#0f172a; }
      .muted { color:#6b7280; font-size:13px; margin-top:8px; }
      .code { margin:10px auto; font-weight:700; background:#f8fafc; padding:8px 12px; display:inline-block; border-radius:8px; color:#0f172a; }
      .code.boxed { border:1px solid #e6eef9; padding:10px 14px; }
      .code.small { font-size:14px; padding:6px 10px; }
      .code.tiny { font-size:13px; padding:5px 8px; background:transparent; }
      .qr { width:240px; height:240px; border-radius:8px; border:1px solid #e6eef9; display:block; margin:12px auto; }
      .btn { display:inline-block; background:#2563eb; color:#fff; padding:10px 14px; border-radius:8px; text-decoration:none; font-weight:600; }
      .instructions { font-size:13px; color:#374151; margin-top:8px; }
      .event { font-weight:700; color:#374151; font-size:14px; }
      .datetime, .venue { color:#6b7280; font-size:13px; }
      .sig { margin-top:10px; color:#1f2937; font-weight:600; }
      .qr-wrap { display:flex; justify-content:center; }
      @media(max-width:480px){
        .card { padding:16px; }
        .qr { width:200px; height:200px; }
      }
    </style>
    """

    tpl = random.choice(templates)
    html_body = tpl.format(name=name_s, token=token_s, event=event_s, header=header_html)
    full_html = f"""<html><head>{css}</head><body><div class=\"wrap\">{html_body}</div></body></html>"""
    return full_html


def gmail_authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES_GMAIL)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES_GMAIL)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def create_message(sender, to, subject, html_body, qr_path):
    msg = MIMEMultipart("related")
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(html_body, "html"))

    if qr_path and os.path.exists(qr_path):
        with open(qr_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<qrimage>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(qr_path))
            msg.attach(img)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def send_message(service, message):
    return service.users().messages().send(userId="me", body=message).execute()


# === GUI APP ===
class App:
    def __init__(self, root):
        self.root = root
        root.title("📨 QR Ticket Sender")
        root.geometry("720x520")

        Label(root, text="QR Ticket Sender (Sheets + Gmail API)", font=("Segoe UI", 14)).pack(pady=8)

        frame = Frame(root)
        frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        scroll = Scrollbar(frame)
        scroll.pack(side=RIGHT, fill=Y)
        self.log = Text(frame, wrap="word", yscrollcommand=scroll.set, bg="#fbfdfe")
        self.log.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.config(command=self.log.yview)

        Button(root, text="🔄 Sync from Sheets", command=self.sync_from_sheets, width=22).pack(pady=6)
        Button(root, text="✉️ Send Tickets (PAID)", command=self.send_tickets, width=22).pack(pady=6)
        Button(root, text="🚪 Quit", command=root.quit, width=22).pack(pady=6)

        # DB connection for main thread (we'll open new connections in threads)
        # but keep a handle to ensure DB exists
        try:
            conn = get_conn()
            conn.close()
        except Exception as e:
            self.log_message(f"Warning: DB init failed: {e}")

    def log_message(self, text):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.insert(END, f"{ts}  {text}\n")
        self.log.see(END)

    # Sync wrapper
    def sync_from_sheets(self):
        def job():
            self.log_message("🔄 Starting sync_from_sheets() ...")
            try:
                sync_from_sheets()
                self.log_message("✅ Sync from Sheets complete.")
            except Exception as e:
                self.log_message(f"❌ Sync failed: {e}")
        threading.Thread(target=job).start()

    # Main send tickets function (must be bound to button)
    def send_tickets(self):
        """Send tickets to PAID participants with proper scoping and threading."""
        def job():
            conn = get_conn()
            cur = conn.cursor()

            self.log_message("🚀 Starting SEND TICKETS (PAID)...")

            cur.execute(
                "SELECT id, name, email, phone, status, code, sheet_row FROM participants ORDER BY sheet_row ASC"
            )
            rows = cur.fetchall()

            sent = 0
            skip_paid = skip_email = skip_has_code = 0

            for row in rows:
                id_, name, email, phone, status, code, sheet_row = row

                name = normalize(name)
                email = normalize(email)
                status = normalize(status)
                code = normalize(code)

                if not is_paid(status):
                    skip_paid += 1
                    self.log_message(f"⏭ SKIP (not PAID): {name} [{status}]")
                    continue

                if not email:
                    skip_email += 1
                    self.log_message(f"⏭ SKIP (no email): {name}")
                    continue

                if code:
                    skip_has_code += 1
                    continue

                token = generate_token(12)
                qr_url = f"https://bit.ly/thisisfullycustom?id={token}"
                qr_path = os.path.join(QR_OUT, f"{token}.png")

                try:
                    img = qrcode.make(qr_url)
                    img.save(qr_path)
                    self.log_message(f"📦 QR generated: {token}")
                except Exception as e:
                    self.log_message(f"❌ QR failed for {name}: {e}")
                    continue

                html = make_email_html(
                    name=name,
                    token=token,
                    event=EVENT_NAME,
                    venue=VENUE,
                    datetime_str=EVENT_DATETIME
                )

                try:
                    msg = create_message(
                        SENDER_EMAIL,
                        email,
                        f"Tiket Digital – {EVENT_NAME}",
                        html,
                        qr_path
                    )
                    service = gmail_authenticate()
                    send_message(service, msg)
                    self.log_message(f"✉️ SENT → {email}")
                except Exception as e:
                    self.log_message(f"❌ EMAIL FAILED {email}: {e}")
                    continue

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    "UPDATE participants SET code=?, sent_at=? WHERE id=?",
                    (token, now, id_)
                )
                conn.commit()

                upsert_code(conn, token, valid=1, used=0, last_used=None)

                try:
                    update_participant_sheet_row(sheet_row, token, now, email=email, name=name)
                except Exception as e:
                    self.log_message(f"⚠️ Sheet Peserta update failed: {e}")

                try:
                    push_code_to_sheet(token, email)
                except Exception as e:
                    self.log_message(f"⚠️ Sheet Codes append failed: {e}")

                sent += 1
                time.sleep(3)

            conn.close()
            self.log_message(
                f"✅ DONE → Sent:{sent}, Skipped(not PAID):{skip_paid}, Skipped(no email):{skip_email}, Skipped(has code):{skip_has_code}"
            )

        threading.Thread(target=job, daemon=True).start()


if __name__ == "__main__":
    root = Tk()
    app = App(root)
    root.mainloop()
