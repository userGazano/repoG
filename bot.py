import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler, PreCheckoutQueryHandler
)

from config import BOT_TOKEN, ADMIN_IDS
from db import db
import telegram_account_handler

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
    
    markup = InlineKeyboardMarkup(keyboard)
    text = "🎯 <b>Магазин Telegram Аккаунтов</b>\n\nВыберите раздел меню:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "❓ <b>Справка и Поддержка</b>\n\n1. Выберите аккаунт в каталоге.\n2. Оплатите покупку с помощью Telegram Stars ⭐.\n3. Перейдите в раздел «Мои покупки» и получите SMS-код авторизации."
    keyboard = [[InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def my_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    purchases = db.get_user_purchases(user_id) if hasattr(db, 'get_user_purchases') else []
    
    if not purchases:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back_to_main')]]
        await query.edit_message_text("📦 У вас пока нет купленных аккаунтов.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
        
    text = "📦 <b>Ваши купленные аккаунты:</b>\n\n"
    keyboard = []
    for acc in purchases:
        text += f"📱 {acc['phone_number']} | Страна: {acc['country']}\n"
        keyboard.append([InlineKeyboardButton(f"🔑 Код {acc['phone_number']}", callback_data=f"get_code_{acc['id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить аккаунт", callback_data='add_account_request_phone')],
        [InlineKeyboardButton("📂 Управление аккаунтами", callback_data='manage_accounts')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')]
    ]
    await query.edit_message_text("⚙️ <b>Панель администратора</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def manage_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    accounts = db.get_all_accounts() if hasattr(db, 'get_all_accounts') else db.get_available_accounts()
    
    if not accounts:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
        await query.edit_message_text("📂 В базе нет аккаунтов.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
        
    text = "📂 <b>Список аккаунтов:</b>\n\n"
    keyboard = []
    for acc in accounts[:10]:
        status_icon = "✅" if acc['status'] == 'available' else "❌"
        text += f"{status_icon} ID: {acc['id']} | {acc['phone_number']} | {acc['price']} ⭐\n"
        keyboard.append([InlineKeyboardButton(f"❌ Удалить {acc['phone_number']}", callback_data=f"delete_acc_{acc['id']}")])
        
    keyboard.append([InlineKeyboardButton("◀️ В админ-панель", callback_data='admin_panel')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acc_id = int(query.data.split('_')[2])
    if hasattr(db, 'delete_account'):
        db.delete_account(acc_id)
    await query.edit_message_text(f"✅ Аккаунт #{acc_id} удален.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data='manage_accounts')]]))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    s = db.get_stats()
    text = (
        f"📊 <b>Статистика магазина:</b>\n\n"
        f"📦 Всего аккаунтов: {s['total']}\n"
        f"✅ Доступно: {s['available']}\n"
        f"💰 Продано: {s['sold']}\n"
        f"⭐ Выручка: {int(s['revenue'])} Stars"
    )
    keyboard = [[InlineKeyboardButton("◀️ В админ-панель", callback_data='admin_panel')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

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
    
    mgr = telegram_account_handler.account_manager
    if not mgr:
        await update.message.reply_text("❌ Менеджер аккаунтов ещё не готов.")
        return ConversationHandler.END

    success, msg = await mgr.request_code(temp_id, phone)
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
    
    mgr = telegram_account_handler.account_manager
    success, msg = await mgr.verify_code(phone, code)
    if success:
        await update.message.reply_text("🌍 <b>Шаг 3: Укажите страну (RU, US, EU):</b>", parse_mode='HTML')
        return ADMIN_ADD_COUNTRY
    else:
        await update.message.reply_text(f"❌ {msg}")
        return ConversationHandler.END

async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['add_country'] = update.message.text.strip().upper()
    await update.message.reply_text("⭐ <b>Шаг 4: Укажите цену в Telegram Stars (целое число):</b>", parse_mode='HTML')
    return ADMIN_ADD_PRICE

async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Ошибка. Введите целое число:")
        return ADMIN_ADD_PRICE
    
    phone = context.user_data['add_phone']
    country = context.user_data['add_country']
    admin_id = context.user_data['add_admin_id']
    temp_id = context.user_data['temp_account_id']
    
    mgr = telegram_account_handler.account_manager
    success, real_id = db.add_account(phone, country, price, admin_id)
    if success and mgr and temp_id in mgr.clients:
        mgr.clients[real_id] = mgr.clients.pop(temp_id)
        await update.message.reply_text(f"✅ Аккаунт добавлен и готов к продаже! ID: {real_id}")
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
        text += f"📱 {acc['phone_number']} | {acc['country']} | ⭐ {int(acc['price'])} Stars\n"
        keyboard.append([InlineKeyboardButton(f"Купить ⭐ {int(acc['price'])} Stars", callback_data=f"buy_{acc['id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data='back_to_main')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

# Оплата через Telegram Stars
async def buy_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    account_id = int(query.data.split('_')[1])
    
    acc = db.get_account_by_id(account_id)
    if not acc or acc['status'] != 'available':
        await query.edit_message_text("❌ Извините, данный аккаунт уже продан.")
        return

    title = f"Покупка аккаунта {acc['phone_number']}"
    description = f"Оплата аккаунта Telegram ({acc['country']})"
    payload = f"buy_account_{account_id}"
    currency = "XTR" # Telegram Stars
    prices = [LabeledPrice("Цена", int(acc['price']))]

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="", # Для Telegram Stars токен должен быть пустым
        currency=currency,
        prices=prices
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    account_id = int(payload.split('_')[2])
    user_id = update.message.from_user.id
    
    acc = db.get_account_by_id(account_id)
    if acc:
        db.mark_sold(account_id, user_id)
        db.log_transaction(user_id, account_id, payment.total_amount)
        
        text = (
            f"🎉 <b>Оплата Telegram Stars прошла успешно!</b>\n\n"
            f"📱 Номер: <code>{acc['phone_number']}</code>\n\n"
            f"Нажмите кнопку ниже, чтобы получить SMS-код."
        )
        keyboard = [
            [InlineKeyboardButton("📬 Получить SMS код", callback_data=f"get_code_{account_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='back_to_main')]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    account_id = int(query.data.split('_')[2])
    
    acc = db.get_account_by_id(account_id)
    mgr = telegram_account_handler.account_manager
    code_data = mgr.get_code(account_id) if mgr else None
    
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

async def post_init(application: Application):
    db.init_db()
    await telegram_account_handler.init_account_manager(db)

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    add_account_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_account_request_phone, pattern='^add_account_request_phone$')],
        states={
            ADMIN_ADD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            ADMIN_ADD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            ADMIN_ADD_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country)],
            ADMIN_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
        },
        fallbacks=[],
        per_message=False
    )
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(add_account_conv)
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    app.add_handler(CallbackQueryHandler(manage_accounts, pattern='^manage_accounts$'))
    app.add_handler(CallbackQueryHandler(delete_account, pattern='^delete_acc_'))
    app.add_handler(CallbackQueryHandler(stats, pattern='^stats$'))
    app.add_handler(CallbackQueryHandler(catalog, pattern='^catalog$'))
    app.add_handler(CallbackQueryHandler(my_purchases, pattern='^my_purchases$'))
    app.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    app.add_handler(CallbackQueryHandler(buy_account, pattern='^buy_'))
    app.add_handler(CallbackQueryHandler(get_code, pattern='^get_code_'))
    app.add_handler(CallbackQueryHandler(start, pattern='^back_to_main$'))
    
    # Обработчики платежей Telegram Stars
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
