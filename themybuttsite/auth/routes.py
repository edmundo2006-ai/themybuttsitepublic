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
    if session.get('netid'):
        return redirect(url_for('auth.login'))
    CAS_ENABLED = True if current_app.config.get("CAS_ENABLED") == "True" else False
    if request.method == 'POST':
        return redirect(url_for('auth.login'))
    return render_template(
        "login.html",
        CAS_ENABLED = CAS_ENABLED,
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
            session.clear()
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
    session.clear()
    flash("Email must be a Yale email (ending in @yale.edu).")
    return redirect(url_for('auth.index'))



@bp_auth.route("/firebase", methods=["POST"])
def firebase_login():
    data = request.get_json(silent=True) or {}
    id_token = data.get("idToken")
    if not id_token:
        abort(400, "Missing idToken")

    try:
        decoded = fb_auth.verify_id_token(id_token)
        email = decoded.get("email")
        if not decoded.get("email_verified") or not email or not email.lower().endswith("@yale.edu"):
            abort(401, "Yale Google email required")

        session.clear()
        session["email"] = email
        session.permanent = True

        # Send client to your existing /auth/api/me, then that will redirect to /login
        next_url = url_for("auth.me", next=url_for("auth.login"))
        return jsonify({"ok": True, "next": next_url})
    except Exception:
        abort(401, "Invalid or expired token")