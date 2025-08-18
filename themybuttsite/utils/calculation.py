from models import MenuItemIngredients

def calculate_cart_total(cart, db_session):
    if not cart or not cart.items:
        return 0, cart

    # Build add_price map
    menu_item_ids = {item.menu_item_id for item in cart.items}
    add_price_map = {}
    if menu_item_ids:
        results = (
            db_session.query(
                MenuItemIngredients.menu_item_id,
                MenuItemIngredients.ingredient_id,
                MenuItemIngredients.add_price
            )
            .filter(MenuItemIngredients.menu_item_id.in_(menu_item_ids))
            .all()
        )
        add_price_map = {
            (food_id, ingredient_id): price
            for food_id, ingredient_id, price in results
        }

    # Calculate total price
    total_price = 0
    for cart_item in cart.items:
        cart_item.effective_price = cart_item.menu_item.price
        for cart_item_ingredient in cart_item.selected_ingredients:
            key = (cart_item.menu_item_id, cart_item_ingredient.ingredient_id)
            addon_price = add_price_map.get(key, 0)
            cart_item_ingredient.addon_price = addon_price
            cart_item.effective_price += addon_price
        total_price += cart_item.effective_price

    return total_price, cart
