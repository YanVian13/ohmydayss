# common.py
import os
import sqlite3
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import secrets
from google.oauth2.service_account import Credentials

DB_FILE = "data.db"
SPREADSHEET_NAME = "QR Code Database"
SHEET_PESERTA = "Peserta"
SHEET_CODES = "Codes"

# initialize output folder
QR_DIR = "output_qr"
os.makedirs("output_qr", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)
    cur = conn.cursor()
    # table participants mirror sheet Peserta
    cur.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        phone TEXT,
        status TEXT,
        code TEXT,
        sent_at TEXT,
        sheet_row INTEGER  -- optional mapping to sheet row index
    )
    """)
    # codes table for verifier
    cur.execute("""
    CREATE TABLE IF NOT EXISTS codes (
        code TEXT PRIMARY KEY,
        valid INTEGER DEFAULT 1,
        used INTEGER DEFAULT 0,
        last_used TEXT,
        used_by TEXT
    )
    """)
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)

def get_sheet():
    # pastikan credentials.json adalah service account key JSON
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        raise FileNotFoundError("credentials.json (service account) tidak ditemukan.")
    gc = gspread.service_account(filename=creds_path)
    sh = gc.open(SPREADSHEET_NAME)
    return sh.worksheet(SHEET_PESERTA)

# sheets client
def get_sheets_client():
    if not os.path.exists("credentials.json"):
        raise FileNotFoundError("credentials.json not found (service account).")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    return client

def open_worksheet(name):
    client = get_sheets_client()
    ss = client.open(SPREADSHEET_NAME)
    return ss.worksheet(name)

def generate_token(nbytes=12):
    # urlsafe base token (length roughly 16-24 chars)
    return secrets.token_urlsafe(nbytes).upper()

# Sync helpers (lightweight)
def sync_from_sheets():
    """
    Pull data from Sheets (Peserta and Codes) -> upsert into SQLite.
    This is called at startup or manually.
    """
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    try:
        ws = open_worksheet(SHEET_PESERTA)
    except Exception as e:
        print("Cannot open Peserta sheet:", e)
        conn.close()
        return

    records = ws.get_all_records()
    # helper aman: ambil value, ubah jadi str, lalu strip
    def safe(record, key):
        v = record.get(key, "")
        if v is None:
            return ""
        return str(v).strip()

    # We'll map by email+name pair to upsert
    for idx, r in enumerate(records, start=2):
        try:
            name = safe(r, "Nama Peserta")
            email = safe(r, "Email")
            phone = safe(r, "Nomor HP")
            status = safe(r, "Status").upper()
            code = safe(r, "Kode Unik")
            sent_at = safe(r, "Waktu Kirim")
            # upsert by email+name (simple heuristic)
            cur.execute("SELECT id FROM participants WHERE email=? AND name=?", (email, name))
            row = cur.fetchone()
            if row:
                cur.execute("""UPDATE participants SET phone=?, status=?, code=?, sent_at=?, sheet_row=? WHERE id=?""",
                            (phone, status, code, sent_at, idx, row[0]))
            else:
                cur.execute("""INSERT INTO participants (name,email,phone,status,code,sent_at,sheet_row)
                               VALUES (?,?,?,?,?,?,?)""",
                            (name, email, phone, status, code, sent_at, idx))
        except Exception as e:
            # jangan crash keseluruhan; log dan lanjut
            print(f"⚠️ Error processing Peserta row {idx}: {e}")
            continue

    # sync codes sheet
    try:
        ws_codes = open_worksheet(SHEET_CODES)
        codes = ws_codes.get_all_records()
        for r in codes:
            try:
                # coba beberapa nama kolom yang mungkin berbeda
                code = r.get("Kode") or r.get("Code") or r.get("UniqueCode") or r.get("unique_code") or ""
                code = str(code).strip()
                if not code:
                    continue
                valid_raw = r.get("Valid", "TRUE")
                used_raw = r.get("Used", "")
                last_used = r.get("LastUsed", "") or ""
                used_by = r.get("UsedBy", "") or ""
                valid = 1 if str(valid_raw).strip().upper() in ("TRUE", "1", "YES", "Y") else 0
                used = 1 if str(used_raw).strip().upper() in ("TRUE", "1", "YES", "Y") else 0
                cur.execute("INSERT OR REPLACE INTO codes (code, valid, used, last_used, used_by) VALUES (?,?,?,?,?)",
                            (code, valid, used, last_used, used_by))
            except Exception as e:
                print(f"⚠️ Error processing Codes row: {e}")
                continue
    except gspread.exceptions.WorksheetNotFound:
        # no Codes sheet yet; ignore
        pass
    conn.commit()
    conn.close()


def push_code_to_sheet(code, email):
    """
    Append new code row to Codes sheet. If sheet not exist, create it.
    Also convenient to update Peserta row externally — we'll handle Peserta updates outside.
    """
    try:
        ws_codes = open_worksheet(SHEET_CODES)
    except gspread.exceptions.WorksheetNotFound:
        client = get_sheets_client()
        ss = client.open(SPREADSHEET_NAME)
        ws_codes = ss.add_worksheet(title=SHEET_CODES, rows="1000", cols="5")
        ws_codes.update('A1:E1', [["Kode","Valid","Used","LastUsed","UsedBy"]])
    ws_codes.append_row([code, "TRUE", "FALSE", "", email])

# common.py — ganti fungsi ini dengan versi yang lebih toleran
def update_participant_sheet_row(sheet_row, code, sent_at, email=None, name=None):
    """
    Update Peserta sheet kolom E (Kode Unik) dan F (Waktu Kirim).
    Kompatibel dengan gspread v6.x+ (values harus berupa list of lists).
    """
    try:
        ws = open_worksheet(SHEET_PESERTA)
    except Exception as e:
        print("Failed opening Peserta sheet:", e)
        return

    def safe_update(cell_addr, value):
        """Pastikan update memakai list of lists."""
        try:
            ws.update(cell_addr, [[value]])
        except Exception as e:
            print(f"Warn: failed update {cell_addr} -> {value}: {e}")

    def safe_find(query):
        """Cari cell tanpa bergantung ke CellNotFound."""
        try:
            return ws.find(query)
        except Exception:
            return None

    # 1️⃣ update langsung jika sheet_row valid
    if sheet_row and isinstance(sheet_row, int) and sheet_row > 1:
        safe_update(f"E{sheet_row}", code)
        safe_update(f"F{sheet_row}", sent_at)
        return

    # 2️⃣ fallback cari email
    if email:
        cell = safe_find(email)
        if cell:
            safe_update(f"E{cell.row}", code)
            safe_update(f"F{cell.row}", sent_at)
            return

    # 3️⃣ fallback cari nama
    if name:
        cell = safe_find(name)
        if cell:
            safe_update(f"E{cell.row}", code)
            safe_update(f"F{cell.row}", sent_at)
            return

    print("Warning: Could not update Peserta sheet row (no sheet_row, no email/name match).")



# init DB on import
init_db()
