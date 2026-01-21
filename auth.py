"""
Facebook OAuth authentication module for Instagram Graph API access.
Handles OAuth flow, token exchange, and token management.
"""

import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode
import os
from database import (
    create_account, 
    update_access_token, 
    get_account_by_ig_id,
    log_activity,
    get_setting,
    set_setting
)


class AuthError(Exception):
    """Custom exception for authentication errors with user-friendly messages."""
    pass


class FacebookAuth:
    """Handles Facebook OAuth flow and Instagram API authentication."""
    
    def __init__(self, app_id: str = None, app_secret: str = None):
        """
        Initialize Facebook Auth handler.
        
        Args:
            app_id: Facebook App ID (defaults to env var or database setting)
            app_secret: Facebook App Secret (defaults to env var or database setting)
        """
        self.app_id = app_id or get_setting('FACEBOOK_APP_ID') or os.getenv('FACEBOOK_APP_ID')
        self.app_secret = app_secret or get_setting('FACEBOOK_APP_SECRET') or os.getenv('FACEBOOK_APP_SECRET')
        
        self.graph_api_version = 'v19.0'
        self.graph_base_url = f'https://graph.facebook.com/{self.graph_api_version}'
    
    def validate_credentials(self) -> bool:
        """Check if Facebook App credentials are configured."""
        return bool(self.app_id and self.app_secret)
    
    def get_login_url(self, redirect_uri: str, state: str = None, permissions: list = None) -> str:
        """
        Generate Facebook OAuth login URL.
        
        Args:
            redirect_uri: URL where Facebook will redirect after login
            state: Optional state parameter for CSRF protection
            permissions: List of permissions to request (uses comprehensive defaults if None)
            
        Returns:
            Complete OAuth authorization URL
        """
        if not self.validate_credentials():
            raise AuthError(
                "Facebook App is not configured yet. "
                "Please set up your Facebook App ID and Secret in the settings."
            )
        
        if not permissions:
            # Comprehensive permission set for full Instagram automation
            permissions = [
                # Instagram Core
                'instagram_basic',                      # Read basic profile info
                'instagram_content_publish',            # Publish photos/videos/stories
                'instagram_manage_comments',            # Read and reply to comments
                'instagram_manage_insights',            # View analytics and insights
                'instagram_manage_messages',            # Read and send DMs
                
                # Instagram Advanced
                'instagram_shopping_tag_products',      # Tag products in posts
                'instagram_manage_events',              # Manage events
                
                # Pages (required for Instagram Business)
                'pages_show_list',                      # List user's Facebook Pages
                'pages_read_engagement',                # Read Page engagement data
                'pages_manage_posts',                   # Manage Page posts
                'pages_manage_metadata',                # Manage Page settings
                'pages_read_user_content',              # Read user content on Page
                
                # Business
                'business_management',                  # Manage business accounts
                
                # Optional (if you want WhatsApp integration later)
                # 'whatsapp_business_messaging',        # Send WhatsApp messages
            ]
        
        params = {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'scope': ','.join(permissions),
            'response_type': 'code',
        }
        
        if state:
            params['state'] = state
        
        return f"https://www.facebook.com/v19.0/dialog/oauth?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Tuple[str, datetime]:
        """
        Exchange authorization code for short-lived access token.
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Same redirect URI used in login URL
            
        Returns:
            Tuple of (access_token, expires_at)
            
        Raises:
            AuthError: If token exchange fails
        """
        try:
            response = requests.get(
                f"{self.graph_base_url}/oauth/access_token",
                params={
                    'client_id': self.app_id,
                    'client_secret': self.app_secret,
                    'redirect_uri': redirect_uri,
                    'code': code,
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if 'access_token' not in data:
                raise AuthError(
                    "Could not get access token from Facebook. "
                    "Please try logging in again."
                )
            
            # Short-lived tokens expire in ~2 hours
            expires_in = data.get('expires_in', 7200)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            return data['access_token'], expires_at
            
        except requests.RequestException as e:
            raise AuthError(
                f"Failed to connect to Facebook. Please check your internet connection and try again. "
                f"(Error: {str(e)})"
            )
    
    def exchange_for_long_lived_token(self, short_lived_token: str) -> Tuple[str, datetime]:
        """
        Exchange short-lived token for long-lived token (60 days).
        
        Args:
            short_lived_token: Short-lived access token from code exchange
            
        Returns:
            Tuple of (long_lived_token, expires_at)
            
        Raises:
            AuthError: If exchange fails
        """
        try:
            response = requests.get(
                f"{self.graph_base_url}/oauth/access_token",
                params={
                    'grant_type': 'fb_exchange_token',
                    'client_id': self.app_id,
                    'client_secret': self.app_secret,
                    'fb_exchange_token': short_lived_token,
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if 'access_token' not in data:
                raise AuthError(
                    "Could not extend your access token. "
                    "Please try disconnecting and reconnecting your account."
                )
            
            # Long-lived tokens expire in ~60 days
            expires_in = data.get('expires_in', 5184000)  # Default 60 days
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            return data['access_token'], expires_at
            
        except requests.RequestException as e:
            raise AuthError(
                f"Failed to extend access token. Please try again later. "
                f"(Error: {str(e)})"
            )
    
    def get_instagram_accounts(self, access_token: str) -> list:
        """
        Get list of Instagram Business Accounts connected to user's Facebook Pages.
        
        Args:
            access_token: User access token
            
        Returns:
            List of Instagram account dictionaries with id, username, profile_picture_url
            
        Raises:
            AuthError: If API call fails
        """
        try:
            # First, get user's Facebook Pages
            response = requests.get(
                f"{self.graph_base_url}/me/accounts",
                params={
                    'access_token': access_token,
                    'fields': 'id,name,instagram_business_account'
                },
                timeout=30
            )
            response.raise_for_status()
            pages_data = response.json()
            
            instagram_accounts = []
            
            for page in pages_data.get('data', []):
                ig_account = page.get('instagram_business_account')
                if not ig_account:
                    continue
                
                # Get Instagram account details
                ig_response = requests.get(
                    f"{self.graph_base_url}/{ig_account['id']}",
                    params={
                        'access_token': access_token,
                        'fields': 'id,username,profile_picture_url,followers_count'
                    },
                    timeout=30
                )
                ig_response.raise_for_status()
                ig_data = ig_response.json()
                
                instagram_accounts.append({
                    'ig_user_id': ig_data['id'],
                    'username': ig_data.get('username', 'Unknown'),
                    'profile_picture_url': ig_data.get('profile_picture_url'),
                    'followers_count': ig_data.get('followers_count', 0),
                    'page_id': page['id'],
                    'page_name': page['name']
                })
            
            if not instagram_accounts:
                raise AuthError(
                    "No Instagram Business Accounts found. "
                    "Make sure you have connected an Instagram Business Account to your Facebook Page. "
                    "Visit https://www.facebook.com/pages to connect one."
                )
            
            return instagram_accounts
            
        except requests.RequestException as e:
            raise AuthError(
                f"Could not retrieve your Instagram accounts. Please try again. "
                f"(Error: {str(e)})"
            )
    
    def validate_token(self, access_token: str) -> Dict:
        """
        Validate an access token and get expiration info.
        
        Args:
            access_token: Token to validate
            
        Returns:
            Dict with is_valid, expires_at, data_access_expires_at
            
        Raises:
            AuthError: If validation fails
        """
        try:
            response = requests.get(
                f"{self.graph_base_url}/debug_token",
                params={
                    'input_token': access_token,
                    'access_token': f"{self.app_id}|{self.app_secret}"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json().get('data', {})
            
            is_valid = data.get('is_valid', False)
            expires_at = None
            
            if 'expires_at' in data and data['expires_at'] > 0:
                expires_at = datetime.utcfromtimestamp(data['expires_at'])
            elif 'data_access_expires_at' in data:
                expires_at = datetime.utcfromtimestamp(data['data_access_expires_at'])
            
            return {
                'is_valid': is_valid,
                'expires_at': expires_at,
                'app_id': data.get('app_id'),
                'user_id': data.get('user_id')
            }
            
        except requests.RequestException as e:
            raise AuthError(f"Could not validate token: {str(e)}")


def refresh_token_if_needed(account_id: int) -> bool:
    """
    Check if account token needs refresh and attempt to refresh.
    
    Args:
        account_id: Database account ID
        
    Returns:
        True if token is valid or was refreshed, False if manual re-auth needed
    """
    from database import get_account, get_token_status
    
    account = get_account(account_id)
    if not account:
        return False
    
    token_status = get_token_status(account_id)
    
    # If token is valid for more than 7 days, no action needed
    if token_status['status'] == 'valid' and token_status['days_remaining'] > 7:
        return True
    
    # For now, we can't automatically refresh Instagram tokens
    # The user needs to re-authenticate via OAuth
    # We'll just log and return False to trigger re-auth flow
    
    if token_status['status'] == 'expired':
        log_activity(
            account_id,
            'token_expired',
            'warning',
            f"Access token expired for {account['name']}. Please reconnect your Instagram account."
        )
        return False
    
    if token_status['status'] == 'expiring_soon':
        log_activity(
            account_id,
            'token_expiring',
            'warning',
            f"Access token for {account['name']} expires in {token_status['days_remaining']} days. Consider reconnecting soon."
        )
        return True  # Still valid, just warning
    
    return True
