import os
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR

logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self, db):
        self.db = db
        self.clients: Dict[int, TelegramClient] = {}
        self.last_codes: Dict[int, Dict] = {}
        self.pending_auth: Dict[str, Dict] = {}
        os.makedirs(SESSIONS_DIR, exist_ok=True)

    async def request_code(self, account_id: int, phone_number: str) -> Tuple[bool, str]:
        try:
            session_name = f"account_{account_id}_{phone_number.replace('+', '').replace(' ', '')}"
            session_path = os.path.join(SESSIONS_DIR, session_name)
            
            client = TelegramClient(session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH)
            await client.connect()
            
            if await client.is_user_authorized():
                self.clients[account_id] = client
                self._start_listening(account_id, client)
                return True, "Аккаунт уже авторизован!"
            
            result = await client.send_code_request(phone_number)
            self.pending_auth[phone_number] = {
                'account_id': account_id,
                'client': client,
                'phone_code_hash': result.phone_code_hash
            }
            return True, f"Код отправлен на {phone_number}."
        except FloodWaitError as e:
            return False, f"Флуд-лимит. Подождите {e.seconds} сек."
        except Exception as e:
            return False, f"Ошибка: {str(e)}"

    async def verify_code(self, phone_number: str, code: str) -> Tuple[bool, str]:
        if phone_number not in self.pending_auth:
            return False, "Авторизация не найдена."
        
        try:
            auth_data = self.pending_auth[phone_number]
            client: TelegramClient = auth_data['client']
            phone_code_hash = auth_data['phone_code_hash']
            account_id = auth_data['account_id']
            
            await client.sign_in(phone_number, code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            
            self.clients[account_id] = client
            del self.pending_auth[phone_number]
            
            self._start_listening(account_id, client)
            self.db.update_account_auth(account_id, phone_number, me.first_name or '', me.username or '')
            return True, f"✅ Аккаунт авторизован! Владелец: {me.first_name}"
        except Exception as e:
            return False, f"❌ Ошибка кода: {str(e)}"

    def _start_listening(self, account_id: int, client: TelegramClient):
        # Исправлено: передача параметра account_id через замыкание/lambda вместо args
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            await self._handle_incoming_message(event, account_id)

    async def _handle_incoming_message(self, event, account_id: int):
        try:
            message_text = event.message.message
            if not message_text:
                return
            
            sender = await event.get_sender()
            sender_name = getattr(sender, 'first_name', 'System') or 'System'
            sender_id = getattr(sender, 'id', 0)
            
            code = self._extract_code(message_text)
            if code:
                logger.info(f"🎯 [Аккаунт {account_id}] SMS КОД ПЕРЕХВАТАН: {code}")
                self.last_codes[account_id] = {
                    'code': code,
                    'timestamp': datetime.now(),
                    'expires_at': datetime.now() + timedelta(minutes=10),
                    'from_sender': sender_name
                }
                self.db.log_code_capture(account_id, code, sender_name, sender_id, message_text)
        except Exception as e:
            logger.error(f"Ошибка чтения SMS: {e}")

    def _extract_code(self, text: str) -> Optional[str]:
        patterns = [
            r'(?:код|code|подтверждения|verification)[\s:]*(\d{5})',
            r'(\d{5})\s+(?:is\s+)?your\s+(?:telegram\s+)?code',
            r'^(\d{5})$',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1)
        return None

    def get_code(self, account_id: int) -> Optional[Dict]:
        db_code = self.db.get_captured_code(account_id)
        if db_code:
            return db_code
        
        if account_id in self.last_codes:
            code_data = self.last_codes[account_id]
            if code_data['code'] and code_data['expires_at'] > datetime.now():
                return code_data
        return None

    async def cleanup_all(self):
        for acc_id in list(self.clients.keys()):
            await self.clients[acc_id].disconnect()

account_manager: Optional[AccountManager] = None

async def init_account_manager(db_instance) -> AccountManager:
    global account_manager
    account_manager = AccountManager(db_instance)
    return account_manager
