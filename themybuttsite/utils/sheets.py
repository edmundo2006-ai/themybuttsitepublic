import json
import re 
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# you already have this — make sure it returns a Python `date` object
from models import Ingredients, MenuItems, Settings
from themybuttsite.utils.time import service_date, get_service_window
from themybuttsite.extensions import db_session

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

    out_of_stock = db_session.query(Ingredients.name).filter(Ingredients.in_stock.is_(False)).all()
    menu_items = db_session.query(MenuItems.name).filter(MenuItems.is_default.is_(False)).all()
    announcements = db_session.query(Settings.announcement).one_or_none()
    announcements = "ANNOUNCEMENTS: " + (announcements[0] if announcements else "")
    out_of_stock = [o[0] for o in out_of_stock]
    menu_items = [m[0] for m in menu_items]
    out_of_stock = "OUT OF STOCK: " + ", ".join(out_of_stock)
    menu_items = "Special menu items: " + ", ".join(menu_items)

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {
                    "range":f"'{title}'!B2",
                    "values": [[announcements]]
                },
                {
                    "range": f"'{title}'!B3",   # anchor of B3:G3
                    "values": [[menu_items]]
                },
                {
                    "range": f"'{title}'!B4",   # anchor of B4:G4
                    "values": [[out_of_stock]]
                },
            ],
        },
    ).execute()

    return title

def append_order_rows(rows):
    """
    Append a row to the first empty row at the bottom of today's tab.
    `values` is a list like: [#, Name, Order, DONE, PAID]
    """
    svc = _svc()
    tab = ensure_date_tab()

    # Append all rows in one call
    resp = svc.spreadsheets().values().append(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        range=f"'{tab}'!A8:G",
        valueInputOption="USER_ENTERED",
        insertDataOption="OVERWRITE",
        body={"values": rows},
    ).execute()

    # Example: "'8/20/2025'!A12:G14" with 3 updated rows
    updated_range = resp["updates"]["updatedRange"]
    updated_rows = resp["updates"]["updatedRows"]

    # Parse ending row (e.g., "G14" -> 14), then compute start row
    end_a1 = updated_range.split(":")[1]           # "G14"
    last_row = int(re.findall(r"\d+", end_a1)[0])  # 14
    first_row = last_row - updated_rows + 1        # 12

    # Sheet metadata → get numeric sheetId for today's tab
    meta = _sheet_meta(svc)
    sheet_id = _find_sheet_by_title(meta, tab)["sheetId"]

    # Apply checkbox data validation (columns F:G) to ALL newly written rows
    svc.spreadsheets().batchUpdate(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        body={
            "requests": [
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": first_row - 1,  # 0-based inclusive
                            "endRowIndex": last_row,         # 0-based exclusive
                            "startColumnIndex": 5,           # F (0-based)
                            "endColumnIndex": 7              # up to G (exclusive)
                        },
                        "rule": {
                            "condition": {"type": "BOOLEAN"},  # checkbox
                            "strict": True,
                            "showCustomUi": True
                        }
                    }
                }
            ]
        }
    ).execute()

    return tab

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

def update_to_stock():
    svc = _svc()
    tab = ensure_date_tab()
    out_of_stock = db_session.query(Ingredients.name).filter(Ingredients.in_stock.is_(False)).all()
    out_of_stock = [o[0] for o in out_of_stock]
    out_of_stock = "OUT OF STOCK: " + ", ".join(out_of_stock)

    svc.spreadsheets().values().update(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        range=f"'{tab}'!B4",   # anchor of B4:G4
        valueInputOption="USER_ENTERED",
        body={"values": [[out_of_stock]]},
    ).execute()


def update_menu_sheets():
    svc = _svc()
    tab = ensure_date_tab()
    menu_items = db_session.query(MenuItems.name).filter(MenuItems.is_default.is_(False)).all()
    menu_items = [m[0] for m in menu_items]
    menu_items = "Special menu items: " + ", ".join(menu_items)

    svc.spreadsheets().values().update(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        range=f"'{tab}'!B3",
        valueInputOption="USER_ENTERED",
        body={"values": [[menu_items]]},
    ).execute()


def update_to_announcements():
    svc = _svc()
    tab = ensure_date_tab()
    announcements = db_session.query(Settings.announcement).one_or_none()
    announcements = "ANNOUNCEMENTS: " + (announcements[0] if announcements else "")

    svc.spreadsheets().values().update(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        range=f"'{tab}'!B2",   # anchor of B4:G4
        valueInputOption="USER_ENTERED",
        body={"values": [[announcements]]},
    ).execute()

def update_staff_table(order_id, new_status, paying=False):
    svc = _svc()
    tab = ensure_date_tab()
    ssid = os.environ["SHEETS_SPREADSHEET_ID"]

    resp = svc.spreadsheets().values().get(
        spreadsheetId=ssid,
        range=f"'{tab}'!A8:A",
        majorDimension="COLUMNS",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()

    colA = (resp.get("values") or [[]])[0]  
    target = str(order_id).strip()

    row = None
    for idx, cell in enumerate(colA):       
        if str(cell).strip() == target:
            row = 8 + idx
            break

    if row is None:
        raise RuntimeError(f"Order ID {order_id} not found in sheet '{tab}'.")

    target_col = "G" if paying else "F"
    svc.spreadsheets().values().update(
        spreadsheetId=ssid,
        range=f"'{tab}'!{target_col}{row}",
        valueInputOption="USER_ENTERED",
        body={"values": [[new_status]]},
    ).execute()

def copy_grill_snippet():
    svc = _svc()
    spreadsheet_id = os.environ["SHEETS_SPREADSHEET_ID"]

    tab = ensure_date_tab()

    # Get source/destination sheetIds
    spreadsheet = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    source_id = next(s["properties"]["sheetId"] for s in spreadsheet["sheets"] if s["properties"]["title"] == "SNIPPETS")
    dest_id = next(s["properties"]["sheetId"] for s in spreadsheet["sheets"] if s["properties"]["title"] == tab)

    # Find next empty row from A8 downward
    dest_values = (
        svc.spreadsheets().values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A8:A")
        .execute()
        .get("values", [])
    )
    last_row_index = 7 + len(dest_values)  # 0-based API index; row shown in UI is +1

    # 1) Paste formatting (including merge/borders/colors) ONLY from SNIPPETS!A1:G1
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "copyPaste": {
                        "source": {
                            "sheetId": source_id,
                            "startRowIndex": 0,   # row 1
                            "endRowIndex": 1,     # exclusive
                            "startColumnIndex": 0,  # col A
                            "endColumnIndex": 7,    # exclusive (A..G)
                        },
                        "destination": {
                            "sheetId": dest_id,
                            "startRowIndex": last_row_index,
                            "startColumnIndex": 0,  # paste at A{row}
                        },
                        "pasteType": "PASTE_FORMAT",   # <-- formatting only, no formulas/values
                        "pasteOrientation": "NORMAL",
                    }
                }
            ]
        }
    ).execute()

    # 2) Write static value into the merged cell's anchor (A{row})
    banner = "*GRILL IS CLOSED*"
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab}'!A{last_row_index + 1}",   # write just the anchor cell; merge will display it across
        valueInputOption="USER_ENTERED",
        body={"values": [[banner]]},
    ).execute()

    return tab

def closing_buttery_effects():
    print()
