from flask import Blueprint, render_template, request, redirect, flash, session, url_for, current_app
import requests
import jwt



from models import Users
from themybuttsite.extensions import db_session
from themybuttsite.wrappers.wrappers import login_required
from themybuttsite.yalies_api.yalies_api import fetch_profile, YaliesError

bp_auth = Blueprint("auth", __name__)



@bp_auth.route('/', methods=['GET', 'POST'])
def index():
    CAS_ENABLED = True if current_app.config.get("CAS_ENABLED") == "True" else False
    if request.method == 'POST':
        return redirect(url_for('auth.login'))
    return render_template(
        "login.html",
        CAS_ENABLED = CAS_ENABLED,
        SUPABASE_URL=current_app.config.get("SUPABASE_URL"),
        SUPABASE_ANON_KEY=current_app.config.get("SUPABASE_ANON_KEY")
    )

@bp_auth.route('/login')
def login():
    # Already logged in? Route based on role
    if 'netid' in session:
        if 'role' in session:
            return redirect(url_for('auth.choose_role'))
        # Look up role from DB
        netid = session['netid']
        role = db_session.query(Users.role).filter_by(netid=netid).scalar()
        if role == 'staff':
            session["role"] = 'staff'
            return redirect(url_for('auth.choose_role'))
        return redirect(url_for('consumer_pages.buttery'))  

    CAS_ENABLED = True if current_app.config.get("CAS_ENABLED") == "True" else False
    if CAS_ENABLED:
        ticket = request.args.get('ticket')
        if not ticket:
            # Redirect to CAS login page
            cas_login = current_app.config.get("CAS_LOGIN_URL")
            service = current_app.config.get("SERVICE_URL")
            return redirect(f"{cas_login}?service={service}")

        # Validate CAS ticket
        cas_validate = current_app.config.get("CAS_VALIDATE_URL")
        service = current_app.config.get("SERVICE_URL")
        validate_url = f"{cas_validate}?service={service}&ticket={ticket}"

        resp = requests.get(validate_url, timeout=10)
        lines = resp.text.strip().splitlines()

        if lines and lines[0] == 'yes':
            # Successful CAS login
            netid = lines[1]
            session['netid'] = netid

            # Look up role in DB
            role = db_session.query(Users.role).filter_by(netid=netid).scalar()
            if role == 'staff':
                session["role"] = 'staff'
                return redirect(url_for('auth.choose_role'))
            return redirect(url_for('consumer_pages.buttery'))
        else:
            flash("CAS login failed. Please try again.", "danger")
            return redirect(url_for('auth.index'))


@bp_auth.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.index'))

@bp_auth.route('/choose_role', methods=['GET', 'POST']) 
@login_required 
def choose_role(): 
    if request.method == 'POST': 
        role = request.form.get('role') 
        if role == 'staff': 
            return redirect(url_for('staff_pages.staff')) 
        return redirect(url_for('consumer_pages.buttery')) 
    return render_template('staff/choose_role.html')

@bp_auth.route('/auth/callback', methods=['GET'])
def supabase_callback():
    # If user already has a server session, bounce to your normal login flow
    if 'netid' in session:
        return redirect(url_for('auth.login'))

    return render_template(
        'callback.html',
        SUPABASE_URL=current_app.config.get("SUPABASE_URL"),
        SUPABASE_ANON_KEY=current_app.config.get("SUPABASE_ANON_KEY"),
    )

# Read current user from server session cookie
@bp_auth.route('/auth/api/me', methods=['GET'])
def me():
    if 'netid' in session:
        return redirect(url_for('auth.login'))
    if 'email' in session:
        user = db_session.query(Users).filter_by(email=session.get('email')).one_or_none()
        if user:
            session['netid'] = user.netid
            return redirect(url_for('auth.login'))
        YALIES_API = current_app.config.get("YALIES_API_KEY")
        CAS_ENABLED = True if current_app.config.get("CAS_ENABLED") == "True" else False
        try:
            profile = fetch_profile(YALIES_API, CAS_ENABLED=CAS_ENABLED, email=session.get('email'))
        except YaliesError as e:
            flash(f"Unable to load your profile: {e}", "danger")
            return redirect(url_for('auth.index'))
        if profile:
            session['netid'] = profile["netid"]
            user = Users(
                netid = profile["netid"],
                name = profile["first_name"],
                email = session["email"]
            )
            db_session.add(user)
            db_session.commit()
            return redirect(url_for("auth.login"))
    flash("Email must be a Yale email (ending in @yale.edu).")
    return redirect(url_for('auth.index'))



@bp_auth.route("/auth/api/session", methods=["POST"])
def create_session_from_supabase():
    # Required config
    SUPABASE_URL = (current_app.config.get("SUPABASE_URL") or "").rstrip("/")
    SUPABASE_JWT_SECRET = current_app.config.get("SUPABASE_JWT_SECRET")  # <-- from env/config
    token = bearer()

    if not token:
        return {"error": "Missing bearer token"}, 401
    if not SUPABASE_URL or not SUPABASE_JWT_SECRET:
        # If you really want a network fallback, you could call /userinfo here,
        # but best is to set SUPABASE_JWT_SECRET properly.
        return {"error": "Server misconfigured: SUPABASE_URL or SUPABASE_JWT_SECRET missing"}, 500

    EXPECTED_ISS = f"{SUPABASE_URL}/auth/v1"
    EXPECTED_AUD = "authenticated"  # Supabase access-token audience

    try:
        # Verify signature (HS256), exp, iat, iss, aud
        claims = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            issuer=EXPECTED_ISS,
            audience=EXPECTED_AUD,
            options={"require": ["exp", "iat", "iss", "sub"]},
            leeway=10,  # small clock skew tolerance
        )
    except jwt.InvalidTokenError as e:
        # Don't log the token; just return a safe message
        return {"error": f"Invalid token: {e.__class__.__name__}"}, 401
    except Exception as e:
        return {"error": f"Token verify error: {str(e)}"}, 500

    email = claims.get("email").strip().lower()
    if not email or not email.endswith("@yale.edu"):
        flash("Email must be a Yale email ending in @yale.edu")
        return redirect(url_for('auth.index'))
    # Success: create your server session (Redis/file, depending on Flask-Session)
    session.clear()
    session["supabase_user_id"] = claims["sub"]
    session["email"] = email
    return {"ok": True}


def bearer():
    h = request.headers.get("Authorization", "")
    return h.split(" ", 1)[1] if h.startswith("Bearer ") else None