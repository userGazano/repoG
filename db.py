import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, List, Tuple
from config import DATABASE_URL, ADMIN_IDS

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    def get_connection(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def init_db(self):
        if not self.db_url:
            logger.warning("⚠️ DATABASE_URL не задан!")
            return

        queries = [
            '''
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(32) UNIQUE NOT NULL,
                country VARCHAR(10) NOT NULL,
                price NUMERIC(10, 2) NOT NULL,
                status VARCHAR(20) DEFAULT 'available',
                user_first_name VARCHAR(128),
                user_username VARCHAR(128),
                is_listening INT DEFAULT 0,
                added_by BIGINT DEFAULT 0,
                added_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sold_to BIGINT,
                sold_timestamp TIMESTAMP
            );
            ''',
            '''
            CREATE TABLE IF NOT EXISTS code_captures (
                id SERIAL PRIMARY KEY,
                account_id INT UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                code VARCHAR(20) NOT NULL,
                from_sender VARCHAR(128),
                sender_id BIGINT,
                message_text TEXT,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '10 minutes')
            );
            ''',
            '''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username VARCHAR(128),
                first_name VARCHAR(128),
                last_name VARCHAR(128),
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin INT DEFAULT 0
            );
            ''',
            '''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                buyer_id BIGINT NOT NULL REFERENCES users(telegram_id),
                account_id INT NOT NULL REFERENCES accounts(id),
                price NUMERIC(10, 2) NOT NULL,
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            '''
        ]
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    for q in queries:
                        cur.execute(q)
            logger.info("✅ База данных Supabase готова")
        except Exception as e:
            logger.error(f"❌ Ошибка БД: {e}")

    def execute(self, query: str, params: tuple = (), fetch: bool = False):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    if fetch:
                        return [dict(row) for row in cur.fetchall()]
                    conn.commit()
            return None
        except Exception as e:
            logger.error(f"Error query: {e}")
            return None

    def add_account(self, phone: str, country: str, price: float, admin_id: int) -> Tuple[bool, int]:
        query = '''
            INSERT INTO accounts (phone_number, country, price, added_by, is_listening)
            VALUES (%s, %s, %s, %s, 1) RETURNING id
        '''
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (phone, country, price, admin_id))
                    account_id = cur.fetchone()['id']
                    conn.commit()
                    return True, account_id
        except Exception as e:
            logger.error(f"Failed to add account: {e}")
            return False, 0

    def update_account_auth(self, account_id: int, phone: str, first_name: str, username: str):
        query = 'UPDATE accounts SET user_first_name = %s, user_username = %s, is_listening = 1 WHERE id = %s'
        self.execute(query, (first_name, username, account_id))

    def get_available_accounts(self, country: Optional[str] = None) -> List[Dict]:
        if country:
            query = 'SELECT * FROM accounts WHERE status = %s AND country = %s ORDER BY id DESC'
            return self.execute(query, ('available', country), fetch=True) or []
        query = 'SELECT * FROM accounts WHERE status = %s ORDER BY id DESC'
        return self.execute(query, ('available',), fetch=True) or []

    def get_account_by_id(self, account_id: int) -> Optional[Dict]:
        query = 'SELECT * FROM accounts WHERE id = %s'
        res = self.execute(query, (account_id,), fetch=True)
        return res[0] if res else None

    def mark_sold(self, account_id: int, user_id: int) -> bool:
        query = "UPDATE accounts SET status = 'sold', sold_to = %s, sold_timestamp = CURRENT_TIMESTAMP WHERE id = %s"
        self.execute(query, (user_id, account_id))
        return True

    def log_code_capture(self, account_id: int, code: str, from_sender: str, sender_id: int, message_text: str):
        query = '''
            INSERT INTO code_captures (account_id, code, from_sender, sender_id, message_text, captured_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
            ON CONFLICT (account_id) DO UPDATE SET 
                code = EXCLUDED.code,
                from_sender = EXCLUDED.from_sender,
                sender_id = EXCLUDED.sender_id,
                message_text = EXCLUDED.message_text,
                captured_at = CURRENT_TIMESTAMP,
                expires_at = CURRENT_TIMESTAMP + INTERVAL '10 minutes'
        '''
        self.execute(query, (account_id, code, from_sender, sender_id, message_text))

    def get_captured_code(self, account_id: int) -> Optional[Dict]:
        query = "SELECT * FROM code_captures WHERE account_id = %s AND expires_at > CURRENT_TIMESTAMP"
        res = self.execute(query, (account_id,), fetch=True)
        return res[0] if res else None

    def log_transaction(self, buyer_id: int, account_id: int, price: float):
        query = 'INSERT INTO transactions (buyer_id, account_id, price) VALUES (%s, %s, %s)'
        self.execute(query, (buyer_id, account_id, price))

    def register_user(self, user_id: int, username: str, first_name: str, last_name: str):
        is_admin = 1 if user_id in ADMIN_IDS else 0
        query = '''
            INSERT INTO users (telegram_id, username, first_name, last_name, is_admin)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (telegram_id) DO NOTHING
        '''
        self.execute(query, (user_id, username, first_name, last_name, is_admin))

    def get_stats(self) -> Dict:
        total = self.execute('SELECT COUNT(*) as cnt FROM accounts', fetch=True)
        sold = self.execute("SELECT COUNT(*) as cnt FROM accounts WHERE status = 'sold'", fetch=True)
        available = self.execute("SELECT COUNT(*) as cnt FROM accounts WHERE status = 'available'", fetch=True)
        revenue = self.execute('SELECT SUM(price) as total FROM transactions', fetch=True)
        
        return {
            'total': total[0]['cnt'] if total else 0,
            'sold': sold[0]['cnt'] if sold else 0,
            'available': available[0]['cnt'] if available else 0,
            'revenue': float(revenue[0]['total']) if revenue and revenue[0]['total'] else 0.0
        }

db = Database()
