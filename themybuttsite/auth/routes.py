from flask import Blueprint, render_template, request, redirect, flash, session, url_for, current_app, jsonify, abort
import requests
from firebase_admin import auth as fb_auth



from models import Users
from themybuttsite.extensions import db_session
from themybuttsite.wrappers.wrappers import login_required
from themybuttsite.yalies_api.yalies_api import fetch_profile, YaliesError

bp_auth = Blueprint("auth", __name__)



@bp_auth.route('/', methods=['GET', 'POST'])
def index():
    CAS_ENABLED = current_app.config.get("CAS_ENABLED") == "True" 
    if request.method == 'POST':
            return redirect(url_for('auth.login'))
    return render_template(
        "login.html",
        CAS_ENABLED = CAS_ENABLED,
    )

@bp_auth.route('/login')
def login():
    print(session.get('netid', "whats going on"))
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

    CAS_ENABLED = current_app.config.get("CAS_ENABLED") == "True" 
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
    return render_template(
        "login.html",
        CAS_ENABLED=CAS_ENABLED
    )

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

    
@bp_auth.route("/firebase", methods=["POST"])
def firebase_login():
    data = request.get_json(silent=True) or {}
    print(data if data else "no data", flush=True)
    id_token = data.get("idToken")
    print(id_token if id_token else "nothing no token", flush=True)
    if not id_token:
        abort(400, "Missing idToken")

    try:
        decoded = fb_auth.verify_id_token(id_token)
        print(decoded, flush=True)
        email = decoded.get("email")
        print(email, flush=True)
        if not decoded.get("email_verified") or not email or not email.lower().endswith("@yale.edu"):
            abort(401, "Yale Google email required")

        session.clear()
        session["email"] = email
        print(f"session: {session['email']}")

        # Send client to your existing /auth/api/me, then that will redirect to /login
        ok, next_url = identify_user(
            # Prefer a post-login router or your real landing page:
            final_next=url_for("auth.login"),
            error_next=url_for("auth.index"),
        )

        return jsonify({"ok": ok, "next": next_url})
    except Exception:
        abort(401, "Invalid or expired token")

@bp_auth.after_request
def allow_popups(resp):
    # Only for this blueprint’s responses (your login page, etc.)
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return resp

def identify_user(final_next, error_next):
    """
    Ensure session['netid'] exists given a verified Yale email in session.
    Returns (ok: bool, next_url: str).
    final_next: where to send the user if identification succeeds
    error_next: where to send them if it fails (usually login/index)
    """
    # Default destinations
    final_next = final_next or url_for("auth.login")
    error_next = error_next or url_for("auth.index")

    # Already identified
    if session.get("netid"):
        # print(session['netid'], flush=True)
        return True, final_next

    # Have a verified Yale email from Firebase/CAS?
    email = session.get("email")
    if email:
        user = db_session.query(Users).filter_by(email=email).one_or_none()
        if user:
            session["netid"] = user.netid
            print(user.netid)
            return True, final_next

        YALIES_API = current_app.config.get("YALIES_API_KEY")
        CAS_ENABLED = (current_app.config.get("CAS_ENABLED") == "True")
        try:
            profile = fetch_profile(YALIES_API, CAS_ENABLED=CAS_ENABLED, email=email)
        except YaliesError as e:
            session.clear()
            flash(f"Unable to load your profile: {e}", "danger")
            return False, error_next

        if profile and profile.get("netid"):
            print()
            session["netid"] = profile["netid"]
            user = Users(
                netid=profile["netid"],
                name=profile.get("first_name"),
                email=email
            )
            db_session.add(user)
            db_session.commit()
            return True, final_next

    # No email → not a Yale user / bad flow
    session.clear()
    flash("Email must be a Yale email (ending in @yale.edu).", "danger")
    return False, error_next