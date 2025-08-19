from flask import Flask
import redis

from themybuttsite.extensions import socketio, cors, session_ext, init_db
import themybuttsite.extensions as ext 
from themybuttsite.firebase_admin_ext import init_firebase 

def create_app(config_class='themybuttsite.config.Config'):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(config_class)

    if app.config.get("REDIS_URL"):
        # Flask-Session expects a Redis *client*, not a URL string
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = redis.Redis.from_url(app.config["REDIS_URL"])
    else:
        app.config["SESSION_TYPE"] = "filesystem"

    # Flask extensions
    cors.init_app(app)            # CORS
    session_ext.init_app(app)     # Server-side sessions (if configured)
    socketio.init_app(app)        # Socket.IO

    # DB session (SQLAlchemy core)
    init_db(app.config['DATABASE_URL'])
    init_firebase(app)

    # Teardown: remove scoped_session at end of request/app context
    @app.teardown_request
    def end_txn_on_request(exc):
        sess = ext.db_session
        if not sess:
            return  # avoid AttributeError if something initializes before init_db
        try:
            if exc is not None:
                sess.rollback()
            else:
                sess.commit()
        finally:
            sess.remove()
    # in app factory
    import time
    import logging
    from flask import g, request

    # configure once (e.g., in create_app)
    log = logging.getLogger("perf")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False

    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()

    @app.after_request
    def _log_slow(resp):
        t0 = getattr(g, "_t0", None)
        if t0 is not None:
            dt_ms = (time.perf_counter() - t0) * 1000
            if dt_ms > 250:  # tweak threshold
                log.warning("SLOW %s %s %.0f ms status=%s",
                            request.method, request.path, dt_ms, resp.status_code)
        return resp

    # Blueprints
    from themybuttsite.auth.routes import bp_auth
    from themybuttsite.consumer.api import bp_consumer_api
    from themybuttsite.consumer.pages import bp_consumer_pages 
    from themybuttsite.staff.api import bp_staff_api
    from themybuttsite.staff.pages import bp_staff_pages
    from themybuttsite.stripe.routes import bp_stripe
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_consumer_api)
    app.register_blueprint(bp_consumer_pages)
    app.register_blueprint(bp_staff_api)
    app.register_blueprint(bp_staff_pages)
    app.register_blueprint(bp_stripe)

    # Jinja filters
    from .jinjafilters.filters import register_filters
    register_filters(app)


    # Socket.IO event handlers (IMPORT so decorators bind)
    from themybuttsite.staff import events as _

    return app
