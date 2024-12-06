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

async def title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the product title"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if len(text) > 64:
        await update.message.reply_text("El título es demasiado largo. Por favor, intenta con uno más corto (máx. 64 caracteres)")
        return TITLE
    
    temp_offers[user_id]['title'] = text
    
    await update.message.reply_text(
        "¿Cuál es la descripción del producto que quieres vender? (máx. 512 caracteres)"
    )
    return DESCRIPTION

async def description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the product description"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if len(text) > 512:
        await update.message.reply_text("La descripción es demasiado larga. Por favor, intenta con una más corta (máx. 512 caracteres)")
        return DESCRIPTION
    
    temp_offers[user_id]['description'] = text
    
    await update.message.reply_text(
        "¿Dónde está el producto, para un posible trato en mano?"
    )
    return LOCATION

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the product location"""
    user_id = update.effective_user.id
    temp_offers[user_id]['location'] = update.message.text
    
    await update.message.reply_text(
        "¿Cuál es el precio del producto que quieres vender? (máx. 2 decimales)"
    )
    return PRICE

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the product price"""
    user_id = update.effective_user.id
    text = update.message.text
    
    try:
        price = float(text)
        if price < 0:
            raise ValueError
        temp_offers[user_id]['price'] = "{:.2f}".format(price)
        
        keyboard = [['SÍ', 'NO']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text(
            "¿Está el envío incluído?",
            reply_markup=reply_markup
        )
        return SHIPPING
    except ValueError:
        await update.message.reply_text("Por favor, introduce un precio válido (ejemplo: 99.99)")
        return PRICE

async def shipping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shipping information"""
    user_id = update.effective_user.id
    text = update.message.text.upper()
    
    if text not in ['SÍ', 'NO']:
        keyboard = [['SÍ', 'NO']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        await update.message.reply_text(
            "Por favor, selecciona SÍ o NO",
            reply_markup=reply_markup
        )
        return SHIPPING
    
    temp_offers[user_id]['shipping'] = text == 'SÍ'
    
    await update.message.reply_text(
        "Ya casi estamos. Envía algunas fotos del producto para finalizar.\n"
        "Cuando hayas terminado, escribe 'LISTO'",
        reply_markup=ReplyKeyboardRemove()
    )
    return PHOTOS

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos"""
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    
    if user_id not in temp_offers:
        temp_offers[user_id] = {'photos': []}
    
    # Store photo file_id
    temp_offers[user_id]['photos'].append(photo_file.file_id)
    
    await update.message.reply_text(f"Foto recibida ({len(temp_offers[user_id]['photos'])}). "
                                  "Envía más fotos o escribe 'LISTO' para continuar.")
    return PHOTOS

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle completion of photo uploads"""
    user_id = update.effective_user.id
    
    if user_id not in temp_offers:
        await update.message.reply_text("Ha ocurrido un error. Por favor, empieza de nuevo con /createoffer")
        return ConversationHandler.END
        
    if not temp_offers[user_id].get('photos'):
        await update.message.reply_text("Por favor, envía al menos una foto del producto.")
        return PHOTOS
    
    offer = temp_offers[user_id]
    preview = (
        f"📦 {offer.get('title', 'Sin título')}\n\n"
        f"📝 {offer.get('description', 'Sin descripción')}\n\n"
        f"📍 Ubicación: {offer.get('location', 'No especificada')}\n"
        f"💰 Precio: {offer.get('price', '0')}€\n"
        f"🚚 Envío: {'Incluido' if offer.get('shipping', False) else 'No incluido'}\n\n"
        "¿Quieres publicar esta oferta? (SÍ/NO)"
    )
    
    keyboard = [['SÍ', 'NO']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text(preview, reply_markup=reply_markup)
    
    # Send preview photos
    for photo_id in offer['photos']:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_id)
    
    return CONFIRM

async def confirm_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle final confirmation and publication of the offer"""
    user_id = update.effective_user.id
    text = update.message.text.upper()
    
    if text == 'SÍ':
        if user_id in temp_offers:
            # Save to database
            conn = sqlite3.connect('marketplace.db')
            c = conn.cursor()
            
            now = datetime.now()
            expires_at = now + timedelta(days=7)
            
            offer = temp_offers[user_id]
            
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
            
            await update.message.reply_text(
                "¡Oferta publicada con éxito! 🎉\n"
                "Puedes ver todas tus ofertas con /myoffers",
                reply_markup=ReplyKeyboardRemove()
            )
            
            del temp_offers[user_id]
        else:
            await update.message.reply_text(
                "Ha ocurrido un error. Por favor, intenta crear la oferta de nuevo.",
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        await update.message.reply_text(
            "Oferta cancelada. Puedes crear una nueva oferta cuando quieras con /createoffer",
            reply_markup=ReplyKeyboardRemove()
        )
        
        if user_id in temp_offers:
            del temp_offers[user_id]
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation"""
    user_id = update.effective_user.id
    if user_id in temp_offers:
        del temp_offers[user_id]
    
    await update.message.reply_text(
        "Operación cancelada. Puedes empezar de nuevo cuando quieras.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    """Main function to run the bot"""
    # Setup database
    setup_database()
    
    # Initialize bot
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # Add conversation handler
    conv_handler = ConversationHandler(
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
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', start))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
