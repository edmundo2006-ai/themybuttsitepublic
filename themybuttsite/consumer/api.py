from flask import Blueprint, request, session, flash, redirect, url_for
from sqlalchemy.orm import selectinload

from models import Cart, CartItem, CartItemIngredient
from themybuttsite.wrappers.wrappers import login_required, cart_unlocked_required
from themybuttsite.extensions import db_session
from themybuttsite.utils.validation import validate_item  



bp_consumer_api = Blueprint("consumer_api", __name__)

@bp_consumer_api.route("/add_to_cart", methods=["POST"])
@login_required
@cart_unlocked_required
def add_to_cart():
    netid = session.get("netid")

    cart = db_session.query(Cart).filter_by(netid=netid).first()
    if not cart:
        cart = Cart(netid=netid)
        db_session.add(cart)
        db_session.commit()
    

    item_id = int(request.form.get("item_id"))
    optional_ids = list(set(int(i) for i in request.form.getlist("ingredient_ids")))
    choice_ids = list(set(int(i) for i in request.form.getlist("ingredients_choice")))

    if not validate_item(item_id, choice_ids, optional_ids):
        return redirect(url_for("consumer_pages.buttery"))

    # Create cart item
    cart_item = CartItem(cart_netid=netid, menu_item_id=item_id)
    db_session.add(cart_item)
    db_session.flush()

    # Choice ingredient
    if choice_ids:
        db_session.add(CartItemIngredient(
            cart_item_id=cart_item.id,
            ingredient_id=choice_ids[0],
            type="choice"
        ))

    # Optional ingredients
    for ing_id in optional_ids:
        db_session.add(CartItemIngredient(
            cart_item_id=cart_item.id,
            ingredient_id=ing_id,
            type="optional"
        ))

    db_session.commit()

    flash("Item added to cart.", "success")
    return redirect(url_for("consumer_pages.buttery"))

@bp_consumer_api.route('/remove_from_cart', methods=['POST'])
@login_required
@cart_unlocked_required
def remove_from_cart():
    netid = session.get('netid')
    item_id = request.form.get('item_id')
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        flash("Item ID is missing or invalid.", "danger")
        return redirect("/cart")

    cart_item = db_session.query(CartItem).filter_by(id=item_id, cart_netid=netid).first()

    if cart_item:
        # ✅ Grab name before delete
        item_name = cart_item.menu_item.name  
        db_session.delete(cart_item)
        db_session.commit()
        
        flash(f'Removed {item_name} from your cart.', 'success')
    else:
        flash('Item not found in your cart.', 'info')

    return redirect(url_for('consumer_pages.view_cart'))

@bp_consumer_api.route('/clear_cart', methods=['POST'])
@login_required
@cart_unlocked_required
def clear_cart():
    netid = session.get('netid')

    cart = db_session.query(Cart).filter_by(netid=netid).first()
    if not cart:
        flash('Your cart is already empty.', 'info')
        return redirect(url_for('consumer_pages.view_cart'))  # or url_for('consumer_pages.cart')

    db_session.delete(cart)
    db_session.commit()

    flash('Your cart has been cleared.', 'success')
    return redirect(url_for('consumer_pages.view_cart'))  # or url_for('consumer_pages.cart')






