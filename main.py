import asyncio
import json

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import User, initialize_db, UserStatus, TournamentStatus, Tournament
from peewee import DoesNotExist, IntegrityError, DatabaseError
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove, ForceReply
from aiogram.types import WebAppInfo
from config import ADMIN_GROUP_ID, BOT_TOKEN

print("Starting bot")

# Initialize bot with new default properties syntax
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

initialize_db()

# States definition
class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()  # New state
    waiting_for_comment = State()

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    try:
        user = User.get(User.id == message.from_user.id)

        # Update chat_id and username of the user to keep these values up-to-date
        User.update(
            chat_id = message.chat.id,
            username = message.from_user.username
        ).where(
            User.id == message.from_user.id
        ).execute()

        if user.status == UserStatus.ACTIVATED:
            await message.answer("✅ Welcome back! You have full access.")
        elif user.status == UserStatus.BLOCKED:
            await message.answer("⛔ Your account is blocked. Contact administrator.")
        else:
            await message.answer("⌛ Your registration request is pending approval.")

    except DoesNotExist:
        await message.answer(
            "📱 Please share your phone number using the button below:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📱 Share Phone Number", request_contact=True)]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        await state.update_data(user_id=message.from_user.id)
        await state.set_state(Registration.waiting_for_phone)


@dp.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
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


@dp.message(Registration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    data = await state.get_data()
    full_name = message.text

    if len(full_name) > 50:
        await message.answer("❌ Name too long (max 50 chars). Try again:")
        return

    await state.update_data(full_name=full_name)
    await message.answer("📝 Please enter your comment:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.waiting_for_comment)


@dp.message(Registration.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext):
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
        await notify_admins(data)
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
        #logger.error(f"Registration error for {message.from_user.id}: {error_message}")

    await state.clear()


# In your registration handler:
async def notify_admins(user_data: dict):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"approve_{user_data['user_id']}"
            ),
            InlineKeyboardButton(
                text="❌ Deny",
                callback_data=f"deny_{user_data['user_id']}"
            ),
            InlineKeyboardButton(
                text="🗑️ Delete Request",
                callback_data=f"delete_{user_data['user_id']}")
        ]
    ])

    await bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"📨 New User Registration Request:\n"
             f"• User: {user_data['full_name']} (ID: {user_data['user_id']})\n"
             f"• Phone: {user_data['phone_number']}\n"
             f"• Comment: {user_data['comment']}",
        reply_markup=markup
    )

@dp.callback_query(F.data.startswith("approve_"))
async def approve_user(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    User.update(status=UserStatus.ACTIVATED).where(User.id == user_id).execute()
    await bot.send_message(user_id, "🎉 Your registration was approved!")

    await callback.answer(
        f"✅ Approved by {callback.from_user.full_name}"
    )

@dp.callback_query(F.data.startswith("deny_"))
async def deny_user(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    User.update(status=UserStatus.BLOCKED).where(User.id == user_id).execute()
    await bot.send_message(user_id, "❌ Your registration was denied.")

    # Edit original message to show denial
    await callback.answer(
        f"❌ Denied by {callback.from_user.full_name}"
    )

@dp.callback_query(F.data.startswith("delete_"))
async def delete_request(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    # full DB delete
    User.delete().where(User.id == user_id).execute()

    # Delete the admin notification message
    await callback.message.delete()

    await callback.answer("Request deleted by {callback.from_user.full_name}")


# Add to command handlers
@dp.message(Command("tournaments"))
async def handle_tournaments(message: types.Message):
    # Verify admin status (replace with your admin check logic)
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Admin access required")
        return

    await message.answer(
        "Tournament Management",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Open Tournament Manager",
                web_app=WebAppInfo(url="https://sarbasov.github.io/tournament_webapp.html")
            )]]
        )
    )

# Add to your Dispatcher setup
@dp.update()
async def handle_webapp_data(update: types.Update):
    if update.web_app_data:
        try:
            user_id = update.web_app_data.user.id
            data = json.loads(update.web_app_data.data)

            if not await is_admin(user_id):
                return

            if data['action'] == 'list_tournaments':
                tournaments = list(Tournament.select().dicts())
                await bot.send_message(
                    chat_id=user_id,
                    text=json.dumps({
                        'action': 'display_tournaments',
                        'tournaments': [
                            {
                                'id': t['id'],
                                'event_name': t['event_name'],
                                'event_datetime': t['event_datetime'].isoformat(),
                                'status': t['status']
                            } for t in tournaments
                        ]
                    }),
                    reply_markup=ForceReply(selective=True)
                )

            elif data['action'] == 'create_tournament':
                Tournament.create(
                    event_name=data['data']['event_name'],
                    event_datetime=datetime.fromisoformat(data['data']['event_datetime']),
                    location_name=data['data']['location_name'],
                    number_of_teams=data['data']['number_of_teams'],
                    number_of_sectors=data['data']['number_of_sectors'],
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
                await bot.send_message(user_id, "✅ Tournament created!")

            elif data['action'] == 'update_tournament':
                Tournament.update(
                    event_name=data['data']['event_name'],
                    event_datetime=datetime.fromisoformat(data['data']['event_datetime']),
                    location_name=data['data']['location_name'],
                    number_of_teams=data['data']['number_of_teams'],
                    number_of_sectors=data['data']['number_of_sectors'],
                    players_per_game=data['data']['players_per_game'],
                    players_registered=data['data']['players_registered'],
                    round_robin_rounds=data['data']['round_robin_rounds'],
                    playoff_starts_at=data['data']['playoff_starts_at'],
                    playoff_seeding=data['data']['playoff_seeding'],
                    competition_type=data['data']['competition_type'],
                    comment=data['data']['comment']
                ).where(Tournament.id == data['data']['id']).execute()
                await bot.send_message(user_id, "✅ Tournament updated!")

            elif data['action'] == 'delete_tournament':
                Tournament.update(status=TournamentStatus.DELETED).where(
                    Tournament.id == data['id']
                ).execute()
                await bot.send_message(user_id, "✅ Tournament marked as deleted!")

        except Exception as e:
            await bot.send_message(user_id, f"❌ Error: {str(e)}")

async def is_member(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(ADMIN_GROUP_ID, user_id)
        return member is not None
    except:
        return False

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())