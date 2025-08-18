import requests

class YaliesError(Exception):
    pass

def fetch_profile(api_key, timeout=(5, 5), CAS_ENABLED = True, netid = None, email = None):
    
    headers = {"Authorization": f"Bearer {api_key}"}
    if CAS_ENABLED:
        payload = {"filters": {"netid": netid}, "fields": ["first_name", "email"]}
    else:
        payload = {"filters": {"email": email}, "fields": ["first_name", "email"]}

    try:
        r = requests.post(
            "https://api.yalies.io/v2/people",
            json=payload,
            headers=headers,
            timeout=timeout
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise YaliesError(f"Request to Yalies failed: {e}")

    if not data:
        raise YaliesError(f"No data returned for netid '{netid}'.")

    if CAS_ENABLED:
        return {
            "first_name": data[0].get("first_name", "Unknown").strip(),
            "email": data[0].get("email", f"{netid}@unknown.example").strip()
        }
    else:
        return {
            "first_name": data[0].get("first_name", "Unknown").strip(),
            "netid": data[0].get("netid").strip()
        }
