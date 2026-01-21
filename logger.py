"""
User-friendly logging system for Instalaz.
Provides plain English messages and activity tracking.
"""

from datetime import datetime
from typing import Optional
from database import log_activity as db_log_activity
import sys


class UserFriendlyLogger:
    """Logger that translates technical errors into plain English."""
    
    # Error message dictionary for common issues
    ERROR_MESSAGES = {
        # Authentication errors
        'auth_missing_token': "Your Instagram account needs to be connected. Please log in with Facebook to continue.",
        'auth_token_expired': "Your Instagram session has expired. Please reconnect your account to continue posting.",
        'auth_invalid_token': "There's a problem with your Instagram connection. Please try reconnecting your account.",
        'auth_permission_denied': "We don't have permission to post to your Instagram account. Please reconnect and grant the necessary permissions.",
        
        # Network errors
        'network_timeout': "The request took too long. Please check your internet connection and try again.",
        'network_connection': "Unable to connect to Instagram. Please check your internet connection.",
        'network_unavailable': "Instagram's servers might be temporarily unavailable. Please try again in a few minutes.",
        
        # Content errors
        'content_not_found': "The image or video couldn't be found. Please check that the file exists and is accessible.",
        'content_invalid_format': "The file format isn't supported by Instagram. Please use a different image or video.",
        'content_too_large': "The file is too large to upload. Instagram has a size limit for media files.",
        'content_invalid_aspect_ratio': "The image dimensions don't meet Instagram's requirements. Please use a different image.",
        
        # API errors
        'api_rate_limit': "You've made too many requests to Instagram. Please wait a few minutes before trying again.",
        'api_quota_exceeded': "You've reached your daily posting limit on Instagram. Try again tomorrow.",
        'api_media_not_ready': "Instagram is still processing your media. This usually takes a few seconds. We'll keep trying.",
        
        # General errors
        'unknown_error': "Something went wrong. Please try again or contact support if this persists.",
    }
    
    def __init__(self, account_id: Optional[int] = None):
        """Initialize logger for specific account."""
        self.account_id = account_id
    
    def _log(self, level: str, action: str, message: str, details: dict = None):
        """Internal logging method."""
        # Print to console
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        icon = {
            'success': '✅',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'running': '🔄'
        }.get(level, '📝')
        
        print(f"[{timestamp}] {icon} {message}", file=sys.stdout)
        
        # Log to database
        try:
            db_log_activity(self.account_id, action, level, message, details)
        except Exception as e:
            print(f"⚠️ Failed to log to database: {e}", file=sys.stderr)
    
    def success(self, action: str, message: str, details: dict = None):
        """Log success message."""
        self._log('success', action, message, details)
    
    def error(self, action: str, error_key: str = None, custom_message: str = None, details: dict = None):
        """Log error with user-friendly message."""
        if custom_message:
            message = custom_message
        elif error_key and error_key in self.ERROR_MESSAGES:
            message = self.ERROR_MESSAGES[error_key]
        else:
            message = self.ERROR_MESSAGES['unknown_error']
        
        self._log('error', action, message, details)
    
    def warning(self, action: str, message: str, details: dict = None):
        """Log warning message."""
        self._log('warning', action, message, details)
    
    def info(self, action: str, message: str, details: dict = None):
        """Log info message."""
        self._log('info', action, message, details)
    
    def running(self, action: str, message: str, details: dict = None):
        """Log running/in-progress message."""
        self._log('running', action, message, details)
    
    @staticmethod
    def translate_exception(exception: Exception) -> tuple:
        """
        Translate Python exception into user-friendly error key and message.
        
        Returns:
            Tuple of (error_key, user_message)
        """
        error_str = str(exception).lower()
        
        # Network/connection errors
        if 'timeout' in error_str:
            return ('network_timeout', UserFriendlyLogger.ERROR_MESSAGES['network_timeout'])
        if 'connection' in error_str or 'network' in error_str:
            return ('network_connection', UserFriendlyLogger.ERROR_MESSAGES['network_connection'])
        
        # Authentication errors
        if 'token' in error_str and ('expired' in error_str or 'invalid' in error_str):
            return ('auth_token_expired', UserFriendlyLogger.ERROR_MESSAGES['auth_token_expired'])
        if 'permission' in error_str or 'oauth' in error_str:
            return ('auth_permission_denied', UserFriendlyLogger.ERROR_MESSAGES['auth_permission_denied'])
        
        # Content errors
        if '404' in error_str or 'not found' in error_str:
            return ('content_not_found', UserFriendlyLogger.ERROR_MESSAGES['content_not_found'])
        if 'format' in error_str or 'invalid' in error_str:
            return ('content_invalid_format', UserFriendlyLogger.ERROR_MESSAGES['content_invalid_format'])
        
        # API errors
        if 'rate limit' in error_str:
            return ('api_rate_limit', UserFriendlyLogger.ERROR_MESSAGES['api_rate_limit'])
        if 'quota' in error_str:
            return ('api_quota_exceeded', UserFriendlyLogger.ERROR_MESSAGES['api_quota_exceeded'])
        
        # Default
        return ('unknown_error', UserFriendlyLogger.ERROR_MESSAGES['unknown_error'])


# Global helper functions for backward compatibility
def log_success(message: str, account_id: Optional[int] = None):
    """Quick success log."""
    logger = UserFriendlyLogger(account_id)
    logger.success('general', message)


def log_error(message: str, account_id: Optional[int] = None, exception: Exception = None):
    """Quick error log."""
    logger = UserFriendlyLogger(account_id)
    if exception:
        error_key, user_message = logger.translate_exception(exception)
        logger.error('general', error_key, f"{message} {user_message}", {'exception': str(exception)})
    else:
        logger.error('general', custom_message=message)


def log_info(message: str, account_id: Optional[int] = None):
    """Quick info log."""
    logger = UserFriendlyLogger(account_id)
    logger.info('general', message)
