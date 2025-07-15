#!/usr/bin/env python3

import pyshark
import threading
import paho.mqtt.publish as publish
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
import re

MQTT_HOST = "192.168.20.55"
MQTT_USER = "admin"
MQTT_PASS = "123456"
TOPIC = "ampio/sip/invite"
DEFAULT_SESSION_TIMEOUT = 180  # fallback 3 min

@dataclass
class ActiveCall:
    state: str
    from_number: str
    to_uri: str
    last_update: datetime
    session_timeout: int = DEFAULT_SESSION_TIMEOUT
    ringing_timer_start: datetime = None

    def to_dict(self):
        return {
            "state": self.state,
            "from": self.from_number,
            "to": self.to_uri,
            "last_update": self.last_update,
            "session_timeout": self.session_timeout,
        }

    def __str__(self):
        return (
            f"{self.state} | from: {self.from_number} | to: {self.to_uri} "
            f"| last_update: {self.last_update} | ringing_timer_start: {self.ringing_timer_start}"
        )


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


class SipDialog:
    def __init__(self, method, status_line, cseq_method, call_id, from_uri, to_uri, from_tag, to_tag, from_number):
        self.method = method
        self.status_line = status_line
        self.cseq_method = cseq_method
        self.call_id = call_id
        self.from_uri = from_uri
        self.to_uri = to_uri
        self.from_tag = from_tag
        self.to_tag = to_tag
        self.from_number = from_number

    @property
    def id(self):
        dialog_id = DialogId(self.call_id, self.from_tag, self.to_tag)
        return dialog_id

    def __str__(self):
        parts = []
        if self.method:
            parts.append(f"📥 {self.method}")
        elif self.status_line:
            parts.append(f"📤 {self.status_line}")
        else:
            parts.append("📄 <no method/status>")

        if self.from_number:
            parts.append(f"from: {self.from_number}")
        if self.to_uri:
            parts.append(f"to: {self.to_uri}")

        if self.call_id:
            parts.append(f"Call-ID: {self.call_id}")
        if self.from_tag or self.to_tag:
            tags = []
            if self.from_tag:
                tags.append(f"from-tag={self.from_tag}")
            if self.to_tag:
                tags.append(f"to-tag={self.to_tag}")
            parts.append(f"tags: {', '.join(tags)}")

        return " | ".join(parts)


active_calls: dict[DialogId, ActiveCall] = {}
current_global_state = "idle"


def now():
    return datetime.now()


def log_active_calls():
    print("Current active calls:", flush=True)
    for call_id, data in active_calls.items():
        base = f"  • {call_id} – {data}"
        print(base, flush=True)
    print("==================================")


def determine_global_state():
    if any(call.state == "active" for call in active_calls.values()):
        return "active"
    elif any(call.state == "ringing" for call in active_calls.values()):
        return "ringing"
    else:
        return "idle"


def send_mqtt(global_state):
    global current_global_state
    if global_state != current_global_state:
        payload = {
            "state": global_state,
            "active_calls": [
                {k: v for k, v in call.to_dict().items() if k not in ["last_update", "session_timeout"]} 
                for call in active_calls.values()
            ],
            "timestamp": now().isoformat(timespec='seconds')
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
        if call.state != "ringing":
            continue
        if call.ringing_timer_start is None:
            continue  # jeszcze nie liczymy czasu
        cutoff = call.ringing_timer_start + timedelta(seconds=call.session_timeout)
        if now() >= cutoff:
            print(f"🧹 Expiring ringing: {call_id} (timeout {call.session_timeout}s since {call.ringing_timer_start})", flush=True)
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


def extract_phone(uri):
    m = re.search(r'sip:(\d+)', uri)
    return m.group(1) if m else None


def update_ringing_timeouts():
    active_now = any(call.state == "active" for call in active_calls.values())

    for call in active_calls.values():
        if call.state != "ringing":
            continue

        if active_now:
            if call.ringing_timer_start is not None:
                print(f"⏹️ Reset ringing timer for call from {call.from_number} (new active call appeared)", flush=True)
                call.ringing_timer_start = None
        else:
            if call.ringing_timer_start is None:
                print(f"⏱️ Start ringing timeout for call from {call.from_number}", flush=True)
                call.ringing_timer_start = now()

## ==============================================================================

print("🔍 SIP watcher with dynamic Session-Expires started...", flush=True)

capture = pyshark.LiveCapture(
    interface="br-lan",
    display_filter='sip',
)

for packet in capture.sniff_continuously():
    sip = packet.sip
    dialog = SipDialog(
        method=getattr(sip, 'Method', None),
        status_line=getattr(sip, 'status_line', ""),
        cseq_method=getattr(sip, 'cseq_method', ""),
        call_id=getattr(sip, 'call_id', None),
        from_uri=getattr(sip, 'from', ""),
        to_uri=getattr(sip, 'to', ""),
        from_tag=getattr(sip, 'from_tag', ""),
        to_tag=getattr(sip, 'to_tag', ""),
        from_number=extract_phone(getattr(sip, 'from', ""))
    )

    if dialog.call_id is None:
        print(f"call_id is none, method {dialog.method}")
        continue

    timestamp = now()

    print(dialog)
    log_active_calls()

    if "180 Ringing" in dialog.status_line:
        # Deduplicate ringing by from_number (phone number)
        existing = None
        for did, call in active_calls.items():
            if call.state == "ringing" and call.from_number == dialog.from_number:
                existing = did
                break

        if existing:
            print(f"🔁 Updating existing ringing for {dialog.from_number} (was {existing}, now {dialog.id})", flush=True)
            # Update existing entry with new dialog_id data
            del active_calls[existing]
        
        print(f"🔔 Ringing: {dialog.id}", flush=True)
        active_calls[dialog.id] = ActiveCall(
            state= "ringing",
            from_number= dialog.from_number,
            to_uri= dialog.to_uri,
            last_update= timestamp,
        )
        log_active_calls()

    elif "200 OK" in dialog.status_line and dialog.cseq_method == "INVITE":
        timeout = parse_session_expires(sip)
        print(f"📞 Call accepted: {dialog.id} (Session-Expires: {timeout}s)", flush=True)

        to_remove = [
            cid for cid, data in active_calls.items()
            if data.state == "active" and cid != dialog.id
        ]
        for cid in to_remove:
            print(f"🧹 Removing other active call: {cid} (conflict with new active)", flush=True)
            del active_calls[cid]

        # Remove any ringing entries with the same phone number
        to_remove = [
            cid for cid, data in active_calls.items()
            if data.state == "ringing" and data.from_number == dialog.from_number and cid != dialog.id
        ]
        for cid in to_remove:
            print(f"🧹 Removing duplicate ringing from same number: {cid}", flush=True)
            del active_calls[cid]

        active_calls[dialog.id] = ActiveCall(
            state= "active",
            from_number= dialog.from_number,
            to_uri= dialog.to_uri,
            last_update= timestamp,
            session_timeout= timeout,
        )
        print(f"📞 Call processed: {dialog.id}", flush=True)
        log_active_calls()

    elif dialog.method in ["CANCEL"]:
        removed_any = False
        to_remove = [cid for cid, call in active_calls.items() if call.from_number == dialog.from_number]
        for cid in to_remove:
            print(f"❌ Call ended via {dialog.method}: {cid}", flush=True)
            del active_calls[cid]
            removed_any = True

        if not removed_any:
            print(f"⚠️ No active calls found for {dialog.from_number} to end via {dialog.method}", flush=True)
        log_active_calls()

    elif dialog.method == "BYE":
        if dialog.id in active_calls:
            print(f"❌ Call ended via BYE: {dialog.id}", flush=True)
            del active_calls[dialog.id]
        else:
            print(f"⚠️ No active calls found for {dialog.id} to end via {dialog.method} via dialog_id {dialog.id}", flush=True)
            print("Looking by from")
            removed_any = False
            to_remove = [cid for cid, call in active_calls.items() if call.from_number == dialog.from_number]
            for cid in to_remove:
                print(f"❌ Call ended via {dialog.method}: {cid}", flush=True)
                del active_calls[cid]
                removed_any = True

            if not removed_any:
                print(f"⚠️ No active calls found for {dialog.from_number} to end via {dialog.method} via {dialog.from_number}", flush=True)
        log_active_calls()

    update_ringing_timeouts()
    expired = cleanup_expired_sessions()
    new_state = determine_global_state()
    if new_state != current_global_state or expired:
        send_mqtt(new_state)

