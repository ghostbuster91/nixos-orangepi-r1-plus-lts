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

active_calls = {}  # dialog_id -> { state, from, to, last_update, session_timeout }
current_global_state = "idle"
DEFAULT_SESSION_TIMEOUT = 900  # fallback 15 min

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
                {k: v for k, v in call.items() if k not in ["last_update", "session_timeout"]} 
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
    for call_id, call in list(active_calls.items()):
        timeout = call.get("session_timeout", DEFAULT_SESSION_TIMEOUT)
        cutoff = now() - timedelta(seconds=timeout)
        if call["last_update"] < cutoff:
            print(f"🧹 Expiring stale call: {call_id} (timeout={timeout}s)", flush=True)
            expired.append(call_id)
            del active_calls[call_id]
    return len(expired) > 0

def parse_session_expires(sip):
    if hasattr(sip, "session_expires"):
        try:
            return int(sip.session_expires.split(";")[0].strip())
        except Exception:
            pass
    return DEFAULT_SESSION_TIMEOUT

print("🔍 SIP watcher with dynamic Session-Expires started...", flush=True)

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
        from_tag = getattr(sip, 'from_tag', "")
        to_tag = getattr(sip, 'to_tag', "")

        if call_id is None:
            continue

        dialog_id = f"{call_id};from-tag={from_tag};to-tag={to_tag}"
        timestamp = now()

        if "180 Ringing" in status_line:
            print(f"🔔 Ringing: {dialog_id}", flush=True)
            active_calls[dialog_id] = {
                "state": "ringing",
                "from": from_uri,
                "to": to_uri,
                "last_update": timestamp,
                "session_timeout": DEFAULT_SESSION_TIMEOUT,
            }

        elif "200 OK" in status_line and cseq_method == "INVITE":
            timeout = parse_session_expires(sip)
            print(f"📞 Call accepted: {dialog_id} (Session-Expires: {timeout}s)", flush=True)
            active_calls[dialog_id] = {
                "state": "active",
                "from": from_uri,
                "to": to_uri,
                "last_update": timestamp,
                "session_timeout": timeout,
            }

        elif method in ["CANCEL", "BYE"]:
            if dialog_id in active_calls:
                print(f"❌ Call ended via {method}: {dialog_id}", flush=True)
                del active_calls[dialog_id]

        elif method in ["INVITE", "UPDATE"] and dialog_id in active_calls:
            timeout = parse_session_expires(sip)
            print(f"🔄 Refreshing session via {method}: {dialog_id} (Session-Expires: {timeout}s)", flush=True)
            active_calls[dialog_id]["last_update"] = timestamp
            active_calls[dialog_id]["session_timeout"] = timeout

        expired = cleanup_expired_sessions()
        new_state = determine_global_state()
        if new_state != current_global_state or expired:
            send_mqtt(new_state)

    except AttributeError:
        continue

