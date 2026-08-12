import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

# Убедитесь, что имена переменных здесь совпадают с вашими в config.py
from config import TELEGRAM_API_ID as API_ID, TELEGRAM_API_HASH as API_HASH

logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self, db_instance):
        self.db = db_instance
        self.clients = {}

    def _save_session_to_db(self, account_id: int, session_str: str):
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO telegram_sessions (account_id, session_data) 
                        VALUES (%s, %s) 
                        ON CONFLICT (account_id) 
                        DO UPDATE SET session_data = %s;
                    """, (account_id, session_str, session_str))
                    conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии в БД для #{account_id}: {e}")

    def _get_session_from_db(self, account_id: int):
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT session_data FROM telegram_sessions WHERE account_id = %s;", (account_id,))
                    res = cur.fetchone()
                    return res[0] if res else None
        except Exception as e:
            logger.error(f"Ошибка получения сессии из БД для #{account_id}: {e}")
            return None

    async def init_existing_accounts(self):
        accounts = self.db.get_all_accounts()
        for acc in accounts:
            acc_id = acc['id']
            phone = acc['phone_number']
            session_str = self._get_session_from_db(acc_id)
            if session_str:
                try:
                    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                    await client.connect()
                    if await client.is_user_authorized():
                        self.clients[acc_id] = client
                        self._register_handlers(client, acc_id)
                        me = await client.get_me()
                        self.db.update_account_auth(acc_id, first_name=me.first_name, username=me.username)
                        logger.info(f"✅ Сессия аккаунта #{acc_id} ({phone}) успешно загружена из БД.")
                    else:
                        await client.disconnect()
                        logger.warning(f"⚠️ Сессия аккаунта #{acc_id} ({phone}) не авторизована.")
                except Exception as e:
                    logger.error(f"❌ Ошибка инициализации сессии #{acc_id}: {e}")

    def _register_handlers(self, client: TelegramClient, account_id: int):
        from telethon import events
        import re

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            text = event.message.message
            logger.info(f"📩 [Аккаунт #{account_id}] Новое сообщение: {text}")

            match = re.search(r'\b(\d{5,6})\b', text)
            if match:
                code = match.group(1)
                try:
                    with self.db.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO captured_codes (account_id, code, sender_name, sender_id, raw_message)
                                VALUES (%s, %s, %s, %s, %s);
                            """, (account_id, code, 'Telegram', 777000, text))
                            conn.commit()
                    logger.info(f"📥 УСПЕШНО СХВАЧЕН КОД для аккаунта #{account_id}: {code}")
                except Exception as e:
                    logger.error(f"Ошибка сохранения кода в БД: {e}")

    async def request_code(self, account_id: int, phone: str):
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            self.clients[account_id] = client
            return True, result.phone_code_hash
        except Exception as e:
            logger.error(f"Ошибка запроса кода для {phone}: {e}")
            return False, str(e)

    async def verify_code(self, phone: str, code: str):
        for acc_id, client in list(self.clients.items()):
            try:
                await client.sign_in(phone=phone, code=code)
                
                # Сохраняем готовую строку сессии в Supabase навсегда
                self._save_session_to_db(acc_id, client.session.save())
                
                self._register_handlers(client, acc_id)
                me = await client.get_me()
                self.db.update_account_auth(acc_id, first_name=me.first_name, username=me.username)
                
                logger.info(f"✅ Аккаунт #{acc_id} ({phone}) успешно авторизован!")
                return True, "Успешно авторизован"
            except Exception as e:
                logger.error(f"Ошибка проверки кода для {phone}: {e}")
                return False, str(e)
        return False, "Клиент не найден"

    def get_code(self, account_id: int):
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT code FROM captured_codes 
                        WHERE account_id = %s 
                        ORDER BY created_at DESC LIMIT 1;
                    """, (account_id,))
                    res = cur.fetchone()
                    return {'code': res[0]} if res else None
        except Exception as e:
            logger.error(f"Ошибка получения кода из БД: {e}")
            return None

account_manager = None

async def init_account_manager(db_instance):
    global account_manager
    account_manager = AccountManager(db_instance)
    await account_manager.init_existing_accounts()
