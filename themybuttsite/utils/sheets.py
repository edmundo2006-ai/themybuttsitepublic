import json
import re 
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# you already have this — make sure it returns a Python `date` object
from themybuttsite.utils.time import service_date

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ---- helpers --------------------------------------------------------------

def _svc():
    creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON"))
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)

def _sheet_meta(svc):
    return svc.spreadsheets().get(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID")
    ).execute()

def _find_sheet_by_title(meta, title):
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == title:
            return s["properties"]
    return None

def _get_template_id(meta):
    tpl_title = os.environ.get("SHEETS_TEMPLATE_TITLE")
    s = _find_sheet_by_title(meta, tpl_title)
    if not s:
        raise RuntimeError(f"Template tab '{tpl_title}' not found.")
    return s["sheetId"]

def _format_mdy(d):
    """
    Return M/D/YYYY (no zero padding).
    """
    try:
        return d.strftime("%-m/%-d/%Y")   # Unix/Mac
    except ValueError:
        return d.strftime("%#m/%#d/%Y")   # Windows

def _tab_title_for_service_date():
    return _format_mdy(service_date(datetime.now()))

def _row_from_updated_range(a1: str) -> int:
    # e.g., "'8/20/2025'!A12:G12" -> 12
    m = re.search(r"![A-Z]+(\d+):", a1)
    return int(m.group(1))

# ---- public API -----------------------------------------------------------

def ensure_date_tab():
    """
    Ensure a tab exists named after service_date() in M/D/YYYY.
    If missing, clone from the template tab.
    Returns the tab title.
    """
    svc = _svc()
    title = _tab_title_for_service_date()

    meta = _sheet_meta(svc)
    if _find_sheet_by_title(meta, title):
        return title

    # 1) copy template
    copied = svc.spreadsheets().sheets().copyTo(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        sheetId=_get_template_id(meta),
        body={"destinationSpreadsheetId": os.environ.get("SHEETS_SPREADSHEET_ID")},
    ).execute()
    new_sheet_id = copied["sheetId"]

    # 2) rename to date title
    svc.spreadsheets().batchUpdate(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        body={"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": new_sheet_id, "title": title},
                "fields": "title"
            }
        }]}
    ).execute()

    return title

def append_order_row(values):
    """
    Append a row to the first empty row at the bottom of today's tab.
    `values` is a list like: [#, Name, Order, DONE, PAID]
    """
    svc = _svc()
    tab = ensure_date_tab()

    resp = svc.spreadsheets().values().append(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        range=f"'{tab}'!A8:G",                 # anchor; Sheets finds the bottom
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()

    updated_a1 = resp["updates"]["updatedRange"]   # e.g. "'8/20/2025'!A12:G12"
    row = _row_from_updated_range(updated_a1)      # -> 12

    # 3) Apply checkbox validation only to F & G for that row
    meta = _sheet_meta(svc)
    sheet_id = _find_sheet_by_title(meta, tab)["sheetId"]

    svc.spreadsheets().batchUpdate(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        body={"requests": [{
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row - 1,   # 0-based, end-exclusive
                    "endRowIndex": row,
                    "startColumnIndex": 0,      # A
                    "endColumnIndex": 7         # G is exclusive end
                },
                # Empty userEnteredFormat = clear bg, borders, fonts, number formats, etc.
                "cell": {"userEnteredFormat": {}},
                "fields": "userEnteredFormat"
            }
        }]}
    ).execute()

    svc.spreadsheets().batchUpdate(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        body={"requests": [{
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row - 1,  # 0-based, end-exclusive
                    "endRowIndex": row,
                    "startColumnIndex": 5,     # F = 5 (0-based)
                    "endColumnIndex": 7        # G is exclusive end
                },
                "rule": {
                    "condition": {"type": "BOOLEAN"},  # checkbox
                    "strict": True,
                    "showCustomUi": True
                }
            }
        }]}
    ).execute()

    return tab, updated_a1

def _format_order_text(order):
    """
    Build a readable multi-line summary like:
    - Mac & Cheese — $6.50
      • Extra bacon (+$1.00)
      • No onions
    """
    lines = []
    for oi in order.order_items:   
        name = oi.menu_item_name
        price_cents = oi.menu_item_price or 0
        lines.append(f"- {name} — ${price_cents/100.0:0.2f}")

        # quick lookup for add-on prices from menu_item_ingredients
        add_price_by_ing = {
            mmi.ingredient_id: (mmi.add_price or 0)
            for mmi in getattr(oi.menu_item, "menu_item_ingredients", [])
        }

        for sel in oi.selected_ingredients:
            ing_name = sel.ingredient_name or (sel.ingredient.name if sel.ingredient else "Ingredient")
            add_cents = sel.add_price or add_price_by_ing.get(sel.ingredient_id, 0)

            bullet = f"  • {ing_name}"
            if add_cents:
                bullet += f" (+${add_cents/100.0:0.2f})"
            lines.append(bullet)

    return "\n".join(lines)

