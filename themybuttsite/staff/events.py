# staff/events.py
from flask_socketio import join_room

from themybuttsite.extensions import socketio
from themybuttsite.wrappers.wrappers import socket_login_required, socket_role_required

NAMESPACE = "/staff"

@socketio.on("connect", namespace=NAMESPACE)
@socket_login_required
@socket_role_required("staff")
def staff_connect():
    pass

@socketio.on("join_staff", namespace=NAMESPACE)
@socket_login_required
@socket_role_required("staff")
def handle_join_staff(payload=None, *args, **kwargs):
    room = "staff_updates"
    if isinstance(payload, str) and payload:
        room = payload
    elif isinstance(payload, dict) and payload.get("room"):
        room = payload["room"]
    join_room(room)
    return {"ok": True, "room": room}