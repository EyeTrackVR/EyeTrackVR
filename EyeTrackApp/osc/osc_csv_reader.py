import csv
import time
import os
from datetime import datetime
from pathlib import Path
from eye import EyeId, EyeInfo
from threading import Lock
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config import EyeTrackConfig


class CSVLogger:
    """
    Thread-safe CSV logger for eye tracking data.
    
    Creates separate CSV files per recording session for each eye/eye pair.
    Logs: timestamp_ms, eye_id, x, y, pupil_dilation, eye_blink
    """

    def __init__(self, eye_id: EyeId, config: Optional["EyeTrackConfig"] = None):
        """
        Initialize CSV logger for a specific eye.

        Args:
            eye_id: EyeId.LEFT, EyeId.RIGHT, or EyeId.BOTH
            config: Optional config to read gui_csv_participant_id from (shared across all loggers)
        """
        self.eye_id = eye_id
        self.config = config
        self.start_time_ms: Optional[int] = None
        self.csv_file: Optional[str] = None
        self.is_recording = False
        self._lock = Lock()
        self.base_folder = "csv_files"
        self.participant_id: Optional[str] = None  # Override: use this if set, else config

    def set_participant_id(self, participant_id: Optional[str]) -> None:
        """Set participant ID for organizing recordings. Use None to use config value or disable."""
        self.participant_id = participant_id

    def _get_participant_id(self) -> Optional[str]:
        """Get participant ID from override, config, or None."""
        if self.participant_id is not None and self.participant_id.strip():
            return self.participant_id.strip()
        if self.config and getattr(self.config.settings, "gui_csv_participant_id", ""):
            pid = self.config.settings.gui_csv_participant_id.strip()
            return pid if pid else None
        return None

    def start_recording(self, camera_connected: bool = True, left_test=False, right_test=False) -> bool:
        """
        Starts a new CSV recording session for the specified eye.
        
        Args:
            camera_connected: bool, optional (default=True)
                Whether the camera is connected or not. If False, cannot start recording.
            left_test: bool, optional (default=False)
                If True, will record left eye orientation gaze test
            right_test: bool, optional (default=False)
                If True, will record right eye orientation gaze test
        
        Returns:
            bool: True if recording was started, False otherwise
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

                formatted_timestamp = datetime.now().strftime("%Y-%m-%d")
                participant_id = self._get_participant_id()
                if participant_id:
                    session_folder = os.path.join(
                        self.base_folder, f"{formatted_timestamp}_Participant_{participant_id}"
                    )
                else:
                    session_folder = os.path.join(self.base_folder, f"session_{formatted_timestamp}")
                
                Path(session_folder).mkdir(parents=True, exist_ok=True)

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
        Log the current eye data from the specified eye to the CSV file.
        
        Args:
            eye_id: EyeId of the eye to log data from
            eye_info: EyeInfo containing the data to log
        
        Returns:
            bool: True if data was logged successfully, False otherwise
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

    ## Current inclusion can be debated, but leaving for now.
    # def get_recording_status(self) -> dict:
    #     """
    #     Get current recording status.
        
    #     Returns:
    #         dict: Contains is_recording, csv_file path, eye_id, and session start time
    #     """
    #     with self._lock:
    #         return {
    #             'is_recording': self.is_recording,
    #             'csv_file': self.csv_file,
    #             'eye_id': self.eye_id.name,
    #             'start_time_ms': self.start_time_ms
    #         }