# generate_qr_batch.py
import os
import csv
import secrets
import qrcode
from datetime import datetime

# Optional Google Sheets support:
try:
    from oauth2client.service_account import ServiceAccountCredentials
    import gspread
    GS_AVAILABLE = True
except Exception:
    GS_AVAILABLE = False

OUTPUT_DIR = "output_qr"
CSV_FILE = "tickets.csv"      # local record of generated tokens
URL_PREFIX = "https://bit.ly/thisisfullycustom?id="
SPREADSHEET_NAME = "QR Code Database"
SHEET_PESERTA = "Peserta"
SHEET_CODES = "Codes"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_token(nbytes=16):
    return secrets.token_urlsafe(nbytes).upper()

def make_qr(token):
    url = f"{URL_PREFIX}{token}"
    img = qrcode.make(url)
    filename = os.path.join(OUTPUT_DIR, f"qr_{token}.png")
    img.save(filename)
    return filename, url

def append_to_csv(token, filename):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["Token","File","CreatedAt"])
        w.writerow([token, filename, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# --- Optional: Google Sheets helpers ---
def gs_client_from_credentials(path='credentials.json'):
    if not GS_AVAILABLE:
        raise RuntimeError("gspread not installed")
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(path, scope)
    return gspread.authorize(creds)

def generate_from_sheet():
    client = gs_client_from_credentials()
    ws = client.open(SPREADSHEET_NAME).worksheet(SHEET_PESERTA)
    records = ws.get_all_records()
    for idx, r in enumerate(records, start=2):
        status = str(r.get("Status","")).strip().upper()
        code = str(r.get("Kode Unik","")).strip()
        email = str(r.get("Email","")).strip()
        name = str(r.get("Nama Peserta","")).strip()
        if status == "PAID" and (not code):
            token = generate_token()
            fn, url = make_qr(token)
            append_to_csv(token, fn)
            # update Peserta (kol E) and Waktu Kirim (kol F)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                ws.update(f"E{idx}", token)
                ws.update(f"F{idx}", now)
            except Exception as e:
                print("Warning: failed update Peserta sheet:", e)
            # append to Codes sheet (create if necessary)
            try:
                try:
                    ws_codes = client.open(SPREADSHEET_NAME).worksheet(SHEET_CODES)
                except gspread.exceptions.WorksheetNotFound:
                    ss = client.open(SPREADSHEET_NAME)
                    ws_codes = ss.add_worksheet(title=SHEET_CODES, rows="1000", cols="5")
                    ws_codes.update('A1:E1', [["Kode","Valid","Used","LastUsed","UsedBy"]])
                ws_codes.append_row([token,"TRUE","FALSE","",""+email])
            except Exception as e:
                print("Warning: failed append to Codes sheet:", e)
            print(f"Generated for row {idx}: {name} <{email}> -> {token} ({fn})")

def generate_from_csv():
    # If you keep a CSV of participants (with headers), you can implement reading and generating similarly.
    print("CSV-mode generation: implement as needed (tickets.csv used to record created tokens).")

if __name__ == "__main__":
    # choose path: sheet if credentials exist, else manual single generation demo
    if GS_AVAILABLE and os.path.exists("credentials.json"):
        print("Generating QR for PAID entries from Google Sheets...")
        generate_from_sheet()
        print("Done.")
    else:
        # fallback: create a single QR to demonstrate
        t = generate_token()
        fn, url = make_qr(t)
        append_to_csv(t, fn)
        print("Generated single QR:", fn, url)
