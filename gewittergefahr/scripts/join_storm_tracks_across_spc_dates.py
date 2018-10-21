"""Joins storm tracks across SPC dates.

This gets rid of the cutoff at 1200 UTC of each day.
"""

import argparse
from gewittergefahr.gg_utils import radar_utils
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import echo_top_tracking

TIME_FORMAT = '%Y-%m-%d-%H%M%S'
MYRORSS_START_TIME_STRING = '1990-01-01-000000'
MYRORSS_END_TIME_STRING = '2012-01-01-000813'

MYRORSS_START_TIME_UNIX_SEC = time_conversion.string_to_unix_sec(
    MYRORSS_START_TIME_STRING, TIME_FORMAT)
MYRORSS_END_TIME_UNIX_SEC = time_conversion.string_to_unix_sec(
    MYRORSS_END_TIME_STRING, TIME_FORMAT)

FIRST_SPC_DATE_ARG_NAME = 'first_spc_date_string'
LAST_SPC_DATE_ARG_NAME = 'last_spc_date_string'
RADAR_SOURCE_ARG_NAME = 'radar_source'
FOR_CLIMATOLOGY_ARG_NAME = 'for_storm_climatology'
ORIG_TRACKING_DIR_ARG_NAME = 'orig_tracking_dir_name'
NEW_TRACKING_DIR_ARG_NAME = 'new_tracking_dir_name'
START_TIME_ARG_NAME = 'start_time_string'
END_TIME_ARG_NAME = 'end_time_string'

SPC_DATE_HELP_STRING = (
    'SPC (Storm Prediction Center) date in format "yyyymmdd".  Tracks will be '
    'joined across all dates from `{0:s}`...`{1:s}`.'
).format(FIRST_SPC_DATE_ARG_NAME, LAST_SPC_DATE_ARG_NAME)

RADAR_SOURCE_HELP_STRING = (
    'Source of radar data.  Must be in the following list:\n{0:s}'
).format(str(radar_utils.DATA_SOURCE_IDS))

FOR_CLIMATOLOGY_HELP_STRING = (
    'Boolean flag.  If 1, tracks joined will be used for storm climatology, in '
    'which case the tracking period will be set to `{0:s}`...`{1:s}`.  If 0, '
    'the tracking period will just be the period on which this script operates.'
).format(MYRORSS_START_TIME_STRING, MYRORSS_END_TIME_STRING)

ORIG_TRACKING_DIR_HELP_STRING = (
    'Name of top-level directory with original storm tracks (before joining).')

NEW_TRACKING_DIR_HELP_STRING = (
    'Name of top-level directory for new storm tracks (after joining).')

START_TIME_HELP_STRING = (
    'Start time (format "yyyy-mm-dd-HHMMSS") of period to be processed.  This '
    'time must be in the first SPC date, given by `{0:s}`.  If "None", will '
    'default to the start of the first SPC date.'
).format(FIRST_SPC_DATE_ARG_NAME)

END_TIME_HELP_STRING = (
    'End time (format "yyyy-mm-dd-HHMMSS") of period to be processed.  This '
    'time must be in the last SPC date, given by `{0:s}`.  If "None", will '
    'default to the end of the last SPC date.'
).format(LAST_SPC_DATE_ARG_NAME)

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + FIRST_SPC_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + LAST_SPC_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + RADAR_SOURCE_ARG_NAME, type=str, required=False,
    default=radar_utils.MYRORSS_SOURCE_ID, help=RADAR_SOURCE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FOR_CLIMATOLOGY_ARG_NAME, type=int, required=False,
    default=0, help=FOR_CLIMATOLOGY_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + ORIG_TRACKING_DIR_ARG_NAME, type=str, required=True,
    help=ORIG_TRACKING_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NEW_TRACKING_DIR_ARG_NAME, type=str, required=True,
    help=NEW_TRACKING_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + START_TIME_ARG_NAME, type=str, required=False, default='None',
    help=START_TIME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + END_TIME_ARG_NAME, type=str, required=False, default='None',
    help=END_TIME_HELP_STRING)

if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()
    RADAR_SOURCE_NAME = getattr(INPUT_ARG_OBJECT, RADAR_SOURCE_ARG_NAME)
    FOR_STORM_CLIMATOLOGY = bool(
        getattr(INPUT_ARG_OBJECT, FOR_CLIMATOLOGY_ARG_NAME))

    if (FOR_STORM_CLIMATOLOGY and
            RADAR_SOURCE_NAME == radar_utils.MYRORSS_SOURCE_ID):
        TRACKING_START_TIME_UNIX_SEC = MYRORSS_START_TIME_UNIX_SEC + 0
        TRACKING_END_TIME_UNIX_SEC = MYRORSS_END_TIME_UNIX_SEC + 0
    else:
        TRACKING_START_TIME_UNIX_SEC = None
        TRACKING_END_TIME_UNIX_SEC = None

    START_TIME_STRING = getattr(INPUT_ARG_OBJECT, START_TIME_ARG_NAME)
    END_TIME_STRING = getattr(INPUT_ARG_OBJECT, END_TIME_ARG_NAME)

    if START_TIME_STRING == 'None' and END_TIME_STRING == 'None':
        START_TIME_UNIX_SEC = None
        END_TIME_UNIX_SEC = None
    else:
        START_TIME_UNIX_SEC = time_conversion.string_to_unix_sec(
            START_TIME_STRING, TIME_FORMAT)
        END_TIME_UNIX_SEC = time_conversion.string_to_unix_sec(
            END_TIME_STRING, TIME_FORMAT)

    echo_top_tracking.join_tracks_across_spc_dates(
        first_spc_date_string=getattr(
            INPUT_ARG_OBJECT, FIRST_SPC_DATE_ARG_NAME),
        last_spc_date_string=getattr(INPUT_ARG_OBJECT, LAST_SPC_DATE_ARG_NAME),
        top_input_dir_name=getattr(
            INPUT_ARG_OBJECT, ORIG_TRACKING_DIR_ARG_NAME),
        top_output_dir_name=getattr(
            INPUT_ARG_OBJECT, NEW_TRACKING_DIR_ARG_NAME),
        start_time_unix_sec=START_TIME_UNIX_SEC,
        end_time_unix_sec=END_TIME_UNIX_SEC,
        tracking_start_time_unix_sec=TRACKING_START_TIME_UNIX_SEC,
        tracking_end_time_unix_sec=TRACKING_END_TIME_UNIX_SEC)
