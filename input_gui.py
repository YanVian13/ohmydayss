import gspread
from tkinter import Tk, Label, Entry, Button, StringVar, ttk, messagebox, Frame, END
from oauth2client.service_account import ServiceAccountCredentials

SPREADSHEET_NAME = "QR Code Database"
SHEET_NAME = "Peserta"

# === Fungsi koneksi Google Sheets ===
def get_sheet():
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)

# === GUI Utama ===
class InputApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🧾 Input Data Peserta - QR Ticketing")
        self.root.geometry("600x400")
        self.sheet = get_sheet()

        Label(root, text="Form Input Peserta", font=("Segoe UI", 16, "bold")).pack(pady=10)

        form_frame = Frame(root)
        form_frame.pack(pady=10)

        # --- Input Fields ---
        Label(form_frame, text="Nama Peserta:", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.nama = Entry(form_frame, width=40)
        self.nama.grid(row=0, column=1)

        Label(form_frame, text="Email:", font=("Segoe UI", 11)).grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.email = Entry(form_frame, width=40)
        self.email.grid(row=1, column=1)

        Label(form_frame, text="Nomor HP:", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.hp = Entry(form_frame, width=40)
        self.hp.grid(row=2, column=1)


        # --- Buttons ---
        Button(root, text="💾 Simpan ke Sheets", command=self.save_data, bg="#059669", fg="white", font=("Segoe UI", 11), width=20).pack(pady=5)
        Button(root, text="🔄 Sinkronkan Data", command=self.load_data, bg="#2563eb", fg="white", font=("Segoe UI", 11), width=20).pack(pady=5)

        # --- Table for displaying data ---
        self.tree = ttk.Treeview(root, columns=("nama", "email", "hp", "status"), show="headings", height=8)
        self.tree.heading("nama", text="Nama Peserta")
        self.tree.heading("email", text="Email")
        self.tree.heading("hp", text="Nomor HP")
        self.tree.heading("status", text="Status")
        self.tree.column("nama", width=150)
        self.tree.column("email", width=150)
        self.tree.column("hp", width=100)
        self.tree.column("status", width=80)
        self.tree.pack(pady=10, fill="x")

        self.load_data()

    def load_data(self):
        """Membaca data dari Google Sheets dan menampilkannya di tabel"""
        try:
            for row in self.tree.get_children():
                self.tree.delete(row)
            data = self.sheet.get_all_records()
            for row in data:
                self.tree.insert("", END, values=(row["Nama Peserta"], row["Email"], row["Nomor HP"], row["Status"]))
        except Exception as e:
            messagebox.showerror("Error", f"Gagal memuat data:\n{e}")

    def save_data(self):
        """Menyimpan data baru ke Google Sheets"""
        nama = self.nama.get().strip()
        email = self.email.get().strip()
        hp = self.hp.get().strip()
        status = "PAID"

        if not (nama and email and hp):
            messagebox.showwarning("Input Kosong", "Harap isi semua data peserta!")
            return

        try:
            self.sheet.append_row([nama, email, hp, status, "", ""])
            messagebox.showinfo("Berhasil", f"Data {nama} berhasil ditambahkan.")
            self.nama.delete(0, END)
            self.email.delete(0, END)
            self.hp.delete(0, END)
            self.load_data()
        except Exception as e:
            messagebox.showerror("Error", f"Gagal menyimpan data:\n{e}")

# === MAIN ===
if __name__ == "__main__":
    root = Tk()
    app = InputApp(root)
    root.mainloop()
