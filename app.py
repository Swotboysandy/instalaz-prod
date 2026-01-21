import os, threading, json, secrets
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from datetime import datetime

from runner import (
    load_accounts, save_accounts, run_account, load_status, save_status,
    peek_caption, image_candidates, video_candidates,
    publish_selected_carousel, publish_selected_reel
)

# Import new modules
try:
    from database import (
        init_database, get_all_accounts as db_get_all_accounts,
        create_account as db_create_account, update_account as db_update_account,
        get_account as db_get_account, get_token_status, get_expiring_accounts,
        get_recent_activity, set_setting, get_setting
    )
    from auth import FacebookAuth, AuthError
    from logger import UserFriendlyLogger, log_info, log_error
    DATABASE_ENABLED = True
except ImportError as e:
    print(f"⚠️ Database/Auth modules not available: {e}")
    DATABASE_ENABLED = False

# Import notification status (graceful fallback)
try:
    from notifications import get_notification_status, notify_custom
except ImportError:
    def get_notification_status(): return {"enabled": False, "configured": False}
    def notify_custom(msg): return False

load_dotenv()

# Initialize database
if DATABASE_ENABLED:
    try:
        init_database()
        log_info("Database initialized successfully")
    except Exception as e:
        print(f"⚠️ Database initialization failed: {e}")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ─────────────────────────────────────────────────────
# SCHEDULE SETTINGS
# ─────────────────────────────────────────────────────
SCHEDULE_FILE = "schedule_settings.json"

def load_schedule_times():
    """Load schedule times from JSON. Returns dict with named slots."""
    default = {
        "enabled": True,
        "morning": {"hour": 7, "minute": 30},
        "afternoon": {"hour": 15, "minute": 0},
        "evening": {"hour": 18, "minute": 30},
        "night": {"hour": 23, "minute": 0},
    }
    if not os.path.exists(SCHEDULE_FILE):
        return default
    try:
        with open(SCHEDULE_FILE) as f:
            data = json.load(f)
            # Migration check: if list (old format), convert to dict
            if isinstance(data, list):
                # Map old list to slots if possible, otherwise use default
                new_data = default.copy()
                # Try to map first 4 items
                slots = ["morning", "afternoon", "evening", "night"]
                for i, t in enumerate(data[:4]):
                    new_data[slots[i]] = t
                return new_data
            return data
    except:
        return default

def save_schedule_times(data):
    """Save schedule times to JSON."""
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_global_times_list():
    """Helper: Flatten the global config dict into a list of {hour, minute} for the scheduler."""
    config = load_schedule_times()
    if not config.get("enabled", True):
        return []
        
    times = []
    for key in ["morning", "afternoon", "evening", "night"]:
        t = config.get(key)
        if t:
            times.append(t)
    return times

def ist_to_utc(hour, minute):
    """Convert IST time to UTC (subtract 5:30)."""
    total_minutes = hour * 60 + minute - 330  # 5:30 = 330 minutes
    if total_minutes < 0:
        total_minutes += 1440  # Add 24 hours
    return total_minutes // 60, total_minutes % 60

def background_run(acct):
    run_account(acct)

@app.route("/")
def index():
    """Redirect to welcome page."""
    return redirect(url_for("welcome"))

@app.route("/welcome")
def welcome():
    """Welcome landing page - guides users to setup or dashboard."""
    return render_template("welcome.html")

@app.route("/dashboard")
def dashboard():
    """Main dashboard - shows all Instagram accounts."""
    accounts = load_accounts()
    for acct in accounts:
        acct["status"] = load_status(acct["state_prefix"])
    return render_template("index.html", accounts=accounts)

@app.route("/status")
def all_status():
    accounts = load_accounts()
    return jsonify([
        load_status(acct["state_prefix"])
        for acct in accounts
    ])

@app.route("/run/<int:idx>", methods=["POST"])
def run_now(idx):
    accounts = load_accounts()
    if not (0 <= idx < len(accounts)):
        return jsonify({"error": "Invalid account index"}), 400
    threading.Thread(target=background_run, args=(accounts[idx],), daemon=True).start()
    return jsonify({"status": "started"}), 202

@app.route("/notifications/status")
def notification_status():
    """Check if Telegram notifications are configured."""
    return jsonify(get_notification_status())

@app.route("/notifications/test", methods=["POST"])
def test_notification():
    """Send a test notification to verify Telegram setup."""
    success = notify_custom("🧪 <b>Test Notification</b>\n\nInstalaz is connected and working!")
    return jsonify({"success": success})

# ─────────────────────────────────────────────────────
# Preview + Selective publish (with paging)
# ─────────────────────────────────────────────────────
@app.get("/preview/<int:idx>")
def preview(idx):
    accounts = load_accounts()
    if not (0 <= idx < len(accounts)):
        return jsonify({"error": "Invalid account index"}), 400

    acct = accounts[idx]
    data = {"type": acct.get("type"), "caption": peek_caption(acct)}

    # paging params
    page = max(int(request.args.get("page", 1) or 1), 1)
    page_size = int(request.args.get("page_size") or (12 if acct.get("type") == "carousel" else 8))
    include_used = (str(request.args.get("include_used", "0")).lower() in ("1","true","yes"))

    if acct.get("type") == "carousel":
        res = image_candidates(acct, page=page, page_size=page_size, include_used=include_used)
        data["images"] = res["items"]
        data["has_more"] = res["has_more"]
        data["total_items"] = res.get("total_items", 0)
    else:
        res = video_candidates(acct, page=page, page_size=page_size, include_used=include_used)
        data["videos"] = res["items"]
        data["has_more"] = res["has_more"]
        data["total_items"] = res.get("total_items", 0)

    return jsonify(data), 200


def background_publish_task(acct, payload):
    """Helper to run publish in a background thread."""
    name = acct.get('name')
    prefix = acct.get('state_prefix')
    print(f"🧵 [Background] Starting publish for {name}")
    
    # 1. MARK RUNNING
    save_status(prefix, "running", "Processing in background...")

    try:
        res = None
        options = {
            "hide_likes": payload.get("hide_likes", False),
            "first_comment": payload.get("first_comment", "")
        }

        if acct.get("type") == "carousel":
            selected = payload.get("images") or []
            caption  = payload.get("caption")
            print(f"🖼️ [Background] Publishing carousel with {len(selected)} images")
            res = publish_selected_carousel(acct, selected, caption=caption, options=options)
        else:
            video_url = payload.get("video")
            caption  = payload.get("caption")
            print(f"🎬 [Background] Publishing reel: {video_url}")
            res = publish_selected_reel(acct, video_url, caption=caption, options=options)
        
        print(f"✅ [Background] Publish success: {res}")
        # NOTE: publish_selected_* already calls save_status(..., "success", ...)
    except Exception as e:
        print(f"❌ [Background] Publish failed: {e}")
        import traceback
        traceback.print_exc()
        
        # 2. MARK ERROR
        save_status(prefix, "error", str(e))

        # Fallback notification if runner didn't catch it
        try:
            from notifications import notify_publish_failure
            notify_publish_failure(name, str(e))
        except:
            pass

@app.post("/publish/<int:idx>")
def publish(idx):
    accounts = load_accounts()
    if not (0 <= idx < len(accounts)):
        return jsonify({"error": "Invalid account index"}), 400
    
    acct = accounts[idx]
    payload = request.get_json(silent=True) or {}
    
    # Basic validation before spawning thread
    if acct.get("type") == "reel" and not payload.get("video"):
         return jsonify({"error": "Missing 'video'"}), 400

    print(f"t📤 Received publish request for {acct.get('name')}. Spawning background thread...")
    
    # Spawn background thread
    threading.Thread(target=background_publish_task, args=(acct, payload), daemon=True).start()
    
    return jsonify({
        "status": "accepted", 
        "message": "Publishing started in background. Check Telegram for final status."
    }), 202

# ─────────────────────────────────────────────────────
# Account form (create/edit)
# ─────────────────────────────────────────────────────
@app.route("/account/new", methods=["GET","POST"])
@app.route("/account/<int:idx>/edit", methods=["GET","POST"])
def account_form(idx=None):
    accounts = load_accounts()
    acct = accounts[idx] if idx is not None and 0 <= idx < len(accounts) else {}
    if request.method == "POST":
        data = {
            "name":             request.form["name"],
            "type":             request.form["type"],
            "access_token_env": request.form["access_token_env"],
            "ig_user_id_env":   request.form["ig_user_id_env"],
            "caption_url":      request.form["caption_url"],
            "state_prefix":     request.form["state_prefix"],
            "schedule_enabled": request.form.get("schedule_enabled"), # 'on' or None
            "schedule_times":   request.form.get("schedule_times"),   # RAW string "07:30, 21:00"
        }
        if data["type"] == "carousel":
            data["base_url"]        = request.form["base_url"]
            data["slides_per_post"] = int(request.form.get("slides_per_post") or 1)
            data.pop("video_base_url", None)
        else:
            data["video_base_url"]  = request.form["video_base_url"]
            data.pop("base_url", None)
            data.pop("slides_per_post", None)

        if acct and idx is not None:
            # Merge with existing to avoid losing extra keys (likes video_dir, max_images)
            accounts[idx].update(data)
        else:
            accounts.append(data)

        save_accounts(accounts)
        return redirect(url_for("index"))

    # Load schedule times to show in the form
    times = load_schedule_times()
    return render_template("account_form.html", account=acct, schedule_times=times)


# ─────────────────────────────────────────────────────
# OAUTH & ONBOARDING
# ─────────────────────────────────────────────────────

@app.route("/onboarding")
def onboarding():
    """Show onboarding wizard for first-time setup."""
    return render_template("onboarding.html")


@app.route("/setup-guide")
def setup_guide():
    """Show detailed setup documentation."""
    return render_template("setup_guide.html")





@app.route("/save-fb-credentials", methods=["POST"])
def save_fb_credentials():
    """Save user's own Facebook App credentials."""
    app_id = request.form.get("app_id", "").strip()
    app_secret = request.form.get("app_secret", "").strip()
    
    if not app_id or not app_secret:
        flash("Please provide both App ID and App Secret", "error")
        return redirect(url_for("onboarding") + "?step=2")
    
    # Save to database settings (user-specific)
    if DATABASE_ENABLED:
        try:
            set_setting('FACEBOOK_APP_ID', app_id)
            set_setting('FACEBOOK_APP_SECRET', app_secret)
            log_info(f"Facebook App credentials saved (App ID: {app_id[:8]}...)")
        except Exception as e:
            log_error(f"Failed to save Facebook credentials: {e}")
            flash("Failed to save credentials. Please try again.", "error")
            return redirect(url_for("onboarding") + "?step=2")
    
    # Set in environment for immediate use in this session
    os.environ['FACEBOOK_APP_ID'] = app_id
    os.environ['FACEBOOK_APP_SECRET'] = app_secret
    
    flash("Credentials saved! Now configure your app settings in Facebook.", "success")
    return redirect(url_for("onboarding") + "?step=3")




@app.route("/auth/login")
def auth_login():
    """Redirect to Facebook OAuth login."""
    if not DATABASE_ENABLED:
        flash("Database is not configured. Please check your installation.", "error")
        return redirect(url_for("index"))
    
    try:
        fb_auth = FacebookAuth()
        
        # Generate state token for CSRF protection
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        # Build redirect URI
        redirect_uri = url_for('auth_callback', _external=True)
        
        # Get authorization URL
        auth_url = fb_auth.get_login_url(redirect_uri, state)
        
        return redirect(auth_url)
        
    except AuthError as e:
        log_error(f"OAuth login error: {e}")
        flash(str(e), "error")
        return redirect(url_for("onboarding"))
    except Exception as e:
        log_error(f"Unexpected OAuth error: {e}")
        flash("Failed to start login process. Please check your Facebook App configuration.", "error")
        return redirect(url_for("onboarding"))


@app.route("/auth/callback")
def auth_callback():
    """Handle OAuth callback from Facebook."""
    if not DATABASE_ENABLED:
        return "Database not configured", 500
    
    # Verify state to prevent CSRF
    state = request.args.get('state')
    if not state or state != session.get('oauth_state'):
        flash("Invalid authentication request. Please try again.", "error")
        return redirect(url_for("onboarding"))
    
    # Clear state
    session.pop('oauth_state', None)
    
    # Check for error
    error = request.args.get('error')
    if error:
        error_desc = request.args.get('error_description', 'Unknown error')
        log_error(f"OAuth callback error: {error} - {error_desc}")
        flash(f"Facebook login failed: {error_desc}", "error")
        return redirect(url_for("onboarding"))
    
    # Get authorization code
    code = request.args.get('code')
    if not code:
        flash("No authorization code received. Please try logging in again.", "error")
        return redirect(url_for("onboarding"))
    
    try:
        fb_auth = FacebookAuth()
        redirect_uri = url_for('auth_callback', _external=True)
        
        # Step 1: Exchange code for short-lived token
        short_token, short_expires = fb_auth.exchange_code_for_token(code, redirect_uri)
        log_info("Received short-lived access token")
        
        # Step 2: Exchange for long-lived token (60 days)
        long_token, long_expires = fb_auth.exchange_for_long_lived_token(short_token)
        log_info(f"Converted to long-lived token (expires: {long_expires})")
        
        # Step 3: Get Instagram accounts
        ig_accounts = fb_auth.get_instagram_accounts(long_token)
        
        if not ig_accounts:
            flash("No Instagram Business Accounts found. Please connect one to your Facebook Page.", "warning")
            return redirect(url_for("onboarding"))
        
        # If multiple accounts, let user choose (for now, use first one)
        # TODO: Add account selection UI
        ig_account = ig_accounts[0]
        
        # Step 4: Save to database
        account_data = {
            'name': f"@{ig_account['username']}",
            'type': 'carousel',  # Default, user can change later
            'ig_user_id': ig_account['ig_user_id'],
            'access_token': long_token,
            'token_expires_at': long_expires,
            'page_id': ig_account['page_id'],
            'page_name': ig_account['page_name'],
            'instagram_username': ig_account['username'],
            'profile_picture_url': ig_account.get('profile_picture_url'),
            'state_prefix': f"ig_{ig_account['ig_user_id'][-6:]}",  # Unique prefix
            'schedule_enabled': 0
        }
        
        account_id = db_create_account(account_data)
        log_info(f"Instagram account connected: @{ig_account['username']} (ID: {account_id})")
        
        flash(f"Successfully connected @{ig_account['username']}! 🎉", "success")
        session['setup_complete'] = True
        
        return redirect(url_for("onboarding") + "?step=5")
        
    except AuthError as e:
        log_error(f"Authentication error: {e}")
        flash(str(e), "error")
        return redirect(url_for("onboarding"))
    except Exception as e:
        log_error(f"Failed to complete OAuth flow: {e}", exception=e)
        flash("Something went wrong during authentication. Please try again.", "error")
        return redirect(url_for("onboarding"))


@app.route("/auth/logout/<int:account_id>", methods=["POST"])
def auth_logout(account_id):
    """Disconnect an Instagram account."""
    if not DATABASE_ENABLED:
        return jsonify({"error": "Database not enabled"}), 500
    
    try:
        account = db_get_account(account_id)
        if account:
            db_update_account(account_id, {'status': 'disconnected'})
            log_info(f"Account disconnected: {account['name']}")
            flash(f"Account {account['name']} disconnected successfully", "success")
        return redirect(url_for("index"))
    except Exception as e:
        log_error(f"Failed to disconnect account: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/token/status/<int:account_id>")
def api_token_status(account_id):
    """Get token status for an account."""
    if not DATABASE_ENABLED:
        return jsonify({"error": "Database not enabled"}), 500
    
    try:
        status = get_token_status(account_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity")
def api_activity():
    """Get recent activity logs."""
    if not DATABASE_ENABLED:
        return jsonify([])
    
    try:
        limit = int(request.args.get('limit', 50))
        account_id = request.args.get('account_id')
        
        if account_id:
            logs = get_recent_activity(int(account_id), limit)
        else:
            logs = get_recent_activity(None, limit)
        
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ─────────────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────────────
import schedule, time

def trigger_scheduled_posts():
    """Checked at scheduled times. Runs all enabled accounts."""
    print("⏰ [Scheduler] Triggering scheduled posts...")
    accounts = load_accounts()
    count = 0
    for acct in accounts:
        if acct.get("schedule_enabled") == "on":
            print(f"⏰ [Scheduler] Launching {acct['name']} (Random Mode)")
            # Run in a separate thread so one account doesn't block others
            threading.Thread(target=run_account, args=(acct, "schedule"), daemon=True).start()
            count += 1
    if count == 0:
        print("⏰ [Scheduler] No accounts have scheduling enabled!")
    return count

@app.route("/trigger-schedule")
def manual_trigger_schedule():
    """Manually trigger the scheduler for testing."""
    count = trigger_scheduled_posts()
    return f"Triggered {count} scheduled account(s). Check logs.", 200

@app.route("/schedule-settings", methods=["GET", "POST"])
def schedule_settings():
    """Page to configure schedule times."""
    if request.method == "POST":
        data = {
            "enabled": (request.form.get("enabled") == "on"),
            "morning": {
                "hour": int(request.form.get("morning_h", 0)),
                "minute": int(request.form.get("morning_m", 0))
            },
            "afternoon": {
                "hour": int(request.form.get("afternoon_h", 0)),
                "minute": int(request.form.get("afternoon_m", 0))
            },
            "evening": {
                "hour": int(request.form.get("evening_h", 0)),
                "minute": int(request.form.get("evening_m", 0))
            },
            "night": {
                "hour": int(request.form.get("night_h", 0)),
                "minute": int(request.form.get("night_m", 0))
            }
        }
        save_schedule_times(data)
        return redirect(url_for("schedule_settings"))
    
    schedule = load_schedule_times()
    return render_template("schedule_settings.html", schedule=schedule)

def should_trigger_now():
    """Check if current time matches any configured schedule time (IST)."""
    from datetime import datetime
    import pytz
    
    # Get current time in IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_hour = now.hour
    current_minute = now.minute
    
    # Load configured times (flattened)
    times = get_global_times_list()
    
    # Check if current time matches any configured time (within 1 minute window)
    for t in times:
        if t["hour"] == current_hour and t["minute"] == current_minute:
            return True
    return False

def parse_account_times(time_str):
    """
    Parses '07:30, 15:00' into [{'hour':7, 'minute':30}, ...].
    Returns None if invalid or empty.
    """
    if not time_str or not time_str.strip():
        return None
    
    times = []
    parts = time_str.split(',')
    for p in parts:
        p = p.strip()
        if not p: continue
        try:
            if ':' in p:
                h, m = map(int, p.split(':'))
                if 0 <= h <= 23 and 0 <= m <= 59:
                    times.append({"hour": h, "minute": m})
        except:
             pass
    return times if times else None

def run_schedule_loop():
    """
    Dynamic scheduler that checks config file AND account-specific times every minute.
    """
    import pytz
    from datetime import datetime
    
    print("⏰ [Scheduler] Starting dynamic scheduler (Independent Mode)...")
    
    # Track last triggger per account to avoid double firing in the same minute
    # Key: account_name, Value: minute_of_day (0-1439)
    last_triggers = {} 
    
    while True:
        try:
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist)
            current_minute_abs = now.hour * 60 + now.minute
            
            accounts = load_accounts()
            global_times = get_global_times_list()
            
            for acct in accounts:
                if acct.get("schedule_enabled") != "on":
                    continue
                
                name = acct.get("name", "Unknown")
                
                # Determine Effective Times
                custom_str = acct.get("schedule_times")
                effective_times = parse_account_times(custom_str)
                
                # Fallback to global if no custom times found
                if not effective_times:
                    effective_times = global_times
                
                # Check match
                should_run = False
                for t in effective_times:
                    if t["hour"] == now.hour and t["minute"] == now.minute:
                        should_run = True
                        break
                
                if should_run:
                    # Prevent duplicate run in same minute
                    if last_triggers.get(name) != current_minute_abs:
                        print(f"⏰ [Scheduler] Triggering {name} at {now.strftime('%H:%M IST')}")
                        threading.Thread(target=run_account, args=(acct, "schedule"), daemon=True).start()
                        last_triggers[name] = current_minute_abs
            
        except Exception as e:
            print(f"⚠️ [Scheduler] Error: {e}")
            import traceback
            traceback.print_exc()
        
        time.sleep(30)  # Check every 30 seconds

# Start scheduler in a separate thread (daemon)
# This executes when the module is imported (e.g., by Gunicorn)
def start_scheduler_service():
    if not os.environ.get("WERKZEUG_RUN_MAIN"): # Avoid double run in Flask debug reloader
       print("⏰ [Scheduler] Starting background thread...")
       print("ℹ️  [Render] To prevent sleep, ping: /keep-alive")
       print("⚠️  [Storage] Warning: JSON state files are lost on Deploy/Restart. Use a DB for persistence.")
       threading.Thread(target=run_schedule_loop, daemon=True).start()

start_scheduler_service()

@app.route("/keep-alive")
def keep_alive():
    """Endpoint for UptimeRobot or similar to prevent sleep."""
    return "Alive", 200

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
