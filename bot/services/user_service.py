from datetime import datetime
from peewee import DoesNotExist, DatabaseError
from database import User, UserStatus

class UserService:
    @staticmethod
    async def register_user(user_data: dict):
        try:
            User.create(
                id=user_data['user_id'],
                chat_id=user_data['chat_id'],
                username=user_data['username'],
                full_name=user_data['full_name'],
                phone_number=user_data['phone_number'],
                url=user_data.get('url'),
                comment=user_data['comment'],
                status=UserStatus.REQUESTED,
                create_date=datetime.now()
            )
            return True, None
        except DatabaseError as e:
            error_message = str(e)
            if "UNIQUE constraint failed" in error_message:
                return False, "⚠️ You already have a pending registration request!"
            elif "NOT NULL constraint failed" in error_message:
                return False, "⚠️ Missing required information. Please start over."
            return False, f"⚠️ Registration error: {error_message}"

    @staticmethod
    async def update_user_status(user_id: int, status: UserStatus):
        try:
            User.update(status=status).where(User.id == user_id).execute()
            return True
        except DoesNotExist:
            return False

    @staticmethod
    async def delete_user(user_id: int):
        try:
            User.delete().where(User.id == user_id).execute()
            return True
        except DoesNotExist:
            return False

    @staticmethod
    async def get_user(user_id: int):
        try:
            return User.get(User.id == user_id)
        except DoesNotExist:
            return None