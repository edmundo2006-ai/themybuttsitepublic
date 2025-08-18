from flask import flash, redirect, url_for
from sqlalchemy.orm import joinedload
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import and_, func
import json

from models import MenuItems, MenuItemIngredients, Ingredients, Settings
from themybuttsite.extensions import db_session
from themybuttsite.utils.image_processing import process_image_upload

def validate_item(item_id, choice_ids, optional_ids, *, flash_errors=True):
    """
    Validate that:
      - inputs are ints
      - buttery is open
      - item exists
      - choice/optional selections match item rules
      - required/selected ingredients are in stock
      - grill-required item allowed only if grill is open
    Returns True/False.
    """
    # 1) Coerce input safely
    try:
        item_id = int(item_id)
        choice_ids = list({int(i) for i in (choice_ids or [])})
        optional_ids = list({int(i) for i in (optional_ids or [])})
    except (ValueError, TypeError):
        flash("Invalid ingredient or item ID format.", "danger")
        return False

    # 2) Status: buttery must be open
    settings = db_session.query(Settings).one()
    if not settings.buttery_open:
        flash("The buttery is currently closed. You cannot add items to the cart.", "danger")
        return False

    # 3) Load menu item + its ingredient links + ingredient rows
    item = (
        db_session.query(MenuItems)
        .options(
            joinedload(MenuItems.menu_item_ingredients)
            .joinedload(MenuItemIngredients.ingredient)
        )
        .filter_by(id=item_id)
        .first()
    )
    if not item:
        if flash_errors: flash("Item not found.", "danger")
        return False

    # 4) Partition ingredient types for this item
    links = item.menu_item_ingredients
    ids_optional = {mi.ingredient_id for mi in links if mi.type == "optional"}
    ids_choice   = {mi.ingredient_id for mi in links if mi.type == "choice"}
    required_ings = [mi.ingredient for mi in links if mi.type == "required"]

    # 5) Validate optional selections
    for ing_id in optional_ids:
        if ing_id not in ids_optional:
            if flash_errors: flash("Invalid optional ingredient selected.", "danger")
            return False

    # 6) Validate choice selections
    if ids_choice:
        if not choice_ids:
            if flash_errors: flash("Please select at least one choice ingredient.", "danger")
            return False
        if len(choice_ids) != 1:
            if flash_errors: flash("Only one choice ingredient can be selected.", "danger")
            return False
        if choice_ids[0] not in ids_choice:
            if flash_errors: flash("Invalid choice ingredient selected.", "danger")
            return False
    else:
        if choice_ids:
            if flash_errors: flash("Choice ingredients are not allowed for this item.", "danger")
            return False

    # 7) Required ingredient stock
    if any((ing is None) or (ing.in_stock is False) for ing in required_ings):
        if flash_errors: flash("One or more required ingredients are out of stock.", "danger")
        return False

    # 8) Stock for selected (optional + choice)
    selected_ids = list({*optional_ids, *choice_ids})
    if selected_ids:
        out_of_stock = (
            db_session.query(Ingredients)
            .filter(and_(Ingredients.id.in_(selected_ids), Ingredients.in_stock.is_(False)))
            .all()
        )
        if out_of_stock:
            if flash_errors: flash("One or more selected ingredients are out of stock.", "danger")
            return False

    # 9) Grill rule
    if item.requires_grill and not settings.grill_open:
        if flash_errors: flash("The grill is currently closed. You cannot add this item to the cart.", "danger")
        return False

    return True

def handle_menu_item_submission(request, update = False):
    name = request.form.get('name')
    price = request.form.get('price', type=float)
    description = request.form.get('description') or ""
    requires_grill = request.form.get('requires_grill') == 'true'
    image = request.files.get('image')

    ingredient_data_raw = request.form.get('ingredient_data')
    ingredient_data = json.loads(ingredient_data_raw) if ingredient_data_raw else {}
    required_ingredients = list(map(int, ingredient_data.get('required', [])))
    choice_ingredients = {int(k): float(v) for k, v in ingredient_data.get('choice', {}).items()}
    optional_ingredients = {int(k): float(v) for k, v in ingredient_data.get('optional', {}).items()}

    if not name:
        flash('Menu item name is required.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))
    if price is None or price <= 0:
        flash('Valid price is required.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))
    if not required_ingredients and not choice_ingredients:
        flash('At least one ingredient is required from Required or Choice.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))
    if not isinstance(requires_grill, bool):
        flash('Invalid grill requirement.', 'danger')
        return redirect(url_for('staff_pages.manage_menu'))

    seen = set()
    for ing_id in required_ingredients + list(choice_ingredients) + list(optional_ingredients):
        if ing_id in seen:
            flash(f"Ingredient {ing_id} is duplicated in your selection.", 'danger')
            return redirect(url_for('staff_pages.manage_menu'))
        seen.add(ing_id)

    # ---- DB work with global db_session (no SessionLocal) ----
    # Check for duplicate names only if we're adding
    existing = db_session.query(MenuItems).filter(func.lower(MenuItems.name) == name.lower()).first()
    if existing and not update:
        flash('A menu item with this name already exists.', 'warning')
        return redirect(url_for('staff_pages.manage_menu'))

    if update:
        item_id = request.form.get('id')
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            flash('Invalid item ID.', 'danger')
            return redirect(url_for('staff_pages.manage_menu'))

        menu_item = db_session.query(MenuItems).filter_by(id=item_id).first()
        if not menu_item:
            flash('Menu item not found.', 'danger')
            return redirect(url_for('staff_pages.manage_menu'))

        # Update fields
        menu_item.name = name
        menu_item.price = price
        menu_item.description = description
        menu_item.requires_grill = requires_grill

        # Update image only if a new one was uploaded
        if image and image.filename:
            object_key = process_image_upload(image, name)
            if not object_key:
                return redirect(url_for('staff_pages.manage_menu'))
            menu_item.object_key = object_key

        # Clear and replace ingredient links
        db_session.query(MenuItemIngredients).filter_by(menu_item_id=menu_item.id).delete()
    else:
        # Process image for new item
        object_key = process_image_upload(image, name, default="default.png")
        if object_key is None:
            return redirect(url_for('staff_pages.manage_menu'))

        menu_item = MenuItems(
            name=name,
            price=price,
            description=description,
            requires_grill=requires_grill,
            object_key=object_key,
            is_default=False
        )
        db_session.add(menu_item)
        db_session.flush()

    # Add new ingredients
    for ing_id in required_ingredients:
        db_session.add(MenuItemIngredients(
            menu_item_id=menu_item.id,
            ingredient_id=ing_id,
            type="required",
            add_price=0
        ))
    for ing_id, price in choice_ingredients.items():
        db_session.add(MenuItemIngredients(
            menu_item_id=menu_item.id,
            ingredient_id=ing_id,
            type="choice",
            add_price=int((Decimal(str(price)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        ))
    for ing_id, price in optional_ingredients.items():
        db_session.add(MenuItemIngredients(
            menu_item_id=menu_item.id,
            ingredient_id=ing_id,
            type="optional",
            add_price=int((Decimal(str(price)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        ))

    db_session.commit()
    flash("Menu item updated successfully!" if update else "Menu item added successfully!", "success")
    return redirect(url_for('staff_pages.manage_menu'))
