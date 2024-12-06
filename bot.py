from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from datetime import datetime, timedelta
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# States for the conversation handler
TITLE, DESCRIPTION, LOCATION, PRICE, SHIPPING, PHOTOS, CONFIRM = range(7)
EDIT_CHOOSE, EDIT_FIELD, EDIT_VALUE = range(7, 10)

# Dictionary to store temporary offer data
temp_offers = {}

def setup_database():
    """Create the SQLite database and tables"""
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Create offers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            price REAL NOT NULL,
            shipping BOOLEAN NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    ''')
    
    # Create photos table
    c.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            FOREIGN KEY (offer_id) REFERENCES offers (id)
        )
    ''')
    
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    await update.message.reply_text(
        "¡Bienvenido al Bot de Ventas! 👋\n\n"
        "Comandos disponibles:\n"
        "/createoffer - Crear una nueva oferta\n"
        "/getalloffers - Ver todas las ofertas activas\n"
        "/editoffer - Editar una oferta existente\n"
        "/renewoffer - Renovar una oferta por una semana más\n"
        "/myoffers - Ver tus ofertas activas"
    )

async def create_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the offer creation process"""
    await update.message.reply_text(
        "¡Entendido! Vamos a crear una nueva oferta de venta.\n"
        "Puedes cancelar en cualquier momento con /cancel\n\n"
        "¿Cuál es el título para el producto que quieres vender? (máx. 64 caracteres)"
    )
    
    user_id = update.effective_user.id
    temp_offers[user_id] = {
        'photos': []
    }
    
    return TITLE

async def save_offer_to_db(user_id: int, offer: dict) -> int:
    """Save the offer to the database and return its ID"""
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    now = datetime.now()
    expires_at = now + timedelta(days=7)
    
    # Insert offer
    c.execute('''
        INSERT INTO offers (user_id, title, description, location, price, shipping, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, offer['title'], offer['description'], offer['location'], 
          float(offer['price']), offer['shipping'], now, expires_at))
    
    offer_id = c.lastrowid
    
    # Insert photos
    for photo_id in offer['photos']:
        c.execute('INSERT INTO photos (offer_id, file_id) VALUES (?, ?)',
                 (offer_id, photo_id))
    
    conn.commit()
    conn.close()
    return offer_id

async def get_all_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all active offers"""
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Get all active offers
    c.execute('''
        SELECT o.*, GROUP_CONCAT(p.file_id) as photo_ids
        FROM offers o
        LEFT JOIN photos p ON o.id = p.offer_id
        WHERE o.expires_at > datetime('now')
        GROUP BY o.id
        ORDER BY o.created_at DESC
    ''')
    
    offers = c.fetchall()
    conn.close()
    
    if not offers:
        await update.message.reply_text("No hay ofertas activas en este momento.")
        return
    
    for offer in offers:
        # Create offer message
        message = (
            f"📦 {offer[2]}\n\n"  # title
            f"📝 {offer[3]}\n\n"  # description
            f"📍 Ubicación: {offer[4]}\n"  # location
            f"💰 Precio: {offer[5]}€\n"  # price
            f"🚚 Envío: {'Incluido' if offer[6] else 'No incluido'}\n"  # shipping
            f"📅 Expira: {offer[8]}\n"  # expires_at
        )
        
        # Send first photo with message
        photo_ids = offer[9].split(',') if offer[9] else []
        if photo_ids:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo_ids[0],
                caption=message
            )
            # Send remaining photos
            for photo_id in photo_ids[1:]:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo_id
                )
        else:
            await update.message.reply_text(message)

async def my_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's active offers"""
    user_id = update.effective_user.id
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT * FROM offers 
        WHERE user_id = ? AND expires_at > datetime('now')
        ORDER BY created_at DESC
    ''', (user_id,))
    
    offers = c.fetchall()
    conn.close()
    
    if not offers:
        await update.message.reply_text("No tienes ofertas activas.")
        return
    
    for offer in offers:
        keyboard = [
            [
                InlineKeyboardButton("Editar", callback_data=f"edit_{offer[0]}"),
                InlineKeyboardButton("Renovar", callback_data=f"renew_{offer[0]}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"📦 {offer[2]}\n\n"
            f"📝 {offer[3]}\n\n"
            f"📍 Ubicación: {offer[4]}\n"
            f"💰 Precio: {offer[5]}€\n"
            f"🚚 Envío: {'Incluido' if offer[6] else 'No incluido'}\n"
            f"📅 Expira: {offer[8]}"
        )
        
        await update.message.reply_text(message, reply_markup=reply_markup)

async def renew_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renew an offer for another week"""
    query = update.callback_query
    offer_id = int(query.data.split('_')[1])
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Update expiration date
    c.execute('''
        UPDATE offers 
        SET expires_at = datetime('now', '+7 days')
        WHERE id = ? AND user_id = ?
    ''', (offer_id, update.effective_user.id))
    
    conn.commit()
    conn.close()
    
    await query.answer("¡Oferta renovada por una semana más!")
    await query.edit_message_reply_markup(reply_markup=None)

async def edit_offer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the offer editing process"""
    query = update.callback_query
    offer_id = int(query.data.split('_')[1])
    
    keyboard = [
        ['Título', 'Descripción'],
        ['Ubicación', 'Precio'],
        ['Envío', 'Cancelar']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    context.user_data['editing_offer_id'] = offer_id
    await query.message.reply_text(
        "¿Qué campo quieres editar?",
        reply_markup=reply_markup
    )
    return EDIT_FIELD

async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle field selection for editing"""
    field = update.message.text.lower()
    context.user_data['editing_field'] = field
    
    await update.message.reply_text(
        f"Por favor, introduce el nuevo valor para {field}:",
        reply_markup=ReplyKeyboardRemove()
    )
    return EDIT_VALUE

async def edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new value for the edited field"""
    new_value = update.message.text
    field = context.user_data['editing_field']
    offer_id = context.user_data['editing_offer_id']
    
    conn = sqlite3.connect('marketplace.db')
    c = conn.cursor()
    
    # Map field names to database columns
    field_mapping = {
        'título': 'title',
        'descripción': 'description',
        'ubicación': 'location',
        'precio': 'price',
        'envío': 'shipping'
    }
    
    db_field = field_mapping[field]
    
    # Handle special cases
    if field == 'precio':
        try:
            new_value = float(new_value)
        except ValueError:
            await update.message.reply_text("Por favor, introduce un precio válido.")
            return EDIT_VALUE
    elif field == 'envío':
        new_value = new_value.upper() == 'SÍ'
    
    # Update the field
    c.execute(f'''
        UPDATE offers 
        SET {db_field} = ?
        WHERE id = ? AND user_id = ?
    ''', (new_value, offer_id, update.effective_user.id))
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"¡Campo {field} actualizado correctamente!"
    )
    return ConversationHandler.END

def main():
    """Main function to run the bot"""
    # Setup database
    setup_database()
    
    # Initialize bot with token from environment variable
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # Create conversation handler for offer creation
    create_offer_handler = ConversationHandler(
        entry_points=[CommandHandler('createoffer', create_offer)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, title)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, location)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price)],
            SHIPPING: [MessageHandler(filters.TEXT & ~filters.COMMAND, shipping)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.Regex('^LISTO$'), photos_done)
            ],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_offer)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Create conversation handler for offer editing
    edit_offer_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_offer_start, pattern='^edit_')],
        states={
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field)],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Add handlers
    application.add_handler(create_offer_handler)
    application.add_handler(edit_offer_handler)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('getalloffers', get_all_offers))
    application.add_handler(CommandHandler('myoffers', my_offers))
    application.add_handler(CallbackQueryHandler(renew_offer, pattern='^renew_'))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
