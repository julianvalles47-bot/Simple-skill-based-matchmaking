"""Optional local configuration window; run after installing requirements."""
from __future__ import annotations
import os
import secrets
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
process = None


def save_settings():
    env = mode.get()
    server_key = server_key_var.get().strip()
    secret_key = secret_key_var.get().strip()
    if env == "production":
        if not server_key:
            server_key = secrets.token_urlsafe(32)
            server_key_var.set(server_key)
        if not secret_key:
            secret_key = secrets.token_urlsafe(48)
            secret_key_var.set(secret_key)
        if host.get().strip() in ("127.0.0.1", "localhost"):
            if not messagebox.askyesno("Local bind address", "Production is set to localhost, so remote games cannot connect. Keep it local anyway?"):
                return False
    content = "\n".join([
        f"MATCHMAKER_ENV={env}",
        f"MATCHMAKER_HOST={host.get().strip() or '127.0.0.1'}",
        f"MATCHMAKER_PORT={port.get().strip() or '8000'}",
        "MATCHMAKER_DB=matchmaker.sqlite3",
        f"MATCHMAKER_CORS_ORIGINS={cors_origins.get().strip() or '*'}",
        f"MATCHMAKER_SERVER_KEY={server_key}",
        f"MATCHMAKER_SECRET_KEY={secret_key}",
        "",
    ])
    (ROOT / ".env").write_text(content, encoding="utf-8")
    return True


def start_server():
    global process
    if process and process.poll() is None:
        messagebox.showinfo("Server", "The server is already running.")
        return
    if not save_settings():
        return
    log = open(ROOT / "server.log", "a", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "matchmaker"], cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT)
    status.set(f"Starting (PID {process.pid}). API docs: http://{host.get()}:{port.get()}/docs")


def stop_server():
    global process
    if process and process.poll() is None:
        process.terminate()
        status.set("Stop requested. See server.log for output.")
    else:
        status.set("Server is not running.")


root = tk.Tk()
root.title("Indie Matchmaker setup")
root.geometry("520x420")
root.resizable(False, False)
mode = tk.StringVar(value="development")
host = tk.StringVar(value="127.0.0.1")
port = tk.StringVar(value="8000")
cors_origins = tk.StringVar(value="*")
server_key_var = tk.StringVar()
secret_key_var = tk.StringVar()
status = tk.StringVar(value="Ready. Development mode is for local testing only.")

frame = tk.Frame(root, padx=18, pady=14)
frame.pack(fill="both", expand=True)
tk.Label(frame, text="Indie Matchmaker", font=("Segoe UI", 16, "bold")).pack(anchor="w")
tk.Label(frame, text="Local server setup. For public hosting, read the production notes in README.md.", wraplength=475).pack(anchor="w", pady=(4, 12))

def row(label, widget):
    line = tk.Frame(frame)
    line.pack(fill="x", pady=4)
    tk.Label(line, text=label, width=19, anchor="w").pack(side="left")
    widget.pack(side="left", fill="x", expand=True)

row("Mode", tk.OptionMenu(frame, mode, "development", "production"))
row("Bind address", tk.Entry(frame, textvariable=host))
row("Port", tk.Entry(frame, textvariable=port))
row("Browser origins", tk.Entry(frame, textvariable=cors_origins))
row("Server key", tk.Entry(frame, textvariable=server_key_var, show="*"))
row("Signing secret", tk.Entry(frame, textvariable=secret_key_var, show="*"))
buttons = tk.Frame(frame)
buttons.pack(anchor="w", pady=12)
tk.Button(buttons, text="Save settings", command=lambda: (save_settings() and messagebox.showinfo("Saved", "Settings saved to .env"))).pack(side="left", padx=(0, 8))
tk.Button(buttons, text="Start server", command=start_server).pack(side="left", padx=(0, 8))
tk.Button(buttons, text="Stop server", command=stop_server).pack(side="left")
tk.Label(frame, textvariable=status, wraplength=475, fg="#245b37", justify="left").pack(anchor="w", pady=4)
tk.Label(frame, text="Changing to production generates keys if blank. Keep them private; never ship them in a game client.", wraplength=475, fg="#805000", justify="left").pack(anchor="w", pady=4)
root.protocol("WM_DELETE_WINDOW", lambda: (stop_server(), root.destroy()))
root.mainloop()
