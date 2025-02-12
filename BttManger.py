#!/usr/bin/env python3
import sys
import logging
from datetime import datetime

import psycopg2
from PyQt5 import QtWidgets, QtCore

# Configure logging for error debugging.
logging.basicConfig(
    filename="error.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s",
)

# -------------------------
# Helper function for date formatting
# -------------------------
def format_date(datestr):
    """
    Convert a date string in YYYYMMDD format into a more readable format,
    e.g., "Monday 22/01/25"
    """
    try:
        dt = datetime.strptime(datestr, "%Y%m%d")
        return dt.strftime("%A %d/%m/%y")
    except Exception as e:
        logging.exception("Failed to format date: %s", datestr)
        return datestr

# -------------------------
# Helper function to set table height to content
# -------------------------
def set_table_height_to_content(table):
    header_height = table.horizontalHeader().height()
    row_count = table.rowCount()
    if row_count > 0:
        row_height = table.verticalHeader().defaultSectionSize()
    else:
        row_height = 30
    new_height = header_height + row_count * row_height + 2
    table.setFixedHeight(new_height)

# -------------------------
# Database Manager Class
# -------------------------
class DatabaseManager:
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
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
            )
            self.initialize_car_info_table()
            self.sync_car_info()
            return True
        except Exception as e:
            logging.exception("Database connection failed")
            return False

    def initialize_car_info_table(self):
        """Create the extra car info table if it doesn't exist."""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS car_info (
                    dwvkey TEXT PRIMARY KEY,
                    dwvvehref TEXT,
                    offloaded TEXT DEFAULT 'N',
                    docs TEXT DEFAULT 'Y',
                    sparekeys TEXT DEFAULT 'Y',
                    photos TEXT DEFAULT ''
                );
            """)
            self.conn.commit()
            cur.close()
        except Exception as e:
            logging.exception("Failed to initialize car_info table")
            self.conn.rollback()

    def sync_car_info(self):
        """
        Ensure every vehicle in the vehicles table has a matching record in car_info.
        """
        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO car_info (dwvkey, dwvvehref, offloaded, docs, sparekeys, photos)
                SELECT dwvkey, dwvvehref, 'N', 'Y', 'Y', ''
                FROM vehicles
                ON CONFLICT (dwvkey) DO NOTHING;
            """)
            self.conn.commit()
            cur.close()
        except Exception as e:
            logging.exception("Failed to sync car_info table")
            self.conn.rollback()

    def fetch_loads(self, start_date, end_date):
        """
        Fetch collection loads (jobs where dwjtype = 'C') between start_date and end_date.
        """
        try:
            cur = self.conn.cursor()
            query = """
                SELECT * FROM jobs 
                WHERE dwjdate BETWEEN %s AND %s 
                  AND dwjtype = 'C'
                ORDER BY dwjdate DESC
            """
            cur.execute(query, (start_date, end_date))
            rows = cur.fetchall()
            cur.close()
            return rows
        except Exception as e:
            logging.exception("Failed to fetch loads")
            return []

    def fetch_destination(self, load_id):
        """
        For a given collection load, return the matching destination record (dwjtype = 'D')
        with the same load number.
        """
        try:
            cur = self.conn.cursor()
            query = "SELECT * FROM jobs WHERE dwjload = %s AND dwjtype = 'D' LIMIT 1"
            cur.execute(query, (load_id,))
            dest = cur.fetchone()
            cur.close()
            return dest
        except Exception as e:
            logging.exception("Failed to fetch destination for load %s", load_id)
            return None

    def fetch_collection(self, load_id):
        """
        For a given destination load, return the matching collection record (dwjtype = 'C')
        with the same load number.
        """
        try:
            cur = self.conn.cursor()
            query = "SELECT * FROM jobs WHERE dwjload = %s AND dwjtype = 'C' LIMIT 1"
            cur.execute(query, (load_id,))
            coll = cur.fetchone()
            cur.close()
            return coll
        except Exception as e:
            logging.exception("Failed to fetch collection for destination load %s", load_id)
            return None

    def fetch_vehicle_details(self, load_id):
        """
        Fetch vehicles for a load, joining extra car info.
        Returns a list of tuples:
          (dwvvehref, dwvmoddes, offloaded, docs, sparekeys, photos, dwvkey)
        """
        try:
            cur = self.conn.cursor()
            query = """
                SELECT v.dwvvehref, v.dwvmoddes, c.offloaded, c.docs, c.sparekeys, c.photos, v.dwvkey
                FROM vehicles v
                LEFT JOIN car_info c ON v.dwvkey = c.dwvkey
                WHERE v.dwvload = %s
            """
            cur.execute(query, (load_id,))
            rows = cur.fetchall()
            cur.close()
            return rows
        except Exception as e:
            logging.exception("Failed to fetch vehicle details for load %s", load_id)
            return []

    def update_load(self, load_data):
        """
        Update a load record.
        (Placeholder: implement the UPDATE query as needed.)
        """
        try:
            cur = self.conn.cursor()
            # Example: update query here
            self.conn.commit()
            cur.close()
        except Exception as e:
            logging.exception("Failed to update load")
            self.conn.rollback()

    def add_vehicle(self, vehicle_data):
        """
        Add a new vehicle record.
        (Placeholder: implement the INSERT query as needed.)
        """
        try:
            cur = self.conn.cursor()
            self.conn.commit()
            cur.close()
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO car_info (dwvkey, dwvvehref, offloaded, docs, sparekeys, photos)
                VALUES (%s, %s, 'N', 'Y', 'Y', '')
                ON CONFLICT (dwvkey) DO NOTHING;
            """, (vehicle_data['dwvkey'], vehicle_data['dwvvehref']))
            self.conn.commit()
            cur.close()
        except Exception as e:
            logging.exception("Failed to add vehicle")
            self.conn.rollback()

    def update_vehicle_details(self, dwvkey, new_model, offloaded, docs, sparekeys, photos):
        """
        Update vehicle details in both vehicles and car_info tables.
        """
        try:
            cur = self.conn.cursor()
            cur.execute("UPDATE vehicles SET dwvmoddes = %s WHERE dwvkey = %s", (new_model, dwvkey))
            cur.execute("""
                UPDATE car_info 
                SET offloaded = %s, docs = %s, sparekeys = %s, photos = %s
                WHERE dwvkey = %s
            """, (offloaded, docs, sparekeys, photos, dwvkey))
            self.conn.commit()
            cur.close()
        except Exception as e:
            logging.exception("Failed to update vehicle details for %s", dwvkey)
            self.conn.rollback()

# -------------------------
# Settings Dialog (with saved settings)
# -------------------------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Database Settings")
        self.db_manager = None
        self.settings = QtCore.QSettings("MyCompany", "BttManager")
        self.initUI()

    def initUI(self):
        layout = QtWidgets.QFormLayout(self)

        self.host_edit = QtWidgets.QLineEdit(self.settings.value("host", "localhost"))
        self.port_edit = QtWidgets.QLineEdit(self.settings.value("port", "5432"))
        self.dbname_edit = QtWidgets.QLineEdit(self.settings.value("dbname", "your_database"))
        self.user_edit = QtWidgets.QLineEdit(self.settings.value("user", "postgres"))
        self.password_edit = QtWidgets.QLineEdit(self.settings.value("password", ""))
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)

        layout.addRow("Host:", self.host_edit)
        layout.addRow("Port:", self.port_edit)
        layout.addRow("Database:", self.dbname_edit)
        layout.addRow("Username:", self.user_edit)
        layout.addRow("Password:", self.password_edit)

        btn_connect = QtWidgets.QPushButton("Connect")
        btn_connect.clicked.connect(self.try_connect)
        layout.addRow(btn_connect)

    def try_connect(self):
        host = self.host_edit.text()
        port = self.port_edit.text()
        dbname = self.dbname_edit.text()
        user = self.user_edit.text()
        password = self.password_edit.text()

        self.db_manager = DatabaseManager(host, port, dbname, user, password)
        if self.db_manager.connect():
            self.settings.setValue("host", host)
            self.settings.setValue("port", port)
            self.settings.setValue("dbname", dbname)
            self.settings.setValue("user", user)
            self.settings.setValue("password", password)
            QtWidgets.QMessageBox.information(
                self, "Success", "Connected to database successfully!"
            )
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "Failed to connect to database. Check error.log for details.",
            )

    def get_db_manager(self):
        return self.db_manager

# -------------------------
# Main Application Window (Collections View)
# -------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.setWindowTitle("Collection Loads Viewer/Editor")
        self.db_manager = db_manager
        self.settings = QtCore.QSettings("MyCompany", "BttManager")
        self.initUI()
        geometry = self.settings.value("MainWindow/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 800)

    def initUI(self):
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_widget)

        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("From:"))
        self.date_from = QtWidgets.QDateEdit()
        self.date_from.setCalendarPopup(True)
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(QtWidgets.QLabel("To:"))
        self.date_to = QtWidgets.QDateEdit()
        self.date_to.setCalendarPopup(True)
        filter_layout.addWidget(self.date_to)
        btn_filter = QtWidgets.QPushButton("Filter Loads")
        btn_filter.clicked.connect(self.load_loads)
        filter_layout.addWidget(btn_filter)
        main_layout.addLayout(filter_layout)

        week_layout = QtWidgets.QHBoxLayout()
        week_layout.addWidget(QtWidgets.QLabel("Week Ending (Sunday):"))
        self.week_combo = QtWidgets.QComboBox()
        self.populate_week_combo()
        self.week_combo.currentIndexChanged.connect(self.week_selected)
        week_layout.addWidget(self.week_combo)
        main_layout.addLayout(week_layout)

        self.loads_table = QtWidgets.QTableWidget()
        self.loads_table.setColumnCount(5)
        self.loads_table.setHorizontalHeaderLabels(
            ["Load ID", "Date", "Collection", "Destination", "Car Count"]
        )
        self.loads_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.loads_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.loads_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.loads_table.doubleClicked.connect(self.open_load_details)
        main_layout.addWidget(self.loads_table)

        self.setCentralWidget(main_widget)
        self.statusBar().showMessage("Ready")

        today = QtCore.QDate.currentDate()
        two_weeks_ago = today.addDays(-14)
        self.date_to.setDate(today)
        self.date_from.setDate(two_weeks_ago)

        self.load_loads()

    def populate_week_combo(self):
        self.week_combo.clear()
        today = QtCore.QDate.currentDate()
        days_to_sunday = today.dayOfWeek() % 7
        recent_sunday = today.addDays(-days_to_sunday)
        for i in range(8):
            week_end = recent_sunday.addDays(-7 * i)
            formatted = format_date(week_end.toString("yyyyMMdd"))
            self.week_combo.addItem(formatted, week_end)

    def week_selected(self, index):
        week_end = self.week_combo.itemData(index)
        if week_end:
            week_start = week_end.addDays(-6)
            self.date_from.setDate(week_start)
            self.date_to.setDate(week_end)
            self.load_loads()

    def load_loads(self):
        try:
            start_date_str = self.date_from.date().toString("yyyyMMdd")
            end_date_str = self.date_to.date().toString("yyyyMMdd")
            loads = self.db_manager.fetch_loads(start_date_str, end_date_str)
            self.loads_table.setRowCount(0)
            for row in loads:
                load_id = row[6]
                raw_date = row[2]
                formatted_date = format_date(raw_date)
                collection_name = row[13]
                car_count = row[10]
                dest = self.db_manager.fetch_destination(load_id)
                destination = dest[13] if dest else ""
                row_pos = self.loads_table.rowCount()
                self.loads_table.insertRow(row_pos)
                self.loads_table.setItem(row_pos, 0, QtWidgets.QTableWidgetItem(str(load_id)))
                self.loads_table.setItem(row_pos, 1, QtWidgets.QTableWidgetItem(formatted_date))
                self.loads_table.setItem(row_pos, 2, QtWidgets.QTableWidgetItem(collection_name))
                self.loads_table.setItem(row_pos, 3, QtWidgets.QTableWidgetItem(destination))
                self.loads_table.setItem(row_pos, 4, QtWidgets.QTableWidgetItem(str(car_count)))
            self.statusBar().showMessage(f"Loaded {len(loads)} collection loads")
            self.loads_table.resizeColumnsToContents()
        except Exception as e:
            logging.exception("Error loading loads")
            QtWidgets.QMessageBox.critical(
                self, "Error", "Failed to load loads. Check error.log for details."
            )

    def closeEvent(self, event):
        self.settings.setValue("MainWindow/geometry", self.saveGeometry())
        event.accept()

    def open_load_details(self):
        row = self.loads_table.currentRow()
        if row < 0:
            return
        load_id_item = self.loads_table.item(row, 0)
        if not load_id_item:
            return
        load_id = load_id_item.text()
        details_dialog = LoadDetailsDialog(self.db_manager, load_id, load_type='C', parent=self)
        details_dialog.exec_()

# -------------------------
# Load Details Dialog (no scrolling; resizes to fit content)
# -------------------------
class LoadDetailsDialog(QtWidgets.QDialog):
    def __init__(self, db_manager, load_id, load_type='C', parent=None):
        super().__init__(parent)
        # For collection loads default to "Open Destination" and vice versa.
        self.setWindowTitle(f"Load Details - {load_id} ({load_type})")
        self.setMinimumSize(800, 600)
        self.resize(1000, 800)
        self.db_manager = db_manager
        self.load_id = load_id
        self.load_type = load_type  # 'C' for collection, 'D' for destination
        self.initUI()
        self.load_details()

    def initUI(self):
        self.layout = QtWidgets.QVBoxLayout(self)

        # Load details label (non-editable, auto-resizes)
        self.details_label = QtWidgets.QLabel()
        self.details_label.setWordWrap(True)
        self.layout.addWidget(self.details_label)

        # Vehicles table (editable); no scrolling—its height will be set to content.
        self.vehicles_table = QtWidgets.QTableWidget()
        self.vehicles_table.setColumnCount(6)
        self.vehicles_table.setHorizontalHeaderLabels(
            ["VehRef", "Model", "Offloaded", "Docs", "Sparekeys", "Photos"]
        )
        self.vehicles_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.vehicles_table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        self.layout.addWidget(self.vehicles_table)

        # Button to open linked load (destination if collection; collection if destination)
        self.open_linked_button = QtWidgets.QPushButton()
        if self.load_type == 'C':
            self.open_linked_button.setText("Open Destination")
        else:
            self.open_linked_button.setText("Open Collection")
        self.open_linked_button.clicked.connect(self.open_linked_load)
        self.layout.addWidget(self.open_linked_button)

        # Save and Close buttons
        self.btn_save = QtWidgets.QPushButton("Save Car Changes")
        self.btn_save.clicked.connect(self.save_car_changes)
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_close)
        self.layout.addLayout(btn_layout)

    def load_details(self):
        try:
            cur = self.db_manager.conn.cursor()
            query = "SELECT * FROM jobs WHERE dwjload = %s AND dwjtype = %s"
            cur.execute(query, (self.load_id, self.load_type))
            load = cur.fetchone()
            cur.close()
            if load:
                formatted_date = format_date(load[2])
                driver = load[1]
                load_id = load[6]
                car_count = load[10]
                address_parts = [load[13], load[14], load[15], load[16], load[17], load[19]]
                full_address = " ".join([str(part).strip() for part in address_parts if part and str(part).strip() != ""])
                details_text = (f"Date: {formatted_date}\n"
                                f"Driver: {driver}\n"
                                f"Load: {load_id}\n"
                                f"Car Count: {car_count}\n"
                                f"Collection Address: {full_address}\n")
                # Append linked load info
                if self.load_type == 'C':
                    dest = self.db_manager.fetch_destination(self.load_id)
                    if dest:
                        details_text += f"Destination: {dest[13]}\n"
                else:  # load_type == 'D'
                    coll = self.db_manager.fetch_collection(self.load_id)
                    if coll:
                        details_text += f"Collection: {coll[13]}\n"
                self.details_label.setText(details_text)
            else:
                self.details_label.setText("No details found.")
        except Exception as e:
            logging.exception("Error loading load details")
            QtWidgets.QMessageBox.critical(
                self, "Error", "Failed to load load details. Check error.log for details."
            )
        self.load_vehicles()
        self.adjust_dialog_size()

    def load_vehicles(self):
        try:
            vehicles = self.db_manager.fetch_vehicle_details(self.load_id)
            self.vehicles_table.setRowCount(0)
            for v in vehicles:
                row_pos = self.vehicles_table.rowCount()
                self.vehicles_table.insertRow(row_pos)
                item_ref = QtWidgets.QTableWidgetItem(v[0])
                item_ref.setData(QtCore.Qt.UserRole, v[6])
                self.vehicles_table.setItem(row_pos, 0, item_ref)
                self.vehicles_table.setItem(row_pos, 1, QtWidgets.QTableWidgetItem(v[1]))
                self.vehicles_table.setItem(row_pos, 2, QtWidgets.QTableWidgetItem(v[2]))
                self.vehicles_table.setItem(row_pos, 3, QtWidgets.QTableWidgetItem(v[3]))
                self.vehicles_table.setItem(row_pos, 4, QtWidgets.QTableWidgetItem(v[4]))
                self.vehicles_table.setItem(row_pos, 5, QtWidgets.QTableWidgetItem(v[5]))
            set_table_height_to_content(self.vehicles_table)
        except Exception as e:
            logging.exception("Error loading vehicles")
            QtWidgets.QMessageBox.critical(
                self, "Error", "Failed to load vehicles. Check error.log for details."
            )

    def open_linked_load(self):
        # For a collection, open the destination; for a destination, open the collection.
        if self.load_type == 'C':
            linked_type = 'D'
        else:
            linked_type = 'C'
        linked_dialog = LoadDetailsDialog(self.db_manager, self.load_id, load_type=linked_type, parent=self)
        linked_dialog.exec_()

    def save_car_changes(self):
        row_count = self.vehicles_table.rowCount()
        for row in range(row_count):
            veh_item = self.vehicles_table.item(row, 0)
            dwvkey = veh_item.data(QtCore.Qt.UserRole)
            model = self.vehicles_table.item(row, 1).text() if self.vehicles_table.item(row, 1) else ""
            offloaded = self.vehicles_table.item(row, 2).text() if self.vehicles_table.item(row, 2) else ""
            docs = self.vehicles_table.item(row, 3).text() if self.vehicles_table.item(row, 3) else ""
            sparekeys = self.vehicles_table.item(row, 4).text() if self.vehicles_table.item(row, 4) else ""
            photos = self.vehicles_table.item(row, 5).text() if self.vehicles_table.item(row, 5) else ""
            self.db_manager.update_vehicle_details(dwvkey, model, offloaded, docs, sparekeys, photos)
        QtWidgets.QMessageBox.information(self, "Saved", "Vehicle details updated.")
        self.adjust_dialog_size()

    def adjust_dialog_size(self):
        # Resize the dialog to fit its content.
        self.adjustSize()

# -------------------------
# Main Entry Point
# -------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    settings_dialog = SettingsDialog()
    if settings_dialog.exec_() == QtWidgets.QDialog.Accepted:
        db_manager = settings_dialog.get_db_manager()
        main_win = MainWindow(db_manager)
        main_win.show()
        sys.exit(app.exec_())
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
