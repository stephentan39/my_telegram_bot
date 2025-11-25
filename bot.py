import asyncio
import os
import logging
from io import BytesIO
from PIL import Image

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

TOKEN = os.environ["BOT_TOKEN"]
PACK_NAME = os.environ["STICKER_PACK_NAME"]
OWNER_ID = int(os.environ["OWNER_USER_ID"])

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

async def pack_exists():
    try:
        await bot.get_sticker_set(PACK_NAME)
        return True
    except:
        return False

async def create_pack(png_file):
    """Create sticker pack if it doesn't exist."""
    try:
        await bot.create_new_sticker_set(
            user_id=OWNER_ID,
            name=PACK_NAME,
            title="Shared Sticker Pack",
            png_sticker=png_file,
            emojis="⭐"
        )
    except Exception as e:
        raise Exception(f"Failed to create sticker pack: {e}")

async def add_to_pack(png_file):
    """Add sticker to existing pack."""
    try:
        await bot.add_sticker_to_set(
            user_id=OWNER_ID,
            name=PACK_NAME,
            png_sticker=png_file,
            emojis="⭐"
        )
    except Exception as e:
        raise Exception(f"Failed to add sticker to pack: {e}")

# -------------------------
# Handlers
# -------------------------

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "Hi! Send me a photo and I will prepare it for a sticker.\n\n"
        "You will then be able to select objects to keep using Telegram's sticker editor.\n"
        f"Sticker pack link: https://t.me/addstickers/{PACK_NAME}"
    )

@dp.message()
async def handle_photo(message: types.Message):
    if not message.photo:
        return await message.answer("Please send a photo.")

    await message.answer("Processing your photo...")

    # Take the highest quality photo
    file_id = message.photo[-1].file_id
    try:
        file = await bot.download_file(file_id)
        photo_bytes = await file.read()
        sticker_file = resize_to_sticker(photo_bytes)

        # Ensure sticker pack exists
        if not await pack_exists():
            await create_pack(sticker_file)
            await message.answer(
                f"Sticker pack created!\nYou can add more here: https://t.me/addstickers/{PACK_NAME}"
            )
        else:
            try:
                await add_to_pack(sticker_file)
                await message.answer(
                    f"Sticker added to pack!\nSee: https://t.me/addstickers/{PACK_NAME}"
                )
            except Exception as e:
                await message.answer(
                    f"Failed to add sticker. Reason: {e}\n"
                    "You might need to manually add the sticker using Telegram's interactive editor."
                )

    except Exception as e:
        await message.answer(f"Sticker creation failed. Reason: {e}")

# -------------------------
# Run bot
# -------------------------

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
