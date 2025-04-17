import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.core.bot_core import BotCore
from config import BOT_TOKEN
from bot.handlers.user_handlers import UserHandlers
from bot.handlers.tournament_handlers import TournamentHandlers
from database import initialize_db

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Initialize database
    initialize_db()

    # Register handlers
    bot_core = BotCore(dp, bot)
    bot_core.register_handlers()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())