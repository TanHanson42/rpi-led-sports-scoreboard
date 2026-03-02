from .games_scene import GamesScene
from setup.matrix_setup import matrix
import data.cfb_data
from utils import data_utils, date_utils

from datetime import datetime as dt
from time import sleep


class CFBGamesScene(GamesScene):
    """ Game scene for CFB. Contains functionality to pull data from ESPN API, parse, and build+display specific images based on the result.
    This class extends the general Scene and GameScene classes. An object of this class type is created when the scoreboard is started.
    """

    def __init__(self):
        """ Defines the league as CFB. Used to identify the correct files when adding logos to images.
        First runs init from the generic GameScene class.
        """

        super().__init__()
        self.LEAGUE = 'CFB'


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
                    'games': data.cfb_data.get_games(dates_to_display[0])
                }

        self.data = {
            'games_previous_pull': self.data['games'] if hasattr(self, 'data') else None,
            'games': data.cfb_data.get_games(dates_to_display[-1]),
        }

        if display_yesterday and self.settings['rollover']['show_completed_games_until_rollover_end_time']:
            if self.settings['splash']['display_splash']:
                self.display_splash_image(len(self.data_previous_day['games']), date=dates_to_display[0])
            self.display_game_images(self.data_previous_day['games'], date=dates_to_display[0])

        # Note if any scores changed since the last data pull.
        if self.data['games_previous_pull']:
            for game in self.data['games']:
                if game['status_state'] != 'pre':
                    prev_matches = [x for x in self.data['games_previous_pull'] if x['game_id'] == game['game_id']]
                    if prev_matches and prev_matches[0]['status_state'] != 'pre':
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
                if game['status_state'] == 'pre':
                    self.build_game_not_started_image(game)
                elif game['status_state'] == 'post':
                    self.build_game_complete_image(game)
                elif game['status_state'] == 'in':
                    self.build_game_in_progress_image(game)
                else:
                    print(f"Unexpected status_state encountered from ESPN API: {game['status_state']}.")

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
        """ Adds current playing period (quarter) to the centre image.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        # Halftime.
        if game['is_halftime']:
            self.draw['centre'].text((0, -1), 'H', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((6, -1), 'a', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((11, -1), 'l', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((15, -1), 'f', font=self.FONTS['med'], fill=self.COLOURS['white'])

        # 1st quarter.
        elif game['period_num'] == 1:
            self.draw['centre'].text((4, -1), '1', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((8, -1), 's', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((12, -1), 't', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # 2nd quarter.
        elif game['period_num'] == 2:
            self.draw['centre'].text((3, -1), '2', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((9, -1), 'n', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((13, -1), 'd', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # 3rd quarter.
        elif game['period_num'] == 3:
            self.draw['centre'].text((3, -1), '3', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((9, -1), 'r', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((13, -1), 'd', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # 4th quarter.
        elif game['period_num'] == 4:
            self.draw['centre'].text((3, -1), '4', font=self.FONTS['med'], fill=self.COLOURS['white'])
            self.draw['centre'].text((8, -1), 't', font=self.FONTS['sm'], fill=self.COLOURS['white'])
            self.draw['centre'].text((13, -1), 'h', font=self.FONTS['sm'], fill=self.COLOURS['white'])

        # Single OT.
        elif game['period_num'] == 5:
            self.draw['centre'].text((4, -1), 'OT', font=self.FONTS['med'], fill=self.COLOURS['white'])

        # 2OT or later (CFB can have multiple OT periods).
        elif game['period_num'] > 5:
            per = f'{game["period_num"] - 4}OT'
            self.draw['centre'].text((1, -1), per, font=self.FONTS['med'], fill=self.COLOURS['white'])


    def add_final_playing_period_to_image(self, game):
        """ Adds final playing period to the centre image if game ended in OT.

        Args:
            game (dict): Dictionary with all details of a specific game.
        """

        if game['period_num'] == 5:
            self.draw['centre'].text((4, 8), 'OT', font=self.FONTS['med'], fill=self.COLOURS['white'])
        elif game['period_num'] > 5:
            per = f'{game["period_num"] - 4}OT'
            self.draw['centre'].text((1, 8), per, font=self.FONTS['med'], fill=self.COLOURS['white'])


    def should_display_time_remaining_in_playing_period(self, game):
        """ Determines if the time remaining should be added to the centre image.

        Args:
            game (dict): Dictionary with all details of a specific game.

        Returns:
            bool: True if time remaining should be displayed.
        """

        return not game['is_halftime']
