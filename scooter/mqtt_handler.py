from threading import Thread

from paho.mqtt.client import Client, MQTTMessage
from stmpy import Driver

from helpers import pretty_print

MQTT_BROKER = "mqtt.item.ntnu.no"
MQTT_PORT = 1883

class MQTT_Client:
    """
    Handles MQTT communication for the scooter system.
    """

    def __init__(self):
        self.client: Client = Client()
        self.stm_driver: Driver = None
        self.scooter_id: int = None
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client: Client, userdata, flags, rc):
        """
        Callback for when the client connects to the MQTT broker.

        Args:
            client (Client): The MQTT client instance.
            userdata: User-defined data.
            flags: Response flags sent by the broker.
            rc: Connection result.
        """
        pretty_print("Connected to MQTT broker.", "MQTT")
        client.subscribe(f"team20/scooter/command/{self.scooter_id}")

    def on_message(self, client, userdata, msg: MQTTMessage):
        """
        Callback for when a message is received from the MQTT broker.

        Args:
            client (Client): The MQTT client instance.
            userdata: User-defined data.
            msg (MQTTMessage): The received message.
        """
        command = msg.payload.decode()
        pretty_print(f"Received command: {command}", "MQTT")
        state = self.stm_driver._stms_by_id['scooter'].state

        if command == "start" and state == "Idle":
            self.stm_driver.send('start', 'scooter')
        elif command == "stop" and state == "Active":
            self.stm_driver.send('stop', 'scooter')
        elif command == "service_checked" and state == "Collision_detected":
            self.stm_driver.send('service_checked', 'scooter')

    def start(self, broker, port):
        """
        Start the MQTT client and connect to the broker.

        Args:
            broker (str): The MQTT broker address.
            port (int): The MQTT broker port.
        """
        pretty_print(f"Connecting to {broker}:{port}...", "MQTT")
        self.client.connect(broker, port)

        try:
            thread = Thread(target=self.client.loop_forever)
            thread.start()
        except KeyboardInterrupt:
            pretty_print("Stopping MQTT client...", "MQTT")
            self.client.disconnect()

