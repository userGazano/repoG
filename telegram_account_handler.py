import os
import re
import logging
from telethon import TelegramClient, events
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self, db_instance):
        self.db = db_instance
        self.clients = {}
        self.codes = {}
        os.makedirs("sessions", exist_ok=True)

    async def init_existing_accounts(self):
        accounts = self.db.get_all_accounts()
        for acc in accounts:
            acc_id = acc['id']
            phone = acc['phone_number']
            session_path = os.path.join("sessions", f"account_{acc_id}")
            if os.path.exists(session_path + ".session"):
                try:
                    client = TelegramClient(session_path, API_ID, API_HASH)
                    await client.connect()
                    if await client.is_user_authorized():
                        self.clients[acc_id] = client
                        self._register_handlers(client, acc_id)
                        me = await client.get_me()
                        self.db.update_account_auth(acc_id, first_name=me.first_name, username=me.username)
                        logger.info(f"✅ Сессия аккаунта #{acc_id} ({phone}) успешно загружена.")
                    else:
                        await client.disconnect()
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки сессии #{acc_id}: {e}")

    def _register_handlers(self, client: TelegramClient, account_id: int):
        @client.on(events.NewMessage(incoming=True, chats=777000))
        async def handler(event):
            text = event.message.message
            match = re.search(r'\b(\d{5})\b', text)
            if match:
                code = match.group(1)
                self.codes[account_id] = {'code': code, 'message': text}
                try:
                    with self.db.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO captured_codes (account_id, code, sender_name, sender_id, raw_message)
                                VALUES (%s, %s, %s, %s, %s);
                            """, (account_id, code, 'Telegram', 777000, text))
                            conn.commit()
                    logger.info(f"📥 Получен SMS-код для аккаунта #{account_id}: {code}")
                except Exception as e:
                    logger.error(f"Ошибка сохранения кода в БД: {e}")

    async def request_code(self, account_id: int, phone: str):
        try:
            session_path = os.path.join("sessions", f"account_{account_id}")
            client = TelegramClient(session_path, API_ID, API_HASH)
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
                # Ищем сессию по номеру телефона среди подключенных
                await client.sign_in(phone=phone, code=code)
                self._register_handlers(client, acc_id)
                me = await client.get_me()
                self.db.update_account_auth(acc_id, first_name=me.first_name, username=me.username)
                return True, "Успешно авторизован"
            except Exception as e:
                logger.error(f"Ошибка проверки кода для {phone}: {e}")
                return False, str(e)
        return False, "Клиент не найден"

    def get_code(self, account_id: int):
        return self.codes.get(account_id)

account_manager = None

async def init_account_manager(db_instance):
    global account_manager
    account_manager = AccountManager(db_instance)
    await account_manager.init_existing_accounts()
