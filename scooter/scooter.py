import time
import threading

from paho.mqtt.client import Client
from stmpy import Machine, Driver

from mqtt_handler import MQTT_Client, MQTT_BROKER, MQTT_PORT
from sense_hat_utils import BlinkAndWaitThread, detect_impact, check_orientation, set_led_matrix, GREEN, RED

class ScooterLogic:
    def __init__(self):
        self.stm: Machine = None
        self.mqtt_client: Client = None
        self.driver: Driver = None

    def lock(self):
        """ Lock the scooter. """
        print("Scooter locked.")
        set_led_matrix(RED)

    def unlock(self):
        """ Unlock the scooter. """
        print("Scooter unlocked.")
        set_led_matrix(GREEN)

    def add_fare(self):
        """ Add fare when the ride ends. """
        print("Fare added.")

    def publish_msg(self, msg, topic):
        """ Publish a message to MQTT. """
        print(f"Publishing message: '{msg}' to topic: '{topic}'")
        self.mqtt_client.publish(topic, msg)

    def monitor_collision(self):
        """ Monitor for collisions and handle state transitions. """
        while True:
            impact, _ = detect_impact()
            if impact and self.stm.state == 'Active':
                self.stm.send('collision')
            time.sleep(0.01)

    def check_orientation_stop(self):
        """ Check the orientation of the scooter. """
        orientation = check_orientation()
        if orientation == RED:
            self.add_fare()
        return "Idle"
    
    def check_orientation_collision(self):
        """ Check the orientation of the scooter after a collision. """
        orientation = check_orientation()
        if orientation == GREEN:
            return "Active"
        return "Collision_detected"
    
    def handle_collision_response(self):
        """ Handle the collision response logic. """
        blink_thread = BlinkAndWaitThread(timeout=120)
        blink_thread.start()
        blink_thread.join()  # Wait for the thread to finish

        set_led_matrix(RED)

        if blink_thread.clicked:
            print("User acknowledged collision.")
            self.publish_msg("collision_acknowledged", "scooter1/status")
        else:
            print("No user response to collision.")
            self.publish_msg("collision_no_response", "scooter1/status")

# State Machine Definition
def create_state_machine(scooter_logic: ScooterLogic):
    t0 = {'source': 'initial', 'target': 'Idle'}
    t1 = {'source': 'Idle', 'trigger': 'start', 'target': 'Active', 'effect': 'unlock(); publish_msg("booked", "scooter1/status")'}
    t2 = {'source': 'Active', 'trigger': 'stop', 'function': scooter_logic.check_orientation_stop}
    t3 = {'source': 'Collision_detected', 'trigger': 'service_checked', 'target': 'Idle'}
    t4 = {'source': 'Active', 'trigger': 'collision', 'function': scooter_logic.check_orientation_collision}

    states = [
        {'name': 'Idle', 'entry': 'lock()', 'collision': 'defer', 'stop': 'defer', 'service_checked': 'defer'},
        {'name': 'Active', 'start': 'defer', 'service_checked': 'defer'},
        {'name': 'Collision_detected', 
         'entry': 'lock(); publish_msg("collision", "scooter1/status"); handle_collision_response()', 
         'collision': 'defer', 'start': 'defer', 'stop': 'defer'}
    ]

    return Machine(name='scooter', transitions=[t0, t1, t2, t3, t4], obj=scooter_logic, states=states)

def main():
    # State Machine Setup
    scooter = ScooterLogic()
    stm = create_state_machine(scooter)
    scooter.stm = stm

    # Driver Setup
    driver = Driver()
    driver.add_machine(stm)
    scooter.driver = driver

    # MQTT Setup
    mqtt_client = MQTT_Client()
    scooter.mqtt_client = mqtt_client.client
    mqtt_client.stm_driver = driver

    # Start the system
    driver.start()
    mqtt_client.start(MQTT_BROKER, MQTT_PORT)

    # Start collision monitoring in a separate thread
    collision_thread = threading.Thread(target=scooter.monitor_collision, daemon=True)
    collision_thread.start()

    print("Scooter system is running. Press Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("Stopping system...")
        set_led_matrix(None)
        driver.stop()
        mqtt_client.client.disconnect()

if __name__ == "__main__":
    main()
