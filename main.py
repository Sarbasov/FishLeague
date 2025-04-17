import asyncio
import json
import urllib
from urllib.parse import quote

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
from config import ADMIN_GROUP_ID, BOT_TOKEN, TOURNAMENT_WEBAPP_URL

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


@dp.message(Command("tournaments"))
async def handle_tournaments(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Admin access required")
        return

    # Get all tournaments from the database
    tournaments = Tournament.select().order_by(Tournament.event_datetime.desc())

    if not tournaments:
        # If no tournaments, show create button
        await message.answer(
            "No tournaments found. Would you like to create one?",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[
                KeyboardButton(
                    text="Create Tournament",
                    web_app=WebAppInfo(url=TOURNAMENT_WEBAPP_URL)
                )
            ]])
        )
        return

    # Create inline keyboard with tournament list
    keyboard = []
    for tournament in tournaments:
        # Format date for display
        event_date = tournament.event_datetime.strftime("%Y-%m-%d %H:%M")

        # Create buttons for each tournament
        keyboard.append([
            InlineKeyboardButton(
                text=f"{tournament.event_name} ({event_date})",
                callback_data=f"view_tournament_{tournament.id}"
            )
        ])
        keyboard.append([
            InlineKeyboardButton(
                text="✏️ Edit",
                callback_data=f"edit_tournament_{tournament.id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Delete",
                callback_data=f"delete_tournament_{tournament.id}"
            )
        ])

    # Add create button at the end
    keyboard.append([
        InlineKeyboardButton(
            text="➕ Create New Tournament",
            web_app=WebAppInfo(url=TOURNAMENT_WEBAPP_URL)
        )
    ])

    await message.answer(
        "🏆 Tournament List:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[
            KeyboardButton(
                text="Open Tournament Manager",
                web_app=WebAppInfo(url=TOURNAMENT_WEBAPP_URL)
            )
        ]])
    )

# Add handlers for the new callback queries
@dp.callback_query(F.data.startswith("view_tournament_"))
async def view_tournament(callback: types.CallbackQuery):
    tournament_id = int(callback.data.split("_")[2])
    try:
        tournament = Tournament.get_by_id(tournament_id)
        event_date = tournament.event_datetime.strftime("%Y-%m-%d %H:%M")

        text = (
            f"🏆 <b>{tournament.event_name}</b>\n"
            f"📅 <b>Date:</b> {event_date}\n"
            f"📍 <b>Location:</b> {tournament.location_name}\n"
            f"👥 <b>Teams:</b> {tournament.number_of_teams}\n"
            f"⚽ <b>Players per game:</b> {tournament.players_per_game}\n"
            f"🏟️ <b>Sectors:</b> {tournament.number_of_sectors}\n"
            f"🔄 <b>Round Robin Rounds:</b> {tournament.round_robin_rounds}\n"
            f"🏁 <b>Playoff Starts:</b> {tournament.playoff_starts_at}\n"
            f"📝 <b>Comment:</b> {tournament.comment or 'None'}"
        )

        await callback.message.answer(text)
        await callback.answer()
    except DoesNotExist:
        await callback.answer("Tournament not found", show_alert=True)


@dp.callback_query(F.data.startswith("edit_tournament_"))
async def edit_tournament(callback: types.CallbackQuery):
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
            "number_of_sectors": tournament.number_of_sectors,
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

@dp.callback_query(F.data.startswith("delete_tournament_"))
async def delete_tournament(callback: types.CallbackQuery):
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
        await callback.answer("Tournament deleted")
    except DoesNotExist:
        await callback.answer("Tournament not found", show_alert=True)


@dp.callback_query(F.data == "refresh_tournaments")
async def refresh_tournaments(callback: types.CallbackQuery):
    # Re-run the handle_tournaments function
    await handle_tournaments(callback.message)
    await callback.answer()


@dp.message(Command("get_tournament"))
async def get_tournament(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Admin access required")
        return

    try:
        tournament_id = int(message.text.split()[1])
        tournament = Tournament.get_by_id(tournament_id)

        # Convert datetime to ISO format for the web app
        event_datetime = tournament.event_datetime.isoformat()

        tournament_data = {
            "id": tournament.id,
            "event_name": tournament.event_name,
            "event_datetime": event_datetime,
            "location_name": tournament.location_name,
            "number_of_teams": tournament.number_of_teams,
            "number_of_sectors": tournament.number_of_sectors,
            "players_per_game": tournament.players_per_game,
            "players_registered": tournament.players_registered,
            "round_robin_rounds": tournament.round_robin_rounds,
            "playoff_starts_at": tournament.playoff_starts_at,
            "playoff_seeding": tournament.playoff_seeding,
            "competition_type": tournament.competition_type,
            "comment": tournament.comment,
            "status": tournament.status
        }

        await message.answer(json.dumps(tournament_data))
    except (IndexError, ValueError):
        await message.answer("Usage: /get_tournament <tournament_id>")
    except DoesNotExist:
        await message.answer("Tournament not found")

@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message):
    print("Received WebApp data:", message.web_app_data)

    try:
        data = json.loads(message.web_app_data.data)
        user_id = message.from_user.id

        if not await is_admin(user_id):
            return await message.answer("❌ Admin access required")

        if data['action'] == 'create_tournament':
            # Create new tournament
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
            await message.answer("✅ Tournament created successfully!")

        elif data['action'] == 'update_tournament':
            # Update existing tournament
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
                "number_of_sectors": tournament.number_of_sectors,
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

async def is_admin(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(ADMIN_GROUP_ID, user_id)
        return member is not None
    except:
        return False

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())