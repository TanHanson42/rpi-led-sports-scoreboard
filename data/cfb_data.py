from setup.session_setup import session
from datetime import datetime as dt
from datetime import timezone as tz


def get_games(date):
    """ Loads CFB game data for the provided date (FBS only).

    Args:
        date (date): Date that game data should be pulled for.

    Returns:
        list: List of dicts of game data.
    """

    games = []

    # groups=80 limits results to FBS teams.
    url = f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={date.strftime("%Y%m%d")}&groups=80&limit=100'
    response = session.get(url=url)
    events = response.json().get('events', [])

    for event in events:
        competition = event['competitions'][0]
        season_type = event.get('season', {}).get('type', 0)

        # Only regular season (2) and postseason (3) games.
        if season_type not in [2, 3]:
            continue

        home_comp = next(c for c in competition['competitors'] if c['homeAway'] == 'home')
        away_comp = next(c for c in competition['competitors'] if c['homeAway'] == 'away')

        status = competition['status']
        status_name = status['type']['name']
        status_state = status['type']['state']  # 'pre', 'in', 'post'
        period = status.get('period', 0)
        period_type = 'OT' if period > 4 else 'Std'
        is_halftime = status_name == 'STATUS_HALFTIME'
        has_started = status_state in ['in', 'post']

        start_utc = dt.strptime(competition['date'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=tz.utc)

        # Pad clock to 5-char MM:SS so add_time_to_image works correctly.
        raw_clock = status.get('displayClock', '0:00')
        if raw_clock and ':' in raw_clock:
            mins, secs = raw_clock.split(':', 1)
            period_time_remaining = mins.zfill(2) + ':' + secs
        else:
            period_time_remaining = '00:00'

        games.append({
            'game_id': event['id'],
            'home_abrv': home_comp['team']['abbreviation'],
            'away_abrv': away_comp['team']['abbreviation'],
            'home_score': int(home_comp.get('score') or 0),
            'away_score': int(away_comp.get('score') or 0),
            'start_datetime_utc': start_utc,
            'start_datetime_local': start_utc.astimezone(tz=None),
            'status': status_name,
            'status_state': status_state,
            'has_started': has_started,
            'period_num': period,
            'period_type': period_type,
            'period_time_remaining': period_time_remaining,
            'is_halftime': is_halftime,
            'home_team_scored': False,
            'away_team_scored': False,
            'scoring_team': None
        })

    games = sorted(games, key=lambda x: x['game_id'])
    return games


def get_next_game(team):
    """ Loads next game details for the supplied CFB team.
    If the team is currently playing, will return details of the current game.

    Args:
        team (str): ESPN team abbreviation (e.g., 'BAMA', 'OSU', 'MICH').

    Returns:
        dict or None: Dict of next game details, or None if not found.
    """

    cur_datetime = dt.today().astimezone()
    cur_date = cur_datetime.date()
    year = determine_current_season()

    team_id = _get_espn_team_id(team)
    if not team_id:
        return None

    url = f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{team_id}/schedule?season={year}'
    response = session.get(url=url)
    events = response.json().get('events', [])

    for event in events:
        competition = event['competitions'][0]
        season_type = event.get('season', {}).get('type', 0)

        if season_type not in [2, 3]:
            continue

        status_state = competition['status']['type']['state']
        is_completed = competition['status']['type'].get('completed', False)

        # Skip games that are fully complete.
        if status_state == 'post' and is_completed:
            continue

        home_comp = next(c for c in competition['competitors'] if c['homeAway'] == 'home')
        away_comp = next(c for c in competition['competitors'] if c['homeAway'] == 'away')

        start_utc = dt.strptime(competition['date'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=tz.utc)
        start_local = start_utc.astimezone(tz=None)

        home_abrv = home_comp['team']['abbreviation']
        away_abrv = away_comp['team']['abbreviation']
        home_or_away = 'home' if home_abrv.upper() == team.upper() else 'away'
        opponent_abrv = away_abrv if home_or_away == 'home' else home_abrv

        has_started = status_state == 'in'

        next_game = {
            'home_or_away': home_or_away,
            'opponent_abrv': opponent_abrv,
            'start_datetime_utc': start_utc,
            'start_datetime_local': start_local,
            'is_today': start_local.date() == cur_date or start_local < cur_datetime,
            'has_started': has_started
        }

        # Skip if the game started more than 4 hours ago (longer than an avg CFB game).
        if has_started and (cur_datetime - start_local).total_seconds() > 14400:
            continue

        return next_game

    return None


def get_standings():
    """ Loads current CFB standings by conference (FBS only).

    Returns:
        dict: Dict containing standings grouped by conference.
    """

    year = determine_current_season()
    # group=80 = FBS.
    url = f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/standings?season={year}&group=80'
    response = session.get(url=url)
    data = response.json()

    standings = {
        'rank_method': 'Win Percentage',
        'conference': {
            'conferences': {}  # Populated dynamically from API response.
        }
    }

    # Conference abbreviation overrides for display in sidebar (max ~4 chars fits best).
    conf_abrv_map = {
        'Southeastern Conference': 'SEC',
        'Big Ten Conference': 'B10',
        'Big 12 Conference': 'B12',
        'Atlantic Coast Conference': 'ACC',
        'American Athletic Conference': 'AAC',
        'Mountain West Conference': 'MWC',
        'Conference USA': 'CUSA',
        'Sun Belt Conference': 'SBC',
        'Mid-American Conference': 'MAC',
        'FBS Independents': 'Ind',
        'Pac-12 Conference': 'P12',
    }

    for conf_group in data.get('children', []):
        conf_name = conf_group.get('name', '')
        conf_abrv = conf_abrv_map.get(conf_name, conf_name[:4])

        standings['conference']['conferences'][conf_name] = {
            'abrv': conf_abrv,
            'teams': []
        }

        entries = conf_group.get('standings', {}).get('entries', [])
        for conf_rank, entry in enumerate(entries, start=1):
            team_abrv = entry['team']['abbreviation']
            stats = entry.get('stats', [])

            win_pct = _get_stat_value(stats, 'winPercent') or 0.0
            has_clinched = _stat_has_display_value(stats, 'clincher')
            percent = f'{float(win_pct):.3f}'

            standings['conference']['conferences'][conf_name]['teams'].append({
                'team_abrv': team_abrv,
                'rank': conf_rank,
                'percent': percent,
                'has_clinched': has_clinched
            })

    return standings


def determine_current_season():
    """ Determines the current CFB season year.

    Returns:
        int: Season year (e.g., 2024).
    """

    cur_date = dt.today().astimezone().date()
    # CFB season runs August–January. Season year = year season starts.
    return cur_date.year if cur_date.month >= 8 else cur_date.year - 1


def _get_espn_team_id(team_abrv):
    """ Looks up ESPN team ID from team abbreviation via the ESPN teams API.

    Args:
        team_abrv (str): ESPN team abbreviation (e.g., 'BAMA', 'OSU').

    Returns:
        str or None: ESPN team ID, or None if not found.
    """

    url = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=1000'
    response = session.get(url=url)
    sports = response.json().get('sports', [])

    for sport in sports:
        for league in sport.get('leagues', []):
            for team_entry in league.get('teams', []):
                t = team_entry.get('team', {})
                if t.get('abbreviation', '').upper() == team_abrv.upper():
                    return t['id']
    return None


def _get_stat_value(stats, name):
    """ Extracts a numeric stat value from an ESPN stats array by name. """
    for stat in stats:
        if stat.get('name') == name:
            return stat.get('value')
    return None


def _stat_has_display_value(stats, name):
    """ Returns True if a stat exists in the array with a non-empty displayValue. """
    for stat in stats:
        if stat.get('name') == name:
            return bool(stat.get('displayValue', ''))
    return False
