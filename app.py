import eventlet
eventlet.monkey_patch()

from dotenv import load_dotenv

from themybuttsite import create_app
from themybuttsite.extensions import socketio


load_dotenv()

app = create_app()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
