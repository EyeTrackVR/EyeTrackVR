from eye import EyeId
from enum import Enum
from config import EyeTrackConfig
from utils.CycleCounter import *
import threading

class mirrortrack:
    
    #Defines our possible tracking states
    class States(Enum):
        TRACKING = 0
        STARE = 1
        INVERTED = 2

    state = States.TRACKING

    #Defines our tracked positions
    rx_left_x = 0.0
    rx_left_y = 0.0
    rx_right_x = 0.0
    rx_right_y = 0.0
    rx_dom_eye_x = 0.0
    rx_dom_eye_y = 0.0

    #Defines our processed positions
    tx_left_x = 0.0
    tx_left_y = 0.0
    tx_right_x = 0.0
    tx_right_y = 0.0
    tx_dom_eye_x = 0.0
    tx_dom_eye_y = 0.0

    #Defines other global variables
    inv_x_thresh = 0.3
    is_r_dom = True
    bypass_stare = False

    #Defines variables that require settings
    @classmethod
    def init_config(cls,config: EyeTrackConfig):
        if config.settings.gui_mirrortrack_select_right:
            cls.dom_eye = EyeId.RIGHT
            cls.rec_eye = EyeId.LEFT
            cls.is_r_dom = True
        else:
            cls.dom_eye = EyeId.LEFT
            cls.rec_eye = EyeId.RIGHT
            cls.is_r_dom = False
        
        #Inversion related
        cls.inv_is_enabled = config.settings.gui_mirrortrack_enable_inv
        cls.inv_x_thresh = config.settings.gui_mirrortrack_minthresh
        cls.inv_clamp = config.settings.gui_mirrortrack_rotation_clamp

        cls.cyc_counts_inv = config.settings.gui_mirrortrack_cycle_count_inv
        cls.cyc_counts_stare = config.settings.gui_mirrortrack_cycle_count_stare

        cls.cyc_counter_inv = CycleCounter(cls.cyc_counts_inv)
        cls.cyc_counter_stare = CycleCounter(cls.cyc_counts_stare)

        cls.thread_lock = threading.Lock()

    #Receives changes in configuration and applies them accordingly
    @classmethod
    def config_update(cls,data):

        if "gui_mirrortrack_select_right" in data:
            cls.dom_eye = EyeId.RIGHT if data["gui_mirrortrack_select_right"] else EyeId.LEFT
            cls.rec_eye = EyeId.LEFT if data["gui_mirrortrack_select_right"] else EyeId.RIGHT
            cls.is_r_dom = True if data["gui_mirrortrack_select_right"] else False
            print(f"Dominant eye changed to {cls.dom_eye.name}")

        if "gui_mirrortrack_minthresh" in data:
            cls.inv_x_thresh = data["gui_mirrortrack_minthresh"]
            print(f"MirrorTrack transition threshold changed to {cls.inv_x_thresh}")

        if "gui_mirrortrack_cycle_count_inv" in data:
            cls.cyc_counts_stare = data["gui_mirrortrack_cycle_count_inv"]
            cls.cyc_counter_stare.update(cls.cyc_counts_stare)
            print(f"MirrorTrack inversion transition condition required cycle count changed to {cls.cyc_counts_inv}")

        if "gui_mirrortrack_cycle_count_stare" in data:
            cls.cyc_counts_inv = data["gui_mirrortrack_cycle_count_stare"]
            cls.cyc_counter_stare.update(cls.cyc_counts_inv)
            print(f"MirrorTrack stare transition condition required cycle count changed to {cls.cyc_counts_stare}")

        if "gui_mirrortrack_rotation_clamp" in data:
            cls.inv_clamp = data["gui_mirrortrack_rotation_clamp"]
            print(f"MirrorTrack maximum allowed cross-eye changed to {cls.inv_clamp}")

        if "gui_mirrortrack_enable_inv" in data:
            cls.inv_is_enabled = data["gui_mirrortrack_enable_inv"]
            print(f"MirrorTrack allow cross-eye is set to {cls.inv_is_enabled}")

    #Main processing function
    @classmethod
    def process(cls,eye_id,out_x,out_y):
        with cls.thread_lock:
            cls.store_tracked_positions(eye_id,out_x,out_y)
            cls.check_for_stare()

            if cls.inv_is_enabled:
                cls.check_for_inversion()
                
            out_x, out_y = cls.update_new_position(eye_id,out_x,out_y)
            cls.store_processed_positions(eye_id,out_x,out_y)
            return out_x, out_y
    
    #Main methods that are called during processing
    @classmethod
    def store_tracked_positions(cls, eye_id, out_x,out_y):
        if cls.is_processing_right_eye(eye_id):
            cls.rx_right_x = out_x
            cls.rx_right_y = out_y
            if cls.is_dominant_eye(eye_id):
                cls.rx_dom_eye_x = cls.rx_right_x
                cls.rx_dom_eye_y = cls.rx_right_y
        else:
            cls.rx_left_x = out_x
            cls.rx_left_y = out_y
            if cls.is_dominant_eye(eye_id):
                cls.rx_dom_eye_x = cls.rx_left_x
                cls.rx_dom_eye_y = cls.rx_left_y

    @classmethod
    def store_processed_positions(cls, eye_id, out_x,out_y):
        if cls.is_processing_right_eye(eye_id):
            cls.tx_right_x = out_x
            cls.tx_right_y = out_y
            if cls.is_dominant_eye(eye_id):
                cls.tx_dom_eye_x = cls.tx_right_x
                cls.tx_dom_eye_y = cls.tx_right_y
        else:
            cls.tx_left_x = out_x
            cls.tx_left_y = out_y
            if cls.is_dominant_eye(eye_id):
                cls.tx_dom_eye_x = cls.tx_left_x
                cls.tx_dom_eye_y = cls.tx_left_y

    @classmethod
    def check_for_stare(cls):
        if cls.dom_is_inward() and cls.rec_is_inward():

            #Updates the counter for stare activation
            if not cls.is_stare_mode() and not cls.cyc_counter_stare.is_complete():
                cls.cyc_counter_stare.increase()
            
            #Sets the state to stare if count is_completes
            elif not cls.is_stare_mode() and cls.cyc_counter_stare.is_complete() and not cls.bypass_stare:
                cls.set_state("STARE")

        elif cls.cyc_counter_stare.active():
                cls.cyc_counter_stare.decrease()

        if not cls.cyc_counter_stare.active():
            if cls.bypass_stare:
                cls.bypass_stare = False
            if not cls.is_tracking_mode():
                cls.set_state("TRACKING")
        
    @classmethod
    def check_for_inversion(cls):
        if cls.dom_is_inward() and cls.rec_meets_thresh() and (cls.is_stare_mode() or cls.bypass_stare):

            #Updates the counter for activation
            if not cls.is_inverted_mode() and not cls.cyc_counter_inv.is_complete():
                cls.cyc_counter_inv.increase()
                #print(f"Inversion activation counter is increasing: {cls.cyc_counter_inv.get_count()}")
                
            #Sets the state to inverted if enough cycles have is_completed
            elif not cls.is_inverted_mode() and cls.cyc_counter_inv.is_complete():
                cls.set_state("INVERTED")
                cls.bypass_stare = True
        
        #Begins the counter for deactivation if conditions are not met
        elif cls.cyc_counter_inv.active():
                cls.cyc_counter_inv.decrease()
            
        if not cls.cyc_counter_inv.active():
            if cls.bypass_stare:
                cls.bypass_stare = False
            cls.cyc_counter_stare.force_complete()
            cls.check_for_stare()

    @classmethod
    def update_new_position(cls,eye_id,out_x,out_y):
        if cls.is_stare_mode():
            out_x, out_y = 0, cls.rx_dom_eye_y

        elif not cls.is_dominant_eye(eye_id) and cls.is_inverted_mode():
            out_x, out_y = -cls.rx_dom_eye_x, cls.rx_dom_eye_y
            
        else:
            out_x, out_y = cls.rx_dom_eye_x, cls.rx_dom_eye_y
        
        if cls.is_inverted_mode():
            if cls.is_processing_right_eye(eye_id):
                out_x = max(out_x,-cls.inv_clamp)
            else:
                out_x = min(out_x,cls.inv_clamp)

        return out_x, out_y
      
    #Helper Methods
    @classmethod
    def is_tracking_mode(cls):
        return cls.state == cls.States.TRACKING
    @classmethod
    def is_stare_mode(cls):
        return cls.state == cls.States.STARE
    @classmethod
    def is_inverted_mode(cls):
        return cls.state == cls.States.INVERTED
    @classmethod
    def set_state(cls,new_state: str):
        cls.state = cls.States[new_state]
        print(f"State set to {cls.state.name}")
    @classmethod
    def is_dominant_eye(cls,eye_id):
        return eye_id == cls.dom_eye
    @classmethod
    def is_processing_right_eye(cls,eye_id):
        return eye_id == EyeId.RIGHT
    @classmethod
    def dom_is_inward(cls):
        return (cls.is_r_dom and cls.rx_right_x < 0) or (not cls.is_r_dom and cls.rx_left_x > 0)
    @classmethod
    def rec_is_inward(cls):
        return (cls.is_r_dom and cls.rx_left_x > 0) or (not cls.is_r_dom and cls.rx_right_x < 0)
    @classmethod
    def dom_meets_thresh(cls):
        return (cls.is_r_dom and cls.rx_right_x < -cls.inv_x_thresh) or (not cls.is_r_dom and cls.rx_left_x > cls.inv_x_thresh)
    @classmethod
    def rec_meets_thresh(cls):
        return (cls.is_r_dom and cls.rx_left_x > cls.inv_x_thresh) or (not cls.is_r_dom and cls.rx_right_x < -cls.inv_x_thresh)
    @classmethod
    def x_diff(cls):
        return abs(cls.rx_left_x - cls.rx_right_x)
    
    """class Smoothing:
        def __init__(self, smoothing_rate=0.05):
            self.smoothing_rate = smoothing_rate
            self.start_x = 0.0
            self.target_x = 0.0
            self.out
        
        def process_smoothing(self,out_x,out_y):
            out_x = (self.start_x += (self.start_x - self.target_x) * smoothing_rate)"""