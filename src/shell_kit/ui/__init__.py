"""
Antarmuka grafis opsional untuk shell-kit.

Dijalankan lewat `shell-kit ui`. Bagian ini TIDAK pernah menjalankan engine di
dalam prosesnya sendiri: ia menyusun daftar argumen lalu memanggil CLI sebagai
subprocess.

Aturan itu bukan gaya semata. Repo ini pernah punya UI Streamlit yang
meng-import potongan engine lalu menulis ulang orkestrasinya, sehingga ada dua
implementasi yang harus dijaga sinkron. UI itu akhirnya dihapus. Dengan
memanggil CLI, UI tidak bisa melenceng — ia menjalankan jalur kode yang sama
persis, sehingga setiap opsi dan setiap pemeriksaan code otomatis ikut.
"""
