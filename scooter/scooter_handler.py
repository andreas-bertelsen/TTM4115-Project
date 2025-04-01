import time

from paho.mqtt.client import Client
from stmpy import Machine, Driver

from helpers import pretty_print
from sense_hat_handler import blink_and_wait, detect_impact, check_orientation, set_led_matrix, GREEN, RED

class ScooterLogic:
    def __init__(self):
        self.stm: Machine = None
        self.mqtt_client: Client = None
        self.driver: Driver = None
        self.scooter_id: int = 1

    def lock(self):
        """ Lock the scooter. """
        pretty_print("Scooter locked.", "SCOOTER")
        set_led_matrix(RED)

    def unlock(self):
        """ Unlock the scooter. """
        pretty_print("Scooter unlocked.", "SCOOTER")
        set_led_matrix(GREEN)

    def publish_msg(self, msg):
        """ Publish a message to MQTT. """
        topic = f"team20/scooter/status/{self.scooter_id}"
        pretty_print(f"Publishing message: '{msg}' to topic: '{topic}'", "MQTT")
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
            self.publish_msg("parked_add_fare")
        else:
            self.publish_msg("parked")
        return "Idle"
    
    def check_orientation_collision(self):
        """ Check the orientation of the scooter after a collision. """
        orientation = check_orientation()
        if orientation == GREEN:
            return "Active"
        return "Collision_detected"
    
    def handle_collision_response(self):
        """ Handle the collision response logic. """
        user_acknowledged = blink_and_wait(timeout=120)

        set_led_matrix(RED)

        if user_acknowledged:
            pretty_print("User acknowledged collision.", "SCOOTER")
            self.publish_msg("collision_acknowledged")
        else:
            pretty_print("No user response to collision.", "SCOOTER")
            self.publish_msg("collision_no_response")

# State Machine Definition
def create_state_machine(scooter_logic: ScooterLogic):
    t0 = {'source': 'initial', 'target': 'Idle'}
    t1 = {'source': 'Idle', 'trigger': 'start', 'target': 'Active', 'effect': 'unlock(); publish_msg("activated")'}
    t2 = {'source': 'Active', 'trigger': 'stop', 'function': scooter_logic.check_orientation_stop}
    t3 = {'source': 'Collision_detected', 'trigger': 'service_checked', 'target': 'Idle', 'effect': 'publish_msg("parked")'}
    t4 = {'source': 'Active', 'trigger': 'collision', 'function': scooter_logic.check_orientation_collision}

    states = [
        {'name': 'Idle', 'entry': 'lock()'},
        {'name': 'Active'},
        {'name': 'Collision_detected', 'entry': 'lock(); publish_msg("collision"); handle_collision_response()'}
    ]

    return Machine(name='scooter', transitions=[t0, t1, t2, t3, t4], obj=scooter_logic, states=states)