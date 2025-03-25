import paho.mqtt.client as mqtt

# MQTT setup
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_broker = "mqtt.item.ntnu.no"
mqtt_port = 1883
mqtt_client.connect(mqtt_broker, mqtt_port)