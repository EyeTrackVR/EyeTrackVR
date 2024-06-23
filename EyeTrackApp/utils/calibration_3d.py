# calibration_module.py

class CalibrationProcessor:
    def __init__(self):
        self.left_eye_data = None
        self.right_eye_data = None

    def receive_calibration_data(self, eye_id, data):
        if eye_id == 1:
            self.left_eye_data = data
        elif eye_id == 0:
            self.right_eye_data = data

       # print('receive',len(self.left_eye_data), self.left_eye_data, self.right_eye_data, data, eye_id)
        # Check if both sets of data have been received
        if self.left_eye_data is not None and self.right_eye_data is not None:
            if len(self.left_eye_data) == 8 and len(self.right_eye_data) == 8:
                self.process_calibration_data()

    def process_calibration_data(self):
        # Ensure both data are present
        if self.left_eye_data is None or self.right_eye_data is None:
            raise ValueError("Calibration data for both eyes must be provided")


        print("Processing calibration data for both eyes...")
        print(f"Left Eye Data: {self.left_eye_data}")
        print(f"Right Eye Data: {self.right_eye_data}")

        # After processing, reset the data
       # self.left_eye_data = None
      #  self.right_eye_data = None

# Global instance of CalibrationProcessor
calibration_processor = CalibrationProcessor()

def receive_calibration_data(data, eye_id):
    global calibration_processor
    calibration_processor.receive_calibration_data(eye_id, data)
