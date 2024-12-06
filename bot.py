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
    
    # Store photo file_id
    temp_offers[user_id]['photos'].append(photo_file.file_id)
    
    await update.message.reply_text(f"Foto recibida ({len(temp_offers[user_id]['photos'])}). "
                                  "Envía más fotos o escribe 'LISTO' para continuar.")
    return PHOTOS

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle completion of photo uploads"""
    user_id = update.effective_user.id
    if user_id not in temp_offers or not temp_offers[user_id].get('photos'):
        await update.message.reply_text("Por favor, envía al menos una foto del producto.")
        return PHOTOS
    
    offer = temp_offers[user_id]
    
    # Preview the offer
    preview = (
        f"📦 {offer['title']}\n\n"
        f"📝 {offer['description']}\n\n"
        f"📍 Ubicación: {offer['location']}\n"
        f"💰 Precio: {offer['price']}€\n"
        f"🚚 Envío: {'Incluido' if offer['shipping'] else 'No incluido'}\n\n"
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
            # Save the offer to database
            offer_id = await save_offer_to_db(user_id, temp_offers[user_id])
            
            # Forward to sales channel if configured
            sales_channel = os.getenv('SALES_CHANNEL_ID')
            if sales_channel:
                offer = temp_offers[user_id]
                message = (
                    f"📦 {offer['title']}\n\n"
                    f"📝 {offer['description']}\n\n"
                    f"📍 Ubicación: {offer['location']}\n"
                    f"💰 Precio: {offer['price']}€\n"
                    f"🚚 Envío: {'Incluido' if offer['shipping'] else 'No incluido'}"
                )
                
                # Send to channel
                for photo_id in offer['photos']:
                    await context.bot.send_photo(
                        chat_id=sales_channel,
                        photo=photo_id,
                        caption=message if photo_id == offer['photos'][0] else None
                    )
            
            await update.message.reply_text(
                "¡Oferta publicada con éxito! 🎉\n"
                "Puedes ver todas tus ofertas con /myoffers",
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Clean up
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
