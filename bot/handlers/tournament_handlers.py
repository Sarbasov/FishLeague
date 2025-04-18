from contextlib import nullcontext
from datetime import datetime

from aiogram import F, types, Dispatcher, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import WebAppInfo
from peewee import DoesNotExist

from bot.services.team_service import TeamService
from bot.services.tournament_service import TournamentService
from config import TOURNAMENT_WEBAPP_URL
from urllib.parse import quote
import json

from database import Tournament, TournamentStatus, TeamStatus, TeamMember, Team
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
        self.dp.callback_query(F.data.startswith("admin_delete_team_"))(self.admin_delete_team)
        self.dp.callback_query(F.data.startswith("admin_approve_team_"))(self.admin_approve_team)
        self.dp.message(F.web_app_data)(self.handle_webapp_data)

    async def handle_tournaments(self, message: types.Message):
        await self.show_tournaments_list(message.from_user.id)

    async def show_tournaments_list(self, user_id: int):
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
        await self.bot.send_message(user_id,
            message_text,
            reply_markup=reply_markup
        )

        if await is_admin(self.bot, user_id):
            await self._show_create_button(user_id)

    async def _show_create_button(self, user_id: int):
        message_text = "Press ➕ Create New Tournament to create a new tournament"
        reply_markup = ReplyKeyboardMarkup(keyboard=[[
                    KeyboardButton(
                        text="➕ Create New Tournament",
                        web_app=WebAppInfo(url=TOURNAMENT_WEBAPP_URL)
                    )
                ]])
        await self.bot.send_message(user_id,
            message_text,
            reply_markup=reply_markup
        )

    async def view_tournament(self, callback: types.CallbackQuery):
        print(f"🔹 view_tournament() | User: {callback.from_user.id} | Data: {callback.data}")
        tournament_id = int(callback.data.split("_")[2])
        try:
            tournament = Tournament.get_by_id(tournament_id)
            event_date = tournament.event_datetime.strftime("%Y-%m-%d %H:%M")
            is_admin_user = await is_admin(self.bot, callback.from_user.id)

            # Basic tournament info
            text = (
                f"🏆 <b>{tournament.event_name}</b>\n"
                f"📅 <b>Date:</b> {event_date}\n"
                f"📍 <b>Location:</b> {tournament.location_name}\n"
                f"👥 <b>Teams:</b> {tournament.number_of_teams}\n"
                f"⚽ <b>Players in team:</b> {tournament.players_per_game}\n"
                f"🔄 <b>Round Robin Rounds:</b> {tournament.round_robin_rounds}\n"
                f"🏁 <b>Playoff Starts:</b> {tournament.playoff_starts_at}\n"
                f"📝 <b>Comment:</b> {tournament.comment or 'None'}\n\n"
            )

            # Get all teams for this tournament
            teams = tournament.teams.order_by(Team.create_date)

            # Add teams info if admin
            if is_admin_user and teams.count() > 0:
                text += "<b>Teams:</b>\n"
                for i, team in enumerate(teams, 1):
                    status = {
                        TeamStatus.DRAFT: "Draft",
                        TeamStatus.REQUESTED: "Pending Approval",
                        TeamStatus.ENROLLED: "Enrolled"
                    }.get(team.status, "Unknown")

                    text += (
                        f"\n{i}. <b>{team.name}</b> ({status})\n"
                        f"👤 Captain: {team.captain.full_name}\n"
                        f"👥 Members ({TeamMember.select().where(TeamMember.team == team).count()}):\n"
                    )

                    # List all members
                    for member in team.members:
                        captain_flag = " (Captain)" if member.user == team.captain else ""
                        text += f"   • {member.user.full_name}{captain_flag}\n"

            keyboard = []

            # Add participation button for regular users
            if not is_admin_user:
                keyboard.append([InlineKeyboardButton(
                    text="Подать заявку на участие",
                    callback_data=f"compose_team_{tournament.id}"
                )])

            # Add admin controls
            if is_admin_user:
                # Add team management buttons for each team
                for i, team in enumerate(teams, 1):
                    team_buttons = []

                    # Delete button for all teams
                    team_buttons.append(InlineKeyboardButton(
                        text=f"🗑️ Delete Team {i}",
                        callback_data=f"admin_delete_team_{team.id}"
                    ))

                    # Approve button for requested teams
                    if team.status == TeamStatus.REQUESTED:
                        team_buttons.append(InlineKeyboardButton(
                            text=f"✅ Approve Team {i}",
                            callback_data=f"admin_approve_team_{team.id}"
                        ))

                    keyboard.append(team_buttons)

                # Add tournament management buttons
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

    async def admin_delete_team(self, callback: types.CallbackQuery):
        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        team_id = int(callback.data.split("_")[3])
        try:
            team = Team.get_by_id(team_id)
            tournament_id = team.tournament.id
            team.delete_instance()
            await callback.answer("✅ Team deleted")
            # Refresh the tournament view
            await self.view_tournament(types.CallbackQuery(
                data=f"view_tournament_{tournament_id}",
                message=callback.message,
                from_user=callback.from_user
            ))
        except DoesNotExist:
            await callback.answer("Team not found", show_alert=True)

    async def admin_approve_team(self, callback: types.CallbackQuery):
        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        team_id = int(callback.data.split("_")[3])
        try:
            team = Team.get_by_id(team_id)
            success, error = await TeamService.approve_team(team.id)
            if not success:
                await callback.answer(f"❌ {error}", show_alert=True)
                return

            tournament_id = team.tournament.id
            await callback.answer("✅ Team approved")
            # Refresh the tournament view
            await self.view_tournament(types.CallbackQuery(
                data=f"view_tournament_{tournament_id}",
                message=callback.message,
                from_user=callback.from_user
            ))
        except DoesNotExist:
            await callback.answer("Team not found", show_alert=True)