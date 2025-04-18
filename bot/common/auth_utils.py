from aiogram import Bot
from aiogram.types import ChatMemberMember, ChatMemberLeft, ChatMemberOwner, ChatMemberAdministrator, \
    ChatMemberRestricted

from config import ADMIN_GROUP_ID

async def is_admin(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(ADMIN_GROUP_ID, user_id)
        return isinstance(member, (ChatMemberOwner, ChatMemberAdministrator, ChatMemberMember, ChatMemberRestricted))
    except Exception:
        return False