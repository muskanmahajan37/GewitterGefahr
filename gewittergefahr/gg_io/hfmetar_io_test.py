"""Unit tests for hfmetar_io.py."""

import copy
import unittest
import numpy
from gewittergefahr.gg_io import hfmetar_io

TOLERANCE = 1e-6

OFFLINE_STATION_ID = 'YRL_hfmetar'
POSSIBLE_ONLINE_STATION_IDS = ['CYRL', 'KYRL', 'PYRL', 'TYRL']

UNIX_TIME_SEC_NEG_OFFSET_DIFF_DAYS = 1505443380  # 0243 UTC 15 Sep 2017
LOCAL_TIME_STRING_NEG_OFFSET_DIFF_DAYS = '201709142143'
NEGATIVE_UTC_OFFSET_HOURS_DIFF_DAYS = -5

UNIX_TIME_SEC_NEG_OFFSET_SAME_DAY = 1505443380  # 0243 UTC 15 Sep 2017
LOCAL_TIME_STRING_NEG_OFFSET_SAME_DAY = '201709150043'
NEGATIVE_UTC_OFFSET_HOURS_SAME_DAY = -2

UNIX_TIME_SEC_POS_OFFSET_DIFF_DAYS = 1505512500  # 2155 UTC 15 Sep 2017
LOCAL_TIME_STRING_POS_OFFSET_DIFF_DAYS = '201709160355'
POSITIVE_UTC_OFFSET_HOURS_DIFF_DAYS = 6

UNIX_TIME_SEC_POS_OFFSET_SAME_DAY = 1505443380  # 0243 UTC 15 Sep 2017
LOCAL_TIME_STRING_POS_OFFSET_SAME_DAY = '201709151243'
POSITIVE_UTC_OFFSET_HOURS_SAME_DAY = 10

UNIX_TIME_SEC_ZERO_OFFSET = 1505443380  # 0243 UTC 15 Sep 2017
LOCAL_TIME_STRING_ZERO_OFFSET = '201709150243'

WIND_LINES_5MINUTE = [
    '24156KPIH PIH2011010100440744   0.062 N                             204'
    '    11   208   13                        ',
    '12873KPIE PIE2011010100470547   0.157 N                             121'
    '     8   127    9    17L60+              ',
    '14842KPIA PIA2011010100330633   0.094 N                             260'
    '    11   252   13    13 60+              ',
    '23183KPHX PHX2011010100280728   0.188 N                 0.170 N     267'
    '     4   263    4    07L60+              ',
    '12841KORL ORL2011010100140514   0.221 ^                             128'
    '     4   12>    5                        ']

WIND_ARRAYS_5MINUTE = [
    numpy.array([11., 204., 13., 208.]), numpy.array([8., 121., 9., 127.]),
    numpy.array([11., 260., 13., 252.]), numpy.array([4., 267., 4., 263.]),
    numpy.full(4, numpy.nan)]

WIND_STRING_5MINUTE_PREFIX = (
    '53869KHKA HKA20110306135510303/06/11 13:55:31  5-MIN KHKA 061955Z')

WIND_STRING_5MINUTE_NO_AUTO_NO_GUST = WIND_STRING_5MINUTE_PREFIX + ' 02008KT'
WIND_ARRAY_5MINUTE_NO_AUTO_NO_GUST = numpy.array(
    [8., 20., numpy.nan, numpy.nan])

WIND_STRING_5MINUTE_AUTO_NO_GUST = WIND_STRING_5MINUTE_PREFIX + ' AUTO 02008KT'
WIND_ARRAY_5MINUTE_AUTO_NO_GUST = numpy.array([8., 20., numpy.nan, numpy.nan])

WIND_STRING_5MINUTE_NO_AUTO_WITH_GUST = (
    WIND_STRING_5MINUTE_PREFIX + ' 02008G13KT')
WIND_ARRAY_5MINUTE_NO_AUTO_WITH_GUST = numpy.array([8., 20., 13., numpy.nan])

WIND_STRING_5MINUTE_AUTO_WITH_GUST = (
    WIND_STRING_5MINUTE_PREFIX + ' AUTO 02008G13KT')
WIND_ARRAY_5MINUTE_AUTO_WITH_GUST = numpy.array([8., 20., 13., numpy.nan])

WIND_STRING_5MINUTE_NO_AUTO_TOO_SHORT = copy.deepcopy(
    WIND_STRING_5MINUTE_PREFIX)
WIND_ARRAY_5MINUTE_NO_AUTO_TOO_SHORT = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_AUTO_TOO_SHORT = WIND_STRING_5MINUTE_PREFIX + ' AUTO'
WIND_ARRAY_5MINUTE_AUTO_TOO_SHORT = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_KT_NO_GUST = WIND_STRING_5MINUTE_PREFIX + ' AUTO 02008'
WIND_ARRAY_5MINUTE_NO_KT_NO_GUST = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_DIR_NO_GUST = WIND_STRING_5MINUTE_PREFIX + ' AUTO 08KT'
WIND_ARRAY_5MINUTE_NO_DIR_NO_GUST = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_SPEED_NO_GUST = (
    WIND_STRING_5MINUTE_PREFIX + ' AUTO 020KT')
WIND_ARRAY_5MINUTE_NO_SPEED_NO_GUST = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_KT_WITH_GUST = (
    WIND_STRING_5MINUTE_PREFIX + ' AUTO 02008G13')
WIND_ARRAY_5MINUTE_NO_KT_WITH_GUST = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_DIR_WITH_GUST = (
    WIND_STRING_5MINUTE_PREFIX + ' AUTO 08G13KT')
WIND_ARRAY_5MINUTE_NO_DIR_WITH_GUST = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_SPEED_WITH_GUST = (
    WIND_STRING_5MINUTE_PREFIX + ' AUTO 020G13KT')
WIND_ARRAY_5MINUTE_NO_SPEED_WITH_GUST = numpy.full(4, numpy.nan)

WIND_STRING_5MINUTE_NO_GUST_SPEED = (
    WIND_STRING_5MINUTE_PREFIX + ' AUTO 02008GKT')
WIND_ARRAY_5MINUTE_NO_GUST_SPEED = numpy.full(4, numpy.nan)

STATION_ID = 'CYEG'
MONTH_UNIX_SEC = 1506194267  # Sep 2017
PATHLESS_RAW_1MINUTE_FILE_NAME = '64050CYEG201709.dat'
TOP_DIRECTORY_NAME_RAW_1MINUTE = 'hfmetar/1minute/raw_files'
RAW_1MINUTE_FILE_NAME = 'hfmetar/1minute/raw_files/CYEG/64050CYEG201709.dat'

PATHLESS_RAW_5MINUTE_FILE_NAME = '64010CYEG201709.dat'
TOP_DIRECTORY_NAME_RAW_5MINUTE = 'hfmetar/5minute/raw_files'
RAW_5MINUTE_FILE_NAME = 'hfmetar/5minute/raw_files/CYEG/64010CYEG201709.dat'


class HfmetarIoTests(unittest.TestCase):
    """Each method is a unit test for hfmetar_io.py."""

    def test_station_id_to_online(self):
        """Ensures correct output from _station_id_to_online."""

        these_online_station_ids = hfmetar_io._station_id_to_online(
            OFFLINE_STATION_ID)
        self.assertTrue(these_online_station_ids == POSSIBLE_ONLINE_STATION_IDS)

    def test_local_time_to_unix_neg_offset_diff_days(self):
        """Ensures correct output from _local_time_string_to_unix_sec.

        In this case, local date is before UTC date.
        """

        this_time_unix_sec = hfmetar_io._local_time_string_to_unix_sec(
            LOCAL_TIME_STRING_NEG_OFFSET_DIFF_DAYS,
            NEGATIVE_UTC_OFFSET_HOURS_DIFF_DAYS)
        self.assertTrue(
            this_time_unix_sec == UNIX_TIME_SEC_NEG_OFFSET_DIFF_DAYS)

    def test_local_time_to_unix_neg_offset_same_day(self):
        """Ensures correct output from _local_time_string_to_unix_sec.

        In this case, local date = UTC date but local time < UTC time.
        """

        this_time_unix_sec = hfmetar_io._local_time_string_to_unix_sec(
            LOCAL_TIME_STRING_NEG_OFFSET_SAME_DAY,
            NEGATIVE_UTC_OFFSET_HOURS_SAME_DAY)
        self.assertTrue(this_time_unix_sec == UNIX_TIME_SEC_NEG_OFFSET_SAME_DAY)

    def test_local_time_to_unix_pos_offset_diff_days(self):
        """Ensures correct output from _local_time_string_to_unix_sec.

        In this case, local date is after UTC date.
        """

        this_time_unix_sec = hfmetar_io._local_time_string_to_unix_sec(
            LOCAL_TIME_STRING_POS_OFFSET_DIFF_DAYS,
            POSITIVE_UTC_OFFSET_HOURS_DIFF_DAYS)
        self.assertTrue(
            this_time_unix_sec == UNIX_TIME_SEC_POS_OFFSET_DIFF_DAYS)

    def test_local_time_to_unix_pos_offset_same_day(self):
        """Ensures correct output from _local_time_string_to_unix_sec.

        In this case, local date = UTC date but local time > UTC time.
        """

        this_time_unix_sec = hfmetar_io._local_time_string_to_unix_sec(
            LOCAL_TIME_STRING_POS_OFFSET_SAME_DAY,
            POSITIVE_UTC_OFFSET_HOURS_SAME_DAY)
        self.assertTrue(this_time_unix_sec == UNIX_TIME_SEC_POS_OFFSET_SAME_DAY)

    def test_local_time_to_unix_zero_offset(self):
        """Ensures correct output from _local_time_string_to_unix_sec.

        In this case, local time = UTC time.
        """

        this_time_unix_sec = hfmetar_io._local_time_string_to_unix_sec(
            LOCAL_TIME_STRING_ZERO_OFFSET, 0)
        self.assertTrue(this_time_unix_sec == UNIX_TIME_SEC_ZERO_OFFSET)

    def test_parse_1minute_wind_from_line(self):
        """Ensures correct output from _parse_1minute_wind_from_line."""

        for i in range(len(WIND_LINES_5MINUTE)):
            this_wind_tuple = hfmetar_io._parse_1minute_wind_from_line(
                WIND_LINES_5MINUTE[i])
            this_wind_array = numpy.asarray(this_wind_tuple)

            self.assertTrue(numpy.allclose(
                this_wind_array, WIND_ARRAYS_5MINUTE[i], atol=TOLERANCE,
                equal_nan=True))

    def test_parse_5minute_wind_from_line_no_auto_no_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is properly formatted with no gust.
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_AUTO_NO_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(
            numpy.allclose(this_wind_array, WIND_ARRAY_5MINUTE_NO_AUTO_NO_GUST,
                           atol=TOLERANCE,
                           equal_nan=True))

    def test_parse_5minute_wind_from_line_auto_no_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is properly formatted with no gust.
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_AUTO_NO_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(
            numpy.allclose(this_wind_array, WIND_ARRAY_5MINUTE_AUTO_NO_GUST,
                           atol=TOLERANCE,
                           equal_nan=True))

    def test_parse_5minute_wind_from_line_no_auto_with_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is properly formatted with gust.
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_AUTO_WITH_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_AUTO_WITH_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_auto_with_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is properly formatted with gust.
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_AUTO_WITH_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_AUTO_WITH_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_auto_too_short(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is too short.
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_AUTO_TOO_SHORT)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_AUTO_TOO_SHORT,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_auto_too_short(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is too short.
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_AUTO_TOO_SHORT)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_AUTO_TOO_SHORT,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_kt_no_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (no "KT").
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_KT_NO_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_KT_NO_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_dir_no_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (no direction).
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_DIR_NO_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_DIR_NO_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_speed_no_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (no speed).
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_SPEED_NO_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_SPEED_NO_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_kt_with_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (no "KT").
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_KT_WITH_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_KT_WITH_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_dir_with_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (no direction).
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_DIR_WITH_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_DIR_WITH_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_speed_with_gust(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (no speed).
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_SPEED_WITH_GUST)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_SPEED_WITH_GUST,
                                       atol=TOLERANCE, equal_nan=True))

    def test_parse_5minute_wind_from_line_no_gust_speed(self):
        """Ensures correct output from _parse_5minute_wind_from_line.

        In this case, string is improperly formatted (contains "G" but no gust
        speed).
        """

        this_wind_tuple = hfmetar_io._parse_5minute_wind_from_line(
            WIND_STRING_5MINUTE_NO_GUST_SPEED)
        this_wind_array = numpy.asarray(this_wind_tuple)

        self.assertTrue(numpy.allclose(this_wind_array,
                                       WIND_ARRAY_5MINUTE_NO_GUST_SPEED,
                                       atol=TOLERANCE, equal_nan=True))

    def test_get_pathless_raw_1minute_file_name(self):
        """Ensures correct output from _get_pathless_raw_1minute_file_name."""

        this_pathless_file_name = (
            hfmetar_io._get_pathless_raw_1minute_file_name(STATION_ID,
                                                           MONTH_UNIX_SEC))
        self.assertTrue(
            this_pathless_file_name == PATHLESS_RAW_1MINUTE_FILE_NAME)

    def test_get_pathless_raw_5minute_file_name(self):
        """Ensures correct output from _get_pathless_raw_5minute_file_name."""

        this_pathless_file_name = (
            hfmetar_io._get_pathless_raw_5minute_file_name(STATION_ID,
                                                           MONTH_UNIX_SEC))
        self.assertTrue(
            this_pathless_file_name == PATHLESS_RAW_5MINUTE_FILE_NAME)

    def test_find_local_raw_1minute_file(self):
        """Ensures correct output from find_local_raw_1minute_file."""

        this_file_name = hfmetar_io.find_local_raw_1minute_file(
            station_id=STATION_ID, month_unix_sec=MONTH_UNIX_SEC,
            top_directory_name=TOP_DIRECTORY_NAME_RAW_1MINUTE,
            raise_error_if_missing=False)
        self.assertTrue(this_file_name == RAW_1MINUTE_FILE_NAME)

    def test_find_local_raw_5minute_file(self):
        """Ensures correct output from find_local_raw_5minute_file."""

        this_file_name = hfmetar_io.find_local_raw_5minute_file(
            station_id=STATION_ID, month_unix_sec=MONTH_UNIX_SEC,
            top_directory_name=TOP_DIRECTORY_NAME_RAW_5MINUTE,
            raise_error_if_missing=False)
        self.assertTrue(this_file_name == RAW_5MINUTE_FILE_NAME)


if __name__ == '__main__':
    unittest.main()
