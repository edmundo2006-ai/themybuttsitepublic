import json, firebase_admin
from firebase_admin import credentials

def init_firebase(app):
    if firebase_admin._apps:
        return firebase_admin.get_app()

    sa_json = app.config.get("FIREBASE_SERVICE_ACCOUNT")
    if not sa_json:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT not set in config")

    info = json.loads(sa_json)
    cred = credentials.Certificate(info)

    opts = {}
    if info.get("project_id"):
        opts["projectId"] = info["project_id"]

    return firebase_admin.initialize_app(cred, opts or None)