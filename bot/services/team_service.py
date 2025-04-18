from peewee import DoesNotExist
from database import Team, TeamMember, TeamStatus, User, Tournament
from datetime import datetime


class TeamService:
    @staticmethod
    async def create_team(tournament_id: int, user_id: int, team_name: str):
        """Create a new team with the user as captain and single member"""
        tournament = Tournament.get_by_id(tournament_id)
        user = User.get_by_id(user_id)

        # Create the team
        team = Team.create(
            name=team_name,
            tournament=tournament,
            captain=user,
            status=TeamStatus.REQUESTED,
            create_date=datetime.now()
        )

        # Add user as member
        TeamMember.create(
            team=team,
            user=user,
            join_date=datetime.now()
        )

        return team

    @staticmethod
    async def add_member(team_id: int, phone_number: str):
        """Add a member to team by phone number"""
        try:
            user = User.get(User.phone_number == phone_number)
            team = Team.get_by_id(team_id)

            # Check if user is already in team
            if TeamMember.select().where(
                    (TeamMember.team == team) &
                    (TeamMember.user == user)
            ).exists():
                return False, "User already in team"

            TeamMember.create(
                team=team,
                user=user,
                join_date=datetime.now()
            )
            return True, None
        except DoesNotExist:
            return False, "User not found"

    @staticmethod
    async def remove_member(team_id: int, user_id: int):
        """Remove member from team"""
        try:
            team = Team.get_by_id(team_id)
            user = User.get_by_id(user_id)

            # Can't remove captain
            if team.captain == user:
                return False, "Cannot remove team captain"

            TeamMember.delete().where(
                (TeamMember.team == team) &
                (TeamMember.user == user)
            ).execute()
            return True, None
        except DoesNotExist:
            return False, "Team or user not found"

    @staticmethod
    async def submit_team(team_id: int):
        """Submit team for approval"""
        team = Team.get_by_id(team_id)
        tournament = team.tournament

        # Check member count
        member_count = TeamMember.select().where(TeamMember.team == team).count()
        if member_count < tournament.players_per_game:
            return False, f"Need at least {tournament.players_per_game} members"
        if member_count > tournament.players_registered:
            return False, f"Maximum {tournament.players_registered} members allowed"

        team.status = TeamStatus.REQUESTED
        team.save()
        return True, None

    @staticmethod
    async def approve_team(team_id: int):
        """Approve team enrollment"""
        team = Team.get_by_id(team_id)

        # Check if any members are in other enrolled teams
        for member in team.members:
            other_teams = (
                TeamMember.select()
                .join(Team)
                .where(
                    (TeamMember.user == member.user) &
                    (Team.tournament == team.tournament) &
                    (Team.status == TeamStatus.ENROLLED) &
                    (Team.id != team.id)
                )
            )
            if other_teams.exists():
                return False, f"User {member.user.full_name} is already in another team"

        team.status = TeamStatus.ENROLLED
        team.save()
        return True, None

    @staticmethod
    async def delete_team(team_id: int):
        """Delete team and all members"""
        try:
            team = Team.get_by_id(team_id)
            TeamMember.delete().where(TeamMember.team == team).execute()
            team.delete_instance()
            return True
        except DoesNotExist:
            return False