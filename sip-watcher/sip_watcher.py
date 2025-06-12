#!/usr/bin/env python3

import pyshark
import threading
import paho.mqtt.publish as publish

# Konfiguracja MQTT
MQTT_HOST = "192.168.20.55"
MQTT_USER = "admin"
MQTT_PASS = "123456789"
TOPIC = "ampio/sip/invite"

state = 0
reset_timer = None

def send_mqtt(payload):
    print(f"MQTT → {payload}")
    publish.single(
        topic=TOPIC,
        payload=payload,
        hostname=MQTT_HOST,
        auth={"username": MQTT_USER, "password": MQTT_PASS}
    )

def reset_state():
    global state, reset_timer
    if state == 1:
        print("⏲️ Reset (timeout)")
        send_mqtt("0")
        state = 0
    reset_timer = None

def schedule_reset(timeout=10):
    global reset_timer
    if reset_timer:
        reset_timer.cancel()
    reset_timer = threading.Timer(timeout, reset_state)
    reset_timer.start()

print("🔍 SIP watcher started (pyshark)...")

capture = pyshark.LiveCapture(
    interface="br-lan",
    display_filter='sip',
)

for packet in capture.sniff_continuously():
    try:
        sip = packet.sip
        method = getattr(sip, 'Method', None)
        status_line = getattr(sip, 'status_line', "")
        cseq_method = getattr(sip, 'cseq_method', "")

        if "180 Ringing" in status_line:
            if state == 0:
                print("🔔 Dzwoni")
                send_mqtt("1")
                state = 1
                schedule_reset()
        elif "200 OK" in status_line and cseq_method == "INVITE":
            print("✅ Odebrano")
            if state != 0:
                send_mqtt("0")
            state = 0
            if reset_timer:
                reset_timer.cancel()
                reset_timer = None
        elif method in ["CANCEL", "BYE"]:
            print("❌ Rozłączono")
            if state != 0:
                send_mqtt("0")
            state = 0
            if reset_timer:
                reset_timer.cancel()
                reset_timer = None

    except AttributeError:
        continue

