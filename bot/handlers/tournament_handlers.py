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

class TournamentHandlers:
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
        self.dp.message(Command("tournaments"))(self.handle_tournaments)
        self.dp.callback_query(F.data.startswith("view_tournament_"))(self.view_tournament)
        self.dp.callback_query(F.data.startswith("edit_tournament_"))(self.edit_tournament)
        self.dp.callback_query(F.data.startswith("delete_tournament_"))(self.delete_tournament)
        self.dp.callback_query(F.data == "refresh_tournaments")(self.refresh_tournaments)
        self.dp.message(F.web_app_data)(self.handle_webapp_data)

    async def handle_tournaments(self, message: types.Message):
        await self.show_tournaments_list(message, message.chat.id)

    async def show_tournaments_list(self, message: types.Message | None = None, chat_id: int | None = None):
        if message is None and chat_id is None:
            raise ValueError("Either message or chat_id must be provided")

        tournaments = await TournamentService.list_tournaments()

        keyboard = []
        for tournament in tournaments:
            event_date = tournament.event_datetime.strftime("%Y-%m-%d %H:%M")
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{tournament.event_name} ({event_date})",
                    callback_data=f"view_tournament_{tournament.id}"
                )
            ])

        message_text = "🏆 Tournament List:"
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        if message is not None:
            await message.answer(
                message_text,
                reply_markup=reply_markup
            )
        else:
            await self.bot.send_message(chat_id,
                message_text,
                reply_markup=reply_markup
            )

        if await is_admin(self.bot, message.from_user.id):
            await self._show_create_button(message, chat_id)

    async def _show_create_button(self, message: types.Message, chat_id: int):
        message_text = "Press ➕ Create New Tournament to create a new tournament"
        reply_markup = ReplyKeyboardMarkup(keyboard=[[
                    KeyboardButton(
                        text="➕ Create New Tournament",
                        web_app=WebAppInfo(url=TOURNAMENT_WEBAPP_URL)
                    )
                ]])
        if message is not None:
            await message.answer(
                message_text,
                reply_markup=reply_markup
            )
        else:
            await self.bot.send_message(chat_id,
                message_text,
                reply_markup=reply_markup
            )

    async def view_tournament(self, callback: types.CallbackQuery):
        print(f"🔹 view_tournament() | User: {callback.from_user.id} | Data: {callback.data}")
        tournament_id = int(callback.data.split("_")[2])
        try:
            tournament = Tournament.get_by_id(tournament_id)
            event_date = tournament.event_datetime.strftime("%Y-%m-%d %H:%M")

            text = (
                f"🏆 <b>{tournament.event_name}</b>\n"
                f"📅 <b>Date:</b> {event_date}\n"
                f"📍 <b>Location:</b> {tournament.location_name}\n"
                f"👥 <b>Teams:</b> {tournament.number_of_teams}\n"
                f"⚽ <b>Players in team:</b> {tournament.players_per_game}\n"
                f"🔄 <b>Round Robin Rounds:</b> {tournament.round_robin_rounds}\n"
                f"🏁 <b>Playoff Starts:</b> {tournament.playoff_starts_at}\n"
                f"📝 <b>Comment:</b> {tournament.comment or 'None'}"
            )

            keyboard = [[InlineKeyboardButton(text="Подать заявку на участие", callback_data=f"compose_team_{tournament.id}")]]

            if await is_admin(self.bot, callback.from_user.id):
                keyboard.append([
                    InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit_tournament_{tournament.id}"),
                    InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_tournament_{tournament.id}")
                ])

            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
            await callback.answer()
        except DoesNotExist:
            await callback.answer("Tournament not found", show_alert=True)

    async def edit_tournament(self, callback: types.CallbackQuery):
        print(f"🔹 edit_tournament() | User: {callback.from_user.id} | Data: {callback.data}")

        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        tournament_id = int(callback.data.split("_")[2])
        try:
            tournament = Tournament.get_by_id(tournament_id)

            # Prepare tournament data
            tournament_data = {
                "id": tournament.id,
                "event_name": tournament.event_name,
                "event_datetime": tournament.event_datetime.isoformat(),
                "location_name": tournament.location_name,
                "number_of_teams": tournament.number_of_teams,
                "players_per_game": tournament.players_per_game,
                "players_registered": tournament.players_registered,
                "round_robin_rounds": tournament.round_robin_rounds,
                "playoff_starts_at": tournament.playoff_starts_at,
                "playoff_seeding": tournament.playoff_seeding,
                "competition_type": tournament.competition_type,
                "comment": tournament.comment or ""
            }

            # Encode data as URL-safe JSON string
            encoded_data = quote(json.dumps(tournament_data))
            web_app_url = f"{TOURNAMENT_WEBAPP_URL}?edit={encoded_data}"

            await callback.message.answer(
                "Editing tournament...",
                reply_markup=ReplyKeyboardMarkup(keyboard=[[
                    KeyboardButton(
                        text="✏️ Edit Tournament",
                        web_app=WebAppInfo(url=web_app_url)
                    )
                ]], resize_keyboard=True)
            )
            await callback.answer()
        except DoesNotExist:
            await callback.answer("Tournament not found", show_alert=True)
        except Exception as e:
            print(f"Error in edit_tournament: {e}")
            await callback.answer("Error loading tournament", show_alert=True)

    async def delete_tournament(self, callback: types.CallbackQuery):
        print(f"🔹 delete_tournament() | User: {callback.from_user.id} | Data: {callback.data}")

        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        tournament_id = int(callback.data.split("_")[2])
        try:
            tournament = Tournament.get_by_id(tournament_id)
            tournament.delete_instance()

            # Edit original message to remove the deleted tournament
            await callback.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text="✅ Tournament deleted. Click to refresh",
                            callback_data="refresh_tournaments"
                        )]
                    ]
                )
            )
            await callback.answer("✅ Tournament deleted")
        except DoesNotExist:
            await callback.answer("Tournament not found", show_alert=True)

    async def refresh_tournaments(self, callback: types.CallbackQuery):
        print(f"🔹 refresh_tournaments() | User: {callback.from_user.id} | Data: {callback.data}")
        # Re-run the handle_tournaments function
        await self.handle_tournaments(callback.message)
        await callback.answer()

    async def handle_webapp_data(self, message: types.Message):
        print("Received WebApp data:", message.web_app_data)

        try:
            data = json.loads(message.web_app_data.data)
            user_id = message.from_user.id

            if not await is_admin(self.bot, user_id):
                return await message.answer("❌ Admin access required")

            if data['action'] == 'create_tournament':
                # Create new tournament
                Tournament.create(
                    event_name=data['data']['event_name'],
                    event_datetime=datetime.fromisoformat(data['data']['event_datetime']),
                    location_name=data['data']['location_name'],
                    number_of_teams=data['data']['number_of_teams'],
                    players_per_game=data['data']['players_per_game'],
                    players_registered=data['data']['players_registered'],
                    round_robin_rounds=data['data']['round_robin_rounds'],
                    playoff_starts_at=data['data']['playoff_starts_at'],
                    playoff_seeding=data['data']['playoff_seeding'],
                    competition_type=data['data']['competition_type'],
                    comment=data['data']['comment'],
                    created_by=user_id,
                    status=TournamentStatus.SCHEDULED
                )
                await message.answer("✅ Tournament created successfully!")

            elif data['action'] == 'update_tournament':
                # Update existing tournament
                Tournament.update(
                    event_name=data['data']['event_name'],
                    event_datetime=datetime.fromisoformat(data['data']['event_datetime']),
                    location_name=data['data']['location_name'],
                    number_of_teams=data['data']['number_of_teams'],
                    players_per_game=data['data']['players_per_game'],
                    players_registered=data['data']['players_registered'],
                    round_robin_rounds=data['data']['round_robin_rounds'],
                    playoff_starts_at=data['data']['playoff_starts_at'],
                    playoff_seeding=data['data']['playoff_seeding'],
                    competition_type=data['data']['competition_type'],
                    comment=data['data']['comment']
                ).where(Tournament.id == data['data']['id']).execute()
                await message.answer("✅ Tournament updated successfully!")

            elif data['action'] == 'get_tournament':
                # New handler for fetching tournament data
                tournament_id = data['tournament_id']
                tournament = Tournament.get_by_id(tournament_id)

                # Format datetime for the web app
                event_datetime = tournament.event_datetime.isoformat()

                tournament_data = {
                    "id": tournament.id,
                    "event_name": tournament.event_name,
                    "event_datetime": event_datetime,
                    "location_name": tournament.location_name,
                    "number_of_teams": tournament.number_of_teams,
                    "players_per_game": tournament.players_per_game,
                    "players_registered": tournament.players_registered,
                    "round_robin_rounds": tournament.round_robin_rounds,
                    "playoff_starts_at": tournament.playoff_starts_at,
                    "playoff_seeding": tournament.playoff_seeding,
                    "competition_type": tournament.competition_type,
                    "comment": tournament.comment,
                    "status": tournament.status
                }

                await message.answer(json.dumps({
                    "type": "tournament_data",
                    "data": tournament_data
                }))
        except Exception as e:
            print(f"Error processing web app data: {e}")
            await message.answer(
                text=f"⚠️ Error processing your request: {str(e)}"
            )