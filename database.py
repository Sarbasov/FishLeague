from peewee import *
import datetime

# SQLite database configuration
db = SqliteDatabase('database.sqlite3')

class BaseModel(Model):
    class Meta:
        database = db

class TournamentStatus:
    DELETED = -1
    SCHEDULED = 0
    ENROLLMENT_COMPLETE = 1
    IN_PROGRESS = 2
    COMPLETED = 3

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


class Tournament(BaseModel):
    id = AutoField()  # Auto-incrementing primary key

    # Basic info
    event_name = CharField(max_length=100)
    event_datetime = DateTimeField()

    # Location
    location_name = CharField(max_length=100)
    latitude = FloatField(null=True)  # For map integration
    longitude = FloatField(null=True)  # For map integration

    # Team structure
    number_of_teams = IntegerField()

    # Player info
    players_registered = IntegerField()  # Total registered players
    players_per_game = IntegerField()  # Active players (others on bench)

    # Tournament structure
    round_robin_rounds = IntegerField()

    # Playoff stage (choices)
    PLAYOFF_STAGES = [
        ('1/16', '1/16 Final'),
        ('1/8', '1/8 Final'),
        ('1/4', 'Quarter Final'),
        ('1/2', 'Semi Final'),
        ('final', 'Final'),
        ('none', 'No Play-off Stage')
    ]
    playoff_starts_at = CharField(choices=PLAYOFF_STAGES, default='none')

    # Seeding method
    SEEDING_METHODS = [
        ('standings', 'Based on Round-Robin Standings'),
        ('random', 'Random Draw')
    ]
    playoff_seeding = CharField(choices=SEEDING_METHODS, default='standings')

    # Competition type
    COMPETITION_TYPES = [
        ('team_only', 'Team Competition Only'),
        ('individual_also', 'Individual Competition Counted')
    ]
    competition_type = CharField(choices=COMPETITION_TYPES, default='team_only')

    # Additional info
    comment = TextField(null=True)  # Unlimited length

    # Status tracking
    status = IntegerField(
        choices=[
            (TournamentStatus.DELETED, 'Deleted'),
            (TournamentStatus.SCHEDULED, 'Scheduled'),
            (TournamentStatus.ENROLLMENT_COMPLETE, 'Enrollment Complete'),
            (TournamentStatus.IN_PROGRESS, 'In Progress'),
            (TournamentStatus.COMPLETED, 'Completed')
        ],
        default=TournamentStatus.SCHEDULED
    )

    # Metadata
    created_at = DateTimeField(default=datetime.datetime.now)
    created_by = ForeignKeyField(User, backref='tournaments')

    @classmethod
    def get_default_rounds(cls) -> int:
        return 10

    @classmethod
    def get_default_playoff_stage(cls) -> str:
        return '1/8'

    @classmethod
    def get_default_players(cls, players_per_game: int) -> int:
        return players_per_game + 1


class TeamStatus:
    REQUESTED = 0
    ENROLLED = 1

class Team(BaseModel):
    id = AutoField()  # Auto-incrementing primary key

    # Team information
    name = CharField(max_length=100)
    is_paid = BooleanField(default=False)

    # Tournament reference (on_delete='RESTRICT' prevents tournament deletion if teams exist)
    tournament = ForeignKeyField(Tournament, backref='teams', on_delete='RESTRICT')

    # Status: 0=requested, 1=enrolled
    status = IntegerField(default=TeamStatus.REQUESTED)

    # Auto-set when created
    create_date = DateTimeField(default=datetime.datetime.now)

# Connect and create tables
def initialize_db():
    db.connect()
    db.create_tables([User, Tournament, Team], safe=True)
    db.close()

if __name__ == '__main__':
    initialize_db()