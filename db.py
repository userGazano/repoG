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
                    # 1. Исправление таблицы users (добавляем UNIQUE на user_id)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            username VARCHAR(255),
                            first_name VARCHAR(255),
                            last_name VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS user_id BIGINT;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(255);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(255);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(255);
                        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_pkey CASCADE;
                        ALTER TABLE users ADD CONSTRAINT users_user_id_unique UNIQUE (user_id);
                    """)
                    
                    # 2. Исправление таблицы accounts (снимаем NOT NULL с product_id)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS accounts (
                            id SERIAL PRIMARY KEY,
                            phone_number VARCHAR(50),
                            country VARCHAR(10),
                            price NUMERIC,
                            status VARCHAR(20) DEFAULT 'available',
                            first_name VARCHAR(255),
                            username VARCHAR(255),
                            added_by BIGINT,
                            buyer_id BIGINT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50);
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS country VARCHAR(10);
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS price NUMERIC DEFAULT 0;
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'available';
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS first_name VARCHAR(255);
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS username VARCHAR(255);
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS added_by BIGINT;
                        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS buyer_id BIGINT;
                        
                        -- Снимаем жесткие ограничения со старых колонок
                        ALTER TABLE accounts ALTER COLUMN product_id DROP NOT NULL;
                    """)
                    
                    # 3. Исправление таблицы captured_codes
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS captured_codes (
                            id SERIAL PRIMARY KEY,
                            account_id INT,
                            code VARCHAR(20),
                            sender_name VARCHAR(255),
                            sender_id BIGINT,
                            raw_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        ALTER TABLE captured_codes ADD COLUMN IF NOT EXISTS account_id INT;
                        ALTER TABLE captured_codes ADD COLUMN IF NOT EXISTS code VARCHAR(20);
                        ALTER TABLE captured_codes ADD COLUMN IF NOT EXISTS sender_name VARCHAR(255);
                        ALTER TABLE captured_codes ADD COLUMN IF NOT EXISTS sender_id BIGINT;
                        ALTER TABLE captured_codes ADD COLUMN IF NOT EXISTS raw_message TEXT;
                    """)
                    
                    # 4. Исправление таблицы transactions
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS transactions (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            account_id INT,
                            amount NUMERIC,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id BIGINT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS account_id INT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS amount NUMERIC DEFAULT 0;
                    """)
                    conn.commit()
            logger.info("✅ База данных и структура колонок успешно обновлены!")
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

    def update_account_auth(self, account_id: int, phone_number: str, first_name: str, username: str):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE accounts 
                        SET first_name = %s, username = %s 
                        WHERE id = %s;
                    """, (first_name, username, account_id))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления данных авторизации: {e}")

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

    def log_code_capture(self, account_id: int, code: str, sender_name: str, sender_id: int, raw_message: str):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO captured_codes (account_id, code, sender_name, sender_id, raw_message)
                        VALUES (%s, %s, %s, %s, %s);
                    """, (account_id, code, sender_name, sender_id, raw_message))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка записи SMS в БД: {e}")

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
