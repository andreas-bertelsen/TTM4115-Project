import threading

from stmpy import Driver

from helpers import pretty_print
from mqtt_handler import MQTT_Client, MQTT_BROKER, MQTT_PORT
from scooter_handler import ScooterLogic, create_state_machine
from sense_hat_handler import set_led_matrix

def main():
    """
    Main entry point for the scooter system.

    Sets up the state machine, MQTT client, and collision monitoring.
    """
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
    mqtt_client.scooter_id = scooter.scooter_id

    # Start the system
    driver.start()
    mqtt_client.start(MQTT_BROKER, MQTT_PORT)

    # Start collision monitoring in a separate thread
    collision_thread = threading.Thread(target=scooter.monitor_collision, daemon=True)
    collision_thread.start()

    pretty_print("Scooter system is running. Press Ctrl+C to stop.", "SYSTEM")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pretty_print("Stopping system...", "SYSTEM")
        set_led_matrix(None)
        driver.stop()
        mqtt_client.client.disconnect()

if __name__ == "__main__":
    main()
