import asyncio
import os
import logging
from io import BytesIO
from PIL import Image
from rembg import remove

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramNotFound, TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -------------------------
# Environment Variables & Global State
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_USER_ID", 0)) 
PACK_PREFIX = os.environ.get("STICKER_PACK_PREFIX", "funstickers")

# Global variables to cache bot info and pack name after initialization
BOT_USERNAME = None
PACK_NAME = None

bot = Bot(token=TOKEN)
dp = Dispatcher()

# -------------------------
# FSM States
# -------------------------
class StickerCreation(StatesGroup):
    """States for the multi-step sticker creation process."""
    waiting_for_mode_selection = State()

# -------------------------
# Helper Functions
# -------------------------

def resize_to_sticker(photo_bytes: bytes, mode: str) -> BytesIO:
    """
    Removes background using 'rembg', then resizes the image based on the chosen mode.
    
    Modes:
    - 'fit': Resizes to max 512x512 while preserving aspect ratio (no distortion).
    - 'square': Crops the image to a central square before resizing to 512x512.
    """
    TARGET_SIZE = 512
    try:
        # --- Background Removal Step ---
        output_png_bytes = remove(photo_bytes) 
        
        # Open the processed PNG image using PIL
        img = Image.open(BytesIO(output_png_bytes))
        
        # Ensure it has an alpha channel (RGBA) for transparency
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        if mode == 'square':
            # --- Crop to Square (Zoom/Composition Adjustment) ---
            width, height = img.size
            if width > height:
                # Landscape or wide image: crop horizontally
                left = (width - height) // 2
                right = (width + height) // 2
                top = 0
                bottom = height
                img = img.crop((left, top, right, bottom))
            elif height > width:
                # Portrait or tall image: crop vertically
                left = 0
                right = width
                top = (height - width) // 2
                bottom = (height + width) // 2
                img = img.crop((left, top, right, bottom))
            # Now the image is square, so we can just resize to 512x512
            img = img.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)
            
        elif mode == 'fit':
            # --- Fit (Preserve Aspect Ratio) ---
            # This maintains aspect ratio and prevents distortion, ensuring max size is 512x512
            img.thumbnail((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)
        
        # Save the final resized PNG file into a BytesIO object
        output = BytesIO()
        img.save(output, format="PNG")
        output.name = "sticker.png"
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"Image processing (rembg/resize) failed: {e}")
        raise ValueError(f"Image processing failed: {e}")

async def init_bot_info():
    """Retrieve bot username and calculate the sticker pack name once."""
    global BOT_USERNAME, PACK_NAME
    info = await bot.get_me()
    BOT_USERNAME = info.username.lower()
    PACK_NAME = f"{PACK_PREFIX}_by_{BOT_USERNAME}"
    logger.info(f"Bot initialized. Sticker Pack Name: {PACK_NAME}")

async def pack_exists(pack_name: str) -> bool:
    """Check if the sticker pack exists, catching the specific 'not found' exception."""
    try:
        await bot.get_sticker_set(pack_name)
        return True
    except TelegramNotFound:
        return False
    except Exception as e:
        logger.error(f"Error checking pack existence for {pack_name}: {e}")
        return False

async def create_pack(pack_name: str, png_file: BytesIO):
    """Attempt to create the sticker pack."""
    try:
        await bot.create_new_sticker_set(
            user_id=OWNER_ID,
            name=pack_name,
            title="Shared Sticker Pack (by Bot)",
            png_sticker=png_file,
            emojis="⭐",
        )
        logger.info(f"Sticker pack '{pack_name}' created successfully.")
    except Exception as e:
        logger.error(f"Failed to create sticker pack: {e}")
        raise

async def add_to_pack(pack_name: str, png_file: BytesIO):
    """Attempt to add a sticker to the existing pack."""
    try:
        await bot.add_sticker_to_set(
            user_id=OWNER_ID,
            name=pack_name,
            png_sticker=png_file,
            emojis="⭐"
        )
        logger.info(f"Sticker added to pack '{pack_name}'.")
    except Exception as e:
        logger.error(f"Failed to add sticker to pack: {e}")
        raise

# -------------------------
# Handlers
# -------------------------

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    pack_link = f"https://t.me/addstickers/{PACK_NAME}"
    await message.answer(
        "👋 Welcome! Send me a photo (JPG, PNG) and I will prepare it for our shared sticker pack.\n\n"
        "I will automatically remove the background and then ask you how you want the sticker scaled!\n"
        f"➡️ **Shared Sticker Pack Link:** {pack_link}"
    )

@dp.message(F.photo)
async def handle_photo_start(message: types.Message, state: FSMContext):
    """Step 1: Receive photo, download, and ask for scaling mode."""
    # Acknowledge receipt
    wait_message = await message.answer("Photo received. Downloading and running background removal...")
    
    try:
        # Take the highest quality photo
        file_id = message.photo[-1].file_id
        
        # Download the file content into a BytesIO object
        file_data = await bot.download(file_id, destination=BytesIO())
        photo_bytes = file_data.read()
        
        # Store file data (as bytes) and the wait message ID in the state
        await state.update_data(
            photo_bytes=photo_bytes,
            wait_message_id=wait_message.message_id
        )
        await state.set_state(StickerCreation.waiting_for_mode_selection)

        # Build inline keyboard for scaling options
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="🖼️ Fit (Keep Aspect Ratio)", callback_data="mode_fit"),
        )
        builder.row(
            types.InlineKeyboardButton(text="⏹️ Square Crop (Better for Pack)", callback_data="mode_square"),
        )
        
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=wait_message.message_id,
            text="✅ Background removed! Please choose the final scaling mode for your sticker (512x512 max):",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Error in handle_photo_start: {e}", exc_info=True)
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=wait_message.message_id,
            text=f"❌ Failed to process photo for scaling. Details: {e}"
        )
        await state.clear()


@dp.callback_query(StickerCreation.waiting_for_mode_selection, F.data.startswith("mode_"))
async def handle_mode_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Step 2: Process scaling mode and finalize sticker creation."""
    await callback_query.answer("Processing your choice...")
    
    data = await state.get_data()
    photo_bytes = data.get('photo_bytes')
    wait_message_id = data.get('wait_message_id')
    mode = callback_query.data.split('_')[1] # 'fit' or 'square'
    
    if not photo_bytes:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=wait_message_id,
            text="❌ Error: Original image data not found. Please resend the photo."
        )
        await state.clear()
        return
        
    try:
        # Re-run processing with the chosen mode
        # We use the raw bytes from the state, preventing a second download.
        sticker_file = resize_to_sticker(photo_bytes, mode)
        pack_link = f"https://t.me/addstickers/{PACK_NAME}"
        
        # Attempt to add sticker
        if not await pack_exists(PACK_NAME):
            await create_pack(PACK_NAME, sticker_file)
            final_text = f"✅ Sticker pack created! Your {mode} sticker has been added.\nAdd it here: {pack_link}"
        else:
            await add_to_pack(PACK_NAME, sticker_file)
            final_text = f"✅ {mode} sticker added to the shared pack!\nSee: {pack_link}"
            
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=wait_message_id,
            text=final_text
        )
        
    except ValueError as e:
        final_text = f"❌ Sticker creation failed during processing. Details: {e}"
    except TelegramBadRequest as e:
        final_text = f"❌ Telegram API Error: Failed to add sticker. (Details: {e})"
    except Exception as e:
        logger.error(f"Unhandled error in handle_mode_selection: {e}", exc_info=True)
        final_text = f"❌ An unexpected error occurred during finalization. Details: {e}"
        
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=wait_message_id,
        text=final_text
    )
    await state.clear() # Clear state after successful completion or error

# Catch messages that are not photos (when state is clear)
@dp.message()
async def handle_other_messages(message: types.Message):
    if not message.text or message.text.startswith('/'):
        return # Ignore system messages or commands
    await message.answer("Please send a photo (JPG or PNG) to start the sticker creation process.")


# -------------------------
# Run bot
# -------------------------

async def main():
    if not TOKEN:
        logger.error("BOT_TOKEN environment variable is not set. Exiting.")
        return
    if not OWNER_ID:
        logger.warning("OWNER_USER_ID is not set. Sticker creation will likely fail.")
        
    try:
        # 1. Initialize Bot Info (Cached operation)
        await init_bot_info()
        logger.info("Bot info retrieved successfully. Starting polling...")
        
        # 2. Start Polling
        # Includes a timeout for resilience against network issues
        await dp.start_polling(bot, timeout=60)
        
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")