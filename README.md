# Instalaz

**Instagram Automation Platform**

Instalaz is a self-hosted Instagram automation tool that enables users to schedule and auto-post carousels, reels, and stories to multiple Instagram Business accounts through a simple web interface.

---

## Features

- **Instagram OAuth Integration** - Secure Facebook OAuth 2.0 authentication
- **Multi-Account Management** - Manage unlimited Instagram Business accounts
- **Auto Posting** - Schedule carousels (2-10 images) and video reels
- **Smart Scheduling** - Configure posting times for different time zones
- **Content Management** - Track posting history and prevent duplicates
- **Token Management** - Automatic 60-day token renewal and expiration tracking
- **Activity Logging** - Comprehensive logs with user-friendly error messages
- **Telegram Notifications** - Optional alerts for successful posts and errors
- **Web Dashboard** - Clean, responsive interface for all operations

---

## Technology Stack

- **Backend**: Python, Flask
- **Database**: SQLite
- **Authentication**: Facebook OAuth 2.0
- **API**: Instagram Graph API
- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **Scheduling**: Python schedule library

---

## Quick Start

### Prerequisites

- Python 3.8+
- Instagram Business Account
- Facebook Developer Account
- Facebook Page connected to Instagram

### Installation

```bash
# Clone the repository
git clone https://github.com/Swotboysandy/instalaz-prod.git
cd instalaz-prod

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Open your browser and navigate to `http://localhost:5000`

---

## Setup Guide

### 1. Create Facebook App

1. Visit [Facebook Developers](https://developers.facebook.com/apps/create/)
2. Create a new app (Type: Business)
3. Add Instagram product
4. Configure OAuth redirect URI: `http://localhost:5000/auth/callback`
5. Copy your App ID and App Secret

### 2. Connect Instagram Account

1. Open the Instalaz onboarding wizard at `/onboarding`
2. Enter your Facebook App credentials
3. Click "Connect with Facebook"
4. Authorize the required permissions
5. Your Instagram Business Account will be connected automatically

### 3. Configure Content

1. Navigate to the dashboard
2. Add your content sources (image URLs, video URLs)
3. Set up caption files (one caption per line)
4. Configure posting schedule

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```
FLASK_SECRET_KEY=your-secret-key-here
TELEGRAM_BOT_TOKEN=your-telegram-bot-token (optional)
TELEGRAM_CHAT_ID=your-telegram-chat-id (optional)
```

### Schedule Settings

Edit `schedule_settings.json` to configure posting times:

```json
{
  "enabled": true,
  "morning": {"hour": 9, "minute": 0},
  "afternoon": {"hour": 15, "minute": 0},
  "evening": {"hour": 19, "minute": 0},
  "night": {"hour": 23, "minute": 0}
}
```

---

## API Permissions

Instalaz requests the following Instagram Graph API permissions:

- `instagram_basic` - Read profile information
- `instagram_content_publish` - Post photos and videos
- `instagram_manage_comments` - Read and manage comments
- `instagram_manage_insights` - Access post analytics
- `instagram_shopping_tag_products` - Tag products in posts
- `pages_show_list` - List Facebook Pages
- `pages_manage_posts` - Manage Page posts
- `business_management` - Manage business accounts

---

## Project Structure

```
instalaz-prod/
├── app.py                 # Main Flask application
├── auth.py                # OAuth authentication handler
├── database.py            # SQLite database operations
├── runner.py              # Instagram posting logic
├── logger.py              # User-friendly logging system
├── notifications.py       # Telegram notification service
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates
│   ├── welcome.html       # Landing page
│   ├── index.html         # Dashboard
│   ├── onboarding.html    # Setup wizard
│   └── setup_guide.html   # Documentation
└── static/                # CSS, JS, images
```

---

## Security

- All access tokens are stored locally in SQLite database
- OAuth state validation prevents CSRF attacks
- Long-lived tokens (60 days validity) are managed automatically
- No third-party data sharing
- Self-hosted solution - you control all data

---

## Troubleshooting

### "Insecure connection detected"

**Solution**: Add `http://localhost:5000/auth/callback` to Valid OAuth Redirect URIs in your Facebook App settings.

### "No Instagram accounts found"

**Solution**: Ensure your Instagram account is converted to a Business Account and connected to a Facebook Page.

### "Token expired"

**Solution**: Tokens expire after 60 days. Click "Reconnect" on the dashboard to obtain a new token.

---

## Contributing

Contributions are welcome! Here's how you can help:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

Please ensure your code follows the existing style and includes appropriate tests.

---

## Support

If you find Instalaz useful, please consider:

- Starring this repository
- Sharing it with others who might benefit
- Contributing improvements or bug fixes
- Reporting issues you encounter

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Instagram Graph API by Meta
- Flask web framework
- Bootstrap UI framework
- All contributors and users

---

## Disclaimer

This tool is for educational and personal use only. Users are responsible for complying with Instagram's Terms of Service and API usage policies. The developers are not responsible for any misuse or violations.

---

**Made with care for the Instagram automation community.**

For questions or support, please open an issue on GitHub.
