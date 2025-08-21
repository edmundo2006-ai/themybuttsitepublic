from flask import Blueprint, session, redirect, request, url_for, flash, current_app
from sqlalchemy.orm import selectinload, load_only
import stripe
from threading import Thread

from models import (
    Cart, CartItem, CartItemIngredient,
    Orders, OrderItems, OrderItemIngredient,
    MenuItems, Users, MenuItemIngredients, Ingredients
)
from themybuttsite.extensions import db_session, socketio
from themybuttsite.wrappers.wrappers import login_required
from themybuttsite.utils.calculation import calculate_cart_total
from themybuttsite.utils.validation import validate_item  
from themybuttsite.jinjafilters.filters import format_price


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
                    selectinload(Cart.user),
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
            spawn_side_effects(order.id)
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

def _post_order_side_effects(order_id: int):
    try:
        # Load EXACTLY what _format_order_text needs, nothing more.
        order = (
            db_session.query(Orders)
            .options(
                load_only(Orders.id, Orders.total_price, Orders.specifications, Orders.netid),
                selectinload(Orders.order_items)  
                    .options(
                        load_only(OrderItems.id, OrderItems.menu_item_id,
                                  OrderItems.menu_item_name, OrderItems.menu_item_price),
                        selectinload(OrderItems.menu_item)  
                            .options(
                                load_only(MenuItems.id, MenuItems.name, MenuItems.price),
                                selectinload(MenuItems.menu_item_ingredients)
                                    .options(load_only(MenuItemIngredients.ingredient_id,
                                                       MenuItemIngredients.add_price))
                            ),
                        selectinload(OrderItems.selected_ingredients)
                            .options(
                                load_only(OrderItemIngredient.id, OrderItemIngredient.order_item_id,
                                          OrderItemIngredient.ingredient_id, OrderItemIngredient.type, 
                                          OrderItemIngredient.ingredient_name, OrderItemIngredient.add_price),
                                selectinload(OrderItemIngredient.ingredient)
                                    .options(load_only(Ingredients.id, Ingredients.name))
                            ),
                    ),
            )
            .filter(Orders.id == order_id)
            .one()
        )


        display_name = (
            db_session.query(Users.name)
            .filter(Users.netid == order.netid)
            .scalar()
        ) or ""

        from themybuttsite.utils.sheets import _format_order_text, append_order_row
        order_text = _format_order_text(order)

        values = [
            order.id,
            display_name,
            order_text,
            order.specifications or "",
            format_price(order.total_price),
            False,  
            False,  
        ]

        # Lazy-import the heavy Google client here (keep webhook lean)
        from themybuttsite.utils.sheets import append_order_row
        append_order_row(values)

        # Optional, small notify
        socketio.emit(
            "order_update",
            {"type": "new_order", "order_id": order.id},
            namespace="/staff",
            to="staff_updates",
        )

    except Exception:
        current_app.logger.exception("Side effects failed")
        db_session.rollback()  
    finally:
        db_session.remove()  

def spawn_side_effects(order_id: int):
    Thread(target=_post_order_side_effects, args=(order_id,), daemon=True).start()

@bp_stripe.route('/payment_success')
def payment_success():
    flash("Thank you! Processing order.", "success")
    return redirect(url_for('consumer_pages.buttery'))

@bp_stripe.route('/payment_failure')
def payment_failure():
    flash("Payment failed. Please try again.", "warning")
    return redirect(url_for('consumer_pages.buttery'))