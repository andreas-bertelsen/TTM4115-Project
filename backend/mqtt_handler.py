import asyncio

from paho.mqtt.client import Client
from paho.mqtt.client import MQTTMessage

# MQTT setup
mqtt_client = Client()
mqtt_broker = "mqtt.item.ntnu.no"
mqtt_port = 1883

# Dictionary to store responses from scooters
mqtt_responses = {}

def on_connect(client: Client, userdata, flags, rc):
    print("Connected to MQTT broker")
    # Subscribe to the status topic
    client.subscribe("team20/scooter/status/#")

def on_message(client, userdata, msg: MQTTMessage):
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"Received message on topic {topic}: {payload}")

    # Extract scooter ID from the topic
    if topic.startswith("team20/scooter/status/"):
        scooter_id = int(topic.split("/")[-1])
        mqtt_responses[scooter_id] = payload

# Initialize MQTT client
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(mqtt_broker, mqtt_port)
mqtt_client.loop_start()

async def send_command(scooter_id, command):
    """
    Send a start or stop command to the scooter and wait for a response.
    """
    topic = f"team20/scooter/command/{scooter_id}"
    mqtt_client.publish(topic, command)
    print(f"Sent '{command}' command to {topic}")

    # Wait for a response
    for _ in range(30):  # Wait up to 30 seconds
        print(mqtt_responses)
        if mqtt_responses.get(scooter_id) in ["activated", "parked"]:
            response = mqtt_responses.pop(scooter_id)
            print(f"Received response: {response}")
            return response
        await asyncio.sleep(1)

    print("No response received within timeout.")
    return None