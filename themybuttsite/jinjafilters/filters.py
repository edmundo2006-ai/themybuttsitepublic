from flask import current_app
from zoneinfo import ZoneInfo
from urllib.parse import quote


def format_est(dt):
    """Convert a datetime to EST and format as 'YYYY-MM-DD HH:MM AM/PM'."""
    if not dt:
        return ""
    yale_tz = ZoneInfo("America/New_York")
    return dt.astimezone(yale_tz).strftime("%Y-%m-%d %I:%M %p")

def format_price(cents):
    """Convert price in cents to a string like $3.50, or $3 if whole dollars."""
    try:
        dollars = cents / 100  # keep float precision
        if float(dollars).is_integer():
            return f"${int(dollars)}"
        return f"${dollars:,.2f}"
    except (TypeError, ValueError):
        return ""

def cents_to_dollars(cents):
    try:
        return f"{cents / 100:.2f}"
    except (TypeError, ValueError):
        return ""

def public_image_url(key):
    base = current_app.config.get("SUPABASE_URL").rstrip("/")
    bucket = current_app.config.get("SUPABASE_BUCKET")
    return f"{base}/storage/v1/object/public/{bucket}/{key}"

def register_filters(app):
    app.jinja_env.filters["format_est"] = format_est
    app.jinja_env.filters["format_price"] = format_price
    app.jinja_env.filters["public_image_url"] = public_image_url
    app.jinja_env.filters["cents_to_dollars"] = cents_to_dollars
