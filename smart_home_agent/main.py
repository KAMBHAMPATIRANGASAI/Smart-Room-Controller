import cv2
import numpy as np
import pyttsx3
import time
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
from PIL import Image, ImageTk
import speech_recognition as sr

# Initialize TTS engine
engine = pyttsx3.init()
engine.setProperty('rate', 150)
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[0].id)  # 0 for male, 1 for female

# Initialize SQLite database
conn = sqlite3.connect('smart_room.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS device_status (
                    device TEXT PRIMARY KEY,
                    status INTEGER,
                    last_updated TEXT
                 )''')

# Insert initial values if they don't exist
cursor.execute("SELECT COUNT(*) FROM device_status")
if cursor.fetchone()[0] == 0:
    cursor.executemany('INSERT INTO device_status (device, status, last_updated) VALUES (?, ?, ?)', [
        ('light', 0, datetime.now().isoformat()),
        ('fan', 0, datetime.now().isoformat())
    ])
    conn.commit()

# Global flag for voice control
voice_control_active = False

# Device control function
def control_device(device, state, log_area):
    cursor.execute('UPDATE device_status SET status = ?, last_updated = ? WHERE device = ?',
                   (state, datetime.now().isoformat(), device))
    conn.commit()
    message = f"{device.capitalize()} turned {'ON' if state else 'OFF'}"
    announce(message)
    log_action(message, log_area)
    return True

# TTS announcement
def announce(message):
    print(f"Announcement: {message}")
    engine.say(message)
    engine.runAndWait()

# Log actions to the interface
def log_action(message, log_area):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_text = f"{timestamp}: {message}\n"
    
    log_area.configure(state='normal')
    log_area.insert(tk.END, log_text)
    log_area.configure(state='disabled')
    log_area.see(tk.END)
    print(log_text.strip())

# Update device status labels
def update_status_labels(light_label, fan_label):
    cursor.execute('SELECT device, status FROM device_status')
    devices = {row[0]: row[1] for row in cursor.fetchall()}
    
    light_status = devices.get('light', 0)
    light_label.config(
        text=f"Light: {'ON' if light_status else 'OFF'}",
        fg='#27AE60' if light_status else '#C0392B'
    )
    
    fan_status = devices.get('fan', 0)
    fan_label.config(
        text=f"Fan: {'ON' if fan_status else 'OFF'}",
        fg='#27AE60' if fan_status else '#C0392B'
    )

# Voice command listener
def listen_for_commands(log_area, voice_button):
    global voice_control_active
    
    def voice_loop():
        global voice_control_active
        recognizer = sr.Recognizer()
        
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
                log_action("Voice control activated. Say commands like 'turn on light' or 'switch off fan'", log_area)
                
                while voice_control_active:
                    try:
                        audio = recognizer.listen(source, timeout=3, phrase_time_limit=5)
                        command = recognizer.recognize_google(audio).lower()
                        log_action(f"Voice command: {command}", log_area)
                        
                        # Process command
                        if 'light' in command:
                            if any(word in command for word in ['on', 'open', 'start', 'enable']):
                                control_device('light', 1, log_area)
                            elif any(word in command for word in ['off', 'close', 'stop', 'disable']):
                                control_device('light', 0, log_area)
                        elif 'fan' in command:
                            if any(word in command for word in ['on', 'open', 'start', 'enable']):
                                control_device('fan', 1, log_area)
                            elif any(word in command for word in ['off', 'close', 'stop', 'disable']):
                                control_device('fan', 0, log_area)
                        else:
                            announce("Please specify light or fan in your command")
                            
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        log_action("Could not understand audio", log_area)
                    except sr.RequestError as e:
                        log_action(f"Could not request results; check your internet connection: {e}", log_area)
                    except Exception as e:
                        log_action(f"Error in voice recognition: {str(e)}", log_area)
                        
        except Exception as e:
            log_action(f"Microphone error: {str(e)}", log_area)
            voice_control_active = False
            voice_button.config(text="🎤 Start Voice Control", bg="#2980B9")
            return
        
    if not voice_control_active:
        voice_control_active = True
        voice_button.config(text="🎤 Voice Control Active", bg="#C0392B")
        threading.Thread(target=voice_loop, daemon=True).start()
    else:
        voice_control_active = False
        voice_button.config(text="🎤 Start Voice Control", bg="#2980B9")
        log_action("Voice control deactivated", log_area)

# Person detection via webcam
def detect_person(root, light_label, fan_label, log_area, video_label):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        log_action("Error: Could not open camera", log_area)
        return

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    last_presence_time = 0
    presence = False
    auto_mode = True

    def update_frame():
        nonlocal last_presence_time, presence, auto_mode
        
        if not auto_mode:
            root

        ret, frame = cap.read()
        if not ret:
            log_action("Camera feed error", log_area)
            root.after(100, update_frame)
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        current_time = time.time()
        
        # Update presence status
        if len(faces) > 0:
            last_presence_time = current_time
            if not presence:
                presence = True
                log_action("Person detected", log_area)
                if auto_mode:
                    control_device('light', 1, log_area)
                    control_device('fan', 1, log_area)
        
        # Check for absence (5 seconds threshold)
        elif presence and (current_time - last_presence_time > 5):
            presence = False
            log_action("Room empty", log_area)
            if auto_mode:
                control_device('light', 0, log_area)
                control_device('fan', 0, log_area)

        # Draw rectangles around faces
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        # Display frame
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, (320, 240))
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)
        video_label.imgtk = imgtk
        video_label.configure(image=imgtk)

        update_status_labels(light_label, fan_label)
        root.after(30, update_frame)

    def toggle_auto_mode():
        nonlocal auto_mode
        auto_mode = not auto_mode
        status = "ON" if auto_mode else "OFF"
        log_action(f"Auto mode turned {status}", log_area)
        auto_button.config(text=f"Auto Mode: {status}", 
                         bg="#27AE60" if auto_mode else "#C0392B")
        
        if auto_mode and presence:
            control_device('light', 1, log_area)
            control_device('fan', 1, log_area)

    # Add auto mode button
    auto_button = tk.Button(root, text="Auto Mode: ON", font=("Arial", 12), 
                          bg="#27AE60", fg="white", command=toggle_auto_mode)
    auto_button.pack(pady=5)

    update_frame()

# GUI setup
def create_gui():
    root = tk.Tk()
    root.title("Smart Room Controller")
    root.configure(bg="#F5F6F5")
    root.geometry("500x800")

    # Scrolling College Name
    college_frame = tk.Frame(root, bg="#1A237E")
    college_frame.pack(fill=tk.X)
    
    canvas = tk.Canvas(college_frame, height=40, bg="#1A237E", highlightthickness=0)
    canvas.pack(fill=tk.X)
    
    college_name = "Aurora Deemed To Be University"
    text_id = canvas.create_text(-canvas.winfo_reqwidth(), 20, text=college_name, font=("Helvetica", 20, "bold"), fill="#FFFFFF")
    
    def scroll_text():
        canvas.move(text_id, 2, 0)
        x_pos = canvas.coords(text_id)[0]
        text_width = canvas.bbox(text_id)[2] - canvas.bbox(text_id)[0]
        if x_pos > canvas.winfo_width():
            canvas.coords(text_id, -text_width, 20)  # Reset to start at left
        root.after(20, scroll_text)
    
    scroll_text()

    # College Address
    address_frame = tk.Frame(root, bg="#263238")
    address_frame.pack(fill=tk.X)
    tk.Label(address_frame, 
             text="Rayancha Enclave, Parvathapuram, Parvathapur, Peerzadiguda, Hyderabad, Telangana 500098",
             font=("Helvetica", 12), 
             bg="#263238", 
             fg="#FFFFFF",
             wraplength=480).pack(pady=5)

    # Project Title
    tk.Label(root, text="Smart Room Controller", font=("Helvetica", 18, "bold"), bg="#F5F6F5", fg="#003087").pack(pady=10)

    # Camera Feed
    tk.Label(root, text="Camera Feed", font=("Helvetica", 16, "bold"), bg="#F5F6F5", fg="#003087").pack(pady=5)
    video_label = tk.Label(root, bg="#001F5B")
    video_label.pack()

    # Status Indicators
    status_frame = tk.Frame(root, bg="#F5F6F5")
    status_frame.pack(pady=10)
    
    light_label = tk.Label(status_frame, text="Light: OFF", font=("Helvetica", 14), fg="#C0392B", bg="#F5F6F5")
    light_label.pack(side=tk.LEFT, padx=20)
    fan_label = tk.Label(status_frame, text="Fan: OFF", font=("Helvetica", 14), fg="#C0392B", bg="#F5F6F5")
    fan_label.pack(side=tk.LEFT, padx=20)

    # Manual Controls
    tk.Label(root, text="Manual Controls", font=("Helvetica", 15, "bold"), bg="#F5F6F5", fg="#003087").pack(pady=10)
    
    btn_frame = tk.Frame(root, bg="#F5F6F5")
    btn_frame.pack()
    
    tk.Button(btn_frame, text="Light ON", font=("Arial", 12), bg="#27AE60", fg="white",
              command=lambda: control_device('light', 1, log_area)).grid(row=0, column=0, padx=5, pady=5)
    tk.Button(btn_frame, text="Light OFF", font=("Arial", 12), bg="#C0392B", fg="white",
              command=lambda: control_device('light', 0, log_area)).grid(row=0, column=1, padx=5, pady=5)
    tk.Button(btn_frame, text="Fan ON", font=("Arial", 12), bg="#27AE60", fg="white",
              command=lambda: control_device('fan', 1, log_area)).grid(row=1, column=0, padx=5, pady=5)
    tk.Button(btn_frame, text="Fan OFF", font=("Arial", 12), bg="#C0392B", fg="white",
              command=lambda: control_device('fan', 0, log_area)).grid(row=1, column=1, padx=5, pady=5)

    # Voice Control Button
    voice_button = tk.Button(root, text="🎤 Start Voice Control", font=("Arial", 14), 
                           bg="#2980B9", fg="white", command=lambda: listen_for_commands(log_area, voice_button))
    voice_button.pack(pady=10)

    # Log Area
    tk.Label(root, text="Activity Log", font=("Helvetica", 15, "bold"), bg="#F5F6F5", fg="#003087").pack(pady=5)
    log_area = scrolledtext.ScrolledText(root, width=60, height=12, font=("Courier", 10), bg="#FFFFFF", fg="#003087")
    log_area.pack(padx=10, pady=5)
    log_area.configure(state='disabled')

    # Initialize status
    update_status_labels(light_label, fan_label)
    log_action("System initialized", log_area)

    # Start person detection
    detect_person(root, light_label, fan_label, log_area, video_label)

    # Cleanup on window close
    def on_closing():
        global voice_control_active
        voice_control_active = False
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            root.destroy()
            if conn:
                conn.close()
            cv2.destroyAllWindows()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    create_gui()