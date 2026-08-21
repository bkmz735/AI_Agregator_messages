import aiosqlite
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from config import config

logger = logging.getLogger(__name__)

class Storage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH

    async def init_db(self):
        """Initializes SQLite schema."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg_uid TEXT UNIQUE,
                    channel TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    action_required INTEGER NOT NULL,
                    suggested_reply TEXT,
                    is_delivered INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sent_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    delete_at TIMESTAMP NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            await db.commit()
            logger.info("Database schema initialized.")

    async def is_duplicate(self, msg_uid: str) -> bool:
        """Checks if message UID has already been processed."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM messages WHERE msg_uid = ?", (msg_uid,)) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def save_message(
        self,
        msg_uid: str,
        channel: str,
        sender: str,
        text: str,
        category: str,
        summary: str,
        action_required: bool,
        suggested_reply: Optional[str] = None,
        is_delivered: bool = False
    ) -> int:
        """Saves message and analysis result to SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT OR IGNORE INTO messages 
                (msg_uid, channel, sender, text, category, summary, action_required, suggested_reply, is_delivered)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg_uid, channel, sender, text, category, summary,
                1 if action_required else 0, suggested_reply, 1 if is_delivered else 0
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_buffered_messages(self, mark_as_delivered: bool = True) -> List[Dict[str, Any]]:
        """Fetches all non-spam undelivered messages from buffer."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM messages WHERE is_delivered = 0 AND category != 'spam' ORDER BY id ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                messages = [dict(row) for row in rows]

            if mark_as_delivered and messages:
                ids = [m['id'] for m in messages]
                placeholders = ','.join('?' * len(ids))
                await db.execute(f"UPDATE messages SET is_delivered = 1 WHERE id IN ({placeholders})", ids)
                await db.commit()
                
            return messages

    async def get_buffer_count(self) -> int:
        """Returns the number of non-spam pending messages in buffer."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM messages WHERE is_delivered = 0 AND category != 'spam'") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_stats(self) -> Dict[str, int]:
        """Returns message counts grouped by category."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT category, COUNT(*) FROM messages GROUP BY category") as cursor:
                rows = await cursor.fetchall()
                stats = {"spam": 0, "urgent": 0, "important": 0, "general": 0}
                for category, count in rows:
                    if category in stats:
                        stats[category] = count
                return stats

    async def reset_stats(self):
        """Clears all historical delivered and spam message records to reset statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE is_delivered = 1 OR category = 'spam'")
            await db.commit()
            logger.info("Message statistics reset successfully.")

    async def save_sent_notification(self, chat_id: int, message_id: int, delay_seconds: int):
        """Saves sent message ID and calculates deletion time."""
        import datetime
        delete_at = (datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sent_notifications (chat_id, message_id, delete_at) VALUES (?, ?, ?)",
                (chat_id, message_id, delete_at)
            )
            await db.commit()

    async def get_expired_notifications(self) -> List[Dict[str, Any]]:
        """Gets all notifications that should be deleted."""
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sent_notifications WHERE delete_at <= ?", (now_str,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def delete_sent_notification(self, notification_id: int):
        """Deletes a notification record from DB."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sent_notifications WHERE id = ?", (notification_id,))
            await db.commit()

    async def get_setting(self, key: str, default: str) -> str:
        """Fetches a setting value from SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        """Saves a setting value in SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            await db.commit()
