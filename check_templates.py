# check_templates.py
import os
basedir = os.path.dirname(os.path.abspath(__file__))
tpl_dir = os.path.join(basedir, "templates")
print("Berdasarkan file ini:", __file__)
print("Project base dir:", basedir)
print("Mencari folder templates di:", tpl_dir)
print("Folder exists?:", os.path.isdir(tpl_dir))
if os.path.isdir(tpl_dir):
    print("Isi folder templates:")
    for f in sorted(os.listdir(tpl_dir)):
        print(" -", f)
else:
    print("Folder templates tidak ada di lokasi itu. Pastikan kamu menjalankan skrip dari folder proyek yang benar.")
