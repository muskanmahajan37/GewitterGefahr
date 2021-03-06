"""Removes storms that pass outside continental United States (CONUS)."""

import argparse
import numpy
import pandas
from gewittergefahr.gg_utils import conus_boundary
from gewittergefahr.gg_utils import temporal_tracking
from gewittergefahr.gg_utils import echo_top_tracking
from gewittergefahr.gg_utils import storm_tracking_utils as tracking_utils
from gewittergefahr.gg_utils import longitude_conversion as lng_conversion

SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

INPUT_DIR_ARG_NAME = 'input_tracking_dir_name'
FIRST_DATE_ARG_NAME = 'first_spc_date_string'
LAST_DATE_ARG_NAME = 'last_spc_date_string'
MAX_LINK_DISTANCE_ARG_NAME = 'max_link_distance_metres'
MAX_LEAD_TIME_ARG_NAME = 'max_lead_time_sec'
OUTPUT_DIR_ARG_NAME = 'output_tracking_dir_name'

INPUT_DIR_HELP_STRING = (
    'Name of top-level input directory.  Files therein will be found by '
    '`storm_tracking_io.find_file` and read by `storm_tracking_io.read_file`.'
)
SPC_DATE_HELP_STRING = (
    'SPC date (format "yyyymmdd").  This script will filter storms for the '
    'period `{0:s}`...`{1:s}`.'
).format(FIRST_DATE_ARG_NAME, LAST_DATE_ARG_NAME)

MAX_LINK_DISTANCE_HELP_STRING = (
    'Max linkage distance that you plan to use for storm hazards.  See doc for '
    '`{0:s}` for more details.'
).format(MAX_LEAD_TIME_ARG_NAME)

MAX_LEAD_TIME_HELP_STRING = (
    'Max lead time that you plan to use for storm hazards.  Will get rid of all'
    ' storm objects with a successor in the next `{0:s}` seconds that passes '
    'within `{1:s}` of the CONUS boundary.'
).format(MAX_LEAD_TIME_ARG_NAME, MAX_LINK_DISTANCE_ARG_NAME)

OUTPUT_DIR_HELP_STRING = (
    'Name of top-level output directory.  Files with filtered storms will be '
    'written by `storm_tracking_io.write_file` to exact locations determined by'
    ' `storm_tracking_io.find_file`.'
)

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + INPUT_DIR_ARG_NAME, type=str, required=True,
    help=INPUT_DIR_HELP_STRING
)
INPUT_ARG_PARSER.add_argument(
    '--' + FIRST_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING
)
INPUT_ARG_PARSER.add_argument(
    '--' + LAST_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING
)
INPUT_ARG_PARSER.add_argument(
    '--' + MAX_LINK_DISTANCE_ARG_NAME, type=float, required=False,
    default=30000, help=MAX_LINK_DISTANCE_HELP_STRING
)
INPUT_ARG_PARSER.add_argument(
    '--' + MAX_LEAD_TIME_ARG_NAME, type=int, required=False,
    default=3600, help=MAX_LEAD_TIME_HELP_STRING
)
INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=True,
    help=OUTPUT_DIR_HELP_STRING
)


def _handle_one_storm_cell(
        storm_object_table, primary_id_string, conus_latitudes_deg,
        conus_longitudes_deg, max_lead_time_sec):
    """Handles (either keeps or removes) one storm cell.

    In this case, a "storm cell" is a group of storm objects with the same
    primary ID.

    V = number of vertices in CONUS boundary

    :param storm_object_table: pandas DataFrame with columns listed in doc for
        `storm_tracking_io.write_file`.
    :param primary_id_string: Primary ID of storm cell.
    :param conus_latitudes_deg: length-V numpy array of latitudes (deg N) in
        boundary.
    :param conus_longitudes_deg: length-V numpy array of longitudes (deg E) in
        boundary.
    :param max_lead_time_sec: See documentation at top of file.
    :return: bad_object_indices: 1-D numpy array with indices of bad storm
        objects (those with successor outside CONUS).  These are row indices for
        `storm_object_table`.
    """

    object_in_cell_indices = numpy.where(
        storm_object_table[tracking_utils.PRIMARY_ID_COLUMN].values ==
        primary_id_string
    )[0]

    query_latitudes_deg = []
    query_longitudes_deg = []
    query_object_indices = []
    num_storm_objects = len(object_in_cell_indices)

    for i in range(num_storm_objects):
        j = object_in_cell_indices[i]

        this_polygon_object = (
            storm_object_table[tracking_utils.LATLNG_POLYGON_COLUMN].values[j]
        )
        these_latitudes_deg = numpy.array(this_polygon_object.exterior.xy[1])
        these_longitudes_deg = numpy.array(this_polygon_object.exterior.xy[0])

        # Find northeasternmost point in storm boundary.
        this_index = numpy.argmax(these_latitudes_deg + these_longitudes_deg)
        query_latitudes_deg.append(these_latitudes_deg[this_index])
        query_longitudes_deg.append(these_longitudes_deg[this_index])
        query_object_indices.append(j)

        # Find southwesternmost point in storm boundary.
        this_index = numpy.argmin(these_latitudes_deg + these_longitudes_deg)
        query_latitudes_deg.append(these_latitudes_deg[this_index])
        query_longitudes_deg.append(these_longitudes_deg[this_index])
        query_object_indices.append(j)

        # Find northwesternmost point in storm boundary.
        this_index = numpy.argmax(these_latitudes_deg - these_longitudes_deg)
        query_latitudes_deg.append(these_latitudes_deg[this_index])
        query_longitudes_deg.append(these_longitudes_deg[this_index])
        query_object_indices.append(j)

        # Find northeasternmost point in storm boundary.
        this_index = numpy.argmax(these_longitudes_deg - these_latitudes_deg)
        query_latitudes_deg.append(these_latitudes_deg[this_index])
        query_longitudes_deg.append(these_longitudes_deg[this_index])
        query_object_indices.append(j)

    query_latitudes_deg = numpy.array(query_latitudes_deg)
    query_longitudes_deg = numpy.array(query_longitudes_deg)
    query_object_indices = numpy.array(query_object_indices, dtype=int)

    in_conus_flags = conus_boundary.find_points_in_conus(
        conus_latitudes_deg=conus_latitudes_deg,
        conus_longitudes_deg=conus_longitudes_deg,
        query_latitudes_deg=query_latitudes_deg,
        query_longitudes_deg=query_longitudes_deg,
        use_shortcuts=True, verbose=False
    )

    if numpy.all(in_conus_flags):
        return numpy.array([], dtype=int)

    first_bad_index = numpy.where(numpy.invert(in_conus_flags))[0][0]
    first_bad_longitude_deg = -1 * lng_conversion.convert_lng_negative_in_west(
        query_longitudes_deg[first_bad_index]
    )
    print('Point ({0:.1f} deg N, {1:.1f} deg W) is not in CONUS!'.format(
        query_latitudes_deg[first_bad_index], first_bad_longitude_deg
    ))

    object_not_in_conus_indices = numpy.unique(
        query_object_indices[in_conus_flags == False]
    )
    bad_object_indices = numpy.array([], dtype=int)

    for i in object_not_in_conus_indices:
        these_indices = temporal_tracking.find_predecessors(
            storm_object_table=storm_object_table, target_row=i,
            num_seconds_back=max_lead_time_sec, max_num_sec_id_changes=1,
            return_all_on_path=True)

        bad_object_indices = numpy.concatenate((
            bad_object_indices, these_indices
        ))

    return numpy.unique(bad_object_indices)


def _filter_storms_one_day(
        storm_object_table_by_date, spc_date_strings, target_date_index,
        conus_latitudes_deg, conus_longitudes_deg, max_lead_time_sec):
    """Filters storms for one day.

    D = number of days

    :param storm_object_table_by_date: length-D list of pandas DataFrames.  See
        `storm_tracking_io.write_file` for list of columns in each DataFrame.
    :param spc_date_strings: length-D list of SPC dates (format "yyyymmdd").
    :param target_date_index: Target date.  Will remove storms on the [i]th
        date, where i = `target_date_index`.
    :param conus_latitudes_deg: See doc for `_handle_one_storm_cell`.
    :param conus_longitudes_deg: Same.
    :param max_lead_time_sec: See documentation at top of file.
    :return: storm_object_table_by_date: Same as input but possibly with fewer
        storms.
    """

    indices_to_concat = numpy.array([
        target_date_index - 1, target_date_index, target_date_index + 1
    ], dtype=int)

    num_spc_dates = len(storm_object_table_by_date)
    indices_to_concat = indices_to_concat[indices_to_concat >= 0]
    indices_to_concat = indices_to_concat[indices_to_concat < num_spc_dates]

    concat_storm_object_table = pandas.concat(
        [storm_object_table_by_date[k] for k in indices_to_concat],
        axis=0, ignore_index=True
    )

    primary_id_strings = numpy.unique(
        storm_object_table_by_date[target_date_index][
            tracking_utils.PRIMARY_ID_COLUMN
        ].values
    )

    orig_num_storm_objects = len(
        storm_object_table_by_date[target_date_index].index
    )

    num_storm_cells = len(primary_id_strings)
    bad_object_indices = numpy.array([], dtype=int)

    for j in range(num_storm_cells):
        if numpy.mod(j, 10) == 0:
            print((
                'Have tried {0:d} of {1:d} storm cells for SPC date "{2:s}"...'
            ).format(
                j, num_storm_cells, spc_date_strings[target_date_index]
            ))

        these_indices = _handle_one_storm_cell(
            storm_object_table=concat_storm_object_table,
            primary_id_string=primary_id_strings[j],
            conus_latitudes_deg=conus_latitudes_deg,
            conus_longitudes_deg=conus_longitudes_deg,
            max_lead_time_sec=max_lead_time_sec
        )

        bad_object_indices = numpy.concatenate((
            bad_object_indices, these_indices
        ))

    concat_storm_object_table.drop(
        concat_storm_object_table.index[bad_object_indices],
        axis=0, inplace=True
    )

    for k in indices_to_concat:
        storm_object_table_by_date[k] = concat_storm_object_table.loc[
            concat_storm_object_table[tracking_utils.SPC_DATE_COLUMN] ==
            spc_date_strings[k]
            ]

    num_storm_objects = len(
        storm_object_table_by_date[target_date_index].index
    )

    print((
        'Removed {0:d} of {1:d} storm objects for SPC date "{2:s}".'
    ).format(
        orig_num_storm_objects - num_storm_objects, orig_num_storm_objects,
        spc_date_strings[target_date_index]
    ))

    return storm_object_table_by_date


def _run(top_input_dir_name, first_spc_date_string, last_spc_date_string,
         max_link_distance_metres, max_lead_time_sec, top_output_dir_name):
    """Removes storms that pass outside continental United States (CONUS).

    This is effectively the main method.

    :param top_input_dir_name: See documentation at top of file.
    :param first_spc_date_string: Same.
    :param last_spc_date_string: Same.
    :param max_link_distance_metres: Same.
    :param max_lead_time_sec: Same.
    :param top_output_dir_name: Same.
    """

    conus_latitudes_deg, conus_longitudes_deg = (
        conus_boundary.read_from_netcdf()
    )
    conus_latitudes_deg, conus_longitudes_deg = conus_boundary.erode_boundary(
        latitudes_deg=conus_latitudes_deg, longitudes_deg=conus_longitudes_deg,
        erosion_distance_metres=max_link_distance_metres
    )

    spc_date_strings, input_file_names_by_date, times_by_date_unix_sec = (
        echo_top_tracking._find_input_tracking_files(
            top_tracking_dir_name=top_input_dir_name,
            first_spc_date_string=first_spc_date_string,
            last_spc_date_string=last_spc_date_string,
            first_time_unix_sec=None, last_time_unix_sec=None)
    )

    num_spc_dates = len(spc_date_strings)
    storm_object_table_by_date = [None] * num_spc_dates

    for i in range(num_spc_dates + 1):
        storm_object_table_by_date = echo_top_tracking._shuffle_tracking_data(
            tracking_file_names_by_date=input_file_names_by_date,
            valid_times_by_date_unix_sec=times_by_date_unix_sec,
            storm_object_table_by_date=storm_object_table_by_date,
            current_date_index=i, top_output_dir_name=top_output_dir_name
        )
        print(SEPARATOR_STRING)

        if i == num_spc_dates:
            break

        storm_object_table_by_date = _filter_storms_one_day(
            storm_object_table_by_date=storm_object_table_by_date,
            spc_date_strings=spc_date_strings, target_date_index=i,
            conus_latitudes_deg=conus_latitudes_deg,
            conus_longitudes_deg=conus_longitudes_deg,
            max_lead_time_sec=max_lead_time_sec
        )
        print(SEPARATOR_STRING)


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _run(
        top_input_dir_name=getattr(INPUT_ARG_OBJECT, INPUT_DIR_ARG_NAME),
        first_spc_date_string=getattr(INPUT_ARG_OBJECT, FIRST_DATE_ARG_NAME),
        last_spc_date_string=getattr(INPUT_ARG_OBJECT, LAST_DATE_ARG_NAME),
        max_link_distance_metres=getattr(
            INPUT_ARG_OBJECT, MAX_LINK_DISTANCE_ARG_NAME
        ),
        max_lead_time_sec=getattr(INPUT_ARG_OBJECT, MAX_LEAD_TIME_ARG_NAME),
        top_output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME)
    )
