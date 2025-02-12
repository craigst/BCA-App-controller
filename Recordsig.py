import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import os
import json
import threading
import subprocess


class SignatureRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Signature Recorder")

        # Main Canvas for drawing
        self.canvas = tk.Canvas(self.root, bg="white", width=600, height=400)
        self.canvas.pack()

        # Initialize variables
        self.drawing = False
        self.points = []  # Stores all recorded points [(x, y), ...]
        self.playing = False  # To control playback process
        self.current_file = None  # Tracks the current signature file

        # Directories
        self.local_dir = "./signatures"  # Local directory for saving signatures
        self.phone_dir = "/sdcard/scripts/signatures"  # Phone directory for signatures
        os.makedirs(self.local_dir, exist_ok=True)  # Ensure local directory exists

        # Playback settings
        self.playback_x = tk.StringVar(value="0")  # X Offset
        self.playback_y = tk.StringVar(value="0")  # Y Offset
        self.playback_scale = tk.StringVar(value="1.0")  # Scale
        self.playback_speed = tk.StringVar(value="1")  # Speed multiplier

        # Status indicators
        self.script_installed = tk.BooleanVar(value=False)
        self.file_sent = tk.BooleanVar(value=False)

        # UI elements
        self.loaded_file_label = None
        self.file_listbox = None

        # Bind mouse events for drawing
        self.canvas.bind("<ButtonPress-1>", self.start_drawing)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drawing)

        # Add UI elements
        self.add_ui()

        # Initial status check
        self.refresh_status()
        self.refresh_file_list()

    def add_ui(self):
        """Set up the UI buttons and layout."""

        # Row 1 buttons
        button_frame1 = tk.Frame(self.root)
        button_frame1.pack(pady=5)

        save_btn = tk.Button(button_frame1, text="Save", command=self.save_signature, width=15)
        save_btn.pack(side=tk.LEFT, padx=5, pady=5)

        load_btn = tk.Button(button_frame1, text="Load", command=self.load_selected_signature, width=15)
        load_btn.pack(side=tk.LEFT, padx=5, pady=5)

        clear_btn = tk.Button(button_frame1, text="Clear", command=self.clear_canvas, width=15)
        clear_btn.pack(side=tk.LEFT, padx=5, pady=5)

        send_file_btn = tk.Button(button_frame1, text="Send Current File", command=self.send_to_phone, width=15)
        send_file_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Row 2 buttons
        button_frame2 = tk.Frame(self.root)
        button_frame2.pack(pady=5)

        send_script_btn = tk.Button(button_frame2, text="Send Script", command=self.send_script_to_phone, width=15)
        send_script_btn.pack(side=tk.LEFT, padx=5, pady=5)

        play_btn = tk.Button(button_frame2, text="Play on Phone", command=self.trigger_phone_script, width=15)
        play_btn.pack(side=tk.LEFT, padx=5, pady=5)

        stop_playback_btn = tk.Button(button_frame2, text="Stop Playback", command=self.stop_remote_playback, width=15)
        stop_playback_btn.pack(side=tk.LEFT, padx=5, pady=5)

        refresh_btn = tk.Button(button_frame2, text="Refresh Status", command=self.refresh_status, width=15)
        refresh_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Playback Settings Frame
        settings_frame = tk.Frame(self.root)
        settings_frame.pack(pady=10)

        tk.Label(settings_frame, text="X Offset:").grid(row=0, column=0, padx=5)
        tk.Entry(settings_frame, textvariable=self.playback_x, width=5).grid(row=0, column=1, padx=5)

        tk.Label(settings_frame, text="Y Offset:").grid(row=0, column=2, padx=5)
        tk.Entry(settings_frame, textvariable=self.playback_y, width=5).grid(row=0, column=3, padx=5)

        tk.Label(settings_frame, text="Scale:").grid(row=0, column=4, padx=5)
        tk.Entry(settings_frame, textvariable=self.playback_scale, width=5).grid(row=0, column=5, padx=5)

        tk.Label(settings_frame, text="Speed:").grid(row=0, column=6, padx=5)
        tk.Entry(settings_frame, textvariable=self.playback_speed, width=5).grid(row=0, column=7, padx=5)

        # File Listbox for Saved Signatures
        file_frame = tk.Frame(self.root)
        file_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        tk.Label(file_frame, text="Saved Signatures:").pack(anchor=tk.W, padx=5)

        self.file_listbox = tk.Listbox(file_frame, height=10)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        file_buttons_frame = tk.Frame(file_frame)
        file_buttons_frame.pack(pady=5)

        rename_btn = tk.Button(file_buttons_frame, text="Rename", command=self.rename_signature, width=15)
        rename_btn.pack(side=tk.LEFT, padx=5)

        delete_btn = tk.Button(file_buttons_frame, text="Delete", command=self.delete_signature, width=15)
        delete_btn.pack(side=tk.LEFT, padx=5)

        refresh_files_btn = tk.Button(file_buttons_frame, text="Refresh", command=self.refresh_file_list, width=15)
        refresh_files_btn.pack(side=tk.LEFT, padx=5)


    def start_drawing(self, event):
        self.drawing = True
        self.points.append((event.x, event.y))  # Record the starting point

    def draw(self, event):
        if self.drawing:
            x, y = event.x, event.y
            self.canvas.create_line(self.points[-1][0], self.points[-1][1], x, y, fill="black", width=2)
            self.points.append((x, y))  # Record the point

    def stop_drawing(self, event):
        self.drawing = False

    def save_signature(self):
            """Save the current signature to a local file."""
            if not self.points:
                messagebox.showerror("Error", "No signature to save!")
                return

            file_name = simpledialog.askstring("Save Signature", "Enter a name for the signature:")
            if not file_name:
                return

            file_path = os.path.join(self.local_dir, f"{file_name}.json")
            try:
                with open(file_path, "w") as f:
                    json.dump(self.points, f)
                self.current_file = file_path
                self.refresh_file_list()
                messagebox.showinfo("Success", f"Signature saved to {file_path}!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")

    def send_to_phone(self):
        """Send the current signature file to the phone."""
        if not self.current_file:
            messagebox.showerror("Error", "No signature file selected!")
            return

        try:
            target_path = "/data/local/tmp/signature.json"  # Full file path
            os.system(f"adb push {self.current_file} {target_path}")
            self.file_sent.set(True)
            self.update_file_status_label()
            messagebox.showinfo("Success", "File sent to phone!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send file: {e}")


    def send_script_to_phone(self):
        """Send the play_signature.sh script to the phone."""
        try:
            os.system("adb push play_signature.sh /data/local/tmp/play_signature.sh")
            os.system("adb shell chmod +x /data/local/tmp/play_signature.sh")
            self.script_installed.set(True)
            self.update_script_status_label()
            messagebox.showinfo("Success", "Script sent to phone!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send script: {e}")

    def update_script_status_label(self):
        if self.script_installed.get():
            self.script_status_label.config(text="Script Installed: Yes", fg="green")
        else:
            self.script_status_label.config(text="Script Installed: No", fg="red")

    def update_file_status_label(self):
        if self.file_sent.get():
            self.file_status_label.config(text="File Sent: Yes", fg="green")
        else:
            self.file_status_label.config(text="File Sent: No", fg="red")

    def update_loaded_file_label(self):
        if self.current_file:
            self.loaded_file_label.config(text=f"Loaded Signature: {os.path.basename(self.current_file)}", fg="blue")
        else:
            self.loaded_file_label.config(text="Loaded Signature: None", fg="blue")

    def load_signature(self):
        """Load a signature file and redraw it on the canvas."""
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if file_path:
            try:
                with open(file_path, "r") as f:
                    loaded_points = json.load(f)

                # Validate loaded points
                if isinstance(loaded_points, list) and all(
                    isinstance(point, list) and len(point) == 2 for point in loaded_points
                ):
                    self.points = [tuple(point) for point in loaded_points]
                    self.current_file = file_path  # Track the current loaded file
                    self.update_loaded_file_label()  # Update the UI
                    self.redraw_signature()  # Redraw the signature on the canvas
                    messagebox.showinfo("Success", f"Signature loaded from {file_path}!")
                else:
                    raise ValueError("Invalid signature file format.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")



    def redraw_signature(self):
        """Redraw the signature on the canvas based on recorded points."""
        self.clear_canvas()  # Clear the current canvas

        # Ensure there are points to redraw
        if not self.points:
            return

        # Draw lines between consecutive points
        for i in range(1, len(self.points)):
            x1, y1 = self.points[i - 1]
            x2, y2 = self.points[i]
            self.canvas.create_line(x1, y1, x2, y2, fill="black", width=2)


    def clear_canvas(self):
        """Clear the canvas and reset points."""
        self.canvas.delete("all")
        self.points = []

    def start_play_signature(self):
        """Starts the playback in a separate thread to avoid freezing the GUI."""
        if not self.points:
            messagebox.showerror("Error", "No signature to play!")
            return

        # Start playback in a separate thread
        self.playing = True
        threading.Thread(target=self.play_signature).start()

    def play_signature(self):
        """Replays the signature on the phone using ADB."""
        try:
            # Get playback settings
            offset_x = int(self.playback_x.get())
            offset_y = int(self.playback_y.get())
            scale = float(self.playback_scale.get())
            duration = max(1, int(self.playback_speed.get()))  # Speed as duration per point

            # Check if adb is installed
            if not self.check_adb_installed():
                messagebox.showerror("Error", "ADB is not installed or not in PATH.")
                return

            # Optimize by skipping points (use every nth point)
            step = max(1, len(self.points) // 500)  # Adjust to keep only ~500 points
            optimized_points = self.points[::step]

            # Keep "finger down" and play the gesture continuously
            for i in range(1, len(optimized_points)):
                if not self.playing:
                    break  # Stop playback if requested

                x1, y1 = optimized_points[i - 1]
                x2, y2 = optimized_points[i]

                # Scale and offset points
                scaled_x1 = int(x1 * scale + offset_x)
                scaled_y1 = int(y1 * scale + offset_y)
                scaled_x2 = int(x2 * scale + offset_x)
                scaled_y2 = int(y2 * scale + offset_y)

                # Use adb to simulate the swipe
                adb_command = f"adb shell input touchscreen swipe {scaled_x1} {scaled_y1} {scaled_x2} {scaled_y2} {duration}"
                os.system(adb_command)

            messagebox.showinfo("Success", "Signature playback completed!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play signature: {e}")

    def stop_play_signature(self):
        """Stops the playback process."""
        self.playing = False

    def check_adb_installed(self):
        """Check if ADB is installed and accessible from the command line."""
        try:
            subprocess.run(["adb", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except FileNotFoundError:
            return False
        except subprocess.CalledProcessError:
            return False


    def trigger_phone_script(self):
        """Trigger the playback script on the phone."""
        x_offset = self.playback_x.get()
        y_offset = self.playback_y.get()
        scale = self.playback_scale.get()

        try:
            command = f"adb shell sh /data/local/tmp/play_signature.sh {x_offset} {y_offset} {scale}"
            os.system(command)
            messagebox.showinfo("Success", "Playback triggered on phone!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to trigger playback: {e}")

    def save_signature(self):
        """Save the current signature to a local file."""
        if not self.points:
            messagebox.showerror("Error", "No signature to save!")
            return

        file_name = simpledialog.askstring("Save Signature", "Enter a name for the signature:")
        if not file_name:
            return

        file_path = os.path.join(self.local_dir, f"{file_name}.json")
        try:
            with open(file_path, "w") as f:
                json.dump(self.points, f)
            self.current_file = file_path
            self.refresh_file_list()
            messagebox.showinfo("Success", f"Signature saved to {file_path}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def refresh_file_list(self):
        """Refresh the list of saved signatures."""
        self.file_listbox.delete(0, tk.END)
        for file_name in os.listdir(self.local_dir):
            if file_name.endswith(".json"):
                self.file_listbox.insert(tk.END, file_name)

    def load_selected_signature(self):
        """Load the selected signature from the listbox."""
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No signature selected!")
            return

        file_name = self.file_listbox.get(selection[0])
        file_path = os.path.join(self.local_dir, file_name)
        try:
            with open(file_path, "r") as f:
                self.points = json.load(f)
            self.current_file = file_path
            self.redraw_signature()
            messagebox.showinfo("Success", f"Signature loaded from {file_path}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load signature: {e}")

    def delete_signature(self):
        """Delete the selected signature file."""
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No signature selected!")
            return

        file_name = self.file_listbox.get(selection[0])
        file_path = os.path.join(self.local_dir, file_name)
        if messagebox.askyesno("Delete Signature", f"Are you sure you want to delete {file_name}?"):
            try:
                os.remove(file_path)
                self.refresh_file_list()
                messagebox.showinfo("Success", f"{file_name} deleted!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete {file_name}: {e}")

    def rename_signature(self):
        """Rename the selected signature file."""
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No signature selected!")
            return

        old_name = self.file_listbox.get(selection[0])
        old_path = os.path.join(self.local_dir, old_name)
        new_name = simpledialog.askstring("Rename Signature", "Enter a new name for the signature:")
        if not new_name:
            return

        new_path = os.path.join(self.local_dir, f"{new_name}.json")
        try:
            os.rename(old_path, new_path)
            self.refresh_file_list()
            messagebox.showinfo("Success", f"{old_name} renamed to {new_name}.json!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to rename {old_name}: {e}")

    def save_signature_for_phone(self):
        """Save the signature to a file formatted for the phone."""
        if not self.points:
            messagebox.showerror("Error", "No signature to save!")
            return

        file_path = "signature.json"  # Save locally
        try:
            with open(file_path, "w") as f:
                json.dump(self.points, f)
            self.current_file = file_path
            self.update_loaded_file_label()
            messagebox.showinfo("Success", f"Signature saved to {file_path}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def refresh_status(self):
        """Refresh the status of the script and file on the phone."""
        try:
            # Check if script exists on the phone
            result = subprocess.run(
                "adb shell [ -f /data/local/tmp/play_signature.sh ] && echo 'exists'",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.script_installed.set("exists" in result.stdout)

            # Check if file exists on the phone
            result = subprocess.run(
                "adb shell [ -f /data/local/tmp/signature.json ] && echo 'exists'",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.file_sent.set("exists" in result.stdout)

            # Update UI labels
            self.update_script_status_label()
            self.update_file_status_label()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh status: {e}")


    def update_script_status_label(self):
        """Update the status label for the script."""
        if self.script_installed.get():
            self.script_status_label.config(text="Script Installed: Yes", fg="green")
        else:
            self.script_status_label.config(text="Script Installed: No", fg="red")

    def stop_remote_playback(self):
        """Stop playback on the phone."""
        try:
            os.system("adb shell touch /data/local/tmp/stop_playback")
            messagebox.showinfo("Success", "Playback stopped on phone!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop playback: {e}")

    def update_file_status_label(self):
        """Update the status label for the file."""
        if self.file_sent.get():
            self.file_status_label.config(text="File Sent: Yes", fg="green")
        else:
            self.file_status_label.config(text="File Sent: No", fg="red")


    def update_loaded_file_label(self):
        """Update the label for the currently loaded file."""
        if self.current_file:
            self.loaded_file_label.config(text=f"Loaded Signature: {os.path.basename(self.current_file)}", fg="blue")
        else:
            self.loaded_file_label.config(text="Loaded Signature: None", fg="blue")



# Run the app
if __name__ == "__main__":
    root = tk.Tk()
    app = SignatureRecorder(root)
    root.mainloop()
