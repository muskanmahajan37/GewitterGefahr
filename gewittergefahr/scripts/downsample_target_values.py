"""Downsamples storm objects, based on target values."""

import os.path
import argparse
import numpy
import pandas
from gewittergefahr.gg_utils import target_val_utils
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import temporal_tracking
from gewittergefahr.gg_utils import storm_tracking_utils as tracking_utils
from gewittergefahr.deep_learning import fancy_downsampling

LARGE_INTEGER = int(1e12)
SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

INPUT_DIR_ARG_NAME = 'input_target_dir_name'
TARGET_NAME_ARG_NAME = 'target_name_for_downsampling'
FIRST_DATE_ARG_NAME = 'first_spc_date_string'
LAST_DATE_ARG_NAME = 'last_spc_date_string'
DOWNSAMPLING_CLASSES_ARG_NAME = 'downsampling_classes'
DOWNSAMPLING_FRACTIONS_ARG_NAME = 'downsampling_fractions'
FOR_TRAINING_ARG_NAME = 'for_training'
OUTPUT_DIR_ARG_NAME = 'output_target_dir_name'

INPUT_DIR_HELP_STRING = (
    'Name of top-level input directory with target values.  Files therein will '
    'be located by `target_val_utils.find_target_file` and read by '
    '`target_val_utils.read_target_values`.')

TARGET_NAME_HELP_STRING = 'Name of target variable for downsampling.'

SPC_DATE_HELP_STRING = (
    'SPC date (format "yyyymmdd").  Downsampling will be based on all storm '
    'objects from `{0:s}`...`{1:s}` and applied to the same storm objects.'
).format(FIRST_DATE_ARG_NAME, LAST_DATE_ARG_NAME)

DOWNSAMPLING_CLASSES_HELP_STRING = (
    'List of classes (integer labels) for downsampling.')

DOWNSAMPLING_FRACTIONS_HELP_STRING = (
    'List of downsampling fractions.  The [k]th downsampling fraction goes with'
    ' the [k]th class in `{0:s}`, and the sum of all downsampling fractions '
    'must be 1.0.'
).format(DOWNSAMPLING_CLASSES_ARG_NAME)

FOR_TRAINING_HELP_STRING = (
    'Boolean flag.  If 1, will downsample for training, using '
    '`fancy_downsampling.downsample`, which preserves "interesting" negative '
    'examples (time steps from a hazardous storm cell that are not associated '
    'with said hazard -- e.g., non-tornadic time steps from a tornadic cell).  '
    'If 0, will downsample for training or validation, using '
    '`deep_learning_utils.sample_by_class`.')

OUTPUT_DIR_HELP_STRING = (
    'Name of top-level output directory for downsampled target values.  New '
    'files will be written by `target_val_utils.write_target_values`, to '
    'locations in this directory determined by '
    '`target_val_utils.find_target_file`.')

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + INPUT_DIR_ARG_NAME, type=str, required=True,
    help=INPUT_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + TARGET_NAME_ARG_NAME, type=str, required=True,
    help=TARGET_NAME_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FIRST_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + LAST_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + DOWNSAMPLING_CLASSES_ARG_NAME, type=int, nargs='+',
    required=True, help=DOWNSAMPLING_CLASSES_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + DOWNSAMPLING_FRACTIONS_ARG_NAME, type=float, nargs='+',
    required=True, help=DOWNSAMPLING_FRACTIONS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FOR_TRAINING_ARG_NAME, type=int, required=True,
    help=FOR_TRAINING_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=True,
    help=OUTPUT_DIR_HELP_STRING)


def _report_class_fractions(target_values):
    """Reports fraction of examples in each class.

    :param target_values: 1-D numpy array of target values (integer class
        labels).
    """

    unique_target_values, unique_counts = numpy.unique(
        target_values, return_counts=True)

    print('\n')

    for k in range(len(unique_target_values)):
        print('{0:d} examples in class = {1:d}'.format(
            unique_counts[k], unique_target_values[k]
        ))

    print('\n')


def _run(top_input_dir_name, target_name_for_downsampling,
         first_spc_date_string, last_spc_date_string, downsampling_classes,
         downsampling_fractions, for_training, top_output_dir_name):
    """Downsamples storm objects, based on target values.

    This is effectively the main method.

    :param top_input_dir_name: See documentation at top of file.
    :param target_name_for_downsampling: Same.
    :param first_spc_date_string: Same.
    :param last_spc_date_string: Same.
    :param downsampling_classes: Same.
    :param downsampling_fractions: Same.
    :param for_training: Same.
    :param top_output_dir_name: Same.
    """

    all_spc_date_strings = time_conversion.get_spc_dates_in_range(
        first_spc_date_string=first_spc_date_string,
        last_spc_date_string=last_spc_date_string)

    downsampling_dict = dict(list(zip(
        downsampling_classes, downsampling_fractions
    )))

    target_param_dict = target_val_utils.target_name_to_params(
        target_name_for_downsampling
    )
    event_type_string = target_param_dict[target_val_utils.EVENT_TYPE_KEY]

    input_target_file_names = []
    spc_date_string_by_file = []

    for this_spc_date_string in all_spc_date_strings:
        this_file_name = target_val_utils.find_target_file(
            top_directory_name=top_input_dir_name,
            event_type_string=event_type_string,
            spc_date_string=this_spc_date_string, raise_error_if_missing=False)

        if not os.path.isfile(this_file_name):
            continue

        input_target_file_names.append(this_file_name)
        spc_date_string_by_file.append(this_spc_date_string)

    num_files = len(input_target_file_names)
    target_dict_by_file = [None] * num_files

    full_id_strings = []
    storm_times_unix_sec = numpy.array([], dtype=int)
    storm_to_file_indices = numpy.array([], dtype=int)

    target_names = []
    target_matrix = None

    for i in range(num_files):
        print('Reading data from: "{0:s}"...'.format(
            input_target_file_names[i]
        ))

        target_dict_by_file[i] = target_val_utils.read_target_values(
            netcdf_file_name=input_target_file_names[i]
        )

        if i == 0:
            target_names = (
                target_dict_by_file[i][target_val_utils.TARGET_NAMES_KEY]
            )

        these_full_id_strings = (
            target_dict_by_file[i][target_val_utils.FULL_IDS_KEY]
        )

        full_id_strings += these_full_id_strings
        this_num_storm_objects = len(these_full_id_strings)

        storm_times_unix_sec = numpy.concatenate((
            storm_times_unix_sec,
            target_dict_by_file[i][target_val_utils.VALID_TIMES_KEY]
        ))

        storm_to_file_indices = numpy.concatenate((
            storm_to_file_indices,
            numpy.full(this_num_storm_objects, i, dtype=int)
        ))

        this_target_matrix = (
            target_dict_by_file[i][target_val_utils.TARGET_MATRIX_KEY]
        )

        if target_matrix is None:
            target_matrix = this_target_matrix + 0
        else:
            target_matrix = numpy.concatenate(
                (target_matrix, this_target_matrix), axis=0
            )

    print(SEPARATOR_STRING)

    downsampling_index = target_names.index(target_name_for_downsampling)
    good_indices = numpy.where(
        target_matrix[:, downsampling_index] !=
        target_val_utils.INVALID_STORM_INTEGER
    )[0]

    full_id_strings = [full_id_strings[k] for k in good_indices]
    storm_times_unix_sec = storm_times_unix_sec[good_indices]
    target_matrix = target_matrix[good_indices, :]
    storm_to_file_indices = storm_to_file_indices[good_indices]

    primary_id_strings = temporal_tracking.full_to_partial_ids(
        full_id_strings
    )[0]

    if for_training:
        indices_to_keep = fancy_downsampling.downsample_for_training(
            primary_id_strings=primary_id_strings,
            storm_times_unix_sec=storm_times_unix_sec,
            target_values=target_matrix[:, downsampling_index],
            target_name=target_name_for_downsampling,
            class_fraction_dict=downsampling_dict)
    else:
        indices_to_keep = fancy_downsampling.downsample_for_non_training(
            primary_id_strings=primary_id_strings,
            storm_times_unix_sec=storm_times_unix_sec,
            target_values=target_matrix[:, downsampling_index],
            target_name=target_name_for_downsampling,
            class_fraction_dict=downsampling_dict)

    print(SEPARATOR_STRING)

    for i in range(num_files):
        these_object_subindices = numpy.where(
            storm_to_file_indices[indices_to_keep] == i
        )[0]

        these_object_indices = indices_to_keep[these_object_subindices]
        if len(these_object_indices) == 0:
            continue

        these_indices_in_file = tracking_utils.find_storm_objects(
            all_id_strings=target_dict_by_file[i][
                target_val_utils.FULL_IDS_KEY],
            all_times_unix_sec=target_dict_by_file[i][
                target_val_utils.VALID_TIMES_KEY],
            id_strings_to_keep=
            [full_id_strings[k] for k in these_object_indices],
            times_to_keep_unix_sec=storm_times_unix_sec[these_object_indices],
            allow_missing=False)

        this_output_dict = {
            tracking_utils.FULL_ID_COLUMN: [
                target_dict_by_file[i][target_val_utils.FULL_IDS_KEY][k]
                for k in these_indices_in_file
            ],
            tracking_utils.VALID_TIME_COLUMN:
                target_dict_by_file[i][target_val_utils.VALID_TIMES_KEY][
                    these_indices_in_file]
        }

        for j in range(len(target_names)):
            this_output_dict[target_names[j]] = (
                target_dict_by_file[i][target_val_utils.TARGET_MATRIX_KEY][
                    these_indices_in_file, j]
            )

        this_output_table = pandas.DataFrame.from_dict(this_output_dict)

        this_new_file_name = target_val_utils.find_target_file(
            top_directory_name=top_output_dir_name,
            event_type_string=event_type_string,
            spc_date_string=spc_date_string_by_file[i],
            raise_error_if_missing=False)

        print((
            'Writing {0:d} downsampled storm objects (out of {1:d} total) to: '
            '"{2:s}"...'
        ).format(
            len(this_output_table.index),
            len(target_dict_by_file[i][target_val_utils.FULL_IDS_KEY]),
            this_new_file_name
        ))

        target_val_utils.write_target_values(
            storm_to_events_table=this_output_table, target_names=target_names,
            netcdf_file_name=this_new_file_name)


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _run(
        top_input_dir_name=getattr(INPUT_ARG_OBJECT, INPUT_DIR_ARG_NAME),
        target_name_for_downsampling=getattr(
            INPUT_ARG_OBJECT, TARGET_NAME_ARG_NAME),
        first_spc_date_string=getattr(INPUT_ARG_OBJECT, FIRST_DATE_ARG_NAME),
        last_spc_date_string=getattr(INPUT_ARG_OBJECT, LAST_DATE_ARG_NAME),
        downsampling_classes=numpy.array(
            getattr(INPUT_ARG_OBJECT, DOWNSAMPLING_CLASSES_ARG_NAME), dtype=int
        ),
        downsampling_fractions=numpy.array(
            getattr(INPUT_ARG_OBJECT, DOWNSAMPLING_FRACTIONS_ARG_NAME),
            dtype=float
        ),
        for_training=bool(getattr(INPUT_ARG_OBJECT, FOR_TRAINING_ARG_NAME)),
        top_output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME)
    )
