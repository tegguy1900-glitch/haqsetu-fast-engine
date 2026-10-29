import paho.mqtt.client as mqtt
import json
import asyncio

BROKER_ADDRESS = "localhost"
TOPIC_COMMAND = "haqsetu/hardware/cmd"

client = mqtt.Client()
try:
    client.connect(BROKER_ADDRESS, 1883, 60)
except Exception as e:
    print(f"⚠️ MQTT Connect Failed (Broker down?): {e}")

async def publish_iot_command(payload: dict):
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: client.publish(TOPIC_COMMAND, json.dumps(payload)))
        print(f"📡 Published to MQTT: {payload}")
    except Exception as e:
        print(f"❌ Publish Error: {e}")
