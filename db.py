import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_url = DATABASE_URL

    def get_connection(self):
        return psycopg2.connect(self.db_url)

    def init_db(self):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DROP TABLE IF EXISTS captured_codes CASCADE;
                        DROP TABLE IF EXISTS transactions CASCADE;
                        DROP TABLE IF EXISTS accounts CASCADE;
                        DROP TABLE IF EXISTS users CASCADE;

                        CREATE TABLE users (
                            user_id BIGINT PRIMARY KEY,
                            username VARCHAR(255),
                            first_name VARCHAR(255),
                            last_name VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE accounts (
                            id SERIAL PRIMARY KEY,
                            phone_number VARCHAR(50),
                            country VARCHAR(10),
                            price NUMERIC DEFAULT 1,
                            status VARCHAR(20) DEFAULT 'available',
                            first_name VARCHAR(255),
                            username VARCHAR(255),
                            added_by BIGINT,
                            buyer_id BIGINT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE captured_codes (
                            id SERIAL PRIMARY KEY,
                            account_id INT,
                            code VARCHAR(20),
                            sender_name VARCHAR(255),
                            sender_id BIGINT,
                            raw_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE transactions (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            account_id INT,
                            amount NUMERIC DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    conn.commit()
            logger.info("✅ База данных успешно пересоздана и инициализирована!")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")

    def register_user(self, user_id: int, username: str, first_name: str, last_name: str):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (user_id, username, first_name, last_name)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE 
                        SET username = EXCLUDED.username, 
                            first_name = EXCLUDED.first_name, 
                            last_name = EXCLUDED.last_name;
                    """, (user_id, username, first_name, last_name))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя: {e}")

    def add_account(self, phone_number: str, country: str, price: float, added_by: int):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO accounts (phone_number, country, price, added_by)
                        VALUES (%s, %s, %s, %s) RETURNING id;
                    """, (phone_number, country, price, added_by))
                    account_id = cur.fetchone()[0]
                    conn.commit()
                    return True, account_id
        except Exception as e:
            logger.error(f"Ошибка сохранения аккаунта в БД: {e}")
            return False, None

    def get_available_accounts(self):
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM accounts WHERE status = 'available' ORDER BY id DESC;")
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения доступных аккаунтов: {e}")
            return []

    def get_all_accounts(self):
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM accounts ORDER BY id DESC;")
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения всех аккаунтов: {e}")
            return []

    def delete_account(self, account_id: int):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM accounts WHERE id = %s;", (account_id,))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Ошибка удаления аккаунта: {e}")
            return False

    def get_account_by_id(self, account_id: int):
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM accounts WHERE id = %s;", (account_id,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Ошибка получения аккаунта #{account_id}: {e}")
            return None

    def mark_sold(self, account_id: int, buyer_id: int):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE accounts 
                        SET status = 'sold', buyer_id = %s 
                        WHERE id = %s;
                    """, (buyer_id, account_id))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка смены статуса аккаунта: {e}")

    def log_transaction(self, user_id: int, account_id: int, amount: float):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO transactions (user_id, account_id, amount)
                        VALUES (%s, %s, %s);
                    """, (user_id, account_id, amount))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения транзакции: {e}")

    def get_user_purchases(self, user_id: int):
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM accounts WHERE buyer_id = %s ORDER BY id DESC;", (user_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения покупок пользователя: {e}")
            return []

    def get_captured_code(self, account_id: int):
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT code, created_at FROM captured_codes 
                        WHERE account_id = %s 
                        ORDER BY created_at DESC LIMIT 1;
                    """, (account_id,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Ошибка получения кода из БД: {e}")
            return None

    def get_stats(self):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM accounts;")
                    total = cur.fetchone()[0]
                    
                    cur.execute("SELECT COUNT(*) FROM accounts WHERE status = 'available';")
                    available = cur.fetchone()[0]
                    
                    cur.execute("SELECT COUNT(*) FROM accounts WHERE status = 'sold';")
                    sold = cur.fetchone()[0]
                    
                    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions;")
                    revenue = cur.fetchone()[0]
                    
                    return {
                        'total': total,
                        'available': available,
                        'sold': sold,
                        'revenue': revenue
                    }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {'total': 0, 'available': 0, 'sold': 0, 'revenue': 0}

db = Database()
