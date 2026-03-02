from .games_scene import GamesScene
from setup.matrix_setup import matrix
import data.mlb_data
from utils import data_utils, date_utils

from datetime import datetime as dt
from time import sleep


class MLBGamesScene(GamesScene):
    """ Game scene for the MLB. Contains functionality to pull data from the MLB Stats API, parse, and build+display specific images based on the result.
    This class extends the general Scene and GameScene classes. An object of this class type is created when the scoreboard is started.
    """

    def __init__(self):
        """ Defines the league as MLB. Used to identify the correct files when adding logos to images.
        First runs init from the generic GameScene class.
        """

        super().__init__()
        self.LEAGUE = 'MLB'


    def display_scene(self):
        """ Displays the scene on the matrix.
        Includes logic on which image to build, when to display, etc.
        """

        # Refresh config and load to settings key.
        self.settings = data_utils.read_yaml('config.yaml')['scene_settings'][self.LEAGUE.lower()]['games']
        self.alt_logos = data_utils.read_yaml('config.yaml')['alt_logos'][self.LEAGUE.lower()] if data_utils.read_yaml('config.yaml')['alt_logos'][self.LEAGUE.lower()] else {}

        # Determine which days should be displayed.
        dates_to_display = date_utils.determine_dates_to_display_games(self.settings['rollover']['rollover_start_time_local'], self.settings['rollover']['rollover_end_time_local'])
        display_yesterday = True if len(dates_to_display) == 2 else False

        if display_yesterday:
            if (hasattr(self, 'data_previous_day') and self.data_previous_day['saved_date'] != dates_to_display[0]) or not hasattr(self, 'data_previous_day'):
                self.data_previous_day = {
                    'saved_date': dates_to_display[0],
                    'games': data.mlb_data.get_games(dates_to_display[0])
                }

        self.data = {
            'games_previous_pull': self.data['games'] if hasattr(self, 'data') else None,
            'games': data.mlb_data.get_games(dates_to_display[-1]),
        }

        if display_yesterday and self.settings['rollover']['show_completed_games_until_rollover_end_time']:
            if self.settings['splash']['display_splash']:
                self.display_splash_image(len(self.data_previous_day['games']), date=dates_to_display[0])
            self.display_game_images(self.data_previous_day['games'], date=dates_to_display[0])

        # Note if any scores changed since the last data pull.
        if self.data['games_previous_pull']:
            for game in self.data['games']:
                if game['has_started']:
                    prev_matches = [x for x in self.data['games_previous_pull'] if x['game_id'] == game['game_id']]
                    if prev_matches and prev_matches[0]['has_started']:
                        matched_game = prev_matches[0]
                        game['away_team_scored'] = True if game['away_score'] > matched_game['away_score'] else False
                        game['home_team_scored'] = True if game['home_score'] > matched_game['home_score'] else False

                        if game['away_team_scored'] and game['home_team_scored']:
                            game['scoring_team'] = 'both'
                        elif game['away_team_scored']:
                            game['scoring_team'] = 'away'
                        elif game['home_team_scored']:
                            game['scoring_team'] = 'home'

        if self.settings['splash']['display_splash']:
            self.display_splash_image(len(self.data['games']), date=dates_to_display[-1])

        self.display_game_images(self.data['games'], date=dates_to_display[-1])


    def display_splash_image(self, num_games, date):
        """ Builds and displays splash screen for games on date. """

        self.build_splash_image(num_games, date)
        self.transition_image(direction='in', image_already_combined=True)
        sleep(self.settings['splash']['splash_display_duration'])
        self.transition_image(direction='out', image_already_combined=True)


    def display_game_images(self, games, date=None):
        """ Builds and displays images on the matrix for each game in games. """

        if games:
            for game in games:
                if not game['has_started']:
                    self.build_game_not_started_image(game)
                elif game['is_complete']:
                    self.build_game_complete_image(game)
                else:
                    self.build_game_in_progress_image(game)

                self.transition_image(direction='in')

                if self.settings['score_alerting']['score_coloured'] and self.settings['score_alerting']['score_fade_animation']:
                    if game['scoring_team']:
                        self.fade_score_change(game)

                sleep(self.settings['game_display_duration'])
                self.transition_image(direction='out')

        elif not self.settings['splash']['display_splash']:
            self.build_no_games_image(date)
            self.transition_image(direction='in', image_already_combined=True)
            sleep(self.settings['game_display_duration'])
            self.transition_image(direction='out', image_already_combined=True)


    def add_playing_period_to_image(self, game):
        """ Adds current inning and outs to the centre image.
        MLB has no game clock; outs count is displayed instead of time remaining.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # Top/Bottom inning indicator ('T' or 'B').
        half_char = 'T' if game['is_top_inning'] else 'B'
        self.draw['centre'].text((1, -1), half_char, font=self.FONTS['med'], fill=self.COLOURS['white'])

        # Inning number.
        inning_str = str(game['inning']) if game['inning'] > 0 else '1'
        if len(inning_str) == 1:
            self.draw['centre'].text((8, -1), inning_str, font=self.FONTS['med'], fill=self.COLOURS['white'])
        else:
            self.draw['centre'].text((7, -1), inning_str, font=self.FONTS['med'], fill=self.COLOURS['white'])

        # Outs count in place of where time remaining would appear.
        self.draw['centre'].text((4, 8), str(game['outs']), font=self.FONTS['med'], fill=self.COLOURS['white'])
        self.draw['centre'].text((10, 10), 'O', font=self.FONTS['sm'], fill=self.COLOURS['white'])


    def add_final_playing_period_to_image(self, game):
        """ Adds final inning to the centre image if the game went to extra innings.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # Only display inning suffix if the game went beyond the 9th.
        if game.get('inning', 9) > 9:
            self.draw['centre'].text((2, 8), f'/{game["inning"]}', font=self.FONTS['med'], fill=self.COLOURS['white'])


    def should_display_time_remaining_in_playing_period(self, game):
        """ Baseball has no game clock, so time is never displayed during play.

        Args:
            game (dict): Dictionary with all details of a specific game.

        Returns:
            bool: Always False for MLB.
        """

        return False
