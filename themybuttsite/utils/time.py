from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

YALE_TZ = ZoneInfo("America/New_York")

def get_service_window():
    """
    Returns (start_utc, end_utc) for the Yale service window:
    10:00 PM → 1:00 AM local (America/New_York)
    """
    tz_utc = ZoneInfo("UTC")

    now_local = datetime.now(YALE_TZ)
    svc_date = (now_local - timedelta(days=1)).date() if now_local.time() < dtime(1, 0) else now_local.date()

    start_local = datetime.combine(svc_date, dtime(22, 0), tzinfo=YALE_TZ)
    end_local = start_local + timedelta(hours=6)

    return start_local.astimezone(tz_utc), end_local.astimezone(tz_utc)


def service_date(ts):
    """
    Get the service date for an order.
    Anchored at 10 PM: anything from midnight–00:59 counts as the previous day.
    """
    local_dt = ts.astimezone(YALE_TZ)
    return (local_dt - timedelta(days=1)).date() if local_dt.time() < dtime(1, 0) else local_dt.date()
