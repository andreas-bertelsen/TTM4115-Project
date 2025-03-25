import math
import time
import threading

from sense_hat import SenseHat

# Initialize Sense HAT
sense = SenseHat()
sense.set_imu_config(True, False, False)  # Use only accelerometer

# Constants
IMPACT_THRESHOLD = 2.0  # Adjust for sensitivity
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)

def get_acceleration():
    """ Get acceleration vector components. """
    accel = sense.get_accelerometer()
    return accel['roll'], accel['pitch']

def detect_impact():
    """ Detect sudden impact based on acceleration changes. """
    accel = sense.get_accelerometer_raw()
    magnitude = math.sqrt(accel['x']**2 + accel['y']**2 + accel['z']**2)
    return magnitude > IMPACT_THRESHOLD, magnitude

def check_orientation():
    """ Check the orientation based on accelerometer data. """
    roll, pitch = get_acceleration()

    # Normalize roll and pitch to the range [-180, 180]
    roll = (roll + 180) % 360 - 180
    pitch = (pitch + 180) % 360 - 180

    print(f"Roll: {roll:.2f} | Pitch: {pitch:.2f}")
    if abs(roll) < 10 and abs(pitch) < 10:  
        return GREEN  # Upright
    elif abs(roll) < 30 and abs(pitch) < 30:  
        return YELLOW  # Slight tilt
    else:  
        return RED  # Significant tilt

def set_led_matrix(color):
    """ Set the LED matrix to a specific color. """
    if color is None:
        sense.clear()
    else:
        sense.clear(color)

def blink_red():
    """ Blink the LED matrix red for impact alert. """ 
    sense.clear(RED)
    time.sleep(0.2)
    sense.clear()
    time.sleep(0.2)

class BlinkAndWaitThread(threading.Thread):
    """ Thread to handle blinking and waiting for joystick input. """
    def __init__(self, timeout=120):
        super().__init__()
        self.timeout = timeout
        self.clicked = False
        self._stop_event = threading.Event()

    def run(self):
        start_time = time.time()
        while time.time() - start_time < self.timeout and not self._stop_event.is_set():
            blink_red()
            events = sense.stick.get_events()
            if any(event.action == "pressed" for event in events):
                self.clicked = True
                break

    def stop(self):
        """ Stop the blinking thread. """
        self._stop_event.set()
