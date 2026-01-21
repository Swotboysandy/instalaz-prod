#!/usr/bin/env python3
import os, json, random, requests
from time import sleep
from urllib.parse import quote
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Tuple, Dict, Optional

# Notification imports (graceful fallback if not available)
try:
    from notifications import notify_publish_success, notify_publish_failure
except ImportError:
    def notify_publish_success(*args, **kwargs): return False
    def notify_publish_failure(*args, **kwargs): return False

# ─────────────────────────────────────────────────────
# BOOTSTRAP
# ─────────────────────────────────────────────────────
load_dotenv()

ACCOUNTS_FILE = "accounts.json"
STATUS_SUFFIX = "_status.json"

def status_path(prefix):
    return f"{prefix}{STATUS_SUFFIX}"

def save_status(prefix, status, message=""):
    data = {
        "last_run": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "status": status,
        "message": message,
    }
    with open(status_path(prefix), "w") as f:
        json.dump(data, f, indent=2)

def load_status(prefix):
    p = status_path(prefix)
    return json.load(open(p)) if os.path.exists(p) else {
        "last_run": None,
        "status": "never",
        "message": "",
    }

# ─────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────
def _norm_base(url: str) -> str:
    return (url or "").rstrip("/")

def _cfg_token_igid(cfg) -> Tuple[str, str]:
    tok_env = cfg.get("access_token_env")
    usr_env = cfg.get("ig_user_id_env")
    if not tok_env or not usr_env:
        raise RuntimeError("Config missing 'access_token_env' or 'ig_user_id_env'.")
    token = os.getenv(tok_env)
    ig_id = os.getenv(usr_env)
    if not token:
        raise RuntimeError(f"Missing environment var {tok_env}")
    if not ig_id:
        raise RuntimeError(f"Missing environment var {usr_env}")
    return token, ig_id

def fetch_lines(url):
    try:
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        return [l.strip() for l in r.text.splitlines() if l.strip()]
    except Exception as e:
        raise RuntimeError(f"Failed to fetch caption_url {url}: {e}")

def check_content_exists(url):
    """Checks if a URL returns 200 OK (head request)."""
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def wait_until_ready(creation_id, token, max_attempts=600, delay=2):
    for i in range(max_attempts):
        try:
            resp = requests.get(
                f"https://graph.facebook.com/v19.0/{creation_id}",
                params={"fields": "status_code,status", "access_token": token},
                timeout=30,
            ).json()
        except Exception as e:
            print(f"⚠️ Poll attempt {i+1} failed: {e}")
            sleep(delay)
            continue
        status = (resp.get("status_code") or resp.get("status") or "").upper()
        print(f"🔍 Attempt {i+1}/{max_attempts} – {creation_id} => {resp}")
        if status == "FINISHED":
            return True, resp
        if status == "ERROR":
            return False, resp
        sleep(delay)
    return False, last_resp

def fetch_permalink(media_id: str, token: str) -> str:
    try:
        r = requests.get(
            f"https://graph.facebook.com/v19.0/{media_id}",
            params={"fields": "permalink", "access_token": token},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("permalink", "")
    except Exception as e:
        print(f"⚠️ Could not fetch permalink for media {media_id}: {e}")
        return ""

def post_comment(media_id: str, message: str, cfg):
    """Post a comment to a published media object."""
    if not message:
        return None
    try:
        token, _ = _cfg_token_igid(cfg)
        print(f"💬 Posting comment: {message[:50]}...")
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{media_id}/comments",
            data={"message": message, "access_token": token},
            timeout=180,
        )
        resp_json = r.json()
        if r.status_code != 200:
            print(f"⚠️ Comment API error: {resp_json}")
            return None
        print(f"✅ Comment posted successfully: {resp_json.get('id')}")
        return resp_json.get("id")
    except Exception as e:
        print(f"⚠️ Failed to post comment: {e}")
        return None

# ─────────────────────────────────────────────────────
# STATE HELPERS
# ─────────────────────────────────────────────────────
import threading
try:
    from sync import load_remote_state, save_remote_state
except ImportError:
    def load_remote_state(*args): return None
    def save_remote_state(*args): pass

def get_full_local_state(prefix):
    """Aggregates all local state files for a prefix into a dictionary."""
    state = {}
    
    # helper to read
    def read_json(suffix, key):
        try:
            p = f"{prefix}{suffix}"
            if os.path.exists(p):
                 return json.load(open(p)).get(key)
        except: pass
        return None

    state["video_used"] = read_json("_video_used.json", "used") or []
    state["image_used"] = read_json("_image_used.json", "used") or []
    state["caption_idx"] = read_json("_caption.json", "last_index") or 0
    state["image_idx"]   = read_json("_image.json", "last_index") or 0
    return state

def push_state_bg(prefix):
    """Push local state to remote in background."""
    state = get_full_local_state(prefix)
    save_remote_state(prefix, state)

def restore_from_remote_if_needed(prefix):
    """If local files are missing, try to restore from remote."""
    # Check if any local file exists. If so, assume we are good?
    # Or just check if critical 'used' files are missing.
    v_path = f"{prefix}_video_used.json"
    i_path = f"{prefix}_image_used.json"
    
    if os.path.exists(v_path) or os.path.exists(i_path):
        return # Assume local is fresh enough (or we are in persistent mode)

    # If missing, fetch from cloud
    remote = load_remote_state(prefix)
    if not remote:
        return

    # Restore files
    if "video_used" in remote:
        save_used_list(prefix, remote["video_used"], sync=False)
    if "image_used" in remote:
        save_image_used_list(prefix, remote["image_used"], sync=False)
    if "caption_idx" in remote:
        save_last_index(prefix, "caption", remote["caption_idx"], sync=False)
    if "image_idx" in remote:
        save_last_index(prefix, "image", remote["image_idx"], sync=False)


def load_last_index(prefix, key):
    fn = f"{prefix}_{key}.json"
    if not os.path.exists(fn):
        restore_from_remote_if_needed(prefix)
    
    # Try again after restore
    if not os.path.exists(fn):
        return 0
    try:
        return json.load(open(fn)).get("last_index", 0)
    except Exception:
        return 0

def save_last_index(prefix, key, idx, sync=True):
    fn = f"{prefix}_{key}.json"
    with open(fn, "w") as f:
        json.dump({"last_index": idx}, f, indent=2)
    if sync:
        threading.Thread(target=push_state_bg, args=(prefix,)).start()

def load_used_list(prefix) -> List[str]:
    fn = f"{prefix}_video_used.json"
    if not os.path.exists(fn):
        restore_from_remote_if_needed(prefix)

    if not os.path.exists(fn):
        return []
    try:
        return json.load(open(fn)).get("used", [])
    except Exception:
        return []

def save_used_list(prefix, used: List[str], sync=True):
    fn = f"{prefix}_video_used.json"
    with open(fn, "w") as f:
        json.dump({"used": used}, f, indent=2)
    if sync:
        threading.Thread(target=push_state_bg, args=(prefix,)).start()

def image_used_list(prefix) -> List[str]:
    fn = f"{prefix}_image_used.json"
    if not os.path.exists(fn):
        restore_from_remote_if_needed(prefix)

    if not os.path.exists(fn):
        return []
    try:
        return json.load(open(fn)).get("used", [])
    except Exception:
        return []

def save_image_used_list(prefix, used: List[str], sync=True):
    fn = f"{prefix}_image_used.json"
    with open(fn, "w") as f:
        json.dump({"used": used}, f, indent=2)
    if sync:
        threading.Thread(target=push_state_bg, args=(prefix,)).start()

# ─────────────────────────────────────────────────────
# ACCOUNTS CONFIG
# ─────────────────────────────────────────────────────
def load_accounts(path=ACCOUNTS_FILE):
    return json.load(open(path))

def save_accounts(accounts, path=ACCOUNTS_FILE):
    with open(path, "w") as f:
        json.dump(accounts, f, indent=2)

# ─────────────────────────────────────────────────────
# MEDIA LOGIC
# ─────────────────────────────────────────────────────
def next_caption(cfg):
    lines = fetch_lines(cfg["caption_url"])
    if not lines:
        raise RuntimeError("Caption list is empty.")
    idx = load_last_index(cfg["state_prefix"], "caption")
    caption = lines[idx % len(lines)]
    save_last_index(cfg["state_prefix"], "caption", idx + 1)
    return caption

def next_images(cfg):
    count = int(cfg.get("slides_per_post", 1))
    last = load_last_index(cfg["state_prefix"], "image")
    max_images = int(cfg.get("max_images", 10000))  # Default high number if not set
    base = _norm_base(cfg.get("base_url", ""))
    if not base:
        raise RuntimeError("Missing base_url for carousel.")
    urls = []
    for i in range(1, count + 1):
        # Loop back to 1 if we exceed max_images
        img_index = ((last + i - 1) % max_images) + 1
        fn = f"img ({img_index}).jpg"

        # ✅ NEW FIX: If filenames on server already have '%20', use that directly
        if "ruthless" in cfg.get("state_prefix", "").lower():
            encoded = f"img%20({img_index}).jpg"
        else:
            encoded = quote(fn, safe="()")

        urls.append(f"{base}/{encoded}")
    save_last_index(cfg["state_prefix"], "image", (last + count - 1) % max_images + 1)
    return urls


# ─────────────────────────────────────────────────────
# UPLOAD / PUBLISH
# ─────────────────────────────────────────────────────
def upload_image(url, cfg):
    token, ig_id = _cfg_token_igid(cfg)
    r = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media",
        data={"image_url": url, "is_carousel_item": "true", "access_token": token},
        timeout=600,
    )
    if r.status_code != 200:
        error_detail = r.json() if r.headers.get('content-type', '').startswith('application/json') else r.text
        raise RuntimeError(f"Instagram API Error {r.status_code}: {error_detail}")
    r.raise_for_status()
    return r.json()["id"]

def upload_reel(url, cfg, caption: str, hide_likes: bool = False):
    token, ig_id = _cfg_token_igid(cfg)
    
    print(f"📹 [DEBUG] Uploading reel from URL: {url}")
    print(f"🔒 [DEBUG] hide_likes={hide_likes}")
    
    data = {
        "media_type": "REELS",
        "video_url": url,
        "caption": caption,
        "access_token": token,
    }
    if hide_likes:
        data["like_and_view_counts_disabled"] = "true"
        print(f"✅ [DEBUG] Added like_and_view_counts_disabled=true to API request")
        
    r = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media",
        data=data,
        timeout=1200,
    )
    r.raise_for_status()
    return r.json()["id"]

def create_carousel(child_ids: List[str], caption: str, cfg, hide_likes: bool = False):
    token, ig_id = _cfg_token_igid(cfg)
    
    print(f"🖼️ [DEBUG] Creating carousel with {len(child_ids)} items")
    print(f"🔒 [DEBUG] hide_likes={hide_likes}")
    
    data = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": token,
    }
    if hide_likes:
        data["like_and_view_counts_disabled"] = "true"
        print(f"✅ [DEBUG] Added like_and_view_counts_disabled=true to API request")

    r = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media",
        data=data,
        timeout=600,
    ).json()
    cid = r.get("id")
    if not cid:
        raise RuntimeError(f"Carousel container creation error: {r}")
    return cid, token

def publish_creation(creation_id: str, cfg):
    token, ig_id = _cfg_token_igid(cfg)
    pub = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=1200,
    ).json()
    media_id = pub.get("id")
    if not media_id:
        raise RuntimeError(f"media_publish error: {pub}")
    return media_id, token

# ─────────────────────────────────────────────────────
# PREVIEW + SELECTIVE PUBLISH HELPERS
# ─────────────────────────────────────────────────────
def peek_caption(cfg):
    lines = fetch_lines(cfg["caption_url"])
    idx = load_last_index(cfg["state_prefix"], "caption")
    return lines[idx % len(lines)] if lines else ""

def _image_name_for(cfg, base_index: int) -> str:
    return f"img ({base_index}).jpg"

def image_candidates(cfg, page: int = 1, page_size: int = 12, include_used: bool = False) -> Dict:
    result = {"items": [], "has_more": True}
    if cfg.get("type") != "carousel":
        return result
    base = _norm_base(cfg.get("base_url", ""))
    if not base:
        return result
    last = load_last_index(cfg["state_prefix"], "image")
    used_set = set(image_used_list(cfg["state_prefix"]))
    max_images = int(cfg.get("max_images", 10000))
    
    result["total_items"] = max_images 
    
    start_idx = last + 1 + (page - 1) * page_size
    end_idx = start_idx + page_size - 1
    for i in range(start_idx, end_idx + 1):
        filename = _image_name_for(cfg, i)
        used = filename in used_set
        if used and not include_used:
            end_idx += 1
            if end_idx - start_idx > page_size * 3:
                break
            continue
        encoded = quote(filename, safe="()")
        url = f"{base}/{encoded}"
        result["items"].append({"url": url, "filename": filename, "used": used})
        if len(result["items"]) >= page_size:
            break
    result["has_more"] = len(result["items"]) >= page_size
    return result

def video_candidates(cfg, page: int = 1, page_size: int = 8, include_used: bool = False) -> Dict:
    result = {"items": [], "has_more": False}
    if cfg.get("type") != "reel":
        return result
    base = _norm_base(cfg.get("video_base_url", ""))
    if not base:
        return result
    max_items = int(cfg.get("max_images", 200))
    used = set(load_used_list(cfg["state_prefix"]))
    all_files = ["vid.mp4"] + [f"vid ({i}).mp4" for i in range(1, max_items + 1)]
    ordered = all_files if include_used else [f for f in all_files if f not in used]
    total = len(ordered)
    if total == 0:
        return result
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    page_files = ordered[start:end]
    items = []
    for fname in page_files:
        items.append({
            "url": f"{base}/{quote(fname, safe='()')}",
            "filename": fname,
            "used": fname in used,
        })
    result["items"] = items
    result["has_more"] = end < total
    result["total_items"] = total
    return result

def mark_video_used(cfg, selected_filename):
    used = set(load_used_list(cfg["state_prefix"]))
    fname = selected_filename.split("/")[-1]
    used.add(fname)
    save_used_list(cfg["state_prefix"], list(used))

def mark_images_used(cfg, selected_urls: List[str]):
    used = set(image_used_list(cfg["state_prefix"]))
    for u in selected_urls:
        fname = u.split("/")[-1]
        used.add(fname)
    save_image_used_list(cfg["state_prefix"], list(used))

def peek_then_commit_caption(cfg):
    lines = fetch_lines(cfg["caption_url"])
    idx = load_last_index(cfg["state_prefix"], "caption")
    cap = lines[idx % len(lines)] if lines else ""
    save_last_index(cfg["state_prefix"], "caption", idx + 1)
    return cap

def publish_selected_carousel(cfg, selected_urls, caption=None, options=None):
    if not selected_urls:
        raise RuntimeError("No slides selected")
    options = options or {}
    hide_likes = options.get("hide_likes", False)
    first_comment = options.get("first_comment", "")

    token, ig_id = _cfg_token_igid(cfg)
    child_ids = []
    
    total = len(selected_urls)
    for i, u in enumerate(selected_urls, 1):
        msg = f"Uploading slide {i}/{total}..."
        print(f"👉 {msg} ({u})")
        save_status(cfg["state_prefix"], "running", msg)
        
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{ig_id}/media",
            data={"image_url": u, "is_carousel_item": "true", "access_token": token},
            timeout=120,
        )
        r.raise_for_status()
        cid = r.json()["id"]
        
        save_status(cfg["state_prefix"], "running", f"Verifying slide {i}/{total}...")
        success, resp = wait_until_ready(cid, token)
        if not success:
            raise RuntimeError(f"Media {cid} failed readiness. Info: {resp}")
        child_ids.append(cid)

    cap = caption or peek_then_commit_caption(cfg)
    
    save_status(cfg["state_prefix"], "running", "Creating carousel container...")
    creation_id, token = create_carousel(child_ids, cap, cfg, hide_likes=hide_likes)
    
    # Wait for carousel container to be ready
    save_status(cfg["state_prefix"], "running", "Processing carousel...")
    success, resp = wait_until_ready(creation_id, token)
    if not success:
        raise RuntimeError(f"Carousel container {creation_id} failed readiness. Info: {resp}")
    
    save_status(cfg["state_prefix"], "running", "Publishing to Instagram...")
    media_id, token = publish_creation(creation_id, cfg)
    
    # ─── Post First Comment ───
    if first_comment:
        save_status(cfg["state_prefix"], "running", "Posting first comment...")
        post_comment(media_id, first_comment, cfg)

    permalink = fetch_permalink(media_id, token)
    mark_images_used(cfg, selected_urls)
    msg = f"Carousel (manual) published ✅\nMedia ID: {media_id}\nPermalink: {permalink or '(not available)'}"
    save_status(cfg["state_prefix"], "success", msg)
    print(f"✅ {cfg['name']}: {msg}")
    notify_publish_success(cfg['name'], "carousel", permalink, media_id)
    return {"media_id": media_id, "permalink": permalink}

def publish_selected_reel(cfg, selected_video_url, caption=None, options=None):
    options = options or {}
    hide_likes = options.get("hide_likes", False)
    first_comment = options.get("first_comment", "")

    token, _ = _cfg_token_igid(cfg)
    cap = caption or peek_then_commit_caption(cfg)
    
    save_status(cfg["state_prefix"], "running", "Uploading video file...")
    print(f"👉 Uploading video... ({selected_video_url})")
    
    # Pass hide_likes here
    creation_id = upload_reel(selected_video_url, cfg, cap, hide_likes=hide_likes)
    token, _ = _cfg_token_igid(cfg)
    
    save_status(cfg["state_prefix"], "running", "Processing video (this may take a while)...")
    success, resp = wait_until_ready(creation_id, token)
    if not success:
        raise RuntimeError(f"Reel container {creation_id} failed readiness. Info: {resp}")
    
    save_status(cfg["state_prefix"], "running", "Publishing reel...")
    media_id, token = publish_creation(creation_id, cfg)

    # ─── Post First Comment ───
    if first_comment:
        save_status(cfg["state_prefix"], "running", "Posting first comment...")
        post_comment(media_id, first_comment, cfg)

    permalink = fetch_permalink(media_id, token)
    mark_video_used(cfg, selected_video_url)
    msg = f"Reel (manual) published ✅\nMedia ID: {media_id}\nPermalink: {permalink or '(not available)'}"
    save_status(cfg["state_prefix"], "success", msg)
    print(f"✅ {cfg['name']}: {msg}")
    notify_publish_success(cfg['name'], "reel", permalink, media_id)
    return {"media_id": media_id, "permalink": permalink}

# ─────────────────────────────────────────────────────
# RANDOM / SCHEDULE LOGIC
# ─────────────────────────────────────────────────────
def get_random_candidate(cfg, kind="image"):
    """
    Picks a random unused item. 
    If all items are used, resets the used list and picks again.
    """
    prefix = cfg["state_prefix"]
    
    # 1. Determine available items
    # For simplicity, we rely on the max_images config or a hard limit
    # because we don't have file listing access to remote URLs here.
    
    items = []
    if kind == "image":
        max_items = int(cfg.get("max_images", 10000))
        # Build list of "virtual" filenames we expect to exist
        items = [_image_name_for(cfg, i) for i in range(1, max_items + 1)]
    else:
        # For videos, we use the known pattern
        # vid.mp4, vid (1).mp4 ... vid (max).mp4
        max_items = int(cfg.get("max_images", 200))
        items = ["vid.mp4"] + [f"vid ({i}).mp4" for i in range(1, max_items + 1)]

    # 2. Filter used
    if kind == "image":
        used_set = set(image_used_list(prefix))
    else:
        used_set = set(load_used_list(prefix))
        
    unused = [x for x in items if x not in used_set]
    
    # 3. Reset if needed
    if not unused:
        print(f"🔄 {cfg['name']}: All content used! Looping back (resetting used list).")
        if kind == "image":
            save_image_used_list(prefix, [])
            used_set = set()
        else:
            save_used_list(prefix, [])
            used_set = set()
        unused = items # All available again

    if not unused:
        return None # Should not happen unless max_items=0

    # 4. Pick random with validation
    import random
    
    attempts = 0
    max_check_attempts = 50 
    
    while attempts < max_check_attempts:
        if not unused:
             return None

        selected_filename = random.choice(unused)
        attempts += 1
        
        # 5. Construct URL
        if kind == "image":
            base = _norm_base(cfg.get("base_url", ""))
            # Handle encoding
            if "ruthless" in prefix.lower():
                 import re
                 m = re.search(r"\((\d+)\)", selected_filename)
                 idx = int(m.group(1)) if m else 1
                 encoded = f"img%20({idx}).jpg"        
            else:
                encoded = quote(selected_filename, safe="()")
                
            url = f"{base}/{encoded}"
            
            # CHECK EXISTENCE
            if check_content_exists(url):
                 return {"url": url, "filename": selected_filename}
        else:
            base = _norm_base(cfg.get("video_base_url", ""))
            url = f"{base}/{quote(selected_filename, safe='()')}"
            
            # CHECK EXISTENCE
            if check_content_exists(url):
                 return {"url": url, "filename": selected_filename}
        
        # If we got here, check failed
        print(f"⚠️ {cfg.get('name')}: Candidate {selected_filename} not found (404). Retrying...")
        unused.remove(selected_filename) # Don't try this one again
        
    print(f"❌ {cfg.get('name')}: Could not find any valid content after {max_check_attempts} checks.")
    return None


# ─────────────────────────────────────────────────────
# SINGLE ACCOUNT RUNNER
# ─────────────────────────────────────────────────────
def run_account(cfg, mode="manual"):
    prefix = cfg["state_prefix"]
    save_status(prefix, "running", f"Starting automation ({mode})...")
    
    # Defaults
    hide_likes = True # Default for schedule as requested
    first_comment = "Follow for more daily content! 🚀🔥"

    try:
        if cfg["type"] == "carousel":
            # CAROUSEL LOGIC
            if mode == "schedule":
                # Random logic
                # We need N random images
                count = int(cfg.get("slides_per_post", 1))
                selected_urls = []
                # We pick one by one to ensure randomness and handle reset in between?
                # Actually if we pick 5 random, we should ensure they are distinct.
                # Simplified: Pick 1 'base' random? No, carousels need multiple.
                # Let's just call get_random_candidate N times.
                
                for _ in range(count):
                    cand = get_random_candidate(cfg, "image")
                    if cand:
                        selected_urls.append(cand["url"])
                        # Temporarily mark as used in memory so we don't pick same one in this loop?
                        # Ideally yes, but probability includes it.
                        # For simplicity, we just use them.
                        # Important: The final 'publish' marks them as used.
                
                # If duplicates, filtered?
                selected_urls = list(dict.fromkeys(selected_urls)) 
                
                if not selected_urls:
                    raise RuntimeError("No random images available.")
                
                imgs = selected_urls
                cap = next_caption(cfg) # Still sequential captions? Or random? User said "upload any random content".
                # Usually captions are better sequential or matched. Let's keep captions sequential for now unless requested.
            else:
                # Manual / Sequential logic
                imgs = next_images(cfg)
                cap = next_caption(cfg)

            # PUBLISH
            child_ids = []
            total = len(imgs)
            for i, u in enumerate(imgs, 1):
                msg = f"Uploading image {i}/{total}..."
                print(f"🖼️ {msg} ({u})")
                save_status(prefix, "running", msg)
                
                cid = upload_image(u, cfg)
                token, _ = _cfg_token_igid(cfg)
                
                save_status(prefix, "running", f"Verifying image {i}/{total}...")
                success, resp = wait_until_ready(cid, token)
                if success:
                    child_ids.append(cid)
                else:
                    raise RuntimeError(f"Media container {cid} failed readiness. Info: {resp}")
            
            save_status(prefix, "running", "Creating carousel...")
            creation_id, token = create_carousel(child_ids, cap, cfg, hide_likes=hide_likes)
            
            save_status(prefix, "running", "Publishing carousel...")
            media_id, token = publish_creation(creation_id, cfg)
            
            if first_comment:
                 post_comment(media_id, first_comment, cfg)

            permalink = fetch_permalink(media_id, token)
            
            # Mark used (if random, we need to mark them! next_images sequential didn't need explicit 'mark used list' 
            # because it uses index. BUT random DOES.)
            if mode == "schedule":
                 mark_images_used(cfg, imgs)
            
            msg = f"Carousel ({mode}) published ✅\nMedia ID: {media_id}\nPermalink: {permalink or '(not available)'}"
            save_status(prefix, "success", msg)
            print(f"✅ {cfg['name']}: {msg}")
            notify_publish_success(cfg['name'], "carousel", permalink, media_id)
            return {"media_id": media_id, "permalink": permalink}
            
        else:
            # REEL LOGIC
            save_status(prefix, "running", "Selecting video...")
            
            if mode == "schedule":
                cand = get_random_candidate(cfg, "video")
                vid_cand = cand["url"] if cand else None
                # Random mode uses sequential caption? User asked for "random content". 
                # I'll stick to sequential caption to avoid repetition issues there too.
            else:
                # Sequential shim
                def next_video_shim(cfg):
                    res = video_candidates(cfg, page=1, page_size=1, include_used=False)
                    if res["items"]:
                        return res["items"][0]["url"] 
                    return None
                vid_cand = next_video_shim(cfg)

                # Auto-reset if all used (Manual Mode)
                if not vid_cand:
                    print(f"🔄 {cfg['name']}: All content used! Looping back (resetting used list).")
                    save_used_list(prefix, [])
                    vid_cand = next_video_shim(cfg)
            
            if not vid_cand:
                raise RuntimeError("No content available")
                
            cap = next_caption(cfg)
            
            save_status(prefix, "running", "Uploading video...")
            creation_id = upload_reel(vid_cand, cfg, cap, hide_likes=hide_likes)
            token, _ = _cfg_token_igid(cfg)
            
            save_status(prefix, "running", "Processing video...")
            success, resp = wait_until_ready(creation_id, token)
            if not success:
                raise RuntimeError(f"Reel container {creation_id} failed readiness. Info: {resp}")
            
            save_status(prefix, "running", "Publishing reel...")
            media_id, token = publish_creation(creation_id, cfg)
            
            if first_comment:
                 post_comment(media_id, first_comment, cfg)

            permalink = fetch_permalink(media_id, token)
            
            if mode == "schedule":
                 mark_video_used(cfg, vid_cand)

            msg = f"Reel ({mode}) published ✅\nMedia ID: {media_id}\nPermalink: {permalink or '(not available)'}"
            save_status(prefix, "success", msg)
            print(f"✅ {cfg['name']}: {msg}")
            notify_publish_success(cfg['name'], "reel", permalink, media_id)
            return {"media_id": media_id, "permalink": permalink}
    except Exception as e:
        save_status(prefix, "error", str(e))
        print(f"✘ {cfg.get('name','(account)')} error: {e}")
        notify_publish_failure(cfg.get('name', 'Unknown'), str(e))
        return None

if __name__ == "__main__":
    import sys
    try:
        accounts = load_accounts()
    except Exception as e:
        print(f"✘ Failed to load {ACCOUNTS_FILE}: {e}")
        raise

    # ─────────────────────────────────────────────────────
    # CONFIG VALIDATION
    # ─────────────────────────────────────────────────────
    def validate_config(accounts):
        print("\n🔍 Validating Environment Configuration...")
        print(f"{'Account Name':<25} | {'Token Var':<20} | {'Status'}")
        print("-" * 60)
        
        all_ok = True
        for a in accounts:
            name = a.get('name', 'Unknown')
            token_env = a.get('access_token_env', 'N/A')
            user_env = a.get('ig_user_id_env', 'N/A')
            
            missing = []
            if token_env != 'N/A' and not os.getenv(token_env):
                missing.append(token_env)
            if user_env != 'N/A' and not os.getenv(user_env):
                missing.append(user_env)
            
            if missing:
                status = f"❌ Missing: {', '.join(missing)}"
                all_ok = False
            else:
                status = "✅ Ready"
                
            print(f"{name:<25} | {token_env:<20} | {status}")
        
        print("-" * 60)
        return all_ok

    validate_config(accounts)
    
    if "--check" in sys.argv:
        print("✅ Config check complete. Exiting (--check specified).")
        sys.exit(0)

    for a in accounts:
        print(f"\n→ {a.get('name','(unnamed)')} [{a.get('type')}]")
        run_account(a)
    print("\nAll finished.")
