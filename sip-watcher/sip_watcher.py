#!/usr/bin/env python3

import pyshark
import threading
import paho.mqtt.publish as publish
import json
from datetime import datetime, timedelta

MQTT_HOST = "192.168.20.55"
MQTT_USER = "admin"
MQTT_PASS = "123456"
TOPIC = "ampio/sip/invite"

active_calls = {}  # Call-ID -> { state, from, to, last_update }
current_global_state = "idle"
SESSION_TIMEOUT = 900  # 15 minutes in seconds

def now():
    return datetime.now()

def now_iso():
    return now().isoformat(timespec='seconds')

def determine_global_state():
    if any(call["state"] == "active" for call in active_calls.values()):
        return "active"
    elif any(call["state"] == "ringing" for call in active_calls.values()):
        return "ringing"
    else:
        return "idle"

def send_mqtt(global_state):
    global current_global_state
    if global_state != current_global_state:
        payload = {
            "state": global_state,
            "active_calls": [
                {k: v for k, v in call.items() if k != "last_update"} 
                for call in active_calls.values()
            ],
            "timestamp": now_iso()
        }
        print(f"MQTT → {json.dumps(payload)}", flush=True)
        publish.single(
            topic=TOPIC,
            payload=json.dumps(payload),
            hostname=MQTT_HOST,
            auth={"username": MQTT_USER, "password": MQTT_PASS}
        )
        current_global_state = global_state

def cleanup_expired_sessions():
    expired = []
    cutoff = now() - timedelta(seconds=SESSION_TIMEOUT)
    for call_id, call in list(active_calls.items()):
        if call["last_update"] < cutoff:
            print(f"🧹 Expiring stale call: {call_id}", flush=True)
            expired.append(call_id)
            del active_calls[call_id]
    return len(expired) > 0

print("🔍 SIP watcher with Call-ID + timeout tracking started (pyshark)...", flush=True)

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
        call_id = getattr(sip, 'call_id', None)
        from_uri = getattr(sip, 'from', "")
        to_uri = getattr(sip, 'to', "")

        if call_id is None:
            continue

        timestamp = now()

        if "180 Ringing" in status_line:
            active_calls[call_id] = {
                "state": "ringing",
                "from": from_uri,
                "to": to_uri,
                "last_update": timestamp
            }
        elif "200 OK" in status_line and cseq_method == "INVITE":
            active_calls[call_id] = {
                "state": "active",
                "from": from_uri,
                "to": to_uri,
                "last_update": timestamp
            }
        elif method in ["CANCEL", "BYE"]:
            if call_id in active_calls:
                print(f"❌ Call ended via {method}: {call_id}", flush=True)
                del active_calls[call_id]

        expired = cleanup_expired_sessions()
        new_state = determine_global_state()
        if new_state != current_global_state or expired:
            send_mqtt(new_state)

    except AttributeError:
        continue

