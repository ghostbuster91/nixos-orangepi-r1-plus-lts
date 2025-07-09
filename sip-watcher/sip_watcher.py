#!/usr/bin/env python3

import pyshark
import threading
import paho.mqtt.publish as publish
import json
from datetime import datetime, timedelta
from dataclasses import dataclass

MQTT_HOST = "192.168.20.55"
MQTT_USER = "admin"
MQTT_PASS = "123456"
TOPIC = "ampio/sip/invite"

@dataclass(frozen=True)
class DialogId:
    call_id: str
    tag1: str
    tag2: str

    def __init__(self, call_id: str, from_tag: str, to_tag: str):
        tags = sorted([from_tag, to_tag])
        object.__setattr__(self, "call_id", call_id)
        object.__setattr__(self, "tag1", tags[0])
        object.__setattr__(self, "tag2", tags[1])

    def __str__(self):
        return f"{self.call_id};tags={self.tag1}_{self.tag2}"

active_calls: dict[DialogId, dict] = {}
current_global_state = "idle"
DEFAULT_SESSION_TIMEOUT = 900  # fallback 15 min

def now():
    return datetime.now()

def now_iso():
    return now().isoformat(timespec='seconds')

def log_active_calls():
    print("Current active calls:", flush=True)
    for call_id, data in active_calls.items():
        base = f"  • {call_id} – {data['state']} | from: {data['from']} | to: {data['to']} | last_update: {data['last_update']}"
        if "expires_at" in data:
            base += f" | expires_at: {data['expires_at']}"
        print(base, flush=True)

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

        dialog_id = DialogId(call_id, from_tag, to_tag)
        timestamp = now()

        if "180 Ringing" in status_line:
            # Deduplicate ringing by from_uri (phone number)
            existing = None
            for did, call in active_calls.items():
                if call["state"] == "ringing" and call["from"] == from_uri:
                    existing = did
                    break

            if existing:
                print(f"🔁 Updating existing ringing for {from_uri} (was {existing}, now {dialog_id})", flush=True)
                # Update existing entry with new dialog_id data
                del active_calls[existing]
            
            print(f"🔔 Ringing: {dialog_id}", flush=True)
            active_calls[dialog_id] = {
                "state": "ringing",
                "from": from_uri,
                "to": to_uri,
                "last_update": timestamp,
                "session_timeout": DEFAULT_SESSION_TIMEOUT,
            }
            log_active_calls()


        elif "200 OK" in status_line and cseq_method == "INVITE":
            timeout = parse_session_expires(sip)
            print(f"📞 Call accepted: {dialog_id} (Session-Expires: {timeout}s)", flush=True)
            log_active_calls()

            to_remove = [
                cid for cid, data in active_calls.items()
                if data["state"] == "active" and cid != dialog_id
            ]
            for cid in to_remove:
                print(f"🧹 Removing other active call: {cid} (conflict with new active)", flush=True)
                del active_calls[cid]

            active_calls[dialog_id] = {
                "state": "active",
                "from": from_uri,
                "to": to_uri,
                "last_update": timestamp,
                "session_timeout": timeout,
            }
            print(f"📞 Call processed: {dialog_id}", flush=True)
            log_active_calls()

        elif method == "CANCEL":
            # cancel does not have to_tag so we need to compare by call_id
            found = None
            for did, call in active_calls.items():
                if did.call_id == call_id and call["state"] == "ringing":
                    found = did
                    break
            if found:
                print(f"❌ Call cancelled via CANCEL: {found}", flush=True)
                del active_calls[found]
                log_active_calls()
            else:
                print(f"⚠️ Unknown call cancel: {call_id}", flush=True)

        elif method == "BYE":
            if dialog_id in active_calls:
                print(f"❌ Call ended via BYE: {dialog_id}", flush=True)
                del active_calls[dialog_id]
                log_active_calls()
            else:
                print(f"⚠️ Unknown call end via BYE: {dialog_id}", flush=True)


        elif method in ["INVITE", "UPDATE"] and dialog_id in active_calls:
            timeout = parse_session_expires(sip)
            print(f"Refreshing session via {method}: {dialog_id} (Session-Expires: {timeout}s)", flush=True)
            active_calls[dialog_id]["last_update"] = timestamp
            active_calls[dialog_id]["session_timeout"] = timeout
            log_active_calls()

        expired = cleanup_expired_sessions()
        new_state = determine_global_state()
        if new_state != current_global_state or expired:
            send_mqtt(new_state)

    except AttributeError:
        continue

