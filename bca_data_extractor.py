#!/usr/bin/env python3
import subprocess
import sqlite3
from dotenv import load_dotenv
import os
import requests
import time
from datetime import datetime

load_dotenv()

DB_PATH = os.getenv('TEMP_DB_PATH')
SOURCE_PATH = os.getenv('SOURCE_DB_PATH')
LOCAL_DB = os.getenv('LOCAL_DB_PATH')
CAR_API_KEY = os.getenv('CAR_API_KEY')

def execute_command(cmd):
    print(f"\nExecuting: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print("Command succeeded")
            return result
        print(f"Command failed with return code: {result.returncode}")
        print(f"Error output: {result.stderr}")
        return None
    except Exception as e:
        print(f"Error executing command: {str(e)}")
        return None

def pull_database():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    cmd = f"adb pull {SOURCE_PATH} {DB_PATH}"
    result = execute_command(cmd)
    
    if result and os.path.exists(DB_PATH):
        print("Database pulled successfully")
        return True
    return False

def push_database():
    if not os.path.exists(DB_PATH):
        print("No database file found to push")
        return False
    
    cmd = f"adb push {DB_PATH} {SOURCE_PATH}"
    result = execute_command(cmd)
    return bool(result)

def view_jobs():
    if not os.path.exists(DB_PATH):
        print("No database file found. Please pull data first.")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                dwjLoad as 'Load Number',
                dwjCust as 'Contractor',
                dwjVehs as 'Cars',
                dwjName as 'Location',
                dwjAdrCod as 'Location Code',
                CASE dwjType 
                    WHEN 'C' THEN 'Collection'
                    WHEN 'D' THEN 'Delivery'
                    ELSE dwjType
                END as 'Type'
            FROM DWJJOB
            ORDER BY dwjLoad
        """)
        
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        widths = []
        for i in range(len(columns)):
            column_data = [str(row[i]) for row in rows]
            widths.append(max(len(str(columns[i])), max(len(str(x)) for x in column_data)))

        print("\n=== BCA Track Jobs ===\n")
        header = "  ".join(f"{columns[i]:<{widths[i]}}" for i in range(len(columns)))
        print(header)
        print("-" * len(header))
        
        for row in rows:
            print("  ".join(f"{str(item):<{widths[i]}}" for i, item in enumerate(row)))
        print(f"\nTotal records found: {len(rows)}")

    except sqlite3.Error as e:
        print(f"\nDatabase error: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

def view_vehicles():
    if not os.path.exists(DB_PATH):
        print("No database file found. Please pull data first.")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT
                v.dwvVehRef as 'Registration',
                v.dwvModDes as 'Vehicle',
                v.dwvColCod as 'Collection',
                v.dwvDelCod as 'Delivery'
            FROM DWVVEH v
            INNER JOIN DWJJOB j ON v.dwvLoad = j.dwjLoad
            ORDER BY v.dwvVehRef
        """)
        
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        widths = []
        for i in range(len(columns)):
            column_data = [str(row[i]) for row in rows]
            widths.append(max(len(str(columns[i])), max(len(str(x)) for x in column_data)))

        print("\n=== Active Vehicle List ===\n")
        header = "  ".join(f"{columns[i]:<{widths[i]}}" for i in range(len(columns)))
        print(header)
        print("-" * len(header))
        
        for row in rows:
            print("  ".join(f"{str(item):<{widths[i]}}" for i, item in enumerate(row)))
        
        print(f"\nTotal active vehicles found: {len(rows)}")

    except sqlite3.Error as e:
        print(f"\nDatabase error: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

def try_api_request(reg, max_retries=3, delay=5):
    """Helper function to handle API requests with retries"""
    for attempt in range(max_retries):
        try:
            url = "https://api.checkcardetails.co.uk/vehicledata/vehicleregistration"
            params = {
                "apikey": CAR_API_KEY,
                "vrm": reg
            }
            
            print(f"Attempt {attempt + 1} of {max_retries}")
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                print("All retry attempts failed")
                return None

def find_missing_cars():
    if not os.path.exists(DB_PATH):
        print("No database file found. Please pull data first.")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT dwvVehRef, dwvModDes 
            FROM DWVVEH 
            WHERE dwvModDes IS NULL 
            OR dwvModDes = ''
            OR dwvModDes NOT LIKE '% %'
            ORDER BY dwvVehRef
        """)
        
        missing_cars = cursor.fetchall()
        
        if not missing_cars:
            print("No vehicles with missing make/model found.")
            return
            
        print(f"\nFound {len(missing_cars)} vehicles with missing details.")
        choice = input("Would you like to update them? (y/n): ")
        
        if choice.lower() != 'y':
            return
            
        for reg, current_model in missing_cars:
            print(f"\nProcessing registration: {reg}")
            print(f"Current make/model: {current_model or 'Empty'}")
            
            data = try_api_request(reg)
            
            if data and "make" in data and "model" in data:
                make = data.get("make", "")
                model = data.get("model", "")
                full_details = f"{make} {model}".strip()
                
                print(f"Found: {full_details}")
                
                cursor.execute("""
                    UPDATE DWVVEH 
                    SET dwvModDes = ? 
                    WHERE dwvVehRef = ?
                """, (full_details, reg))
                
                conn.commit()
                print("Database updated successfully")
            else:
                print("No valid details found for this vehicle")
            
            time.sleep(5)
                
        print("\nFinished processing all vehicles")
        
    except sqlite3.Error as e:
        print(f"\nDatabase error: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

def export_to_local_db():
    """Export selected data to local SQLite database"""
    if not os.path.exists(DB_PATH):
        print("No source database found. Please pull data first.")
        return
        
    try:
        source_conn = sqlite3.connect(DB_PATH)
        local_conn = sqlite3.connect(LOCAL_DB)
        source_cur = source_conn.cursor()
        local_cur = local_conn.cursor()
        
        # Create jobs table (unchanged)
        local_cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                load_number TEXT,
                contractor TEXT,
                cars INTEGER,
                location TEXT,
                location_code TEXT,
                town TEXT,
                postcode TEXT,
                load_date INTEGER,
                latitude TEXT,
                longitude TEXT,
                job_type TEXT,
                PRIMARY KEY (load_number, job_type)
            )
        """)
        
        # Enhanced vehicles table with new columns and defaults
        local_cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                registration TEXT,
                vehicle TEXT,
                collection TEXT,
                delivery TEXT,
                load_number TEXT,
                notes TEXT DEFAULT '',
                photos TEXT DEFAULT '[]',
                offloaded TEXT DEFAULT 'no',
                docs TEXT DEFAULT 'yes',
                skeys TEXT DEFAULT 'yes',
                PRIMARY KEY (registration, load_number)
            )
        """)
        
        # Get jobs data (unchanged)
        source_cur.execute("""
            SELECT 
                dwjLoad,
                dwjCust,
                dwjVehs,
                dwjName,
                dwjAdrCod,
                dwjTown,
                dwjPostco,
                dwjDate,
                dwjLat,
                dwjLong,
                CASE dwjType 
                    WHEN 'C' THEN 'Collection'
                    WHEN 'D' THEN 'Delivery'
                    ELSE dwjType
                END
            FROM DWJJOB
            ORDER BY dwjLoad
        """)
        jobs = source_cur.fetchall()
        
        # Get vehicles data
        source_cur.execute("""
            SELECT 
                v.dwvVehRef,
                v.dwvModDes,
                v.dwvColCod,
                v.dwvDelCod,
                v.dwvLoad
            FROM DWVVEH v
            INNER JOIN DWJJOB j ON v.dwvLoad = j.dwjLoad
            ORDER BY v.dwvLoad, v.dwvVehRef
        """)
        vehicles = source_cur.fetchall()
        
        # Insert jobs (unchanged)
        for job in jobs:
            try:
                local_cur.execute("""
                    INSERT OR REPLACE INTO jobs 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, job)
            except sqlite3.IntegrityError as e:
                print(f"Job insert error: {e} for load {job[0]}")
        
        # Insert vehicles with default values for new columns
        for vehicle in vehicles:
            try:
                local_cur.execute("""
                    INSERT OR REPLACE INTO vehicles 
                    (registration, vehicle, collection, delivery, load_number)
                    VALUES (?, ?, ?, ?, ?)
                """, vehicle)
            except sqlite3.IntegrityError as e:
                print(f"Vehicle insert error: {e} for reg {vehicle[0]}")
                
        local_conn.commit()
        
        # Print detailed summary
        local_cur.execute("SELECT COUNT(*) FROM jobs")
        jobs_count = local_cur.fetchone()[0]
        local_cur.execute("SELECT COUNT(DISTINCT load_number) FROM jobs")
        unique_loads = local_cur.fetchone()[0]
        local_cur.execute("SELECT COUNT(*) FROM vehicles")
        vehicles_count = local_cur.fetchone()[0]
        
        print(f"\nExport completed successfully:")
        print(f"Total jobs exported: {jobs_count}")
        print(f"Unique load numbers: {unique_loads}")
        print(f"Total vehicles exported: {vehicles_count}")
        
    except sqlite3.Error as e:
        print(f"\nDatabase error: {str(e)}")
    finally:
        if 'source_conn' in locals():
            source_conn.close()
        if 'local_conn' in locals():
            local_conn.close()

def main_menu():
    while True:
        print("\nBCA Track Database Manager")
        print("1. Pull Database from Phone")
        print("2. Push Database to Phone")
        print("3. View BCA Track Jobs")
        print("4. View Vehicles")
        print("5. Find Missing Car Details")
        print("6. Export to Local Database")
        print("7. Exit")
        
        choice = input("\nEnter your choice (1-7): ")

        if choice == '1':
            pull_database()
        elif choice == '2':
            push_database()
        elif choice == '3':
            view_jobs()
        elif choice == '4':
            view_vehicles()
        elif choice == '5':
            find_missing_cars()
        elif choice == '6':
            export_to_local_db()
        elif choice == '7':
            if os.path.exists("/tmp/bca_temp.db"):
                os.remove("/tmp/bca_temp.db")
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main_menu()
