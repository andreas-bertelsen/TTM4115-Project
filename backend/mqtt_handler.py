import asyncio
import sqlite3

from paho.mqtt.client import Client
from paho.mqtt.client import MQTTMessage

from db_setup import DATABASE

# MQTT setup
mqtt_client = Client()
mqtt_broker = "mqtt.item.ntnu.no"
mqtt_port = 1883

# Dictionary to store responses from scooters
mqtt_responses = {}

def on_connect(client: Client, userdata, flags, rc):
    """
    Callback for when the client connects to the MQTT broker.

    Args:
        client (Client): The MQTT client instance.
        userdata: User-defined data.
        flags: Response flags sent by the broker.
        rc: Connection result.
    """
    print("Connected to MQTT broker")
    # Subscribe to the status topic
    client.subscribe("team20/scooter/status/#")

def on_message(client, userdata, msg: MQTTMessage):
    """
    Callback for when a message is received from the MQTT broker.

    Args:
        client (Client): The MQTT client instance.
        userdata: User-defined data.
        msg (MQTTMessage): The received message.
    """
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"Received message on topic {topic}: {payload}")

    # Extract scooter ID from the topic
    if topic.startswith("team20/scooter/status/"):
        scooter_id = int(topic.split("/")[-1])
        mqtt_responses[scooter_id] = payload

        # Detect collision and mark scooter as needing fixing
        if payload == "collision":
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                # Mark the scooter as needing fixing
                cursor.execute("UPDATE scooters SET needs_fixing = 1 WHERE id = ?", (scooter_id,))
                # Terminate any active booking for the scooter
                cursor.execute("""
                    DELETE FROM bookings
                    WHERE scooter_id = ? AND status = 'active'
                """, (scooter_id,))
                # Free up the scooter
                cursor.execute("UPDATE scooters SET isBooked = 0 WHERE id = ?", (scooter_id,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"Error handling collision: {e}")
            finally:
                conn.close()

# Initialize MQTT client
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(mqtt_broker, mqtt_port)
mqtt_client.loop_start()

async def send_command(scooter_id, command):
    """
    Send a command to a scooter and wait for a response.

    Args:
        scooter_id (int): The ID of the scooter.
        command (str): The command to send.

    Returns:
        str or None: The response from the scooter, or None if no response is received.
    """
    topic = f"team20/scooter/command/{scooter_id}"
    mqtt_client.publish(topic, command)
    print(f"Sent '{command}' command to {topic}")

    # Wait for a response
    for _ in range(25):  # Wait up to 5 seconds
        if mqtt_responses.get(scooter_id) in ("activated", "parked", "parked_normal_fare", "parked_increased_fare"):
            response = mqtt_responses.pop(scooter_id)
            print(f"Received response: {response}")
            return response
        await asyncio.sleep(0.2)

    print("No response received within timeout.")
    return None