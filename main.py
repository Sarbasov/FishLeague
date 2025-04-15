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
        await state.set_state(Registration.waiting_for_phone)


@dp.message(Registration.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone_number=message.contact.phone_number)
    default_name = message.from_user.full_name or "Unknown User"

    await message.answer(
        f"👤 Please confirm your full name (default: {default_name}):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=f"✅ Use {default_name}")]
            ],
            resize_keyboard=True
        )
    )
    await state.update_data(default_name=default_name)
    await state.set_state(Registration.waiting_for_full_name)


@dp.message(Registration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    data = await state.get_data()
    full_name = data['default_name'] if message.text.startswith("✅ Use") else message.text

    if len(full_name) > 50:
        await message.answer("❌ Name too long (max 50 chars). Try again:")
        return

    await state.update_data(full_name=full_name)
    await message.answer("📝 Please enter your comment:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.waiting_for_comment)


@dp.message(Registration.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()

    try:
        User.create(
            id=message.from_user.id,
            username=message.from_user.username,
            full_name=data['full_name'],
            phone_number=data['phone_number'],
            url=message.from_user.url,
            comment=message.text,
            status=UserStatus.REQUESTED,
            create_date=datetime.now()
        )
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

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())