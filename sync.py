#!/usr/bin/env python3
import os
import sqlite3
import subprocess
import time
import threading
from datetime import datetime
import configparser
import psycopg2
from psycopg2.extras import execute_batch
import tkinter as tk
from tkinter import filedialog, ttk, simpledialog, messagebox

###########################################
# Global paths and configuration file name
DB_PATH = "temp.db"                         # local file where database is pulled to
SOURCE_PATH = "/sdcard/BCAApp/database.db"  # remote file on phone (adjust as needed)
BACKUP_FOLDER = os.path.join(os.getcwd(), "backups")
METADATA_DB = os.path.join(os.getcwd(), "backup_metadata.db")
CONFIG_FILE = "sql_config.ini"

###########################################
# Utility Functions
def execute_command(cmd):
    """Execute a shell command and return the result."""
    print(f"Executing: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=30)
        if result.returncode == 0:
            return result
        else:
            print(f"Command error: {result.stderr}")
    except Exception as e:
        print(f"Command execution failed: {e}")
    return None

def init_backup_metadata_db():
    """Initialize the SQLite database that stores backup metadata."""
    conn = sqlite3.connect(METADATA_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            timestamp TEXT,
            note TEXT
        );
    """)
    conn.commit()
    conn.close()

init_backup_metadata_db()

def format_date(datestr):
    """Convert a date string in YYYYMMDD format into a more readable format."""
    try:
        dt = datetime.strptime(datestr, "%Y%m%d")
        return dt.strftime("%A %d/%m/%y")
    except Exception as e:
        print(f"Date formatting error: {e}")
        return datestr

###########################################
# Configuration Handling (SQL + Window)
def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    else:
        config['SQL'] = {
            "PG_HOST": "",
            "PG_PORT": "5432",
            "PG_DATABASE": "",
            "PG_USERNAME": "",
            "PG_PASSWORD": "",
            "POLL_INTERVAL": "60"
        }
        config['Window'] = {"geometry": ""}
    return config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        config.write(f)

class SQLConfigDialog(simpledialog.Dialog):
    def body(self, master):
        tk.Label(master, text="PostgreSQL Host:", font=('Arial', 14)).grid(row=0, column=0, sticky="e", pady=5)
        self.host_entry = tk.Entry(master, font=('Arial', 14))
        self.host_entry.grid(row=0, column=1, pady=5)
        tk.Label(master, text="Port:", font=('Arial', 14)).grid(row=1, column=0, sticky="e", pady=5)
        self.port_entry = tk.Entry(master, font=('Arial', 14))
        self.port_entry.grid(row=1, column=1, pady=5)
        self.port_entry.insert(0, "5432")
        tk.Label(master, text="Database:", font=('Arial', 14)).grid(row=2, column=0, sticky="e", pady=5)
        self.database_entry = tk.Entry(master, font=('Arial', 14))
        self.database_entry.grid(row=2, column=1, pady=5)
        tk.Label(master, text="Username:", font=('Arial', 14)).grid(row=3, column=0, sticky="e", pady=5)
        self.username_entry = tk.Entry(master, font=('Arial', 14))
        self.username_entry.grid(row=3, column=1, pady=5)
        tk.Label(master, text="Password:", font=('Arial', 14)).grid(row=4, column=0, sticky="e", pady=5)
        self.password_entry = tk.Entry(master, show="*", font=('Arial', 14))
        self.password_entry.grid(row=4, column=1, pady=5)
        tk.Label(master, text="Polling Interval (sec):", font=('Arial', 14)).grid(row=5, column=0, sticky="e", pady=5)
        self.poll_entry = tk.Entry(master, font=('Arial', 14))
        self.poll_entry.grid(row=5, column=1, pady=5)
        self.poll_entry.insert(0, "60")
        return self.host_entry

    def apply(self):
        self.result = {
            "PG_HOST": self.host_entry.get().strip(),
            "PG_PORT": self.port_entry.get().strip(),
            "PG_DATABASE": self.database_entry.get().strip(),
            "PG_USERNAME": self.username_entry.get().strip(),
            "PG_PASSWORD": self.password_entry.get().strip(),
            "POLL_INTERVAL": int(self.poll_entry.get().strip() or 60)
        }

###########################################
# On startup, load configuration and if SQL settings are empty, show dialog.
config = load_config()
if not config['SQL'].get("PG_HOST"):
    root_temp = tk.Tk()
    root_temp.withdraw()
    dialog = SQLConfigDialog(root_temp, title="SQL Configuration")
    if dialog.result:
        for key, value in dialog.result.items():
            config['SQL'][key] = str(value)
        save_config(config)
    else:
        messagebox.showerror("Error", "SQL configuration is required.")
        exit(1)
    root_temp.destroy()

SQL_CONFIG = dict(config['SQL'])
POLL_INTERVAL = int(SQL_CONFIG.get("POLL_INTERVAL", "60"))

###########################################
# Database Sync Manager (for syncing to PostgreSQL)
class DatabaseManagerSync:
    def __init__(self, host, port, dbname, user, password):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host, port=self.port, database=self.dbname,
                user=self.user, password=self.password
            )
            return True
        except Exception as e:
            print(f"PostgreSQL connection error: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()

###########################################
# Backup Manager Tab
class BackupManagerTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.create_ui()
        self.refresh_backup_list()

    def create_ui(self):
        btn_frame = tk.Frame(self, padx=20, pady=20)
        btn_frame.pack(fill="x")
        self.backup_now_button = tk.Button(btn_frame, text="Backup Now", command=self.backup_now, font=('Arial', 16), width=20)
        self.backup_now_button.grid(row=0, column=0, padx=10, pady=10)
        self.import_backup_button = tk.Button(btn_frame, text="Import Backup", command=self.import_backup, font=('Arial', 16), width=20)
        self.import_backup_button.grid(row=0, column=1, padx=10, pady=10)
        self.view_backup_button = tk.Button(btn_frame, text="View Backup", command=self.view_backup, font=('Arial', 16), width=20)
        self.view_backup_button.grid(row=0, column=2, padx=10, pady=10)
        self.delete_backup_button = tk.Button(btn_frame, text="Delete Backup", command=self.delete_backup, font=('Arial', 16), width=20)
        self.delete_backup_button.grid(row=0, column=3, padx=10, pady=10)
        self.tree = ttk.Treeview(self, columns=("timestamp", "note"), show="headings", selectmode="browse")
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("note", text="Note")
        self.tree.column("timestamp", width=150)
        self.tree.column("note", width=500)
        self.tree.pack(fill="both", expand=True, padx=20, pady=20)

    def backup_now(self):
        # Pull the database from the phone
        cmd = f"adb shell stat -c '%Y' {SOURCE_PATH}"
        result = execute_command(cmd)
        if not result:
            messagebox.showerror("Error", "Phone not connected or cannot access file info.")
            return
        cmd_pull = f"adb pull {SOURCE_PATH} {DB_PATH}"
        result_pull = execute_command(cmd_pull)
        if not result_pull or not os.path.exists(DB_PATH):
            messagebox.showerror("Error", "Failed to pull database from phone.")
            return
        note = simpledialog.askstring("Backup Note", "Enter a note for this backup:")
        if note is None:
            note = ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.db"
        os.makedirs(BACKUP_FOLDER, exist_ok=True)
        backup_path = os.path.join(BACKUP_FOLDER, backup_filename)
        try:
            with open(DB_PATH, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
            conn = sqlite3.connect(METADATA_DB)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO backups (filename, timestamp, note) VALUES (?, ?, ?)",
                           (backup_filename, timestamp, note))
            conn.commit()
            conn.close()
            messagebox.showinfo("Backup", f"Backup created.")
            self.refresh_backup_list()
        except Exception as e:
            messagebox.showerror("Error", "Failed to create backup.")
            print(e)

    def import_backup(self):
        # Let the user select a backup file from anywhere, then import it into our backups folder
        path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.db")])
        if not path:
            return
        note = simpledialog.askstring("Import Backup", "Enter a note for this imported backup:")
        if note is None:
            note = ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.db"
        os.makedirs(BACKUP_FOLDER, exist_ok=True)
        dest_path = os.path.join(BACKUP_FOLDER, backup_filename)
        try:
            with open(path, "rb") as src, open(dest_path, "wb") as dst:
                dst.write(src.read())
            conn = sqlite3.connect(METADATA_DB)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO backups (filename, timestamp, note) VALUES (?, ?, ?)",
                           (backup_filename, timestamp, note))
            conn.commit()
            conn.close()
            messagebox.showinfo("Import Backup", "Backup imported successfully.")
            self.refresh_backup_list()
        except Exception as e:
            messagebox.showerror("Error", "Failed to import backup.")
            print(e)

    def refresh_backup_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        conn = sqlite3.connect(METADATA_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, note FROM backups ORDER BY timestamp DESC")
        for row in cursor.fetchall():
            self.tree.insert("", "end", iid=row[0], values=(row[1], row[2]))
        conn.close()

    def view_backup(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a backup to view.")
            return
        backup_id = selected[0]
        conn = sqlite3.connect(METADATA_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM backups WHERE id = ?", (backup_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            backup_file = os.path.join(BACKUP_FOLDER, row[0])
            if os.path.exists(backup_file):
                if os.name == 'nt':
                    os.startfile(backup_file)
                else:
                    subprocess.call(('xdg-open', backup_file))
            else:
                messagebox.showerror("Error", "Backup file not found.")
        else:
            messagebox.showerror("Error", "Backup record not found.")

    def delete_backup(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a backup to delete.")
            return
        backup_id = selected[0]
        conn = sqlite3.connect(METADATA_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM backups WHERE id = ?", (backup_id,))
        row = cursor.fetchone()
        if row:
            backup_file = os.path.join(BACKUP_FOLDER, row[0])
            if os.path.exists(backup_file):
                try:
                    os.remove(backup_file)
                except Exception as e:
                    messagebox.showerror("Error", "Failed to delete backup file.")
                    conn.close()
                    return
            cursor.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
            conn.commit()
            conn.close()
            messagebox.showinfo("Deleted", "Backup deleted successfully.")
            self.refresh_backup_list()
        else:
            conn.close()
            messagebox.showerror("Error", "Backup record not found.")

###########################################
# Database Comparator Tab
class ComparatorTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.db1_path = None
        self.db2_path = None
        self.create_ui()

    def create_ui(self):
        frame = tk.Frame(self, padx=20, pady=20)
        frame.pack(fill="x")
        tk.Label(frame, text="Database 1:", font=('Arial', 14)).grid(row=0, column=0, sticky="e", pady=5)
        self.db1_entry = tk.Entry(frame, width=50, font=('Arial', 14))
        self.db1_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Button(frame, text="Browse", command=self.browse_db1, font=('Arial', 14)).grid(row=0, column=2, padx=5, pady=5)
        tk.Label(frame, text="Database 2:", font=('Arial', 14)).grid(row=1, column=0, sticky="e", pady=5)
        self.db2_entry = tk.Entry(frame, width=50, font=('Arial', 14))
        self.db2_entry.grid(row=1, column=1, padx=5, pady=5)
        tk.Button(frame, text="Browse", command=self.browse_db2, font=('Arial', 14)).grid(row=1, column=2, padx=5, pady=5)
        tk.Button(frame, text="Compare", command=self.compare_databases, font=('Arial', 16), width=20).grid(row=2, column=1, pady=10)
        self.result_text = tk.Text(self, wrap="none", height=20, width=100, font=('Arial', 12))
        self.result_text.pack(padx=20, pady=20, fill="both", expand=True)

    def browse_db1(self):
        path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.db")])
        if path:
            self.db1_entry.delete(0, tk.END)
            self.db1_entry.insert(0, path)
            self.db1_path = path

    def browse_db2(self):
        path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.db")])
        if path:
            self.db2_entry.delete(0, tk.END)
            self.db2_entry.insert(0, path)
            self.db2_path = path

    def compare_databases(self):
        if not self.db1_path or not self.db2_path:
            messagebox.showwarning("Warning", "Please select two database files to compare.")
            return
        diffs = self.get_differences(self.db1_path, self.db2_path)
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, diffs)

    def get_differences(self, db1, db2):
        diffs = ""
        try:
            conn1 = sqlite3.connect(db1)
            conn2 = sqlite3.connect(db2)
            for table in ["DWJJOB", "DWVVEH"]:
                diffs += f"--- Comparing table {table} ---\n"
                cur1 = conn1.cursor()
                cur2 = conn2.cursor()
                cur1.execute(f"SELECT * FROM {table}")
                rows1 = cur1.fetchall()
                cur2.execute(f"SELECT * FROM {table}")
                rows2 = cur2.fetchall()
                dict1 = {row[0]: row for row in rows1}
                dict2 = {row[0]: row for row in rows2}
                keys1 = set(dict1.keys())
                keys2 = set(dict2.keys())
                added = keys2 - keys1
                removed = keys1 - keys2
                common = keys1 & keys2
                if added:
                    diffs += f"Rows added: {added}\n"
                if removed:
                    diffs += f"Rows removed: {removed}\n"
                for key in common:
                    row1 = dict1[key]
                    row2 = dict2[key]
                    for i, (val1, val2) in enumerate(zip(row1, row2)):
                        if val1 != val2:
                            diffs += f"Table {table}, Row {key}, Column {i} changed from '{val1}' to '{val2}'\n"
                diffs += "\n"
            conn1.close()
            conn2.close()
        except Exception as e:
            diffs += f"Error during comparison: {e}\n"
        return diffs

###########################################
# Sync to PostgreSQL Tab (with stacked layout and smaller text)
class SyncTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.selected_db = None
        self.create_ui()

    def create_ui(self):
        frame = tk.Frame(self, padx=20, pady=20)
        frame.pack(fill="x")
        # Use a smaller font and stack the fields vertically.
        lbl_font = ('Arial', 12)
        ent_font = ('Arial', 12)
        tk.Label(frame, text="PostgreSQL Host:", font=lbl_font).grid(row=0, column=0, sticky="w", pady=5)
        self.pg_host_entry = tk.Entry(frame, font=ent_font, width=40)
        self.pg_host_entry.insert(0, SQL_CONFIG.get("PG_HOST", ""))
        self.pg_host_entry.grid(row=1, column=0, pady=5)
        tk.Label(frame, text="Port:", font=lbl_font).grid(row=2, column=0, sticky="w", pady=5)
        self.pg_port_entry = tk.Entry(frame, font=ent_font, width=20)
        self.pg_port_entry.insert(0, SQL_CONFIG.get("PG_PORT", "5432"))
        self.pg_port_entry.grid(row=3, column=0, pady=5)
        tk.Label(frame, text="Database:", font=lbl_font).grid(row=4, column=0, sticky="w", pady=5)
        self.pg_database_entry = tk.Entry(frame, font=ent_font, width=40)
        self.pg_database_entry.insert(0, SQL_CONFIG.get("PG_DATABASE", ""))
        self.pg_database_entry.grid(row=5, column=0, pady=5)
        tk.Label(frame, text="Username:", font=lbl_font).grid(row=6, column=0, sticky="w", pady=5)
        self.pg_username_entry = tk.Entry(frame, font=ent_font, width=30)
        self.pg_username_entry.insert(0, SQL_CONFIG.get("PG_USERNAME", ""))
        self.pg_username_entry.grid(row=7, column=0, pady=5)
        tk.Label(frame, text="Password:", font=lbl_font).grid(row=8, column=0, sticky="w", pady=5)
        self.pg_password_entry = tk.Entry(frame, font=ent_font, show="*", width=40)
        self.pg_password_entry.insert(0, SQL_CONFIG.get("PG_PASSWORD", ""))
        self.pg_password_entry.grid(row=9, column=0, pady=5)
        tk.Label(frame, text="Backup File (optional):", font=lbl_font).grid(row=10, column=0, sticky="w", pady=5)
        self.backup_file_entry = tk.Entry(frame, font=ent_font, width=50)
        self.backup_file_entry.grid(row=11, column=0, pady=5)
        tk.Button(frame, text="Browse", command=self.browse_backup_file, font=lbl_font).grid(row=11, column=1, padx=5, pady=5)
        tk.Button(self, text="Sync to PostgreSQL", command=self.sync_to_postgresql, font=('Arial', 14), width=25).pack(pady=20)
        self.status_label = tk.Label(self, text="Status: Idle", fg="blue", font=('Arial', 14))
        self.status_label.pack(pady=10)

    def browse_backup_file(self):
        path = filedialog.askopenfilename(initialdir=BACKUP_FOLDER, filetypes=[("SQLite DB", "*.db")])
        if path:
            self.backup_file_entry.delete(0, tk.END)
            self.backup_file_entry.insert(0, path)
            self.selected_db = path

    def sync_to_postgresql(self):
        db_to_sync = self.selected_db if self.selected_db else DB_PATH
        if not os.path.exists(db_to_sync):
            messagebox.showerror("Error", "Database file to sync not found.")
            return
        try:
            db_sync = DatabaseManagerSync(
                host=self.pg_host_entry.get(),
                port=self.pg_port_entry.get(),
                dbname=self.pg_database_entry.get(),
                user=self.pg_username_entry.get(),
                password=self.pg_password_entry.get()
            )
            if not db_sync.connect():
                self.status_label.config(text="Status: Failed to connect to PostgreSQL", fg="red")
                return
            cursor = db_sync.conn.cursor()
            with sqlite3.connect(db_to_sync) as sqlite_conn:
                sqlite_cursor = sqlite_conn.cursor()
                # Sync DWJJOB table (loads)
                sqlite_cursor.execute("PRAGMA table_info(DWJJOB)")
                job_columns = [col[1] for col in sqlite_cursor.fetchall()]
                job_columns_str = ", ".join(job_columns)
                placeholders = ", ".join(["%s"] * len(job_columns))
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS jobs (
                        {', '.join([f'{col} TEXT' for col in job_columns])},
                        PRIMARY KEY (dwjkey)
                    );
                """)
                sqlite_cursor.execute(f"SELECT {job_columns_str} FROM DWJJOB")
                jobs = sqlite_cursor.fetchall()
                execute_batch(
                    cursor,
                    f"""
                    INSERT INTO jobs ({job_columns_str})
                    VALUES ({placeholders})
                    ON CONFLICT (dwjkey) DO UPDATE SET
                    {', '.join([f'{col} = EXCLUDED.{col}' for col in job_columns if col != 'dwjkey'])};
                    """,
                    jobs
                )
                # Sync DWVVEH table (vehicles)
                sqlite_cursor.execute("PRAGMA table_info(DWVVEH)")
                vehicle_columns = [col[1] for col in sqlite_cursor.fetchall()]
                vehicle_columns_str = ", ".join(vehicle_columns)
                placeholders = ", ".join(["%s"] * len(vehicle_columns))
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS vehicles (
                        {', '.join([f'{col} TEXT' for col in vehicle_columns])},
                        PRIMARY KEY (dwvkey)
                    );
                """)
                sqlite_cursor.execute(f"SELECT {vehicle_columns_str} FROM DWVVEH")
                vehicles = sqlite_cursor.fetchall()
                execute_batch(
                    cursor,
                    f"""
                    INSERT INTO vehicles ({vehicle_columns_str})
                    VALUES ({placeholders})
                    ON CONFLICT (dwvkey) DO UPDATE SET
                    {', '.join([f'{col} = EXCLUDED.{col}' for col in vehicle_columns if col != 'dwvkey'])};
                    """,
                    vehicles
                )
            db_sync.conn.commit()
            self.status_label.config(text="Status: Data synced to PostgreSQL", fg="green")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_label.config(text=f"Status: Sync failed: {e}", fg="red")
        finally:
            if 'db_sync' in locals():
                db_sync.close()

###########################################
# Main Application Class
class BCAManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BCA App Data Manager")
        # Load window geometry from config if exists
        self.config_parser = load_config()
        if "Window" in self.config_parser and self.config_parser["Window"].get("geometry"):
            self.geometry(self.config_parser["Window"]["geometry"])
        else:
            self.geometry("1200x800")
        self.create_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_ui(self):
        tab_control = ttk.Notebook(self)
        self.backup_tab = BackupManagerTab(tab_control)
        self.compare_tab = ComparatorTab(tab_control)
        self.sync_tab = SyncTab(tab_control)
        tab_control.add(self.backup_tab, text="Backup Manager")
        tab_control.add(self.compare_tab, text="Database Comparator")
        tab_control.add(self.sync_tab, text="Sync to PostgreSQL")
        tab_control.pack(expand=1, fill="both")

    def on_closing(self):
        # Save the current window geometry into the config file.
        self.config_parser.setdefault("Window", {})
        self.config_parser["Window"]["geometry"] = self.geometry()
        save_config(self.config_parser)
        self.destroy()

def main():
    app = BCAManagerApp()
    app.mainloop()

if __name__ == "__main__":
    main()
