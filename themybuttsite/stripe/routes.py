from flask import Blueprint, session, redirect, request, url_for, flash, current_app
from sqlalchemy.orm import selectinload
import stripe

from models import (
    Cart, CartItem, CartItemIngredient,
    Orders, OrderItems, OrderItemIngredient,
    MenuItems
)
from themybuttsite.extensions import db_session, socketio
from themybuttsite.wrappers.wrappers import login_required
from themybuttsite.utils.calculation import calculate_cart_total
from themybuttsite.utils.validation import validate_item  
from themybuttsite.jinjafilters.filters import format_price
from themybuttsite.utils.sheets import _format_order_text, append_order_row

bp_stripe = Blueprint("stripe", __name__)

FAILED_EVENTS = {
    "checkout.session.expired",
    "payment_intent.payment_failed",
    "payment_intent.canceled",
    "charge.failed",
    "checkout.session.async_payment_failed",
}

@bp_stripe.route("/stripe_checkout", methods=["POST"])
@login_required
def stripe_checkout():
    netid = session.get("netid")
    cart = (
        db_session.query(Cart)
        .options(
            selectinload(Cart.user),
            selectinload(Cart.items).selectinload(CartItem.menu_item),
            selectinload(Cart.items)
                .selectinload(CartItem.selected_ingredients)
                .selectinload(CartItemIngredient.ingredient),
        )
        .filter_by(netid=netid)
        .first()
    )

    if not cart or not cart.items:
        flash("Your cart is empty.", "info")
        return redirect(url_for("consumer_pages.view_cart"))

    # If a Stripe session already exists, reuse it
    if cart.stripe_session_id:
        try:
            sess = stripe.checkout.Session.retrieve(cart.stripe_session_id)
            if sess.status == 'open':
                return redirect(sess.url, code=303)   
        except Exception:
            cart.stripe_session_id = None
            db_session.commit()

    # Validate each item quietly
    invalid_items = []
    for cart_item in list(cart.items):
        item_id = cart_item.menu_item_id
        choice_ids = [ci.ingredient_id for ci in cart_item.selected_ingredients if ci.type == "choice"]
        optional_ids = [ci.ingredient_id for ci in cart_item.selected_ingredients if ci.type == "optional"]

        if not validate_item(item_id, choice_ids, optional_ids, flash_errors=False):
            invalid_items.append(cart_item.menu_item.name)
            db_session.delete(cart_item)

    if invalid_items:
        cart.stripe_session_id = None
        db_session.commit()
        flash(f"The following items were removed due to not being available: {', '.join(invalid_items)}", "warning")
        return redirect(url_for("consumer_pages.view_cart"))

    # Calculate total
    total_price, cart = calculate_cart_total(cart, db_session)

    idempotency_key = f"checkout:{netid}:{cart.updated_at.isoformat()}:{total_price}:{len(cart.items)}"

    # Stripe
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"Buttery Order for {cart.user.name}"},
                "unit_amount": int(total_price),
            },
            "quantity": 1,
        }],
        mode="payment",
        customer_email=cart.user.email,
        client_reference_id=netid,
        metadata={
            "netid": netid,
            "total_price": int(total_price),
        },
        success_url=url_for("stripe.payment_success", _external=True),
        cancel_url=url_for("stripe.payment_failure", _external=True),
        idempotency_key=idempotency_key
    )

    # Lock cart
    cart.stripe_session_id = checkout_session.id
    db_session.commit()
    return redirect(checkout_session.url, code=303)

@bp_stripe.route("/webhook", methods=["POST"])
def stripe_webhook():
    # Verify Stripe signature
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        return "Error creating webhook", 400

    etype = event.get("type")
    data_obj = event.get("data", {}).get("object", {}) or {}

    # Extract identifiers early so we can always update user.paying
    netid = (data_obj.get("metadata") or {}).get("netid") or data_obj.get("client_reference_id")
    session_id = data_obj.get("id")

    # ---- FAILURE / TIMEOUT / CANCEL ----
    if etype in FAILED_EVENTS:
        try:
            if netid:
                cart = db_session.query(Cart).filter_by(netid=netid).first()
                if cart:
                    cart.stripe_session_id = None
            db_session.commit()
        except Exception:
            db_session.rollback()
            current_app.logger.exception("Failed to handle failed Stripe event")
        return "", 200

    # ---- SUCCESS: checkout.session.completed ----
    if etype == "checkout.session.completed":
        try:
            # Idempotency guard
            if db_session.query(Orders).filter_by(stripe_session_id=session_id).first():
                return "", 200

            # Load cart + relationships
            cart = (
                db_session.query(Cart)
                .options(
                    selectinload(Cart.items)
                        .selectinload(CartItem.menu_item)
                        .selectinload(MenuItems.menu_item_ingredients),
                    selectinload(Cart.items)
                        .selectinload(CartItem.selected_ingredients)
                        .selectinload(CartItemIngredient.ingredient),
                )
                .filter_by(netid=netid, stripe_session_id=session_id)
                .one_or_none()
            )
            if not cart or not cart.items:
                return "", 200

            customer_email = (data_obj.get("customer_details") or {}).get("email")
            total_price = int(data_obj.get("amount_total", 0))
            # Create order
            order = Orders(
                netid=netid,
                email=customer_email,
                total_price=total_price,  # cents
                status="pending",
                stripe_session_id=session_id,
                specifications=getattr(cart, "specifications", ""),
            )
            db_session.add(order)
            db_session.flush()

            # Snapshot items + ingredients (all cents)
            for cart_item in cart.items:
                menu_item = cart_item.menu_item

                order_item = OrderItems(
                    order_id=order.id,
                    menu_item_id=cart_item.menu_item_id,
                    menu_item_name=menu_item.name,
                    menu_item_price=menu_item.price, 
                )
                db_session.add(order_item)
                db_session.flush()

                add_price_by_ing = {m.ingredient_id: m.add_price for m in menu_item.menu_item_ingredients}
                for sel in cart_item.selected_ingredients:
                    ing_obj = sel.ingredient

                    order_item_ingredient = OrderItemIngredient(
                        order_item_id=order_item.id,
                        ingredient_id=sel.ingredient_id,
                        ingredient_name=(ing_obj.name if ing_obj else ""),
                        type=sel.type,
                        add_price=add_price_by_ing.get(sel.ingredient_id, 0),
                    )
                    db_session.add(order_item_ingredient)

            db_session.commit()
            socketio.emit(
                "order_update",
                {"type": "new_order", "order_id": order.id},
                namespace="/staff",
                to="staff_updates",
            )
            display_name = ((data_obj.get("customer_details") or {}).get("name"))
            order_text = _format_order_text(cart)
            specs_text = getattr(cart, "specifications", "") or ""
            total_display = format_price(total_price)

            # A..G = [Order ID, Name, Order Items, Specifications, Total, DONE, PAID]
            values = [
                order.id,          # A
                display_name,      # B
                order_text,        # C (multi-line; wrapping shows nicely)
                specs_text,        # D
                total_display,     # E  (you can store cents instead if you prefer)
                False,             # F  DONE
                False,             # G  PAID
            ]

            tab_title, updated_range = append_order_row(values)
            flash("Order has been sucessfully processed.")

            # Clear cart (separate attempt)
            try:
                cart = db_session.query(Cart).filter_by(netid=netid).first()
                if cart:
                    db_session.delete(cart)
                    db_session.commit()
            except Exception:
                db_session.rollback()
                current_app.logger.exception("Order created but failed to clear cart")

        except Exception:
            db_session.rollback()
            current_app.logger.exception("Failed to finalize order from Stripe webhook")

        return "", 200

    # Other events → no-op, but acknowledged
    return "", 200

@bp_stripe.route('/payment_success')
def payment_success():
    flash("Thank you! Processing order.", "success")
    return redirect(url_for('consumer_pages.buttery'))

@bp_stripe.route('/payment_failure')
def payment_failure():
    flash("Payment failed. Please try again.", "warning")
    return redirect(url_for('consumer_pages.buttery'))