import asyncio
import os
import logging
from io import BytesIO
from PIL import Image

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile
from aiohttp import ClientSession

TOKEN = os.environ["BOT_TOKEN"]
PACK_NAME = os.environ["STICKER_PACK_NAME"]  # e.g. mystickerpack_by_mybot
OWNER_ID = int(os.environ["OWNER_USER_ID"])

bot = Bot(token=TOKEN)
dp = Dispatcher()


# -------------------------
# Helpers
# -------------------------
async def remove_background(file_id):
    """Uses Telegram's background removal API."""
    url = f"https://api.telegram.org/bot{TOKEN}/removeBackgroundFile"
    data = {"file_id": file_id}

    async with ClientSession() as session:
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if not result.get("ok"):
                raise Exception("Background removal failed")
            new_file_id = result["result"]["file_id"]

    # Download new file
    file = await bot.get_file(new_file_id)
    download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"

    async with ClientSession() as session:
        async with session.get(download_url) as resp:
            return await resp.read()


def resize_to_sticker(png_bytes):
    """Resize to 512px max while keeping aspect ratio."""
    img = Image.open(BytesIO(png_bytes))
    img.thumbnail((512, 512))
    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


async def pack_exists():
    try:
        await bot.get_sticker_set(PACK_NAME)
        return True
    except:
        return False


async def create_pack(png_bytes):
    """Creates sticker pack if it doesn't exist."""
    file = BytesIO(png_bytes)
    file.name = "sticker.png"

    await bot.create_new_sticker_set(
        user_id=OWNER_ID,
        name=PACK_NAME,
        title="Shared Sticker Pack",
        png_sticker=file,
        emojis="⭐"
    )


async def add_to_pack(png_bytes):
    """Uploads & adds a sticker to the pack."""
    file = BytesIO(png_bytes)
    file.name = "sticker.png"

    await bot.add_sticker_to_set(
        user_id=OWNER_ID,
        name=PACK_NAME,
        png_sticker=file,
        emojis="⭐"
    )


# -------------------------
# Handlers
# -------------------------

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "Send me a photo and I’ll turn it into a sticker with background removed!\n\n"
        f"Sticker pack: https://t.me/addstickers/{PACK_NAME}"
    )


@dp.message()
async def handle_photo(message: types.Message):

    if not message.photo:
        return await message.answer("Please send a *photo*.")

    await message.answer("Processing… removing background…")

    # Highest quality photo
    file_id = message.photo[-1].file_id

    # Step 1 — background removal
    png = await remove_background(file_id)

    # Step 2 — resize
    final_png = resize_to_sticker(png)

    # Step 3 — ensure pack exists
    if not await pack_exists():
        await create_pack(final_png)
        await message.answer(
            f"Created sticker pack!\nhttps://t.me/addstickers/{PACK_NAME}"
        )
    else:
        await add_to_pack(final_png)

    await message.answer(
        f"Sticker added!\nhttps://t.me/addstickers/{PACK_NAME}"
    )


# -------------------------
# Run bot
# -------------------------
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
