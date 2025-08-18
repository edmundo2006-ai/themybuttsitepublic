from flask import Blueprint, render_template, session, flash, redirect, url_for, current_app, request
from sqlalchemy.orm import joinedload, selectinload

from models import (
    Users, MenuItems, MenuItemIngredients,
    Orders, OrderItems, OrderItemIngredient,
    Cart, CartItem, CartItemIngredient,
    Settings
)
from themybuttsite.wrappers.wrappers import login_required
from themybuttsite.extensions import db_session
from themybuttsite.yalies_api.yalies_api import fetch_profile, YaliesError
from themybuttsite.utils.time import service_date 
from themybuttsite.utils.calculation import calculate_cart_total

bp_consumer_pages = Blueprint("consumer_pages", __name__)

@bp_consumer_pages.route('/buttery')
@login_required
def buttery():
    netid = session.get('netid')

    user = db_session.query(Users).options(selectinload(Users.cart)).filter_by(netid=netid).first()

    if not user:
        try:
            profile = fetch_profile(current_app.config["YALIES_API_KEY"], netid=netid)
        except YaliesError as e:
            flash(f"Unable to load your profile: {e}", "danger")
            return redirect(url_for("auth.login"))

        user = Users(netid=netid, name=profile["first_name"], email=profile["email"])
        db_session.add(user)
        db_session.commit()


    # Status
    settings = db_session.query(Settings).limit(1).one()
    buttery_open = settings.buttery_open
    grill_open = settings.grill_open


    # Menu items
    menu_items = (
        db_session.query(MenuItems)
        .options(
            joinedload(MenuItems.menu_item_ingredients)
            .joinedload(MenuItemIngredients.ingredient)
        )
        .filter(
            (MenuItems.requires_grill == False) |
            ((MenuItems.requires_grill == True) & (grill_open == True))
        )
        .all()
    )

    orders = (
        db_session.query(Orders)
        .options(
            selectinload(Orders.order_items)
                .selectinload(OrderItems.menu_item),
            selectinload(Orders.order_items)
                .selectinload(OrderItems.selected_ingredients)
                .selectinload(OrderItemIngredient.ingredient),
        )
        .filter_by(netid=netid)
        .order_by(Orders.timestamp.desc())
        .limit(5)
        .all()
    )


    # Cart count
    cart_count = db_session.query(CartItem).filter_by(cart_netid=netid).count()

    return render_template(
        'consumer/buttery.html',
        menu_items=menu_items,
        orders=orders,
        buttery_open=buttery_open,
        grill_open=grill_open,
        user=user,
        cart_count=cart_count
    )

@bp_consumer_pages.route('/order_history')
@login_required
def order_history():

    netid = session['netid']

    orders = (
        db_session.query(Orders)
        .options(
            joinedload(Orders.users),
            selectinload(Orders.order_items)
                .selectinload(OrderItems.menu_item),
            selectinload(Orders.order_items)
                .selectinload(OrderItems.selected_ingredients)
                .selectinload(OrderItemIngredient.ingredient),
        )
        .filter_by(netid=netid)
        .order_by(Orders.timestamp.desc())
        .all()
    )

    # compute service_date 
    for order in orders:
        order.service_date = service_date(order.timestamp)

    # group by service_date, newest first
    sorted_orders = {}
    for order in orders:
        sorted_orders.setdefault(order.service_date, []).append(order)
    sorted_orders = dict(sorted(sorted_orders.items(), key=lambda x: x[0], reverse=True))

    return render_template('consumer/order_history.html', orders=sorted_orders)

@bp_consumer_pages.route('/cart') 
@login_required
def view_cart():
    netid = session.get('netid')

    cart = (
        db_session.query(Cart)
        .options(
            # Load items, each item's menu_item, and each item's selected_ingredients + ingredient
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
        return render_template('consumer/cart.html', cart=None, total_price=0)

    total_price, cart = calculate_cart_total(cart, db_session)

    return render_template('consumer/cart.html', cart=cart, total_price=total_price)

@bp_consumer_pages.route('/checkout_summary', methods=['GET', 'POST'])
@login_required
def checkout_summary():
    netid = session.get('netid')

    cart = (
        db_session.query(Cart)
        .options(
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
        return redirect(url_for('consumer_pages.view_cart'))
    
    if request.method == "POST":
        new_spec = (request.form.get('cart_specifications') or '').strip()
        cart.specifications = new_spec[:40]  # enforce 40 chars max
        db_session.commit()

    total_price, cart = calculate_cart_total(cart, db_session)


    return render_template(
        "consumer/checkout_summary.html",
        cart=cart,
        total_price=total_price
    )
