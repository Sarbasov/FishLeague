from datetime import datetime

from aiogram import F, types, Dispatcher, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, Message, InlineKeyboardMarkup, \
    InlineKeyboardButton
from peewee import DatabaseError

from bot.common.auth_utils import is_admin
from bot.handlers.tournament_handlers import TournamentHandlers
from bot.services.user_service import UserService
from database import User, UserStatus
from config import ADMIN_GROUP_ID

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()  # New state
    waiting_for_comment = State()

class UserHandlers:
    def __init__(self, dp: Dispatcher, bot: Bot, tournament_handlers: TournamentHandlers):
        self._dp = dp
        self._bot = bot
        self._tournament_handlers = tournament_handlers
        self.register_handlers()

    @property
    def dp(self) -> Dispatcher:
        return self._dp

    @property
    def bot(self) -> Bot:
        return self._bot

    @property
    def tournament_handlers(self) -> TournamentHandlers:
        return self._tournament_handlers

    def register_handlers(self):
        self.dp.message(Command("start"))(self.start)
        self.dp.message(Registration.waiting_for_phone, F.contact)(self.process_phone)
        self.dp.message(Registration.waiting_for_full_name)(self.process_full_name)
        self.dp.message(Registration.waiting_for_comment)(self.process_comment)
        self.dp.callback_query(F.data.startswith("approve_user_"))(self.approve_user)
        self.dp.callback_query(F.data.startswith("deny_user_"))(self.deny_user)
        self.dp.callback_query(F.data.startswith("delete_user_"))(self.delete_request)

    async def start(self, message: types.Message, state: FSMContext):
        try:
            if await is_admin(self.bot, message.from_user.id):
                await message.answer("✅ Welcome back! You are an admin.")
                await self.tournament_handlers.handle_tournaments(message) # show list of tournaments
            else:
                user = await UserService.get_user(message.from_user.id)
                if user:
                    if user.status == UserStatus.ACTIVATED:
                        await message.answer("✅ Welcome back! You have full access.")
                        await self.tournament_handlers.handle_tournaments(message) # show list of tournaments
                    elif user.status == UserStatus.BLOCKED:
                        await message.answer("⛔ Your account is blocked. Contact administrator.")
                    else:
                        await message.answer("⌛ Your registration request is pending approval.")
                else:
                    await self._init_registration(message, state) # user register form
        except Exception as e:
            await message.answer("⚠️ An error occurred. Please try again.")
            print(f"Error in start handler: {e}")

    async def _init_registration(self, message: types.Message, state: FSMContext):
        await message.answer(
            "📱 Please share your phone number using the button below:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Share Phone Number", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        await state.update_data(user_id=message.from_user.id)
        await state.set_state(Registration.waiting_for_phone)

    async def process_phone(self, message: Message, state: FSMContext):
        await state.update_data(phone_number=message.contact.phone_number)

        await message.answer(
            f"👤 Please enter your full name:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=f"✅ Use {message.from_user.full_name}")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(Registration.waiting_for_full_name)

    async def process_full_name(self, message: Message, state: FSMContext):
        data = await state.get_data()
        full_name = message.text

        if len(full_name) > 50:
            await message.answer("❌ Name too long (max 50 chars). Try again:")
            return

        await state.update_data(full_name=full_name)
        await message.answer("📝 Please enter your comment:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Registration.waiting_for_comment)

    async def process_comment(self, message: Message, state: FSMContext):
        comment = message.text
        await state.update_data(comment=comment)

        data = await state.get_data()

        try:
            User.create(
                id=message.from_user.id,
                chat_id=message.chat.id,
                username=message.from_user.username,
                full_name=data['full_name'],
                phone_number=data['phone_number'],
                url=message.from_user.url,
                comment=comment,
                status=UserStatus.REQUESTED,
                create_date=datetime.now()
            )
            await self.notify_admins(data)
            await message.answer("✅ Registration submitted for approval!")
        except DatabaseError as e:
            error_message = str(e)
            if "UNIQUE constraint failed" in error_message:
                user_message = "⚠️ You already have a pending registration request!"
            elif "NOT NULL constraint failed" in error_message:
                user_message = "⚠️ Missing required information. Please start over."
            else:
                user_message = f"⚠️ Registration error: {error_message}"

            await message.answer(user_message)
            # logger.error(f"Registration error for {message.from_user.id}: {error_message}")

        await state.clear()

    async def approve_user(self, callback: types.CallbackQuery):
        print(f"🔹 approve_user() | User: {callback.from_user.id} | Data: {callback.data}")

        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        user_id = int(callback.data.split("_")[2])

        User.update(status=UserStatus.ACTIVATED).where(User.id == user_id).execute()
        await self.bot.send_message(user_id, "🎉 Your registration was approved!")

        await callback.answer(
            f"✅ Approved by {callback.from_user.full_name}"
        )

    async def deny_user(self, callback: types.CallbackQuery):
        print(f"🔹 deny_user() | User: {callback.from_user.id} | Data: {callback.data}")

        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        user_id = int(callback.data.split("_")[2])

        User.update(status=UserStatus.BLOCKED).where(User.id == user_id).execute()
        await self.bot.send_message(user_id, "❌ Your registration was denied.")

        # Edit original message to show denial
        await callback.answer(
            f"❌ Denied by {callback.from_user.full_name}"
        )

    async def delete_request(self, callback: types.CallbackQuery):
        print(f"🔹 delete_request() | User: {callback.from_user.id} | Data: {callback.data}")

        if not await is_admin(self.bot, callback.from_user.id):
            await callback.answer("❌ Admin access required")
            return

        user_id = int(callback.data.split("_")[2])

        # full DB delete
        User.delete().where(User.id == user_id).execute()

        # Delete the admin notification message
        await callback.message.delete()

        await callback.answer("Request deleted by {callback.from_user.full_name}")

    async def notify_admins(self, user_data: dict):
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"approve_user_{user_data['user_id']}"
                ),
                InlineKeyboardButton(
                    text="❌ Deny",
                    callback_data=f"deny_user_{user_data['user_id']}"
                ),
                InlineKeyboardButton(
                    text="🗑️ Delete Request",
                    callback_data=f"delete_user_{user_data['user_id']}")
            ]
        ])

        await self.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"📨 New User Registration Request:\n"
                 f"• User: {user_data['full_name']} (ID: {user_data['user_id']})\n"
                 f"• Phone: {user_data['phone_number']}\n"
                 f"• Comment: {user_data['comment']}",
            reply_markup=markup
        )

