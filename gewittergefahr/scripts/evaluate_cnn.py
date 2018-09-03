"""Evaluates predictions from a convolutional neural network (CNN).

The CNN should be evaluated on independent data (i.e., data used for neither
training nor validation -- the easiest way to ensure independence is to use data
from different years), but this is not enforced by the code.
"""

import random
import os.path
import argparse
import numpy
from keras import backend as K
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import labels
from gewittergefahr.deep_learning import cnn
from gewittergefahr.deep_learning import deployment_io
from gewittergefahr.deep_learning import training_validation_io as trainval_io
from gewittergefahr.scripts import model_evaluation_helper as model_eval_helper

random.seed(6695)
numpy.random.seed(6695)

K.set_session(K.tf.Session(config=K.tf.ConfigProto(
    intra_op_parallelism_threads=1, inter_op_parallelism_threads=1)))

SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'
MINOR_SEPARATOR_STRING = '\n\n' + '-' * 50 + '\n\n'

MODEL_FILE_ARG_NAME = 'input_model_file_name'
RADAR_DIRECTORY_ARG_NAME = 'input_storm_radar_image_dir_name'
SOUNDING_DIRECTORY_ARG_NAME = 'input_sounding_dir_name'
TARGET_DIRECTORY_ARG_NAME = 'input_target_dir_name'
NUM_EXAMPLES_PER_FILE_ARG_NAME = 'num_examples_per_file'
FIRST_EVAL_DATE_ARG_NAME = 'first_eval_spc_date_string'
LAST_EVAL_DATE_ARG_NAME = 'last_eval_spc_date_string'
NUM_STORM_OBJECTS_ARG_NAME = 'num_storm_objects'
OUTPUT_DIR_ARG_NAME = 'output_dir_name'

MODEL_FILE_HELP_STRING = (
    'Path to input file (readable by `cnn.read_model`), containing the trained '
    'CNN.')
RADAR_DIRECTORY_HELP_STRING = (
    'Name of top-level directory with storm-centered radar images.  Files '
    'therein will be found by `training_validation_io.find_radar_files_2d` or '
    '`training_validation_io.find_radar_files_3d`.')
SOUNDING_DIRECTORY_HELP_STRING = (
    'Name of top-level directory with storm-centered soundings.  Files therein '
    'will be found by `training_validation_io.find_sounding_files`.')
TARGET_DIRECTORY_HELP_STRING = (
    'Name of top-level directory with labels (target values).  Files therein '
    'will be found by `labels.find_label_file`.')
NUM_EXAMPLES_PER_FILE_HELP_STRING = (
    'Number of examples (storm objects) per file.')
EVAL_DATE_HELP_STRING = (
    'SPC (Storm Prediction Center) date in format "yyyymmdd".  Storm objects '
    'will be drawn randomly from `{0:s}`...`{1:s}`.  A forecast-observation '
    'pair will be created for each storm object.'
).format(FIRST_EVAL_DATE_ARG_NAME, LAST_EVAL_DATE_ARG_NAME)
NUM_STORM_OBJECTS_HELP_STRING = (
    'Number of storm objects to draw randomly from `{0:s}`...`{1:s}`.'
).format(FIRST_EVAL_DATE_ARG_NAME, LAST_EVAL_DATE_ARG_NAME)
OUTPUT_DIR_HELP_STRING = (
    'Name of output directory.  Evaluation results will be saved here.')

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + MODEL_FILE_ARG_NAME, type=str, required=True,
    help=MODEL_FILE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + RADAR_DIRECTORY_ARG_NAME, type=str, required=True,
    help=RADAR_DIRECTORY_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + SOUNDING_DIRECTORY_ARG_NAME, type=str, required=False,
    default='', help=SOUNDING_DIRECTORY_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + TARGET_DIRECTORY_ARG_NAME, type=str, required=True,
    help=TARGET_DIRECTORY_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_EXAMPLES_PER_FILE_ARG_NAME, type=int, required=True,
    help=NUM_EXAMPLES_PER_FILE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + FIRST_EVAL_DATE_ARG_NAME, type=str, required=True,
    help=EVAL_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + LAST_EVAL_DATE_ARG_NAME, type=str, required=True,
    help=EVAL_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_STORM_OBJECTS_ARG_NAME, type=int, required=True,
    help=NUM_STORM_OBJECTS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=True,
    help=OUTPUT_DIR_HELP_STRING)


def _create_forecast_observation_pairs_2d(
        model_object, top_storm_radar_image_dir_name, top_sounding_dir_name,
        top_target_dir_name, num_examples_per_file, first_eval_time_unix_sec,
        last_eval_time_unix_sec, num_storm_objects, model_metadata_dict):
    """Creates forecast-observation pairs for a network with 2-D convolution.

    N = number of storm objects

    :param model_object: Trained model (instance of `keras.models.Sequential`).
    :param top_storm_radar_image_dir_name: See documentation at top of file.
    :param top_sounding_dir_name: Same.
    :param top_target_dir_name: Same.
    :param num_examples_per_file: Same.
    :param first_eval_time_unix_sec: Same.
    :param last_eval_time_unix_sec: Same.
    :param num_storm_objects: Same.
    :param model_metadata_dict: Dictionary created by `cnn.read_model_metadata`.
    :return: forecast_probabilities: length-N numpy array of forecast event
        probabilities.
    :return: observed_labels: length-N numpy array of observed labels (1 for
        "yes", 0 for "no").
    """

    radar_file_name_matrix = trainval_io.find_radar_files_2d(
        top_directory_name=top_storm_radar_image_dir_name,
        radar_source=model_metadata_dict[cnn.RADAR_SOURCE_KEY],
        radar_field_names=model_metadata_dict[cnn.RADAR_FIELDS_KEY],
        first_file_time_unix_sec=first_eval_time_unix_sec,
        last_file_time_unix_sec=last_eval_time_unix_sec,
        one_file_per_time_step=False,
        radar_heights_m_agl=model_metadata_dict[cnn.RADAR_HEIGHTS_KEY],
        reflectivity_heights_m_agl=model_metadata_dict[
            cnn.REFLECTIVITY_HEIGHTS_KEY])[0]
    print SEPARATOR_STRING

    option_dict = {
        deployment_io.NUM_EXAMPLES_PER_FILE_KEY: num_examples_per_file,
        deployment_io.NUM_ROWS_TO_KEEP_KEY:
            model_metadata_dict[cnn.NUM_ROWS_TO_KEEP_KEY],
        deployment_io.NUM_COLUMNS_TO_KEEP_KEY:
            model_metadata_dict[cnn.NUM_COLUMNS_TO_KEEP_KEY],
        deployment_io.NORMALIZATION_TYPE_KEY:
            model_metadata_dict[cnn.NORMALIZATION_TYPE_KEY],
        deployment_io.MIN_NORMALIZED_VALUE_KEY:
            model_metadata_dict[cnn.MIN_NORMALIZED_VALUE_KEY],
        deployment_io.MAX_NORMALIZED_VALUE_KEY:
            model_metadata_dict[cnn.MAX_NORMALIZED_VALUE_KEY],
        deployment_io.NORMALIZATION_FILE_KEY:
            model_metadata_dict[cnn.NORMALIZATION_FILE_KEY],
        deployment_io.RETURN_TARGET_KEY: True,
        deployment_io.TARGET_NAME_KEY: model_metadata_dict[cnn.TARGET_NAME_KEY],
        deployment_io.TARGET_DIRECTORY_KEY: top_target_dir_name,
        deployment_io.BINARIZE_TARGET_KEY:
            model_metadata_dict[cnn.BINARIZE_TARGET_KEY],
        deployment_io.SOUNDING_FIELDS_KEY:
            model_metadata_dict[cnn.SOUNDING_FIELD_NAMES_KEY],
        deployment_io.SOUNDING_DIRECTORY_KEY: top_sounding_dir_name,
        deployment_io.SOUNDING_LAG_TIME_KEY:
            model_metadata_dict[cnn.SOUNDING_LAG_TIME_KEY]
    }

    forecast_probabilities = numpy.array([])
    observed_labels = numpy.array([], dtype=int)
    num_radar_times = radar_file_name_matrix.shape[0]

    for i in range(num_radar_times):
        print (
            'Have created forecast-observation pair for {0:d} of {1:d} storm '
            'objects...\n'
        ).format(len(observed_labels), num_storm_objects)

        if len(observed_labels) > num_storm_objects:
            break

        option_dict.update({
            deployment_io.RADAR_FILE_NAMES_KEY: radar_file_name_matrix[[i], ...]
        })
        this_example_dict = deployment_io.create_storm_images_2d(option_dict)

        print MINOR_SEPARATOR_STRING
        if this_example_dict is None:
            continue

        this_radar_image_matrix = this_example_dict[
            deployment_io.RADAR_IMAGE_MATRIX_KEY]
        this_sounding_matrix = this_example_dict[
            deployment_io.SOUNDING_MATRIX_KEY]
        these_observed_labels = this_example_dict[
            deployment_io.TARGET_VALUES_KEY]

        this_probability_matrix = cnn.apply_2d_cnn(
            model_object=model_object,
            radar_image_matrix=this_radar_image_matrix,
            sounding_matrix=this_sounding_matrix)

        observed_labels = numpy.concatenate((
            observed_labels, these_observed_labels))
        forecast_probabilities = numpy.concatenate((
            forecast_probabilities, this_probability_matrix[:, 1]))

    if len(observed_labels) > num_storm_objects:
        forecast_probabilities = forecast_probabilities[:num_storm_objects]
        observed_labels = observed_labels[:num_storm_objects]

    return forecast_probabilities, observed_labels


def _create_forecast_observation_pairs_3d(
        model_object, top_storm_radar_image_dir_name, top_sounding_dir_name,
        top_target_dir_name, num_examples_per_file, first_eval_time_unix_sec,
        last_eval_time_unix_sec, num_storm_objects, model_metadata_dict):
    """Creates forecast-observation pairs for a network with 3-D convolution.

    :param model_object: See doc for `_create_forecast_observation_pairs_2d`.
    :param top_storm_radar_image_dir_name: Same.
    :param top_sounding_dir_name: Same.
    :param top_target_dir_name: Same.
    :param num_examples_per_file: Same.
    :param first_eval_time_unix_sec: Same.
    :param last_eval_time_unix_sec: Same.
    :param num_storm_objects: Same.
    :param model_metadata_dict: Same.
    :return: forecast_probabilities: Same.
    :return: observed_labels: Same.
    """

    radar_file_name_matrix = trainval_io.find_radar_files_3d(
        top_directory_name=top_storm_radar_image_dir_name,
        radar_source=model_metadata_dict[cnn.RADAR_SOURCE_KEY],
        radar_field_names=model_metadata_dict[cnn.RADAR_FIELDS_KEY],
        radar_heights_m_agl=model_metadata_dict[cnn.RADAR_HEIGHTS_KEY],
        first_file_time_unix_sec=first_eval_time_unix_sec,
        last_file_time_unix_sec=last_eval_time_unix_sec,
        one_file_per_time_step=False)[0]
    print SEPARATOR_STRING

    option_dict = {
        deployment_io.NUM_EXAMPLES_PER_FILE_KEY: num_examples_per_file,
        deployment_io.NUM_ROWS_TO_KEEP_KEY:
            model_metadata_dict[cnn.NUM_ROWS_TO_KEEP_KEY],
        deployment_io.NUM_COLUMNS_TO_KEEP_KEY:
            model_metadata_dict[cnn.NUM_COLUMNS_TO_KEEP_KEY],
        deployment_io.NORMALIZATION_TYPE_KEY:
            model_metadata_dict[cnn.NORMALIZATION_TYPE_KEY],
        deployment_io.MIN_NORMALIZED_VALUE_KEY:
            model_metadata_dict[cnn.MIN_NORMALIZED_VALUE_KEY],
        deployment_io.MAX_NORMALIZED_VALUE_KEY:
            model_metadata_dict[cnn.MAX_NORMALIZED_VALUE_KEY],
        deployment_io.NORMALIZATION_FILE_KEY:
            model_metadata_dict[cnn.NORMALIZATION_FILE_KEY],
        deployment_io.RETURN_TARGET_KEY: True,
        deployment_io.TARGET_NAME_KEY: model_metadata_dict[cnn.TARGET_NAME_KEY],
        deployment_io.TARGET_DIRECTORY_KEY: top_target_dir_name,
        deployment_io.BINARIZE_TARGET_KEY:
            model_metadata_dict[cnn.BINARIZE_TARGET_KEY],
        deployment_io.SOUNDING_FIELDS_KEY:
            model_metadata_dict[cnn.SOUNDING_FIELD_NAMES_KEY],
        deployment_io.SOUNDING_DIRECTORY_KEY: top_sounding_dir_name,
        deployment_io.SOUNDING_LAG_TIME_KEY:
            model_metadata_dict[cnn.SOUNDING_LAG_TIME_KEY],
        deployment_io.REFLECTIVITY_MASK_KEY: model_metadata_dict[
            cnn.REFL_MASKING_THRESHOLD_KEY]
    }

    forecast_probabilities = numpy.array([])
    observed_labels = numpy.array([], dtype=int)
    num_radar_times = radar_file_name_matrix.shape[0]

    for i in range(num_radar_times):
        print (
            'Have created forecast-observation pair for {0:d} of {1:d} storm '
            'objects...\n'
        ).format(len(observed_labels), num_storm_objects)

        if len(observed_labels) > num_storm_objects:
            break

        option_dict.update({
            deployment_io.RADAR_FILE_NAMES_KEY: radar_file_name_matrix[[i], ...]
        })
        this_example_dict = deployment_io.create_storm_images_3d(option_dict)

        print MINOR_SEPARATOR_STRING
        if this_example_dict is None:
            continue

        this_radar_image_matrix = this_example_dict[
            deployment_io.RADAR_IMAGE_MATRIX_KEY]
        this_sounding_matrix = this_example_dict[
            deployment_io.SOUNDING_MATRIX_KEY]
        these_observed_labels = this_example_dict[
            deployment_io.TARGET_VALUES_KEY]

        this_probability_matrix = cnn.apply_3d_cnn(
            model_object=model_object,
            radar_image_matrix=this_radar_image_matrix,
            sounding_matrix=this_sounding_matrix)

        observed_labels = numpy.concatenate((
            observed_labels, these_observed_labels))
        forecast_probabilities = numpy.concatenate((
            forecast_probabilities, this_probability_matrix[:, 1]))

    if len(observed_labels) > num_storm_objects:
        forecast_probabilities = forecast_probabilities[:num_storm_objects]
        observed_labels = observed_labels[:num_storm_objects]

    return forecast_probabilities, observed_labels


def _create_forecast_observation_pairs_2d3d(
        model_object, top_storm_radar_image_dir_name, top_sounding_dir_name,
        top_target_dir_name, num_examples_per_file, first_eval_time_unix_sec,
        last_eval_time_unix_sec, num_storm_objects, model_metadata_dict):
    """Creates forecast-observation pairs for a network with 2D/3D convolution.

    :param model_object: See doc for `_create_forecast_observation_pairs_2d`.
    :param top_storm_radar_image_dir_name: Same.
    :param top_sounding_dir_name: Same.
    :param top_target_dir_name: Same.
    :param num_examples_per_file: Same.
    :param first_eval_time_unix_sec: Same.
    :param last_eval_time_unix_sec: Same.
    :param num_storm_objects: Same.
    :param model_metadata_dict: Same.
    :return: forecast_probabilities: Same.
    :return: observed_labels: Same.
    """

    radar_file_name_matrix = trainval_io.find_radar_files_2d(
        top_directory_name=top_storm_radar_image_dir_name,
        radar_source=model_metadata_dict[cnn.RADAR_SOURCE_KEY],
        radar_field_names=model_metadata_dict[cnn.RADAR_FIELDS_KEY],
        first_file_time_unix_sec=first_eval_time_unix_sec,
        last_file_time_unix_sec=last_eval_time_unix_sec,
        one_file_per_time_step=False,
        radar_heights_m_agl=model_metadata_dict[cnn.RADAR_HEIGHTS_KEY],
        reflectivity_heights_m_agl=model_metadata_dict[
            cnn.REFLECTIVITY_HEIGHTS_KEY])[0]
    print SEPARATOR_STRING

    option_dict = {
        deployment_io.NUM_EXAMPLES_PER_FILE_KEY: num_examples_per_file,
        deployment_io.NUM_ROWS_TO_KEEP_KEY:
            model_metadata_dict[cnn.NUM_ROWS_TO_KEEP_KEY],
        deployment_io.NUM_COLUMNS_TO_KEEP_KEY:
            model_metadata_dict[cnn.NUM_COLUMNS_TO_KEEP_KEY],
        deployment_io.NORMALIZATION_TYPE_KEY:
            model_metadata_dict[cnn.NORMALIZATION_TYPE_KEY],
        deployment_io.MIN_NORMALIZED_VALUE_KEY:
            model_metadata_dict[cnn.MIN_NORMALIZED_VALUE_KEY],
        deployment_io.MAX_NORMALIZED_VALUE_KEY:
            model_metadata_dict[cnn.MAX_NORMALIZED_VALUE_KEY],
        deployment_io.NORMALIZATION_FILE_KEY:
            model_metadata_dict[cnn.NORMALIZATION_FILE_KEY],
        deployment_io.RETURN_TARGET_KEY: True,
        deployment_io.TARGET_NAME_KEY: model_metadata_dict[cnn.TARGET_NAME_KEY],
        deployment_io.TARGET_DIRECTORY_KEY: top_target_dir_name,
        deployment_io.BINARIZE_TARGET_KEY:
            model_metadata_dict[cnn.BINARIZE_TARGET_KEY],
        deployment_io.SOUNDING_FIELDS_KEY:
            model_metadata_dict[cnn.SOUNDING_FIELD_NAMES_KEY],
        deployment_io.SOUNDING_DIRECTORY_KEY: top_sounding_dir_name,
        deployment_io.SOUNDING_LAG_TIME_KEY:
            model_metadata_dict[cnn.SOUNDING_LAG_TIME_KEY]
    }

    forecast_probabilities = numpy.array([])
    observed_labels = numpy.array([], dtype=int)
    num_radar_times = radar_file_name_matrix.shape[0]

    for i in range(num_radar_times):
        print (
            'Have created forecast-observation pair for {0:d} of {1:d} storm '
            'objects...\n'
        ).format(len(observed_labels), num_storm_objects)

        if len(observed_labels) > num_storm_objects:
            break

        option_dict.update({
            deployment_io.RADAR_FILE_NAMES_KEY: radar_file_name_matrix[[i], ...]
        })
        this_example_dict = deployment_io.create_storm_images_2d3d_myrorss(
            option_dict)

        print MINOR_SEPARATOR_STRING
        if this_example_dict is None:
            continue

        this_reflectivity_matrix_dbz = this_example_dict[
            deployment_io.REFLECTIVITY_MATRIX_KEY]
        this_azimuthal_shear_matrix_s01 = this_example_dict[
            deployment_io.AZ_SHEAR_MATRIX_KEY]
        this_sounding_matrix = this_example_dict[
            deployment_io.SOUNDING_MATRIX_KEY]
        these_observed_labels = this_example_dict[
            deployment_io.TARGET_VALUES_KEY]

        this_probability_matrix = cnn.apply_2d3d_cnn(
            model_object=model_object,
            reflectivity_image_matrix_dbz=this_reflectivity_matrix_dbz,
            azimuthal_shear_image_matrix_s01=this_azimuthal_shear_matrix_s01,
            sounding_matrix=this_sounding_matrix)

        observed_labels = numpy.concatenate((
            observed_labels, these_observed_labels))
        forecast_probabilities = numpy.concatenate((
            forecast_probabilities, this_probability_matrix[:, 1]))

    if len(observed_labels) > num_storm_objects:
        forecast_probabilities = forecast_probabilities[:num_storm_objects]
        observed_labels = observed_labels[:num_storm_objects]

    return forecast_probabilities, observed_labels


def _evaluate_model(
        model_file_name, top_storm_radar_image_dir_name, top_sounding_dir_name,
        top_target_dir_name, num_examples_per_file, first_eval_spc_date_string,
        last_eval_spc_date_string, num_storm_objects, output_dir_name):
    """Evaluates predictions from a convolutional neural network (CNN).

    :param model_file_name: See documentation at top of file.
    :param top_storm_radar_image_dir_name: Same.
    :param top_sounding_dir_name: Same.
    :param top_target_dir_name: Same.
    :param num_examples_per_file: Same.
    :param first_eval_spc_date_string: Same.
    :param last_eval_spc_date_string: Same.
    :param num_storm_objects: Same.
    :param output_dir_name: Same.
    :raises: ValueError: if the target variable is non-binary.  This script is
        designed for binary classification only.
    """

    first_eval_time_unix_sec = time_conversion.spc_date_string_to_unix_sec(
        first_eval_spc_date_string)
    last_eval_time_unix_sec = time_conversion.spc_date_string_to_unix_sec(
        last_eval_spc_date_string)

    print 'Reading model from: "{0:s}"...'.format(model_file_name)
    model_object = cnn.read_model(model_file_name)

    model_directory_name, _ = os.path.split(model_file_name)
    metadata_file_name = '{0:s}/model_metadata.p'.format(model_directory_name)

    print 'Reading metadata from: "{0:s}"...'.format(metadata_file_name)
    model_metadata_dict = cnn.read_model_metadata(metadata_file_name)

    if not model_metadata_dict[cnn.BINARIZE_TARGET_KEY]:
        num_classes = labels.column_name_to_num_classes(
            model_metadata_dict[cnn.TARGET_NAME_KEY])
        if num_classes > 2:
            error_string = (
                'The target variable ("{0:s}") has {1:d} classes.  This script '
                'is designed for binary classification only.'
            ).format(model_metadata_dict[cnn.TARGET_NAME_KEY], num_classes)
            raise ValueError(error_string)

    if model_metadata_dict[cnn.USE_2D3D_CONVOLUTION_KEY]:
        forecast_probabilities, observed_labels = (
            _create_forecast_observation_pairs_2d3d(
                model_object=model_object,
                top_storm_radar_image_dir_name=top_storm_radar_image_dir_name,
                top_sounding_dir_name=top_sounding_dir_name,
                top_target_dir_name=top_target_dir_name,
                num_examples_per_file=num_examples_per_file,
                first_eval_time_unix_sec=first_eval_time_unix_sec,
                last_eval_time_unix_sec=last_eval_time_unix_sec,
                num_storm_objects=num_storm_objects,
                model_metadata_dict=model_metadata_dict))
    else:
        num_radar_dimensions = len(
            model_metadata_dict[cnn.TRAINING_FILES_KEY].shape)
        if num_radar_dimensions == 2:
            forecast_probabilities, observed_labels = (
                _create_forecast_observation_pairs_2d(
                    model_object=model_object,
                    top_storm_radar_image_dir_name=
                    top_storm_radar_image_dir_name,
                    top_sounding_dir_name=top_sounding_dir_name,
                    top_target_dir_name=top_target_dir_name,
                    num_examples_per_file=num_examples_per_file,
                    first_eval_time_unix_sec=first_eval_time_unix_sec,
                    last_eval_time_unix_sec=last_eval_time_unix_sec,
                    num_storm_objects=num_storm_objects,
                    model_metadata_dict=model_metadata_dict))
        else:
            forecast_probabilities, observed_labels = (
                _create_forecast_observation_pairs_3d(
                    model_object=model_object,
                    top_storm_radar_image_dir_name=
                    top_storm_radar_image_dir_name,
                    top_sounding_dir_name=top_sounding_dir_name,
                    top_target_dir_name=top_target_dir_name,
                    num_examples_per_file=num_examples_per_file,
                    first_eval_time_unix_sec=first_eval_time_unix_sec,
                    last_eval_time_unix_sec=last_eval_time_unix_sec,
                    num_storm_objects=num_storm_objects,
                    model_metadata_dict=model_metadata_dict))

    print SEPARATOR_STRING

    model_eval_helper.run_evaluation(
        forecast_probabilities=forecast_probabilities,
        observed_labels=observed_labels, output_dir_name=output_dir_name)


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _evaluate_model(
        model_file_name=getattr(INPUT_ARG_OBJECT, MODEL_FILE_ARG_NAME),
        top_storm_radar_image_dir_name=getattr(
            INPUT_ARG_OBJECT, RADAR_DIRECTORY_ARG_NAME),
        top_sounding_dir_name=getattr(
            INPUT_ARG_OBJECT, SOUNDING_DIRECTORY_ARG_NAME),
        top_target_dir_name=getattr(
            INPUT_ARG_OBJECT, TARGET_DIRECTORY_ARG_NAME),
        num_examples_per_file=getattr(
            INPUT_ARG_OBJECT, NUM_EXAMPLES_PER_FILE_ARG_NAME),
        first_eval_spc_date_string=getattr(
            INPUT_ARG_OBJECT, FIRST_EVAL_DATE_ARG_NAME),
        last_eval_spc_date_string=getattr(
            INPUT_ARG_OBJECT, LAST_EVAL_DATE_ARG_NAME),
        num_storm_objects=getattr(INPUT_ARG_OBJECT, NUM_STORM_OBJECTS_ARG_NAME),
        output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME))
