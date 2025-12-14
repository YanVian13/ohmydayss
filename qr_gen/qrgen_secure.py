#!/usr/bin/env python3
"""
QR Code Generator (Secure Version)
----------------------------------
- Membuat token acak aman (base64-url).
- Menyimpan hasil QR di folder 'output_qr'.
- Mencatat semua kode dan waktu pembuatan di 'tickets.csv'.
- Opsional: bisa otomatis mengisi Google Sheets.
"""

import os
import csv
import secrets
import qrcode
from datetime import datetime
from pathlib import Path

# === Konfigurasi dasar ===
URL_PREFIX = "https://bit.ly/thisisfullycustom?id="
OUTPUT_DIR = Path("output_qr")
CSV_FILE = Path("tickets.csv")

# === Setup direktori ===
OUTPUT_DIR.mkdir(exist_ok=True)

def generate_secure_token(length: int = 24) -> str:
    """Generate token acak aman (URL-safe)."""
    return secrets.token_urlsafe(length)

def make_qr_image(token: str) -> str:
    """Membuat QR code dari token dan menyimpannya sebagai file PNG."""
    url = f"{URL_PREFIX}{token}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    filename = OUTPUT_DIR / f"qr_{token[:8]}.png"
    img.save(filename)
    return str(filename)

def append_to_csv(token: str, filename: str):
    """Mencatat token & file ke CSV dan (opsional) ke Google Sheets."""
    file_exists = CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Token", "File", "CreatedAt"])
        writer.writerow([token, filename, datetime.now().isoformat(sep=" ", timespec="seconds")])

    # opsional: kirim otomatis ke Google Sheets
try:
    from oauth2client.service_account import ServiceAccountCredentials
    import gspread
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open('QR Code Database').worksheet('Codes')
    sheet.append_row([token, ''])
except Exception as e:
    print("⚠️ Gagal sync ke Google Sheets:", e)



def main():
    print("=== Secure QR Generator ===")
    print("Ketik jumlah QR yang ingin dibuat atau 'exit' untuk keluar.\n")

    while True:
        cmd = input("Masukkan jumlah QR (atau 'exit'): ").strip()
        if cmd.lower() in ("exit", "quit"):
            print("Keluar dari generator.")
            break

        if not cmd.isdigit() or int(cmd) <= 0:
            print("⚠️ Masukkan angka positif.")
            continue

        count = int(cmd)
        for i in range(1, count + 1):
            token = generate_secure_token()
            filename = make_qr_image(token)
            append_to_csv(token, filename)
            print(f"[{i}/{count}] ✅ QR dibuat: {filename}")
        print(f"\n✨ {count} QR Code berhasil dibuat!\n")

if __name__ == "__main__":
    main()
