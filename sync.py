import os, json, requests

# ─────────────────────────────────────────────────────
# REMOTE STATE SYNC (JsonBin.io)
# ─────────────────────────────────────────────────────
# To use:
# 1. Sign up at https://jsonbin.io
# 2. Get your Master Key (X-Master-Key)
# 3. Create a new Bin with initial content "{}" (or empty object)
# 4. Get the Bin ID (X-Bin-Meta-Id or url)
# 5. Set ENV vars: JSONBIN_KEY, JSONBIN_ID

def get_remote_config():
    key = os.getenv("JSONBIN_KEY")
    bin_id = os.getenv("JSONBIN_ID")
    if not key or not bin_id:
        return None, None
    return key, bin_id

def load_remote_state(prefix, local_data=None):
    """
    Tries to fetch state from JsonBin.
    If 'prefix' specific data exists in the remote bin, returns it.
    The remote bin is expected to hold a single JSON object with keys as prefixes?
    OR we can store the whole file content of used lists?
    
    Strategy:
    The remote bin holds a HUGE dict of all prefixes.
    {
       "pracandy_a": { ...state... },
       "ruthless_b": { ...state... }
    }
    """
    key, bin_id = get_remote_config()
    if not key:
        return None

    try:
        print(f"☁️ [Sync] Fetching remote state from JsonBin ({bin_id})...")
        r = requests.get(
            f"https://api.jsonbin.io/v3/b/{bin_id}",
            headers={"X-Master-Key": key},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("record", {})
            return data.get(prefix) # Return specific account state or None
        else:
            print(f"⚠️ [Sync] Read failed: {r.status_code} {r.text}")
    except Exception as e:
        print(f"⚠️ [Sync] Read error: {e}")
    
    return None

def save_remote_state(prefix, state_data):
    """
    Updates the remote bin.
    WARNING: Concurrency issue if multiple updates happen at once.
    Since we only have 1 worker (as configured), simple read-modify-write is okay-ish.
    But ideally we need atomic updates or separate bins per account.
    
    For simplicity: We will just try to patch the specific key?
    JsonBin doesn't support PATCH on keys easily without paid/complex path.
    Standard update replaces the whole bin.
    
    Safe approach for free tier:
    1. Read whole bin.
    2. Update local part.
    3. Write whole bin.
    """
    key, bin_id = get_remote_config()
    if not key:
        return

    try:
        # 1. Fetch current (to avoid overwriting others)
        r = requests.get(
            f"https://api.jsonbin.io/v3/b/{bin_id}/latest",
            headers={"X-Master-Key": key},
            timeout=10
        )
        if r.status_code == 200:
            full_data = r.json().get("record", {})
        else:
            full_data = {}

        # 2. Update
        full_data[prefix] = state_data
        
        # 3. Save
        # print(f"☁️ [Sync] Saving remote: {prefix}...")
        r2 = requests.put(
            f"https://api.jsonbin.io/v3/b/{bin_id}",
            headers={
                "X-Master-Key": key,
                "Content-Type": "application/json"
            },
            json=full_data,
            timeout=10
        )
        if r2.status_code != 200:
            print(f"⚠️ [Sync] Save failed: {r2.status_code} {r2.text}")
            
    except Exception as e:
        print(f"⚠️ [Sync] Save error: {e}")
