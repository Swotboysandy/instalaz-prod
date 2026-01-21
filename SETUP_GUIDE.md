# 📖 Instalaz - Complete Setup Guide

Welcome to Instalaz! This guide will help you set up Instagram automation in 5 minutes.

---

## 🚀 Quick Start

### Step 1: Run the App

```bash
# Install dependencies
pip install -r requirements.txt

# Start the app
python app.py
```

Visit: **http://localhost:5000/onboarding**

---

## 📋 Prerequisites

Before you begin, make sure you have:

✅ **Instagram Business Account**  
- Open Instagram app → Settings → Account  
- Switch to Professional Account → Choose "Business"  
- Connect to a Facebook Page

✅ **Facebook Account**  
- Any regular Facebook account

✅ **5 Minutes of Your Time**

---

## 🔧 Complete Setup (Step-by-Step)

### 1️⃣ Create Facebook App

**Why?** This allows Instalaz to connect to Instagram's API.

**Steps:**

1. Go to: https://developers.facebook.com/apps/create/
2. Click **"Create App"**
3. Choose **"Other"** → **"Business"** → **"Next"**
4. App Name: Type **"My Instalaz"** (or any name)
5. Click **"Create App"**

### 2️⃣ Add Instagram Product

1. Left menu → Click **"Add Product"**
2. Find **"Instagram"** → Click **"Set Up"**
3. Wait for it to configure

### 3️⃣ Configure OAuth Settings

**CRITICAL STEP** (This prevents connection errors):

1. Left menu → **"Use Cases"** → **"Authentication and account creation"**
2. Click **"Settings"**
3. Scroll to **"Valid OAuth Redirect URIs"**
4. Add: `http://localhost:5000/auth/callback`
5. Click **"Save Changes"**

### 4️⃣ Get Your Credentials

1. Left menu → **Settings** → **Basic**
2. Copy **App ID** (numbers like: 123456789)
3. Click **"Show"** next to **App Secret**
4. Copy **App Secret** (long text like: abc123def456...)

### 5️⃣ Connect Instagram

1. Go back to Instalaz: http://localhost:5000/onboarding
2. Paste your **App ID** and **App Secret**
3. Click **"Save & Continue"**
4. Follow the wizard to connect your Instagram account
5. Done! ✅

---

## 🎯 Using Instalaz

### Add Content

1. Dashboard → **"Add Account"** or edit existing account
2. Set **Content URLs**:
   - **Images**: Any public URL (e.g., Dropbox, Google Drive)
   - **Videos**: Any public video URL
   - **Captions**: Text file URL with one caption per line

### Schedule Posts

1. Top menu → **"Schedule"**
2. Set times: Morning, Afternoon, Evening, Night
3. Enable/disable scheduling per account

### Manual Posting

1. Dashboard → Click **"Preview & Select"**
2. Browse your content
3. Select what to post
4. Edit caption
5. Click **"Publish"**

---

## ⚠️ Common Issues & Fixes

### "Facebook detected insecure connection"

**Fix:** Add redirect URI to your Facebook App:
- Go to Use Cases → Authentication → Settings
- Add: `http://localhost:5000/auth/callback`
- Save changes

### "No Instagram accounts found"

**Fix:** Make sure your Instagram is a Business Account:
- Instagram app → Settings → Account
- Switch to Professional Account → Business
- Connect to a Facebook Page

### "Token expired"

**Normal!** Tokens last 60 days. When expired:
- Dashboard → Click "Reconnect"
- Re-authorize with Facebook
- New 60-day token issued automatically

---

## 🔒 Security & Privacy

### Your Data is Safe

- ✅ Tokens stored locally in database
- ✅ No data sent to third parties
- ✅ You control all permissions
- ✅ Can disconnect anytime

### Permissions Explained

When you connect, Instalaz requests:

- **instagram_basic** - Read your profile info (username, bio)
- **instagram_content_publish** - Post photos/videos on your behalf
- **instagram_manage_comments** - Read/reply to comments
- **instagram_manage_insights** - View post analytics
- **pages_show_list** - Access your Facebook Pages
- **business_management** - Connect to Business accounts

**You can revoke these anytime** from Facebook settings.

---

## 📊 Features

### ✅ Auto-Posting
- Schedule carousels (2-10 images)
- Schedule reels (videos)
- Custom posting times
- Timezone support

### ✅ Multi-Account
- Manage unlimited Instagram accounts
- Different schedules per account
- Separate content sources

### ✅ Smart Features
- No duplicate posts (tracks history)
- Preview before publishing
- Telegram notifications
- Activity logs

---

## 🛠️ Advanced Configuration

### Telegram Notifications (Optional)

Get alerts when posts succeed/fail:

1. Open Telegram → Find **@BotFather**
2. Send: `/newbot`
3. Follow instructions to create bot
4. Copy your **Bot Token**
5. Find **@userinfobot** → Get your **Chat ID**
6. Edit `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABCdef...
   TELEGRAM_CHAT_ID=987654321
   ```

### Custom Schedules

Edit `schedule_settings.json`:
```json
{
  "enabled": true,
  "morning": {"hour": 7, "minute": 30},
  "afternoon": {"hour": 15, "minute": 0},
  "evening": {"hour": 18, "minute": 30},
  "night": {"hour": 23, "minute": 0}
}
```

---

## 📁 File Structure

```
instalaz/
├── app.py              # Main application (Flask server)
├── auth.py             # Facebook OAuth & token management
├── database.py         # Account & token storage (SQLite)
├── runner.py           # Instagram posting logic
├── logger.py           # User-friendly logging
├── notifications.py    # Telegram alerts
├── templates/          # Web interface (HTML)
├── accounts.json       # Account configurations
├── instalaz.db        # Your database (auto-created)
└── .env               # Your settings (optional)
```

---

## 🆘 Getting Help

### Logs

Check `activity_logs` table in database for detailed error messages.

### Reset Everything

```bash
# Delete database (starts fresh)
rm instalaz.db

# Restart app
python app.py
```

### Facebook App Issues

- Make sure app is in **Development Mode** (not Live)
- Check **Valid OAuth Redirect URIs** are correct
- Verify **Instagram** product is added

---

## 🎓 Tips & Best Practices

### Content Quality
- Use high-resolution images (1080x1080 or 1080x1350)
- Videos: MP4 format, H.264 codec, under 100MB
- Captions: Keep under 2,200 characters

### Posting Times
- Peak engagement: 11 AM - 1 PM, 7 PM - 9 PM
- Test different times for your audience
- Consistency matters more than perfection

### Token Management
- Reconnect every 50 days (before expiration)
- Enable Telegram alerts for reminders
- Keep Facebook App in Development mode for testing

### Multiple Accounts
- Use unique `state_prefix` for each account
- Separate content sources avoid confusion
- Different schedules prevent overlap

---

## 📄 License

MIT License - Use freely!

---

## 🙏 Credits

Built with:
- Flask (Web framework)
- SQLite (Database)
- Instagram Graph API
- Facebook OAuth 2.0

---

**Need help?** Check the `/onboarding` wizard or review this guide.

**Ready to automate?** [Start Setup →](http://localhost:5000/onboarding)
