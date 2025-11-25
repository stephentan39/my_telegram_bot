import asyncio
import os
import logging
from io import BytesIO
from PIL import Image

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

# -------------------------
# Environment Variables
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_USER_ID"))
PACK_PREFIX = os.environ.get("STICKER_PACK_PREFIX", "funstickers")  # default prefix

bot = Bot(token=TOKEN)
dp = Dispatcher()

# -------------------------
# Helpers
# -------------------------
def resize_to_sticker(png_bytes):
    """Resize image to max 512x512 while keeping aspect ratio."""
    try:
        img = Image.open(BytesIO(png_bytes))
        img.thumbnail((512, 512))
        output = BytesIO()
        img.save(output, format="PNG")
        output.name = "sticker.png"
        return output
    except Exception as e:
        raise Exception(f"Image resizing failed: {e}")

async def get_bot_username():
    """Retrieve bot username dynamically and lowercase it."""
    info = await bot.me()
    return info.username.lower()

async def get_pack_name():
    """Generate a valid sticker pack name based on prefix and bot username."""
    username = await get_bot_username()
    return f"{PACK_PREFIX}_by_{username}"

async def pack_exists(pack_name):
    try:
        await bot.get_sticker_set(pack_name)
        return True
    except:
        return False

async def create_pack(pack_name, png_file):
    try:
        await bot.create_new_sticker_set(
            user_id=OWNER_ID,
            name=pack_name,
            title="Shared Sticker Pack",
            png_sticker=png_file,
            emojis="⭐"
        )
    except Exception as e:
        raise Exception(f"Failed to create sticker pack: {e}")

async def add_to_pack(pack_name, png_file):
    try:
        await bot.add_sticker_to_set(
            user_id=OWNER_ID,
            name=pack_name,
            png_sticker=png_file,
            emojis="⭐"
        )
    except Exception as e:
        raise Exception(f"Failed to add sticker to pack: {e}")

async def get_bot_me_with_retry(max_attempts=5):
    """Retry getting bot info with exponential backoff to handle network issues."""
    delay = 5
    for attempt in range(max_attempts):
        try:
            return await bot.me()
        except Exception as e:
            logging.warning(f"Attempt {attempt+1} to get bot info failed: {e}")
            await asyncio.sleep(delay)
            delay *= 2
    raise Exception("Unable to connect to Telegram API after multiple attempts")

# -------------------------
# Handlers
# -------------------------
@dp.message(CommandStart())
async def start(message: types.Message):
    pack_name = await get_pack_name()
    await message.answer(
        "Hi! Send me a photo and I will prepare it for a sticker.\n\n"
        "You can then select objects to keep using Telegram's sticker editor.\n"
        f"Sticker pack link: https://t.me/addstickers/{pack_name}"
    )

@dp.message()
async def handle_photo(message: types.Message):
    if not message.photo:
        return await message.answer("Please send a photo.")

    await message.answer("Processing your photo...")

    try:
        # Take the highest quality photo
        file_id = message.photo[-1].file_id
        file = await bot.download_file(file_id)
        photo_bytes = await file.read()

        sticker_file = resize_to_sticker(photo_bytes)
        pack_name = await get_pack_name()

        # Ensure sticker pack exists
        if not await pack_exists(pack_name):
            await create_pack(pack_name, sticker_file)
            await message.answer(
                f"Sticker pack created!\nYou can add more here: https://t.me/addstickers/{pack_name}"
            )
        else:
            try:
                await add_to_pack(pack_name, sticker_file)
                await message.answer(
                    f"Sticker added to pack!\nSee: https://t.me/addstickers/{pack_name}"
                )
            except Exception as e:
                await message.answer(
                    f"Failed to add sticker. Reason: {e}\n"
                    "You may need to manually add the sticker using Telegram's interactive editor."
                )

    except Exception as e:
        await message.answer(f"Sticker creation failed. Reason: {e}")

# -------------------------
# Run bot
# -------------------------
async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Retry getting bot info with exponential backoff
    await get_bot_me_with_retry()
    logging.info("Bot info retrieved successfully. Starting polling...")

    # Polling loop with error handling to keep bot running
    while True:
        try:
            await dp.start_polling(bot, timeout=60)
        except Exception as e:
            logging.error(f"Polling failed: {e}, retrying in 10 seconds...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
