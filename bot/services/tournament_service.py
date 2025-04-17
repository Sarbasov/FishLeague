from datetime import datetime
from peewee import DoesNotExist
from database import Tournament, TournamentStatus

class TournamentService:
    @staticmethod
    async def create_tournament(data: dict, created_by: int):
        return Tournament.create(
            event_name=data['event_name'],
            event_datetime=datetime.fromisoformat(data['event_datetime']),
            location_name=data['location_name'],
            number_of_teams=data['number_of_teams'],
            players_per_game=data['players_per_game'],
            players_registered=data['players_registered'],
            round_robin_rounds=data['round_robin_rounds'],
            playoff_starts_at=data['playoff_starts_at'],
            playoff_seeding=data['playoff_seeding'],
            competition_type=data['competition_type'],
            comment=data['comment'],
            created_by=created_by,
            status=TournamentStatus.SCHEDULED
        )

    @staticmethod
    async def update_tournament(data: dict):
        return Tournament.update(
            event_name=data['event_name'],
            event_datetime=datetime.fromisoformat(data['event_datetime']),
            location_name=data['location_name'],
            number_of_teams=data['number_of_teams'],
            players_per_game=data['players_per_game'],
            players_registered=data['players_registered'],
            round_robin_rounds=data['round_robin_rounds'],
            playoff_starts_at=data['playoff_starts_at'],
            playoff_seeding=data['playoff_seeding'],
            competition_type=data['competition_type'],
            comment=data['comment']
        ).where(Tournament.id == data['id']).execute()

    @staticmethod
    async def delete_tournament(tournament_id: int):
        try:
            tournament = Tournament.get_by_id(tournament_id)
            tournament.delete_instance()
            return True
        except DoesNotExist:
            return False

    @staticmethod
    async def get_tournament(tournament_id: int):
        try:
            return Tournament.get_by_id(tournament_id)
        except DoesNotExist:
            return None

    @staticmethod
    async def list_tournaments():
        return Tournament.select().order_by(Tournament.event_datetime.desc())