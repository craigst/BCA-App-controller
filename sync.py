import os
import sqlite3
import subprocess
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_batch
import tkinter as tk
from tkinter import filedialog, ttk

# Load environment variables
load_dotenv()

# Configuration from .env
DB_PATH = os.getenv('TEMP_DB_PATH')
SOURCE_PATH = os.getenv('SOURCE_DB_PATH')
LOCAL_DB = os.getenv('LOCAL_DB_PATH')
PG_HOST = os.getenv('PG_HOST')
PG_PORT = os.getenv('PG_PORT')
PG_DATABASE = os.getenv('PG_DATABASE')
PG_USERNAME = os.getenv('PG_USERNAME')
PG_PASSWORD = os.getenv('PG_PASSWORD')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 60))

class DatabaseSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Database Sync Manager")
        self.polling_enabled = False
        self.poll_interval = POLL_INTERVAL

        self.create_ui()

    def create_ui(self):
        frame = tk.Frame(self.root, padx=40, pady=40)
        frame.pack(expand=True)

        button_width = 60
        button_height = 2
        entry_width = 40
        
        # Increased font size to 16
        tk.Label(frame, text="Polling Interval (seconds):", font=('Arial', 16)).grid(row=0, column=0, sticky=tk.W, pady=20)
        self.poll_entry = tk.Entry(frame, width=entry_width, font=('Arial', 16))
        self.poll_entry.insert(0, str(self.poll_interval))
        self.poll_entry.grid(row=0, column=1, pady=20)

        self.poll_button = tk.Button(frame, text="Start Polling", command=self.toggle_polling, 
                                    width=button_width, height=button_height, font=('Arial', 16))
        self.poll_button.grid(row=1, column=0, pady=20)

        # Update all other buttons with larger font
        self.pull_button = tk.Button(frame, text="Pull Database", command=self.pull_database, 
                                    width=button_width, height=button_height, font=('Arial', 16))
        self.pull_button.grid(row=1, column=1, pady=20)

        self.push_button = tk.Button(frame, text="Push Database", command=self.push_database, 
                                    width=button_width, height=button_height, font=('Arial', 16))
        self.push_button.grid(row=2, column=0, pady=20)

        self.backup_button = tk.Button(frame, text="Create Backup", command=self.create_backup, 
                                    width=button_width, height=button_height, font=('Arial', 16))
        self.backup_button.grid(row=2, column=1, pady=20)

        self.sync_button = tk.Button(frame, text="Sync to PostgreSQL", command=self.sync_to_postgresql, 
                                    width=button_width, height=button_height, font=('Arial', 16))
        self.sync_button.grid(row=3, column=0, pady=20)

        self.status_label = tk.Label(frame, text="Status: Idle", fg="blue", font=('Arial', 16))
        self.status_label.grid(row=4, column=0, columnspan=2, pady=20)

    def toggle_polling(self):
        if self.polling_enabled:
            self.polling_enabled = False
            self.poll_button.config(text="Start Polling")
            self.status_label.config(text="Status: Polling stopped", fg="red")
        else:
            try:
                self.poll_interval = int(self.poll_entry.get())
                if self.poll_interval <= 0:
                    raise ValueError
                self.polling_enabled = True
                self.poll_button.config(text="Stop Polling")
                self.status_label.config(text="Status: Polling started", fg="green")
                threading.Thread(target=self.poll_for_changes, daemon=True).start()
            except ValueError:
                print("Invalid polling interval")

    def poll_for_changes(self):
        last_modified_time = None
        while self.polling_enabled:
            try:
                current_modified_time = self.get_remote_file_modified_time()
                if current_modified_time and current_modified_time != last_modified_time:
                    self.status_label.config(text="Status: Database changed, pulling...", fg="orange")
                    if self.pull_database():
                        last_modified_time = current_modified_time
                        self.status_label.config(text="Status: Database updated locally", fg="green")
            except Exception as e:
                print(f"Polling error: {e}")
            time.sleep(self.poll_interval)

    def get_remote_file_modified_time(self):
        cmd = f"adb shell stat -c '%Y' {SOURCE_PATH}"
        result = execute_command(cmd)
        if result and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
        return None

    def pull_database(self):
        cmd = f"adb pull {SOURCE_PATH} {DB_PATH}"
        result = execute_command(cmd)
        if result and os.path.exists(DB_PATH):
            print("Database pulled successfully")
            return True
        print("Failed to pull database")
        return False

    def push_database(self):
        if not os.path.exists(DB_PATH):
            print("No database file to push")
            return

        cmd = f"adb push {DB_PATH} {SOURCE_PATH}"
        result = execute_command(cmd)
        if result:
            print("Database pushed successfully")
        else:
            print("Failed to push database")

    def create_backup(self):
        if not os.path.exists(DB_PATH):
            print("No database file to back up")
            return

        backup_dir = "./manual_backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")

        try:
            with open(DB_PATH, "rb") as src, open(backup_path, "wb") as dst:
                dst.write(src.read())
            print(f"Backup created at {backup_path}")
        except Exception as e:
            print(f"Failed to create backup: {e}")

    def sync_to_postgresql(self):
        if not os.path.exists(DB_PATH):
            print("No database file to sync")
            return

        try:
            conn = psycopg2.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DATABASE,
                user=PG_USERNAME,
                password=PG_PASSWORD
            )
            cursor = conn.cursor()

            with sqlite3.connect(DB_PATH) as sqlite_conn:
                sqlite_cursor = sqlite_conn.cursor()

                # Dynamically handle DWJJOB
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

                # Dynamically handle DWVVEH
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

            conn.commit()
            print("Data synced to PostgreSQL")
        except Exception as e:
            print(f"Failed to sync data: {e}")
        finally:
            if 'conn' in locals():
                conn.close()


def execute_command(cmd):
    print(f"Executing: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=30)
        if result.returncode == 0:
            return result
        print(f"Error: {result.stderr}")
    except Exception as e:
        print(f"Command execution failed: {e}")
    return None


def main():
    print("Starting in terminal mode. Press 1 to load UI.")
    choice = input("Enter your choice: ")
    if choice == "1":
        root = tk.Tk()
        app = DatabaseSyncApp(root)
        root.mainloop()
    else:
        print("Running in headless mode...")


if __name__ == "__main__":
    main()
1