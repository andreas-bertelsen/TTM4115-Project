import math
import time

from sense_hat import SenseHat

# Initialize Sense HAT
sense = SenseHat()
sense.set_imu_config(True, False, False)  # Use only accelerometer

# Constants
IMPACT_THRESHOLD = 2.5  # Adjust for sensitivity
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

def blink_and_wait(timeout=120):
    """ Blink the LED matrix red and wait for joystick input. """
    start_time = time.time()
    while time.time() - start_time < timeout:
        blink_red()
        events = sense.stick.get_events()
        if any(event.action == "pressed" for event in events):
            return True
    return False
