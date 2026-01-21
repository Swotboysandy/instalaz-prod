#!/usr/bin/env python3
"""
Telegram Notification Module for Instalaz
Sends real-time notifications to your phone via Telegram Bot API.

Setup:
1. Message @BotFather on Telegram and create a new bot
2. Copy the bot token to TELEGRAM_BOT_TOKEN env var
3. Message @userinfobot to get your chat ID
4. Copy your chat ID to TELEGRAM_CHAT_ID env var
"""

import os
import requests
from typing import Optional
from urllib.parse import quote


class TelegramNotifier:
    """Send notifications via Telegram Bot API."""

    API_BASE = "https://api.telegram.org/bot"

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to the configured chat.
        Returns True on success, False on failure or if disabled.
        """
        if not self.enabled:
            return False

        try:
            url = f"{self.API_BASE}{self.bot_token}/sendMessage"
            resp = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
            return resp.ok
        except Exception as e:
            print(f"⚠️ Telegram notification failed: {e}")
            return False

    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return self.enabled


# Global notifier instance
notifier = TelegramNotifier()


def notify_publish_success(
    account_name: str,
    media_type: str,
    permalink: str = "",
    media_id: str = ""
) -> bool:
    """
    Send a success notification after publishing.
    
    Args:
        account_name: Name of the Instagram account
        media_type: 'carousel' or 'reel'
        permalink: Instagram permalink to the post
        media_id: Instagram media ID
    """
    emoji = "🎠" if media_type == "carousel" else "🎬"
    msg = f"✅ <b>{account_name}</b>\n{emoji} {media_type.title()} published successfully!"
    
    if permalink:
        msg += f"\n\n🔗 <a href='{permalink}'>View on Instagram</a>"
    
    if media_id:
        msg += f"\n📋 Media ID: <code>{media_id}</code>"
    
    return notifier.send(msg)


def notify_publish_failure(account_name: str, error: str) -> bool:
    """
    Send a failure notification when publishing fails.
    
    Args:
        account_name: Name of the Instagram account
        error: Error message (truncated to 300 chars)
    """
    error_truncated = error[:300] + "..." if len(error) > 300 else error
    msg = f"❌ <b>{account_name}</b>\n\n⚠️ Publish failed:\n<code>{error_truncated}</code>"
    return notifier.send(msg)


def notify_custom(message: str) -> bool:
    """Send a custom notification message."""
    return notifier.send(message)


def get_notification_status() -> dict:
    """Get current notification configuration status."""
    return {
        "enabled": notifier.enabled,
        "configured": notifier.is_configured(),
        "bot_token_set": bool(notifier.bot_token),
        "chat_id_set": bool(notifier.chat_id),
    }


# Quick test when run directly
if __name__ == "__main__":
    print("Notification Status:", get_notification_status())
    if notifier.enabled:
        success = notifier.send("🧪 <b>Test notification</b>\n\nInstalaz is connected!")
        print("Test message sent:", "✅ Success" if success else "❌ Failed")
    else:
        print("⚠️ Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")

