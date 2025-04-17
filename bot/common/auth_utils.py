from aiogram import Bot
from config import ADMIN_GROUP_ID

async def is_admin(bot: Bot, user_id: int) -> bool:
    """Check if user is admin in the admin group"""
    try:
        member = await bot.get_chat_member(ADMIN_GROUP_ID, user_id)
        return member is not None
    except Exception:
        return False