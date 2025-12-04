import csv
import time
import os
from datetime import datetime
from pathlib import Path
from eye import EyeId, EyeInfo
from threading import Lock
from typing import Optional


class CSVLogger:
    """
    Thread-safe CSV logger for eye tracking data.
    
    Creates separate CSV files per recording session for each eye/eye pair.
    Logs: timestamp_ms, eye_id, x, y, pupil_dilation, eye_blink
    """

    def __init__(self, eye_id: EyeId):
        """
        Initialize CSV logger for a specific eye.
        
        Args:
            eye_id: EyeId.LEFT, EyeId.RIGHT, or EyeId.BOTH
        """
        self.eye_id = eye_id
        self.start_time_ms: Optional[int] = None
        self.csv_file: Optional[str] = None
        self.is_recording = False
        self._lock = Lock()
        self.base_folder = "csv_files"

    def start_recording(self, camera_connected: bool = True, left_test = False, right_test = False) -> bool:
        """
        Start a new recording session.
        Creates a new CSV file with headers.
        
        Args:
            camera_connected: Whether the camera is connected and ready. 
                            Recording will only start if True.
        
        Returns:
            bool: True if recording started successfully, False otherwise
        """
        if not camera_connected:
            print("\033[93m[WARN] Cannot start recording - camera not connected\033[0m")
            return False

        with self._lock:
            if self.is_recording:
                print(f"\033[93m[WARN] {self.eye_id.name} is already recording\033[0m")
                return False

            try:
                # Reset time for this session
                self.start_time_ms = int(round(time.time() * 1000))

                # Create session folder with timestamp
                formatted_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                session_folder = os.path.join(self.base_folder, f"session_{formatted_timestamp}")

                # Create directories if they don't exist
                Path(session_folder).mkdir(parents=True, exist_ok=True)

                # Create CSV file path
                if left_test:
                    filename = f"{formatted_timestamp}_{self.eye_id.name}_Left_Orientation_Gaze_Test_eye_data.csv"
                elif right_test:
                    filename = f"{formatted_timestamp}_{self.eye_id.name}_Right_Orientation_Gaze_Test_eye_data.csv"
                else:
                    filename = f"{formatted_timestamp}_{self.eye_id.name}_Main_Recording_eye_data.csv"
                    self.csv_file = os.path.join(session_folder, filename)

                # Write CSV header
                with open(self.csv_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['timestamp_ms', 'eye_id', 'x', 'y', 'pupil_dilation', 'eye_blink'])

                self.is_recording = True
                print(f"\033[92m[INFO] Started recording {self.eye_id.name} to {self.csv_file}\033[0m")
                return True

            except Exception as e:
                print(f"\033[91m[ERROR] Failed to start CSV recording: {e}\033[0m")
                self.is_recording = False
                return False

    def stop_recording(self) -> bool:
        """
        Stop the current recording session.
        
        Returns:
            bool: True if recording was stopped, False if not recording
        """
        with self._lock:
            if not self.is_recording:
                print(f"\033[93m[WARN] {self.eye_id.name} is not recording\033[0m")
                return False

            self.is_recording = False
            print(f"\033[92m[INFO] Stopped recording {self.eye_id.name}\033[0m")
            return True

    def log_eye_data(self, eye_id: EyeId, eye_info: EyeInfo) -> bool:
        """
        Log a single frame of eye data to CSV.
        
        This method should be called directly from the OSC sender thread
        with fresh EyeInfo data to avoid data race conditions.
        
        Args:
            eye_id: The eye being logged (LEFT, RIGHT, or BOTH)
            eye_info: EyeInfo dataclass containing x, y, pupil_dilation, blink
            
        Returns:
            bool: True if log was written, False otherwise
        """
        if not self.is_recording:
            return False

        if self.start_time_ms is None:
            print("[ERROR] Recording started but start_time_ms is None")
            return False

        try:
            # Calculate elapsed time since session start
            elapsed_time_ms = int(round(time.time() * 1000)) - self.start_time_ms

            # Extract eye data
            x = eye_info.x
            y = eye_info.y
            pupil_dilation = eye_info.pupil_dilation
            eye_blink = eye_info.blink

            # Thread-safe file write
            with self._lock:
                if not self.csv_file:
                    return False

                with open(self.csv_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        elapsed_time_ms,
                        eye_id.name,
                        round(x, 6),
                        round(y, 6),
                        round(pupil_dilation, 6),
                        round(eye_blink, 6)
                    ])
            return True

        except Exception as e:
            print(f"\033[91m[ERROR] CSV write failed for {self.eye_id.name}: {e}\033[0m")
            return False

    def get_recording_status(self) -> dict:
        """
        Get current recording status.
        
        Returns:
            dict: Contains is_recording, csv_file path, eye_id, and session start time
        """
        with self._lock:
            return {
                'is_recording': self.is_recording,
                'csv_file': self.csv_file,
                'eye_id': self.eye_id.name,
                'start_time_ms': self.start_time_ms
            }