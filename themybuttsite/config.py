import os

class Config:
    # --- Your env vars ---
    YALIES_API_KEY = os.environ.get("YALIES_API_KEY")
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
    SQLALCHEMY_DATABASE_URL = os.environ.get("SQLALCHEMY_DATABASE_URL")
    DATABASE_URL = os.environ.get("DATABASE_URL")
    DATABASE_URL_DIRECT = os.environ.get("DATABASE_URL_DIRECT")
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET")
    SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    REDIS_URL = os.environ.get("REDIS_URL")
    CAS_LOGIN_URL = os.environ.get("CAS_LOGIN_URL")
    CAS_VALIDATE_URL= os.environ.get("CAS_VALIDATE_URL")
    SERVICE_URL= os.environ.get("SERVICE_URL")
    CAS_ENABLED = os.environ.get("CAS_ENABLED")

    # --- Sessions  ---
    SESSION_TYPE = "redis" 
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = False
    SESSION_KEY_PREFIX = "sess:"

    # --- Cookie hardening ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False     # set False locally if not using HTTPS
    SESSION_COOKIE_SAMESITE = "Lax"

    # --- CORS ---
    CORS_ORIGINS = "*"
    @staticmethod
    def cors_resources():
        return {r"/*": {"origins": Config.CORS_ORIGINS}}
