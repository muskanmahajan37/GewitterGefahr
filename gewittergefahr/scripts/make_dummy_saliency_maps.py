"""Creates dummy saliency map for each storm object.

In these dummy saliency maps, the "saliency map" is actually just the filter
produced by an edge-detector with no learned weights.
"""

import os.path
import argparse
import numpy
from keras import backend as K
from gewittergefahr.gg_io import storm_tracking_io as tracking_io
from gewittergefahr.gg_utils import file_system_utils
from gewittergefahr.deep_learning import cnn
from gewittergefahr.deep_learning import testing_io
from gewittergefahr.deep_learning import training_validation_io as trainval_io
from gewittergefahr.deep_learning import model_interpretation
from gewittergefahr.deep_learning import saliency_maps
from gewittergefahr.deep_learning import standalone_utils

K.set_session(K.tf.Session(config=K.tf.ConfigProto(
    intra_op_parallelism_threads=1, inter_op_parallelism_threads=1
)))

SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

EDGE_DETECTOR_MATRIX = numpy.array([
    [-1, -1, -1],
    [-1, 8, -1],
    [-1, -1, -1]
], dtype=float)

MODEL_FILE_ARG_NAME = 'model_file_name'
EXAMPLE_DIR_ARG_NAME = 'input_example_dir_name'
STORM_METAFILE_ARG_NAME = 'input_storm_metafile_name'
NUM_EXAMPLES_ARG_NAME = 'num_examples'
OUTPUT_FILE_ARG_NAME = 'output_file_name'

MODEL_FILE_HELP_STRING = (
    'Path to input file, containing a CNN.  Only the metadata will be read, by '
    '`cnn.read_model_metadata`.')

EXAMPLE_DIR_HELP_STRING = (
    'Name of top-level directory with input examples.  Files therein will be '
    'found by `input_examples.find_example_file` and read by '
    '`input_examples.read_example_file`.')

STORM_METAFILE_HELP_STRING = (
    'Path to Pickle file with storm IDs and times.  Will be read by '
    '`storm_tracking_io.read_ids_and_times`.')

NUM_EXAMPLES_HELP_STRING = (
    'Number of examples (storm objects) to read from `{0:s}`.  If you want to '
    'read all examples, make this non-positive.'
).format(STORM_METAFILE_ARG_NAME)

OUTPUT_FILE_HELP_STRING = (
    'Path to output file (will be written by '
    '`saliency_maps.write_standard_file`).')

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + MODEL_FILE_ARG_NAME, type=str, required=True,
    help=MODEL_FILE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + EXAMPLE_DIR_ARG_NAME, type=str, required=True,
    help=EXAMPLE_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + STORM_METAFILE_ARG_NAME, type=str, required=True,
    help=STORM_METAFILE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_EXAMPLES_ARG_NAME, type=int, required=False, default=-1,
    help=NUM_EXAMPLES_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_FILE_ARG_NAME, type=str, required=True,
    help=OUTPUT_FILE_HELP_STRING)


def _run(model_file_name, top_example_dir_name, storm_metafile_name,
         num_examples, output_file_name):
    """Creates dummy saliency map for each storm object.

    This is effectively the main method.

    :param model_file_name: See documentation at top of file.
    :param top_example_dir_name: Same.
    :param storm_metafile_name: Same.
    :param num_examples: Same.
    :param output_file_name: Same.
    """

    file_system_utils.mkdir_recursive_if_necessary(file_name=output_file_name)

    model_metafile_name = '{0:s}/model_metadata.p'.format(
        os.path.split(model_file_name)[0]
    )

    print('Reading model metadata from: "{0:s}"...'.format(model_metafile_name))
    model_metadata_dict = cnn.read_model_metadata(model_metafile_name)
    training_option_dict = model_metadata_dict[cnn.TRAINING_OPTION_DICT_KEY]
    training_option_dict[trainval_io.REFLECTIVITY_MASK_KEY] = None

    print('Reading storm metadata from: "{0:s}"...'.format(storm_metafile_name))
    full_id_strings, storm_times_unix_sec = tracking_io.read_ids_and_times(
        storm_metafile_name)

    print(SEPARATOR_STRING)

    if 0 < num_examples < len(full_id_strings):
        full_id_strings = full_id_strings[:num_examples]
        storm_times_unix_sec = storm_times_unix_sec[:num_examples]

    list_of_input_matrices, sounding_pressure_matrix_pascals = (
        testing_io.read_specific_examples(
            top_example_dir_name=top_example_dir_name,
            desired_full_id_strings=full_id_strings,
            desired_times_unix_sec=storm_times_unix_sec,
            option_dict=training_option_dict,
            list_of_layer_operation_dicts=model_metadata_dict[
                cnn.LAYER_OPERATIONS_KEY]
        )
    )

    radar_matrix = list_of_input_matrices[0]
    num_examples = radar_matrix.shape[0]
    num_channels = radar_matrix.shape[-1]

    kernel_matrix = numpy.expand_dims(EDGE_DETECTOR_MATRIX, axis=-1)
    kernel_matrix = numpy.repeat(kernel_matrix, num_channels, axis=-1)
    kernel_matrix = numpy.expand_dims(kernel_matrix, axis=-1)
    kernel_matrix = numpy.repeat(kernel_matrix, num_channels, axis=-1)

    radar_saliency_matrix = numpy.full(radar_matrix.shape, numpy.nan)

    for i in range(num_examples):
        this_saliency_matrix = standalone_utils.do_2d_convolution(
            feature_matrix=radar_matrix[i, ...], kernel_matrix=kernel_matrix,
            pad_edges=True, stride_length_px=1)

        radar_saliency_matrix[i, ...] = this_saliency_matrix[0, ...]

    list_of_saliency_matrices = [
        radar_saliency_matrix if k == 0 else list_of_input_matrices[k]
        for k in range(len(list_of_input_matrices))
    ]

    print('Denormalizing model inputs...')
    list_of_input_matrices = model_interpretation.denormalize_data(
        list_of_input_matrices=list_of_input_matrices,
        model_metadata_dict=model_metadata_dict)

    print('Writing saliency maps to file: "{0:s}"...'.format(output_file_name))

    saliency_metadata_dict = saliency_maps.check_metadata(
        component_type_string=model_interpretation.CLASS_COMPONENT_TYPE_STRING,
        target_class=1)

    saliency_maps.write_standard_file(
        pickle_file_name=output_file_name,
        list_of_input_matrices=list_of_input_matrices,
        list_of_saliency_matrices=list_of_saliency_matrices,
        full_id_strings=full_id_strings,
        storm_times_unix_sec=storm_times_unix_sec,
        model_file_name=model_file_name,
        saliency_metadata_dict=saliency_metadata_dict,
        sounding_pressure_matrix_pascals=sounding_pressure_matrix_pascals)


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _run(
        model_file_name=getattr(INPUT_ARG_OBJECT, MODEL_FILE_ARG_NAME),
        top_example_dir_name=getattr(INPUT_ARG_OBJECT, EXAMPLE_DIR_ARG_NAME),
        storm_metafile_name=getattr(INPUT_ARG_OBJECT, STORM_METAFILE_ARG_NAME),
        num_examples=getattr(INPUT_ARG_OBJECT, NUM_EXAMPLES_ARG_NAME),
        output_file_name=getattr(INPUT_ARG_OBJECT, OUTPUT_FILE_ARG_NAME)
    )