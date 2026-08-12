import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler
)

from config import BOT_TOKEN, ADMIN_IDS
from db import db
from inventory import init_account_manager, account_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

(ADMIN_ADD_PHONE, ADMIN_ADD_CODE, ADMIN_ADD_COUNTRY, ADMIN_ADD_PRICE) = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username or '', user.first_name or '', user.last_name or '')
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Каталог", callback_data='catalog')],
        [InlineKeyboardButton("📦 Мои покупки", callback_data='my_purchases')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_panel')])
    
    await update.message.reply_text("🎯 <b>Магазин Telegram Аккаунтов</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        return
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='add_account_request_phone')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]
    ]
    await query.edit_message_text("⚙️ <b>Панель администратора</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def add_account_request_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 <b>Шаг 1: Введите номер телефона (+7XXXXXXXXXX):</b>", parse_mode='HTML')
    return ADMIN_ADD_PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith('+') or len(phone) < 10:
        await update.message.reply_text("❌ Введите корректный номер с плюсом:")
        return ADMIN_ADD_PHONE
    
    context.user_data['add_phone'] = phone
    context.user_data['add_admin_id'] = update.message.from_user.id
    temp_id = abs(hash(phone)) % 1000000
    
    success, msg = await account_manager.request_code(temp_id, phone)
    if success:
        context.user_data['temp_account_id'] = temp_id
        await update.message.reply_text("📝 <b>Шаг 2: Введите 5-значный SMS-код:</b>", parse_mode='HTML')
        return ADMIN_ADD_CODE
    else:
        await update.message.reply_text(f"❌ {msg}")
        return ConversationHandler.END

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    phone = context.user_data['add_phone']
    
    success, msg = await account_manager.verify_code(phone, code)
    if success:
        await update.message.reply_text("🌍 <b>Шаг 3: Укажите страну (RU, US, EU):</b>", parse_mode='HTML')
        return ADMIN_ADD_COUNTRY
    else:
        await update.message.reply_text(f"❌ {msg}")
        return ConversationHandler.END

async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_country'] = update.message.text.strip().upper()
    await update.message.reply_text("💰 <b>Шаг 4: Укажите цену в USD ($):</b>", parse_mode='HTML')
    return ADMIN_ADD_PRICE

async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Ошибка. Введите число:")
        return ADMIN_ADD_PRICE
    
    phone = context.user_data['add_phone']
    country = context.user_data['add_country']
    admin_id = context.user_data['add_admin_id']
    temp_id = context.user_data['temp_account_id']
    
    success, real_id = db.add_account(phone, country, price, admin_id)
    if success and temp_id in account_manager.clients:
        account_manager.clients[real_id] = account_manager.clients.pop(temp_id)
        await update.message.reply_text(f"✅ Аккаунт добавлен и слушает SMS! ID: {real_id}")
    else:
        await update.message.reply_text("❌ Ошибка сохранения в базе.")
        
    context.user_data.clear()
    return ConversationHandler.END

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    accounts = db.get_available_accounts()
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back_to_main')]]
        await query.edit_message_text("📭 В данный момент нет доступных аккаунтов", reply_markup=InlineKeyboardMarkup(keyboard))
        return
        
    text = "📋 <b>Доступные аккаунты:</b>\n\n"
    keyboard = []
    for acc in accounts[:10]:
        text += f"📱 {acc['phone_number']} | {acc['country']} | ${acc['price']}\n"
        keyboard.append([InlineKeyboardButton(f"Купить ${acc['price']}", callback_data=f"buy_{acc['id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def buy_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    account_id = int(query.data.split('_')[1])
    
    acc = db.get_account_by_id(account_id)
    if not acc or acc['status'] != 'available':
        await query.edit_message_text("❌ Извините, данный аккаунт уже продан.")
        return

    db.mark_sold(account_id, query.from_user.id)
    db.log_transaction(query.from_user.id, account_id, acc['price'])
    
    text = (
        f"🎉 <b>Покупка успешна!</b>\n\n"
        f"📱 Номер: <code>{acc['phone_number']}</code>\n\n"
        f"Нажмите кнопку ниже, чтобы запросить перехваченный SMS-код."
    )
    keyboard = [
        [InlineKeyboardButton("📬 Получить SMS код", callback_data=f"get_code_{account_id}")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_to_main')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    account_id = int(query.data.split('_')[2])
    
    acc = db.get_account_by_id(account_id)
    code_data = account_manager.get_code(account_id)
    
    if code_data and code_data.get('code'):
        code = code_data['code']
        text = (
            f"✅ <b>Ваш SMS-код найден!</b>\n\n"
            f"🔑 Код: <code>{code}</code>\n"
            f"📱 Номер: <code>{acc['phone_number']}</code>\n\n"
            f"Введите этот код в Telegram при авторизации."
        )
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data='back_to_main')]]
    else:
        text = (
            f"⏳ <b>Ожидание входящего SMS-кода...</b>\n\n"
            f"1. Введите номер <code>{acc['phone_number']}</code> в клиент Telegram\n"
            f"2. Нажмите кнопку «Обновить» ниже после отправки SMS"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data=f"get_code_{account_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_to_main')]
        ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def main():
    db.init_db()
    await init_account_manager(db)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    add_account_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_account_request_phone, pattern='add_account_request_phone')],
        states={
            ADMIN_ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            ADMIN_ADD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            ADMIN_ADD_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country)],
            ADMIN_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
        },
        fallbacks=[],
    )
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(add_account_conv)
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='admin_panel'))
    app.add_handler(CallbackQueryHandler(catalog, pattern='catalog'))
    app.add_handler(CallbackQueryHandler(buy_account, pattern='buy_'))
    app.add_handler(CallbackQueryHandler(get_code, pattern='get_code_'))
    app.add_handler(CallbackQueryHandler(start, pattern='back_to_main'))
    
    logger.info("🚀 Бот запущен!")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
