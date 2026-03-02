from setup.session_setup import session
from datetime import datetime as dt, timedelta
from datetime import timezone as tz


# Mapping of MLB team abbreviations (as returned by the MLB Stats API) to team IDs.
# Used for schedule lookups which require a numeric team ID.
MLB_TEAM_IDS = {
    'ARI': 109, 'ATL': 144, 'BAL': 110, 'BOS': 111, 'CHC': 112,
    'CWS': 145, 'CIN': 113, 'CLE': 114, 'COL': 115, 'DET': 116,
    'HOU': 117, 'KC':  118, 'LAA': 108, 'LAD': 119, 'MIA': 146,
    'MIL': 158, 'MIN': 142, 'NYM': 121, 'NYY': 147, 'OAK': 133,
    'PHI': 143, 'PIT': 134, 'SD':  135, 'SF':  137, 'SEA': 136,
    'STL': 138, 'TB':  139, 'TEX': 140, 'TOR': 141, 'WSH': 120,
    'ATH': 133,  # Oakland/Sacramento Athletics (relocated).
}

# Game types to include: R=Regular Season, F=Wild Card, D=Division Series,
# L=League Championship Series, W=World Series.
INCLUDED_GAME_TYPES = {'R', 'F', 'D', 'L', 'W'}


def get_games(date):
    """ Loads MLB game data for the provided date.

    Args:
        date (date): Date that game data should be pulled for.

    Returns:
        list: List of dicts of game data.
    """

    games = []

    url = (
        f'https://statsapi.mlb.com/api/v1/schedule'
        f'?sportId=1&date={date.strftime("%Y-%m-%d")}'
        f'&hydrate=linescore,team&gameType=R,F,D,L,W'
    )
    response = session.get(url=url)
    dates = response.json().get('dates', [])

    if not dates:
        return games

    for game in dates[0].get('games', []):
        if game.get('gameType', 'R') not in INCLUDED_GAME_TYPES:
            continue

        abstract_state = game['status']['abstractGameState']  # 'Preview', 'Live', 'Final'
        detailed_state = game['status'].get('detailedState', '')

        # Skip postponed/suspended games.
        if detailed_state in ['Postponed', 'Suspended', 'Cancelled']:
            continue

        has_started = abstract_state in ['Live', 'Final']
        is_complete = abstract_state == 'Final' or detailed_state == 'Game Over'

        teams = game['teams']
        home_team = teams['home']['team']
        away_team = teams['away']['team']

        home_score = int(teams['home'].get('score', 0) or 0)
        away_score = int(teams['away'].get('score', 0) or 0)

        linescore = game.get('linescore', {})
        inning = linescore.get('currentInning', 0)
        is_top_inning = linescore.get('isTopInning', True)
        outs = linescore.get('outs', 0)

        start_utc = dt.strptime(game['gameDate'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=tz.utc)

        games.append({
            'game_id': game['gamePk'],
            'home_abrv': home_team['abbreviation'],
            'away_abrv': away_team['abbreviation'],
            'home_score': home_score,
            'away_score': away_score,
            'start_datetime_utc': start_utc,
            'start_datetime_local': start_utc.astimezone(tz=None),
            'status': abstract_state,
            'has_started': has_started,
            'is_complete': is_complete,
            'inning': inning,
            'is_top_inning': is_top_inning,
            'outs': outs,
            'home_team_scored': False,
            'away_team_scored': False,
            'scoring_team': None
        })

    games = sorted(games, key=lambda x: x['game_id'])
    return games


def get_next_game(team):
    """ Loads next game details for the supplied MLB team.
    If the team is currently playing, will return details of the current game.

    Args:
        team (str): MLB team abbreviation as returned by the stats API (e.g., 'TOR', 'NYY').

    Returns:
        dict or None: Dict of next game details, or None if not found.
    """

    cur_datetime = dt.today().astimezone()
    cur_date = cur_datetime.date()

    team_id = MLB_TEAM_IDS.get(team.upper())
    if not team_id:
        return None

    # Search upcoming 60 days to ensure we find the next game even during offseason gaps.
    end_date = cur_date + timedelta(days=60)
    url = (
        f'https://statsapi.mlb.com/api/v1/schedule'
        f'?sportId=1&teamId={team_id}'
        f'&startDate={cur_date.strftime("%Y-%m-%d")}'
        f'&endDate={end_date.strftime("%Y-%m-%d")}'
        f'&hydrate=team&gameType=R,F,D,L,W'
    )
    response = session.get(url=url)
    dates = response.json().get('dates', [])

    for date_entry in dates:
        for game in date_entry.get('games', []):
            if game.get('gameType', 'R') not in INCLUDED_GAME_TYPES:
                continue

            abstract_state = game['status']['abstractGameState']
            detailed_state = game['status'].get('detailedState', '')

            # Skip postponed or already finished games.
            if detailed_state in ['Postponed', 'Suspended', 'Cancelled']:
                continue
            if abstract_state == 'Final':
                continue

            teams = game['teams']
            home_abrv = teams['home']['team']['abbreviation']
            away_abrv = teams['away']['team']['abbreviation']

            home_or_away = 'home' if home_abrv.upper() == team.upper() else 'away'
            opponent_abrv = away_abrv if home_or_away == 'home' else home_abrv

            start_utc = dt.strptime(game['gameDate'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=tz.utc)
            start_local = start_utc.astimezone(tz=None)

            has_started = abstract_state == 'Live'

            next_game = {
                'home_or_away': home_or_away,
                'opponent_abrv': opponent_abrv,
                'start_datetime_utc': start_utc,
                'start_datetime_local': start_local,
                'is_today': start_local.date() == cur_date or start_local < cur_datetime,
                'has_started': has_started
            }

            # Skip if the game started more than 4 hours ago (longer than an avg MLB game).
            if has_started and (cur_datetime - start_local).total_seconds() > 14400:
                continue

            return next_game

    return None


def get_standings():
    """ Loads current MLB standings by division and by league (AL/NL).

    Returns:
        dict: Dict containing all standings by each category.
    """

    season = determine_current_season()
    url = (
        f'https://statsapi.mlb.com/api/v1/standings'
        f'?leagueId=103,104&season={season}&standingsTypes=regularSeason'
        f'&hydrate=team'
    )
    response = session.get(url=url)
    records = response.json().get('records', [])

    standings = {
        'rank_method': 'Win Percentage',
        'division': {
            'divisions': {
                'American League West':    {'abrv': 'ALW', 'teams': []},
                'American League East':    {'abrv': 'ALE', 'teams': []},
                'American League Central': {'abrv': 'ALC', 'teams': []},
                'National League West':    {'abrv': 'NLW', 'teams': []},
                'National League East':    {'abrv': 'NLE', 'teams': []},
                'National League Central': {'abrv': 'NLC', 'teams': []}
            }
        },
        'league': {
            'leagues': {
                'American League': {'abrv': 'AL', 'teams': []},
                'National League': {'abrv': 'NL', 'teams': []}
            }
        }
    }

    # league_teams accumulates entries for sorting by league rank.
    league_teams = {'American League': [], 'National League': []}

    for record in records:
        div_name = record['division']['name']       # e.g. 'American League West'
        league_name = record['league']['name']      # e.g. 'American League'

        if div_name not in standings['division']['divisions']:
            continue

        for team_record in record.get('teamRecords', []):
            team_abrv = team_record['team']['abbreviation']
            div_rank = int(team_record.get('divisionRank', 0))
            league_rank = int(team_record.get('leagueRank', 0))

            pct_raw = team_record.get('pct', '.000')
            # MLB Stats API returns pct as '.647'; normalise to '0.647'.
            percent = ('0' + pct_raw) if pct_raw.startswith('.') else pct_raw

            has_clinched = bool(team_record.get('clinchIndicator', ''))

            standings['division']['divisions'][div_name]['teams'].append({
                'team_abrv': team_abrv,
                'rank': div_rank,
                'percent': percent,
                'has_clinched': has_clinched
            })

            if league_name in league_teams:
                league_teams[league_name].append({
                    'team_abrv': team_abrv,
                    'rank': league_rank,
                    'percent': percent,
                    'has_clinched': has_clinched
                })

    # Sort each league by rank and populate standings.
    for league_name, teams in league_teams.items():
        teams_sorted = sorted(teams, key=lambda x: x['rank'])
        standings['league']['leagues'][league_name]['teams'] = teams_sorted

    return standings


def determine_current_season():
    """ Determines the current MLB season year.

    Returns:
        int: Season year (e.g., 2024).
    """

    return dt.today().astimezone().date().year
