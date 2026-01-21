"""
Database layer for Instalaz using SQLite.
Manages user accounts, tokens, and activity logs.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import os
from contextlib import contextmanager

DATABASE_PATH = "instalaz.db"

@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # User accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('carousel', 'reel')),
                ig_user_id TEXT NOT NULL UNIQUE,
                access_token TEXT NOT NULL,
                token_expires_at TIMESTAMP,
                page_id TEXT,
                page_name TEXT,
                instagram_username TEXT,
                profile_picture_url TEXT,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_token_refresh TIMESTAMP,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'disconnected')),
                
                -- Content configuration
                caption_url TEXT,
                base_url TEXT,
                video_base_url TEXT,
                slides_per_post INTEGER DEFAULT 1,
                max_images INTEGER DEFAULT 10000,
                
                -- State tracking
                state_prefix TEXT NOT NULL UNIQUE,
                
                -- Scheduling
                schedule_enabled INTEGER DEFAULT 0,
                schedule_times TEXT,
                
                -- Metadata
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Activity logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('success', 'error', 'running', 'warning')),
                message TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        """)
        
        # Token refresh history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                old_token TEXT,
                new_token TEXT,
                refresh_type TEXT CHECK(refresh_type IN ('short_to_long', 'manual_refresh', 'auto_refresh')),
                expires_at TIMESTAMP,
                refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        """)
        
        # App settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("✅ Database initialized successfully")


# ──────────────────────────────────────────────────────
# ACCOUNT MANAGEMENT
# ──────────────────────────────────────────────────────

def create_account(account_data: Dict) -> int:
    """Create a new account and return its ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO accounts (
                name, type, ig_user_id, access_token, token_expires_at,
                page_id, page_name, instagram_username, profile_picture_url,
                caption_url, base_url, video_base_url, slides_per_post, 
                max_images, state_prefix, schedule_enabled, schedule_times
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_data.get('name'),
            account_data.get('type'),
            account_data.get('ig_user_id'),
            account_data.get('access_token'),
            account_data.get('token_expires_at'),
            account_data.get('page_id'),
            account_data.get('page_name'),
            account_data.get('instagram_username'),
            account_data.get('profile_picture_url'),
            account_data.get('caption_url'),
            account_data.get('base_url'),
            account_data.get('video_base_url'),
            account_data.get('slides_per_post', 1),
            account_data.get('max_images', 10000),
            account_data.get('state_prefix'),
            account_data.get('schedule_enabled', 0),
            account_data.get('schedule_times'),
        ))
        return cursor.lastrowid


def update_account(account_id: int, updates: Dict) -> bool:
    """Update account fields."""
    if not updates:
        return False
    
    # Build dynamic UPDATE query
    allowed_fields = [
        'name', 'type', 'caption_url', 'base_url', 'video_base_url',
        'slides_per_post', 'max_images', 'schedule_enabled', 'schedule_times', 'status'
    ]
    
    set_clauses = []
    values = []
    for field, value in updates.items():
        if field in allowed_fields:
            set_clauses.append(f"{field} = ?")
            values.append(value)
    
    if not set_clauses:
        return False
    
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    values.append(account_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = f"UPDATE accounts SET {', '.join(set_clauses)} WHERE id = ?"
        cursor.execute(query, values)
        return cursor.rowcount > 0


def get_account(account_id: int) -> Optional[Dict]:
    """Get account by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_account_by_ig_id(ig_user_id: str) -> Optional[Dict]:
    """Get account by Instagram User ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE ig_user_id = ?", (ig_user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_account_by_state_prefix(state_prefix: str) -> Optional[Dict]:
    """Get account by state prefix."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE state_prefix = ?", (state_prefix,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_accounts() -> List[Dict]:
    """Get all accounts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def delete_account(account_id: int) -> bool:
    """Delete an account."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return cursor.rowcount > 0


# ──────────────────────────────────────────────────────
# TOKEN MANAGEMENT
# ──────────────────────────────────────────────────────

def update_access_token(account_id: int, new_token: str, expires_at: datetime, refresh_type: str = 'manual_refresh') -> bool:
    """Update account access token and log the change."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get old token first
        cursor.execute("SELECT access_token FROM accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        old_token = row['access_token'] if row else None
        
        # Update token
        cursor.execute("""
            UPDATE accounts 
            SET access_token = ?, token_expires_at = ?, last_token_refresh = CURRENT_TIMESTAMP, status = 'active'
            WHERE id = ?
        """, (new_token, expires_at, account_id))
        
        # Log token change
        cursor.execute("""
            INSERT INTO token_history (account_id, old_token, new_token, refresh_type, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (account_id, old_token, new_token, refresh_type, expires_at))
        
        return cursor.rowcount > 0


def get_token_status(account_id: int) -> Dict:
    """Get token expiration status for an account."""
    account = get_account(account_id)
    if not account or not account.get('token_expires_at'):
        return {'status': 'unknown', 'days_remaining': None}
    
    expires_at = datetime.fromisoformat(account['token_expires_at'])
    now = datetime.utcnow()
    days_remaining = (expires_at - now).days
    
    if days_remaining < 0:
        status = 'expired'
    elif days_remaining <= 7:
        status = 'expiring_soon'
    else:
        status = 'valid'
    
    return {
        'status': status,
        'days_remaining': days_remaining,
        'expires_at': expires_at.isoformat()
    }


def get_expiring_accounts(days_threshold: int = 7) -> List[Dict]:
    """Get accounts with tokens expiring within specified days."""
    threshold_date = datetime.utcnow() + timedelta(days=days_threshold)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM accounts 
            WHERE token_expires_at IS NOT NULL 
            AND token_expires_at <= ?
            AND status = 'active'
            ORDER BY token_expires_at ASC
        """, (threshold_date,))
        return [dict(row) for row in cursor.fetchall()]


# ──────────────────────────────────────────────────────
# ACTIVITY LOGGING
# ──────────────────────────────────────────────────────

def log_activity(account_id: Optional[int], action_type: str, status: str, message: str, details: Optional[Dict] = None):
    """Log an activity."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO activity_logs (account_id, action_type, status, message, details)
            VALUES (?, ?, ?, ?, ?)
        """, (account_id, action_type, status, message, json.dumps(details) if details else None))


def get_recent_activity(account_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
    """Get recent activity logs."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if account_id:
            cursor.execute("""
                SELECT * FROM activity_logs 
                WHERE account_id = ?
                ORDER BY created_at DESC 
                LIMIT ?
            """, (account_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM activity_logs 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
        
        return [dict(row) for row in cursor.fetchall()]


# ──────────────────────────────────────────────────────
# APP SETTINGS
# ──────────────────────────────────────────────────────

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get app setting by key."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default


def set_setting(key: str, value: str):
    """Set app setting."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        """, (key, value, value))


# Initialize database on import if it doesn't exist
if not os.path.exists(DATABASE_PATH):
    print("📦 Creating database for first time...")
    init_database()
