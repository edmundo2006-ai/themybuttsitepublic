# staff.py
from flask import Blueprint, render_template
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import desc, func, cast, text, event
from sqlalchemy.dialects.postgresql import JSON

from models import (
    MenuItems, MenuItemIngredients, Ingredients,
    Orders, OrderItems, Settings
)
from themybuttsite.extensions import db_session
from themybuttsite.wrappers.wrappers import login_required, role_required
from themybuttsite.utils.time import service_date, get_service_window



bp_staff_pages = Blueprint("staff_pages", __name__)



@bp_staff_pages.route("/staff")
@login_required
@role_required("staff")
def staff():

    start_utc, end_utc = get_service_window()
    ingredients = (
        db_session.query(Ingredients)
        .order_by(desc(Ingredients.in_stock), Ingredients.name.asc())
        .all()
    )

    # Orders in the nightly window; eager load users and order item selections
    orders = (
        db_session.query(Orders)
        .options(
            joinedload(Orders.users),
            selectinload(Orders.order_items)
                .selectinload(OrderItems.selected_ingredients)
        )
        .filter(Orders.timestamp >= start_utc, Orders.timestamp < end_utc)
        .order_by(Orders.timestamp.desc())
        .all()
    )
    
    settings = db_session.query(Settings).first()    
    
    return render_template(
        "staff/staff.html",
        ingredients=ingredients,
        orders=orders,
        settings=settings
    )

@bp_staff_pages.route('/order_history_staff', methods=['GET', 'POST'])
@login_required
@role_required('staff')
def order_history_staff():
    orders = (
            db_session.query(Orders)
            .options(
                joinedload(Orders.users), 
                selectinload(Orders.order_items)
                    .selectinload(OrderItems.selected_ingredients) 
            )
            .order_by(Orders.timestamp.desc())
            .all()
    )
        

    for order in orders:
        order.service_date = service_date(order.timestamp)
                
    sorted_orders = {}
    for order in orders:
        if order.service_date in sorted_orders:
            sorted_orders[order.service_date].append(order)
        else:
            sorted_orders[order.service_date] = [order]

    sorted_orders = dict(sorted(sorted_orders.items(), key=lambda x: x[0], reverse=True))
    print(sorted_orders)


    return render_template(
        'staff/order_history_staff.html',
        orders=sorted_orders
    )   

@bp_staff_pages.route('/manage_menu')
@login_required
@role_required('staff')
def manage_menu():
    special_items = ( 
            db_session.query(MenuItems) 
                .options
                    ( selectinload(MenuItems.menu_item_ingredients) 
                    .selectinload(MenuItemIngredients.ingredient) ) 
                    .filter(MenuItems.is_default == False) 
                    .all() 
    )

    for item in special_items:
        structured = {"required": [], "choice": [], "optional": []}
        for link in item.menu_item_ingredients:  
            structured[link.type].append({
                "id": link.ingredient_id,
                "name": link.ingredient.name if link.ingredient else None,
                "add_price": link.add_price or 0,
            })
        item.structured_ingredients = structured 

    ingredients = db_session.query(Ingredients).all()
    special_ingredients = [ingredient for ingredient in ingredients if ingredient.is_default == False]

    return render_template(
        'staff/manage_menu.html',
        special_items=special_items,
        special_ingredients=special_ingredients,
        ingredients=ingredients
    )

    

