from aiogram import Dispatcher, Bot
from bot.handlers.user_handlers import UserHandlers
from bot.handlers.tournament_handlers import TournamentHandlers

class BotCore:
    def __init__(self, dp: Dispatcher, bot: Bot):
        self.dp = dp
        self.bot = bot
        self.tournament_handlers = TournamentHandlers(dp, bot)
        self.user_handlers = UserHandlers(dp, bot, self.tournament_handlers)

    def register_handlers(self):
        self.tournament_handlers.register_handlers()
        self.user_handlers.register_handlers()