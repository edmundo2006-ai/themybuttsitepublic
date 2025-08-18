from flask_session import Session
from flask_socketio import SocketIO
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import create_engine

# Flask extensions
socketio = SocketIO(async_mode="eventlet")
session_ext = Session()

# SQLAlchemy 
engine = None
db_session = None

def init_db(uri):
    global engine, db_session
    engine = create_engine(
    uri,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,        # ping before checkout; auto-dispose dead conns
    pool_recycle=300,          # recycle connections before Supabase/pgbouncer idles them
    pool_timeout=30,
    connect_args={
        # SSL + TCP keepalives so intermediaries don’t kill idle sockets
        "sslmode": "require",
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        # Optional: set a server statement timeout to avoid zombie transactions
        "options": "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=15000",
    },)

    db_session = scoped_session(sessionmaker(bind=engine, autoflush=False))
    return engine, db_session

