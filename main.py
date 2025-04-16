import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import User, initialize_db, UserStatus
from peewee import DoesNotExist, IntegrityError, DatabaseError
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove

print("Starting bot")

# Initialize bot with new default properties syntax
bot = Bot(
    token='7477173505:AAHKk5OYXSFyXIfa7fKdLRZxOEeCYmJZX_M',
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
    admin_chat_id = -4617714875  # group ID of admin group FishingLeagueAdmins

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
        chat_id=admin_chat_id,
        text=f"📨 New Registration Request:\n"
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

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())