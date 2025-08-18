from functools import wraps
from flask import session, flash, redirect, url_for, current_app, request
from flask_socketio import disconnect
from sqlalchemy import func as sql_func
import stripe

from models import Cart
from themybuttsite.extensions import db_session

 
                #
def login_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'netid' not in session:
            flash("You must be logged in to access this page.", "danger")
            return redirect(url_for('auth.login')) 
        return func(*args, **kwargs)
    return decorated_function

def role_required(role):
    # Only allow users with a specific role
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get('role', 'consumer') != role:
                flash('Unauthorized access.', 'danger')
                return redirect(url_for('auth.login'))  
            return func(*args, **kwargs)
        return wrapper
    return decorator

def cart_unlocked_required(func):
    """
    For routes that MODIFY the cart:
    - If session is complete/paid: block edits.
    - If session is open/unpaid: expire it, clear pointers, then allow edit.
    - On Stripe error retrieving session: tell user to wait.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        netid = session.get('netid')
        cart = db_session.query(Cart).filter_by(netid=netid).first()
        if not cart or not cart.stripe_session_id:
            if cart:
                cart.updated_at = sql_func.now()
                db_session.commit()
            return func(*args, **kwargs)

        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

        try:
            checkout_session = stripe.checkout.Session.retrieve(
                cart.stripe_session_id,
                expand=["payment_intent"]
            )
        except Exception:
            flash("We’re verifying your checkout status. Please wait a moment.", "warning")
            return redirect(url_for('consumer_pages.buttery'))

        session_status = checkout_session.status
        payment_status = checkout_session.payment_status

        if (session_status == "complete" and payment_status == "paid"):
            flash("Payment is processing — please wait a moment.", "danger")
            return redirect(url_for('consumer_pages.buttery'))

        if session_status == "open" and payment_status in {"unpaid", "no_payment_required"}:
            try:
                stripe.checkout.Session.expire(cart.stripe_session_id)
            except Exception:
                flash("We’re verifying your checkout status. Please wait a moment.", "warning")
                return redirect(url_for('consumer_pages.buttery'))
            cart.stripe_session_id = None
            cart.updated_at = sql_func.now()
            db_session.commit()
            return func(*args, **kwargs)

        
        if session_status == "expired":
            cart.stripe_session_id = None
            cart.updated_at = sql_func.now()
            db_session.commit()
            return func(*args, **kwargs)
        
        return func(*args, **kwargs)
    return wrapper

def socket_login_required(func):
    """
    Guard for Socket.IO events: requires 'netid' in session.
    Disconnects the socket if unauthenticated.
    """
    @wraps(func)
    def wrapped(*args, **kwargs):
        if 'netid' not in session:
            # Optionally emit an error event here before disconnect
            disconnect()
            return
        return func(*args, **kwargs)
    return wrapped


def socket_role_required(role: str):
    """
    Guard for Socket.IO events: requires matching role in session.
    Usage:
        @socketio.on("join_staff", namespace="/staff")
        @socket_role_required("staff")
        def handle_join_staff(data): ...
    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            user_role = session.get('role', 'consumer')
            if user_role != role:
                disconnect()
                return
            return func(*args, **kwargs)
        return wrapped
    return decorator