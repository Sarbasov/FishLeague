from aiogram import F, types, Dispatcher, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from peewee import DoesNotExist
from config import ADMIN_GROUP_ID
from database import Team, TeamMember, Tournament, User, TeamStatus
from bot.services.team_service import TeamService


class TeamStates(StatesGroup):
    waiting_for_team_name = State()
    waiting_for_member_phone = State()
    waiting_for_member_to_remove = State()


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
        self.dp.callback_query(F.data.startswith("submit_team_"))(self.submit_team)
        self.dp.callback_query(F.data.startswith("cancel_team_"))(self.cancel_team)
        self.dp.callback_query(F.data.startswith("add_member_"))(self.add_member)
        self.dp.callback_query(F.data.startswith("remove_member_"))(self.remove_member)
        self.dp.callback_query(F.data.startswith("approve_team_"))(self.approve_team)
        self.dp.callback_query(F.data.startswith("deny_team_"))(self.deny_team)
        self.dp.message(TeamStates.waiting_for_team_name)(self.process_team_name)
        self.dp.message(TeamStates.waiting_for_member_phone)(self.process_member_phone)
        self.dp.message(TeamStates.waiting_for_member_to_remove)(self.process_member_to_remove)

    async def compose_team(self, callback: types.CallbackQuery, state: FSMContext):
        tournament_id = int(callback.data.split("_")[2])
        user_id = callback.from_user.id

        try:
            tournament = Tournament.get_by_id(tournament_id)

            if tournament.players_per_game == 1:
                # Individual tournament - create team automatically
                user = User.get_by_id(user_id)
                team = await TeamService.create_team(
                    tournament_id=tournament_id,
                    user_id=user_id,
                    team_name=user.full_name
                )
                team.status = TeamStatus.REQUESTED
                team.save()
                await self.notify_admins(team)
                await callback.message.answer("✅ Your participation request submitted!")
            else:
                # Team tournament - start team creation flow
                await state.update_data(tournament_id=tournament_id)
                await callback.message.answer(
                    "🏆 Please enter your team name:",
                    reply_markup=ReplyKeyboardRemove()
                )
                await state.set_state(TeamStates.waiting_for_team_name)
                await callback.answer()

        except DoesNotExist:
            await callback.answer("Tournament not found", show_alert=True)

    async def process_team_name(self, message: types.Message, state: FSMContext):
        team_name = message.text
        data = await state.get_data()

        team = await TeamService.create_team(
            tournament_id=data['tournament_id'],
            user_id=message.from_user.id,
            team_name=team_name
        )

        await state.update_data(team_id=team.id)
        await self.show_team_management(message, team)
        await state.set_state(None)

    async def show_team_management(self, message: types.Message, team: Team):
        tournament = team.tournament
        members = team.members

        text = (
            f"🏆 Team: {team.name}\n"
            f"👥 Members ({len(members)}/{tournament.players_registered}):\n"
        )

        for member in members:
            captain_flag = " (Captain)" if team.captain == member.user else ""
            text += f"• {member.user.full_name}{captain_flag}\n"

        keyboard = []

        if len(members) < tournament.players_registered:
            keyboard.append([
                InlineKeyboardButton(
                    text="➕ Add Member",
                    callback_data=f"add_member_{team.id}"
                )
            ])

        if len(members) > 1:  # At least 1 non-captain member
            keyboard.append([
                InlineKeyboardButton(
                    text="➖ Remove Member",
                    callback_data=f"remove_member_{team.id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                text="✅ Submit Team",
                callback_data=f"submit_team_{team.id}"
            ),
            InlineKeyboardButton(
                text="❌ Cancel",
                callback_data=f"cancel_team_{team.id}"
            )
        ])

        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )

    async def add_member(self, callback: types.CallbackQuery, state: FSMContext):
        team_id = int(callback.data.split("_")[2])
        await state.update_data(team_id=team_id)
        await callback.message.answer(
            "📱 Please enter the phone number of the member to add:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(TeamStates.waiting_for_member_phone)
        await callback.answer()

    async def process_member_phone(self, message: types.Message, state: FSMContext):
        phone_number = message.text
        data = await state.get_data()

        success, error = await TeamService.add_member(data['team_id'], phone_number)
        if not success:
            await message.answer(f"❌ {error}")
            return

        team = Team.get_by_id(data['team_id'])
        await self.show_team_management(message, team)
        await state.set_state(None)

    async def remove_member(self, callback: types.CallbackQuery, state: FSMContext):
        team_id = int(callback.data.split("_")[2])
        team = Team.get_by_id(team_id)

        # Create keyboard with members (excluding captain)
        members = [
            m for m in team.members
            if m.user != team.captain
        ]

        if not members:
            await callback.answer("No members to remove", show_alert=True)
            return

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=m.user.full_name)] for m in members],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await state.update_data(team_id=team_id)
        await callback.message.answer(
            "Select member to remove:",
            reply_markup=keyboard
        )
        await state.set_state(TeamStates.waiting_for_member_to_remove)
        await callback.answer()

    async def process_member_to_remove(self, message: types.Message, state: FSMContext):
        member_name = message.text
        data = await state.get_data()
        team = Team.get_by_id(data['team_id'])

        # Find member by name
        member = next(
            (m for m in team.members
             if m.user.full_name == member_name and m.user != team.captain),
            None
        )

        if not member:
            await message.answer("Member not found")
            return

        success, error = await TeamService.remove_member(team.id, member.user.id)
        if not success:
            await message.answer(f"❌ {error}")
            return

        await self.show_team_management(message, team)
        await state.set_state(None)

    async def submit_team(self, callback: types.CallbackQuery):
        team_id = int(callback.data.split("_")[2])

        success, error = await TeamService.submit_team(team_id)
        if not success:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        team = Team.get_by_id(team_id)
        await self.notify_admins(team)

        # Notify team members
        for member in team.members:
            await self.bot.send_message(
                member.user.chat_id,
                f"✅ Your team {team.name} has been submitted for tournament {team.tournament.event_name}!"
            )

        await callback.answer("Team submitted for approval!")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Team submitted for approval!")

    async def cancel_team(self, callback: types.CallbackQuery):
        team_id = int(callback.data.split("_")[2])
        await TeamService.delete_team(team_id)
        await callback.answer("Team creation cancelled", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)

    async def approve_team(self, callback: types.CallbackQuery):
        team_id = int(callback.data.split("_")[2])

        success, error = await TeamService.approve_team(team_id)
        if not success:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        team = Team.get_by_id(team_id)

        # Notify team members
        for member in team.members:
            await self.bot.send_message(
                member.user.chat_id,
                f"🎉 Your team {team.name} has been approved for tournament {team.tournament.event_name}!"
            )

        # Delete admin notification message
        await callback.message.delete()
        await callback.answer("Team approved!")

    async def deny_team(self, callback: types.CallbackQuery):
        team_id = int(callback.data.split("_")[2])
        team = Team.get_by_id(team_id)

        # Notify team members first
        for member in team.members:
            await self.bot.send_message(
                member.user.chat_id,
                f"❌ Your team {team.name} has been rejected for tournament {team.tournament.event_name}"
            )

        # Delete the team
        await TeamService.delete_team(team_id)

        # Delete admin notification message
        await callback.message.delete()
        await callback.answer("Team rejected")

    async def notify_admins(self, team: Team):
        members_text = "\n".join(
            f"• {m.user.full_name} ({m.user.phone_number})"
            for m in team.members
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"approve_team_{team.id}"
            ),
            InlineKeyboardButton(
                text="❌ Deny",
                callback_data=f"deny_team_{team.id}"
            )
        ]])

        await self.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"🏆 New Team Submission:\n"
                 f"• Tournament: {team.tournament.event_name}\n"
                 f"• Team: {team.name}\n"
                 f"• Captain: {team.captain.full_name}\n"
                 f"• Members:\n{members_text}",
            reply_markup=markup
        )