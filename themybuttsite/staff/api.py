from flask import Blueprint, request, flash, redirect, url_for, jsonify
from sqlalchemy.orm import selectinload
from sqlalchemy import func, true as sa_true
import json
from threading import Thread


from models import (
    Ingredients, MenuItems, Settings,
    Orders, OrderItems, OrderItemIngredient
)
from themybuttsite.utils.sheets import update_to_stock, update_menu_sheets, update_to_announcements, update_staff_table, copy_snippet, closing_buttery_effects
from themybuttsite.extensions import db_session
from themybuttsite.jinjafilters.filters import format_est
from themybuttsite.wrappers.wrappers import login_required, role_required  
from themybuttsite.utils.validation import handle_menu_item_submission
from themybuttsite.utils.time import get_service_window

bp_staff_api = Blueprint('staff_api', __name__, url_prefix="/staff")

@bp_staff_api.route('/update_order', methods=['POST'])
@login_required
@role_required('staff')
def update_order():
    order_id = request.form.get('order_id')
    new_status = request.form.get('status')

    # Validate input
    if not order_id or not new_status:
        flash('Invalid order update request.', 'danger')
        return redirect(url_for('staff_pages.staff'))

    try:
        oid = int(order_id)
    except ValueError:
        flash('Invalid order ID format.', 'danger')
        return redirect(url_for('staff_pages.staff'))

    try:
        order = db_session.query(Orders).filter_by(id=oid).first()
        if not order:
            flash('Order not found.', 'danger')
            return redirect(url_for('staff_pages.staff'))

        order.status = new_status
        db_session.commit()
        new_status = new_status == 'done'
        update_staff_table(oid, new_status)
        flash('Order status updated successfully!', 'success')
    except Exception:
        db_session.rollback()
        flash('Failed to update order status. Please try again.', 'danger')

    return redirect(url_for('staff_pages.staff'))

@bp_staff_api.route('/update_payment', methods=['POST'])
@login_required
@role_required('staff')
def update_payment():
    order_id = request.form.get('order_id')
    new_status = request.form.get('status')

    # Validate input
    if not order_id or not new_status:
        flash('Invalid order update request.', 'danger')
        return redirect(url_for('staff_pages.staff'))

    try:
        paid = int(new_status)
    except ValueError:
        flash("Please do not change form values.", 'danger')
        return redirect(url_for('staff_pages.staff'))


    try:
        oid = int(order_id)
    except ValueError:
        flash('Invalid order ID format.', 'danger')
        return redirect(url_for('staff_pages.staff'))

    try:
        order = db_session.query(Orders).filter_by(id=oid).first()
        if not order:
            flash('Order not found.', 'danger')
            return redirect(url_for('staff_pages.staff'))

        order.paid = bool(paid)
        db_session.commit()
        update_staff_table(oid, bool(paid), paying = True)
        flash('Order status updated successfully!', 'success')
    except Exception:
        db_session.rollback()
        flash('Failed to update order status. Please try again.', 'danger')

    return redirect(url_for('staff_pages.staff'))

@bp_staff_api.route('/update_stock', methods=['POST'])
@login_required
@role_required('staff')
def update_stock():
    try:
        changes_json = request.form.get('changes')
        if not changes_json:
            flash("No changes submitted.", "info")
            return redirect(url_for('staff_pages.staff'))

        changes = json.loads(changes_json)  # {id: new_status}

        for ingredient_id, new_status in changes.items():
            ingredient = db_session.query(Ingredients).filter_by(id=int(ingredient_id)).first()
            if ingredient:
                ingredient.in_stock = bool(new_status)

        db_session.commit()
        Thread(target=update_to_stock, daemon=True).start()
        flash("Ingredient stock statuses updated successfully!", "success")

    except Exception as e:
        db_session.rollback()
        flash(f"Error updating ingredients: {str(e)}", "danger")


    return redirect(url_for('staff_pages.staff'))

@bp_staff_api.route('/add_menu_item', methods=['POST'])
@login_required
@role_required('staff')
def add_menu_item():
    return handle_menu_item_submission(request, update=False)

@bp_staff_api.route('/update_menu_item', methods=['POST'])
@login_required
@role_required('staff')
def update_menu_item():
    return handle_menu_item_submission(request, update=True)

@bp_staff_api.route('/delete_menu_item', methods=['POST'])
@login_required
@role_required('staff')
def delete_menu_item():

    item_id = request.form.get('id')

    try:
        # ✅ Validate ID
        if not item_id:
            flash('Invalid item ID.', 'danger')
            return redirect(url_for('staff_pages.manage_menu'))

        try:
            item_id_int = int(item_id)
        except ValueError:
            flash('Invalid item ID format.', 'danger')
            return redirect(url_for('staff_pages.manage_menu'))

        # ✅ Fetch and delete menu item
        menu_item = db_session.query(MenuItems).filter_by(id=item_id_int, is_default = False).first()
        if not menu_item:
            flash('Menu item not found.', 'danger')
            return redirect(url_for('staff_pages.manage_menu'))

        db_session.delete(menu_item)  
        db_session.commit()        
        Thread(target=update_menu_sheets, daemon=True).start()

        flash('Menu item deleted successfully!', 'success')

    except Exception as e:
        db_session.rollback()
        flash(f'An error occurred while deleting the item: {str(e)}', 'danger')
    

    return redirect(url_for('staff_pages.manage_menu'))

@bp_staff_api.route('/add_ingredient', methods=['POST'])
@login_required
@role_required('staff')
def add_ingredient():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Ingredient name is required.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))

    # Check for exact (case-insensitive) match
    existing = db_session.query(Ingredients).filter(
        func.lower(Ingredients.name) == name.lower()
    ).first()

    if existing:
        flash('An ingredient with this name already exists.', 'warning')
        return redirect(url_for('staff_pages.manage_menu'))

    try:
        ingredient = Ingredients(name=name)
        db_session.add(ingredient)
        db_session.commit()
        flash('Ingredient added successfully!', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'An error occurred: {str(e)}', 'danger')

    return redirect(url_for('staff_pages.manage_menu'))

@bp_staff_api.route('/delete_ingredient', methods = ['POST'])
@login_required
@role_required('staff')
def delete_ingredient():
    ing_id = request.form.get('ingredient_id', '').strip()
    if not ing_id:
        flash('No ingredient selected.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))

    try:
        ing_id = int(ing_id)
    except ValueError:
        flash('Invalid ingredient id.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))
    
    ingredient = db_session.query(Ingredients).filter_by(id=ing_id).first()
    if not ingredient or ingredient.is_default:
        flash('Ingredient not found or cannot be deleted.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))

    db_session.delete(ingredient)  # DB cascades link rows automatically
    db_session.commit()
    flash('Ingredient deleted successfully.', 'success')

    return redirect(url_for('staff_pages.manage_menu'))

@bp_staff_api.route('/update_announcements', methods=['POST'])
@login_required
@role_required('staff')
def update_announcements():
    msg = request.form.get('announcement', '').strip()
    try:
        settings = db_session.query(Settings).first()
        settings.announcement = msg
        db_session.commit()
        Thread(target=update_to_announcements, daemon=True).start()
        flash('Announcement updated!', 'success')
    except Exception as e:
        db_session.rollback()
        flash(f'Error updating announcement: {e}', 'danger')

    return redirect(url_for('staff_pages.staff'))


@bp_staff_api.route('/toggle_grill', methods=['POST'])
@login_required
@role_required('staff')
def toggle_grill():
    settings = db_session.query(Settings).first()
    if settings:
        settings.grill_open = not settings.grill_open  # Toggle boolean
        db_session.commit()
        if not settings.grill_open:
            copy_snippet()
        flash(f'Grill is now {"Open" if settings.grill_open else "Closed"}.', 'success')
    else:
        flash("Settings record not found. Cannot toggle grill.", "danger")
    return redirect(url_for('staff_pages.staff'))



@bp_staff_api.route('/toggle_buttery', methods=['POST'])
@login_required
@role_required('staff')
def toggle_buttery():
    settings = db_session.query(Settings).first()
    if settings:
        settings.buttery_open = not settings.buttery_open  # Toggle boolean
        db_session.commit()
        if not settings.buttery_open:
            closing_buttery_effects()
        flash(f'Buttery is now {"Open" if settings.buttery_open else "Closed"}.', 'success')
    else:
        flash("Settings record not found. Cannot toggle buttery.", "danger")

    return redirect(url_for('staff_pages.staff'))

@bp_staff_api.route("/orders_json", methods=["POST", "GET"])
@login_required
@role_required("staff")
def orders_json():
    # Payload for incremental fetches
    payload = request.get_json(silent=True) or {}

    try:
        since_id = int(payload.get("since_id", 0) or 0)
        if since_id < 0:
            since_id = 0
    except (TypeError, ValueError):
        since_id = 0

    delta_filter = (Orders.id > since_id) if (since_id and since_id > 0) else sa_true()
    
    start_utc, end_utc = get_service_window()

    # Eager loading to avoid N+1
    orders = (
    db_session.query(Orders)
        .options(
            selectinload(Orders.users),
            selectinload(Orders.order_items).selectinload(OrderItems.menu_item),
            selectinload(Orders.order_items)
                .selectinload(OrderItems.selected_ingredients)
                .selectinload(OrderItemIngredient.ingredient),
        )
        .filter(
            Orders.timestamp >= start_utc,
            Orders.timestamp < end_utc,
            delta_filter
        )
        .order_by(Orders.id.asc())
        .all()
    )

    

    orders_list = []
    max_id = orders[-1].id if orders else (since_id or 0)

    for order in orders:
        orders_list.append({
            "id": order.id,
            "name": order.users.name if order.users else "Unknown",
            "email": order.email,
            "total_price": order.total_price,
            "status": order.status,
            "paid": order.paid,
            "specifications": order.specifications or "",
            "timestamp": format_est(order.timestamp),
            "items": [
                {
                    "menu_item_name": item.menu_item_name,
                    "menu_item_price": item.menu_item_price,
                    "selected_ingredients": [
                        {
                            "ingredient_name": ing.ingredient_name,
                            "add_price": ing.add_price,
                        }
                        for ing in item.selected_ingredients
                    ]
                }
                for item in order.order_items
            ]
        })

    # POST returns wrapper with max_id; GET can return just the list
    if request.method == "POST":
        return jsonify({"orders": orders_list, "max_id": max_id})

    return jsonify(orders_list)