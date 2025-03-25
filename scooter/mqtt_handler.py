from threading import Thread

from paho.mqtt.client import Client
from paho.mqtt.client import MQTTMessage
from stmpy import Driver

MQTT_BROKER = "mqtt.item.ntnu.no"
MQTT_PORT = 1883

class MQTT_Client:
    def __init__(self):
        self.client = Client()
        self.stm_driver: Driver = None
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client: Client, userdata, flags, rc):
        print("Connected to MQTT broker.")
        client.subscribe("scooter1/command")

    def on_message(self, client, userdata, msg: MQTTMessage):
        command = msg.payload.decode()
        print(f"Received command: {command}")
        if command == "start":
            self.stm_driver.send('start', 'scooter')
        elif command == "stop":
            self.stm_driver.send('stop', 'scooter')
        elif command == "service_checked":
            self.stm_driver.send('service_checked', 'scooter')

    def start(self, broker, port):
        print(f"Connecting to {broker}:{port}...")
        self.client.connect(broker, port)

        ## TODO: Subscribe to correct topic
        self.client.subscribe("scooter/command")

        try:
            thread = Thread(target=self.client.loop_forever)
            thread.start()
        except KeyboardInterrupt:
            print("Stopping MQTT client...")
            self.client.disconnect()

