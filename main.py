from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
import asyncio
from database import User, initialize_db, UserStatus

print("Starting bot")

# Initialize bot with new default properties syntax
bot = Bot(
    token='7477173505:AAHKk5OYXSFyXIfa7fKdLRZxOEeCYmJZX_M',
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

initialize_db()


@dp.message(Command("start"))
async def start(message: types.Message):
    # Create or update user
    user, created = User.get_or_create(
        id=message.from_user.id,
        defaults={
            'username': message.from_user.username,
            'full_name': message.from_user.full_name,
            'url': message.from_user.url,
            'status': UserStatus.REQUESTED
        }
    )

    if created:
        await message.answer("Sent request!")
    else:
        await message.answer("Welcome back!")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())