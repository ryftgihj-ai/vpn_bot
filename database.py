import sqlite3
from datetime import datetime, timedelta

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('vpn_bot.db')
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                subscription_end TEXT,
                is_trial_used INTEGER DEFAULT 0,
                vpn_link TEXT,
                created_at TEXT
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id, username):
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()
    
    def activate_trial(self, user_id):
        end_date = (datetime.now() + timedelta(days=3)).isoformat()
        self.cursor.execute(
            "UPDATE users SET subscription_end = ?, is_trial_used = 1 WHERE user_id = ?",
            (end_date, user_id)
        )
        self.conn.commit()
        return end_date
    
    def activate_subscription(self, user_id, days):
        user = self.get_user(user_id)
        if user and user[2]:
            current_end = datetime.fromisoformat(user[2])
            if current_end > datetime.now():
                new_end = current_end + timedelta(days=days)
            else:
                new_end = datetime.now() + timedelta(days=days)
        else:
            new_end = datetime.now() + timedelta(days=days)
        
        self.cursor.execute(
            "UPDATE users SET subscription_end = ? WHERE user_id = ?",
            (new_end.isoformat(), user_id)
        )
        self.conn.commit()
        return new_end
    
    def check_subscription(self, user_id):
        user = self.get_user(user_id)
        if not user or not user[2]:
            return False, "Нет активной подписки"
        
        end_date = datetime.fromisoformat(user[2])
        if end_date > datetime.now():
            days_left = (end_date - datetime.now()).days
            hours_left = (end_date - datetime.now()).seconds // 3600
            return True, f"Осталось {days_left} д. {hours_left} ч."
        else:
            return False, "Подписка истекла"
    
    def save_vpn_link(self, user_id, link):
        self.cursor.execute(
            "UPDATE users SET vpn_link = ? WHERE user_id = ?",
            (link, user_id)
        )
        self.conn.commit()
    
    def get_stats(self):
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        active = self.cursor.fetchone()[0]
        
        return total, active
