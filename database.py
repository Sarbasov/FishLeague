from peewee import *
import datetime

# SQLite database configuration
db = SqliteDatabase('database.sqlite3')

class BaseModel(Model):
    class Meta:
        database = db

class UserStatus:
    REQUESTED = 0
    ACTIVATED = 1
    BLOCKED = -1

class User(BaseModel):
    # Telegram user ID (not auto-incrementing)
    id = BigIntegerField(primary_key=True)

    chat_id = BigIntegerField()  # Store chat_id where bot can message them

    # Telegram username (e.g., @john_doe)
    username = CharField(max_length=100, null=True)

    # Full name from Telegram profile
    full_name = CharField(max_length=50)

    # Full name from Telegram profile
    phone_number = CharField(max_length=20)

    # User Telegram URL field
    url = CharField(max_length=30, null=True)

    # User comment
    comment = CharField(max_length=500)

    # Status: 0=requested, 1=activated, -1=blocked
    status = IntegerField(default=UserStatus.REQUESTED)

    # Auto-set when created
    create_date = DateTimeField(default=datetime.datetime.now)

# Connect and create tables
def initialize_db():
    db.connect()
    db.create_tables([User], safe=True)
    db.close()

if __name__ == '__main__':
    initialize_db()