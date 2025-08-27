import json
import re 
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from sqlalchemy import and_
from sqlalchemy.orm import joinedload, selectinload

# you already have this — make sure it returns a Python `date` object
from models import Ingredients, MenuItems, Settings, Orders, OrderItems, Users
from themybuttsite.jinjafilters.filters import format_price
from themybuttsite.utils.time import service_date
from themybuttsite.extensions import db_session
from functools import lru_cache

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ---- helpers --------------------------------------------------------------

@lru_cache(maxsize=1)
def _svc():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

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
    spreadsheet_id = os.environ.get("SHEETS_SPREADSHEET_ID")

    # ✅ Single, slim metadata fetch
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title)"
    ).execute()

    # Find an existing sheet with our target title
    existing = None
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == title:
            existing = props
            break
    if existing:
        return title

    # Find template sheetId from the same meta
    tpl_title = os.environ.get("SHEETS_TEMPLATE_TITLE")
    if not tpl_title:
        raise RuntimeError("SHEETS_TEMPLATE_TITLE env var is not set")

    sheetId = None
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == tpl_title:
            sheetId = props.get("sheetId")
            break
    if sheetId is None:
        raise RuntimeError(f"Template tab '{tpl_title}' not found.")

    # 1) Copy template → new sheet (minimal response)
    copied = svc.spreadsheets().sheets().copyTo(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        sheetId=sheetId,
        body={"destinationSpreadsheetId": os.environ.get("SHEETS_SPREADSHEET_ID")},
        fields="sheetId"  # only need the new sheetId
    ).execute()
    new_sheet_id = copied["sheetId"]

    # 2) Rename to date title (suppress detailed replies)
    svc.spreadsheets().batchUpdate(
        spreadsheetId=os.environ.get("SHEETS_SPREADSHEET_ID"),
        body={"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": new_sheet_id, "title": title},
                "fields": "title"
            }
        }]},
        fields="spreadsheetId"  # minimal response
    ).execute()

    # Build top-of-sheet texts
    out_of_stock = db_session.query(Ingredients.name).filter(Ingredients.in_stock.is_(False)).all()
    menu_items   = db_session.query(MenuItems.name).filter(MenuItems.is_default.is_(False)).all()
    announcements = db_session.query(Settings.announcement).one_or_none()

    announcements = "ANNOUNCEMENTS: " + (announcements[0] if announcements else "")
    out_of_stock = [o[0] for o in out_of_stock]
    menu_items   = [m[0] for m in menu_items]
    out_of_stock = "OUT OF STOCK: " + ", ".join(out_of_stock)
    menu_items   = "Special menu items: " + ", ".join(menu_items)

    # 3) Write B2..B4 (minimal response)
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=os.environ["SHEETS_SPREADSHEET_ID"],
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"'{title}'!B2", "values": [[announcements]]},
                {"range": f"'{title}'!B3", "values": [[menu_items]]},
                {"range": f"'{title}'!B4", "values": [[out_of_stock]]},
            ],
        },
        fields="totalUpdatedCells,totalUpdatedRows"
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
        fields="updates(updatedRange,updatedRows)"
    ).execute()

    # Example: "'8/20/2025'!A12:G14" with 3 updated rows
    updated_range = resp["updates"]["updatedRange"]
    updated_rows = resp["updates"]["updatedRows"]

    # Parse ending row (e.g., "G14" -> 14), then compute start row
    end_a1 = updated_range.split(":")[1]           # "G14"
    last_row = int(re.findall(r"\d+", end_a1)[0])  # 14
    first_row = last_row - updated_rows + 1        # 12


    spreadsheet_id = os.environ.get("SHEETS_SPREADSHEET_ID")
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title)"
    ).execute()

    sheet_id = None
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == tab:
            sheet_id = props.get("sheetId")
            break

    if sheet_id is None:
        raise RuntimeError(f"Tab '{tab}' not found")

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

def copy_snippet(buttery=False):
    svc = _svc()
    spreadsheet_id = os.environ["SHEETS_SPREADSHEET_ID"]
    tab = ensure_date_tab()

    # sheetIds
    meta = svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title)"
    ).execute()

    source_id = next(s["properties"]["sheetId"] for s in meta["sheets"] if s["properties"]["title"] == "SNIPPETS")
    dest_id   = next(s["properties"]["sheetId"] for s in meta["sheets"] if s["properties"]["title"] == tab)

    # next empty row (from A8 downward)
    probe_resp = svc.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab}'!A8:A",                 # start scanning from A8
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["__DUMMY__"]]},      # will be overwritten by copyPaste
    ).execute()

    updated_range = probe_resp["updates"]["updatedRange"]
    a1_first_cell = updated_range.split("!")[1].split(":")[0]  
    row_ui = int("".join(ch for ch in a1_first_cell if ch.isdigit()))
    start_row_index = row_ui - 1  # convert to 0-based for batchUpdate

    # Pick source row based on buttery flag
    if buttery:
        src_start_row, src_end_row = 1, 2   # row 2 (A2:G2)
    else:
        src_start_row, src_end_row = 0, 1   # row 1 (A1:G1)

    src_start_col, src_end_col = 0, 7      # cols A..G

    # Destination bounds must match source shape
    dest_start_row = start_row_index
    dest_end_row   = start_row_index + (src_end_row - src_start_row)
    dest_start_col = 0
    dest_end_col   = src_end_col

    body = {
        "requests": [
            {
                "copyPaste": {
                    "source": {
                        "sheetId": source_id,
                        "startRowIndex": src_start_row,
                        "endRowIndex":   src_end_row,
                        "startColumnIndex": src_start_col,
                        "endColumnIndex":   src_end_col,
                    },
                    "destination": {
                        "sheetId": dest_id,
                        "startRowIndex": dest_start_row,
                        "endRowIndex":   dest_end_row,
                        "startColumnIndex": dest_start_col,
                        "endColumnIndex":   dest_end_col,
                    },
                    "pasteType": "PASTE_NORMAL",
                    "pasteOrientation": "NORMAL",
                }
            }
        ]
    }

    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()

    return tab


def closing_buttery_effects():
    YALE_TZ = ZoneInfo("America/New_York")
    UTC_TZ  = ZoneInfo("UTC")

    now_local = datetime.now(YALE_TZ)
    ten_pm = dtime(22, 0)

    # Anchor start to the most recent 10 PM local
    if now_local.time() >= ten_pm:
        start_local = now_local.replace(hour=22, minute=0, second=0, microsecond=0)
    else:
        y = now_local - timedelta(days=1)
        start_local = y.replace(hour=22, minute=0, second=0, microsecond=0)

    # End is the next 10 PM local
    next_day = (start_local + timedelta(days=1)).date()
    end_local = datetime.combine(next_day, ten_pm, tzinfo=YALE_TZ)

    # Convert to UTC for DB query
    start_utc = start_local.astimezone(UTC_TZ)
    end_utc   = end_local.astimezone(UTC_TZ)

    orders = (
        db_session.query(Orders)
        .options(
            joinedload(Orders.users),
            selectinload(Orders.order_items).selectinload(OrderItems.selected_ingredients),
        )
        .filter(and_(Orders.timestamp >= start_utc, Orders.timestamp < end_utc))
        .order_by(Orders.timestamp.desc())
        .limit(4)
        .all()
    )
    prefix = []
    for o in orders:
        if o.id % 5 == 0:   
            break
        prefix.append(o)
    if prefix:
        rows = []
        user_map = dict(
            db_session.query(Users.netid, Users.name)
            .filter(Users.netid.in_([order.netid for order in prefix]))
            .all()
        )
        for order in prefix:
            values = [
                order.id,
                user_map.get(order.netid),
                _format_order_text(order),
                order.specifications or "",
                format_price(order.total_price),
                False,
                False,
            ]
            rows.append(values)


        append_order_rows(rows)
    db_session.expunge_all()


    orders = (
        db_session.query(Orders.id, Orders.status, Orders.paid)
        .filter(and_(Orders.timestamp >= start_utc, Orders.timestamp < end_utc))
        .order_by(Orders.timestamp.desc())
        .all()
    )
    mirror_statuses(orders)
    copy_snippet(buttery=True)
   


def mirror_statuses(order_statuses):
    """
    order_statuses: iterable of objects with .id, .done, .paid
    """
    svc = _svc()
    spreadsheet_id = os.environ["SHEETS_SPREADSHEET_ID"]
    tab = ensure_date_tab()

    # 1) Read IDs from A8 downward and map to row numbers
    a_col = (
        svc.spreadsheets().values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A8:A")
        .execute()
        .get("values", [])
    )
    id_to_row = {}
    for row_num, vals in enumerate(a_col, start=8):
        if not vals or not str(vals[0]).strip():
            continue
        cell = str(vals[0]).strip()
        try:
            order_id = int(float(cell))  # normalize "123" / "123.0"
        except ValueError:
            continue
        id_to_row.setdefault(order_id, row_num)  # prefer first occurrence

    # 2) Build batch value updates for F:G (objects only)
    data = []
    touched_rows = []
    for order in order_statuses:
        if isinstance(order, tuple):
            oid, status, paid = order
        else:
            oid, status, paid = int(order.id), order.status, order.paid
        r = id_to_row.get(int(oid))
        if not r:
            continue
        done = (status == 'done')
        data.append({"range": f"'{tab}'!F{r}:G{r}", "values": [[done, paid]]})
        touched_rows.append(r)

    if not data:
        return {"tab": tab, "updated": 0}

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()

    return {"tab": tab, "updated": len(touched_rows)}
