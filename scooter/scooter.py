from sense_hat import SenseHat
import time
import math
import os

# Initialize Sense HAT
sense = SenseHat()
sense.set_imu_config(True, True, True)  # Enable gyroscope and accelerometer

# Constants
IMPACT_THRESHOLD = 5.0  # G-force threshold for an impact
SPEED_SENSITIVITY = 0.1  # Adjust based on expected scooter acceleration
ALERT_DURATION = 3       # Duration to display alert in seconds

# Colors
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)

# Variables for speed estimation
prev_time = time.time()
speed = 0  # Estimated speed in arbitrary units

def get_acceleration():
    """ Get the acceleration vector magnitude. """
    accel = sense.get_accelerometer_raw()
    ax, ay, az = accel['x'], accel['y'], accel['z']
    magnitude = math.sqrt(ax**2 + ay**2 + az**2)
    return magnitude, ax, ay, az

def get_gyro():
    """ Get gyroscope data (angular velocity). """
    gyro = sense.get_gyroscope()
    return gyro['roll'], gyro['pitch'], gyro['yaw']

def estimate_speed():
    """ Estimate speed using acceleration over time (basic integration). """
    global prev_time, speed
    magnitude, _, _, _ = get_acceleration()
    
    # Time difference
    current_time = time.time()
    delta_time = current_time - prev_time
    prev_time = current_time

    # Approximate speed using acceleration (simplified)
    speed += magnitude * SPEED_SENSITIVITY * delta_time
    return round(speed, 2)

def detect_impact():
    """ Detect sudden impact based on acceleration changes. """
    magnitude, _, _, _ = get_acceleration()
    if magnitude > IMPACT_THRESHOLD:
        return True, magnitude
    return False, magnitude

def alert_user(message, color):
    """ Display an alert on the Sense HAT LED matrix. """
    sense.show_message(message, text_colour=color)
    # (Optional) Play a buzzer sound if a buzzer is attached
    os.system("play -n synth 0.3 sine 440")  # Requires `sox` package

def main():
    print("Monitoring speed and impacts...")
    while True:
        try:
            speed = estimate_speed()
            impact, impact_value = detect_impact()

            # Display speed on LED matrix
            sense.clear(GREEN if speed < 10 else YELLOW)
            print(f"Speed: {speed} | Impact: {impact_value:.2f}")

            # Impact alert
            if impact:
                print("!!! Impact detected !!!")
                alert_user("IMPACT!", RED)
                time.sleep(ALERT_DURATION)

            time.sleep(0.5)

        except KeyboardInterrupt:
            print("Stopping monitoring...")
            sense.clear()
            break

if __name__ == "__main__":
    main()
