from contextlib import nullcontext
from datetime import datetime

from aiogram import F, types, Dispatcher, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import WebAppInfo
from peewee import DoesNotExist

from bot.services.tournament_service import TournamentService
from config import TOURNAMENT_WEBAPP_URL
from urllib.parse import quote
import json

from database import Tournament, TournamentStatus
from bot.common.auth_utils import is_admin

class TeamHandlers:
    def __init__(self, dp: Dispatcher, bot: Bot):
        self._dp = dp
        self._bot = bot
        self.register_handlers()

    @property
    def dp(self) -> Dispatcher:
        return self._dp

    @property
    def bot(self) -> Bot:
        return self._bot

    def register_handlers(self):
        self.dp.callback_query(F.data.startswith("compose_team_"))(self.compose_team)

    async def compose_team(self, callback: types.CallbackQuery):
        print(f"🔹 submit_team() | User: {callback.from_user.id} | Data: {callback.data}")
        tournament_id = int(callback.data.split("_")[2])
        try:
            tournament = Tournament.get_by_id(tournament_id)

            await callback.answer("Not implemented yet")
        except DoesNotExist:
            await callback.answer("Tournament not found", show_alert=True)
