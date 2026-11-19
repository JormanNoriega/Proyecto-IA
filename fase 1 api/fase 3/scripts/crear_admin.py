"""Crear el primer administrador sin credenciales predeterminadas."""
import getpass
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.main import db, password_hash

username = input("Nombre de usuario administrador: ").strip()
password = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
if len(username) < 3 or len(password) < 10:
    raise SystemExit("Usuario de al menos 3 caracteres y contraseña de al menos 10.")
if password != getpass.getpass("Confirmar contraseña: "):
    raise SystemExit("Las contraseñas no coinciden.")
try:
    with db() as con:
        if con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]:
            raise SystemExit("Ya existe un administrador. Crea otras cuentas desde la aplicación.")
        con.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)", (username, password_hash(password), "admin"))
except sqlite3.IntegrityError:
    raise SystemExit("El usuario ya existe.")
print("Administrador creado.")
