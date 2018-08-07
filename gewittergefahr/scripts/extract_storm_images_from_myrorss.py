"""Extracts storm-centered radar images from MYRORSS data."""

import argparse
import numpy
from gewittergefahr.gg_io import myrorss_io
from gewittergefahr.gg_io import storm_tracking_io as tracking_io
from gewittergefahr.gg_utils import storm_tracking_utils as tracking_utils
from gewittergefahr.gg_utils import radar_utils
from gewittergefahr.gg_utils import echo_top_tracking
from gewittergefahr.deep_learning import storm_images

SEPARATOR_STRING = '\n\n' + '*' * 50 + '\n\n'

ALL_AZ_SHEAR_FIELD_NAMES = [
    radar_utils.LOW_LEVEL_SHEAR_NAME, radar_utils.MID_LEVEL_SHEAR_NAME]

NUM_ROWS_ARG_NAME = 'num_rows_per_image'
NUM_COLUMNS_ARG_NAME = 'num_columns_per_image'
ROTATE_GRIDS_ARG_NAME = 'rotate_grids'
GRID_SPACING_ARG_NAME = 'rotated_grid_spacing_metres'
RADAR_FIELD_NAMES_ARG_NAME = 'radar_field_names'
REFL_HEIGHTS_ARG_NAME = 'reflectivity_heights_m_asl'
SPC_DATE_ARG_NAME = 'spc_date_string'
TARRED_MYRORSS_DIR_ARG_NAME = 'input_tarred_myrorss_dir_name'
UNTARRED_MYRORSS_DIR_ARG_NAME = 'input_untarred_myrorss_dir_name'
TRACKING_DIR_ARG_NAME = 'input_tracking_dir_name'
TRACKING_SCALE_ARG_NAME = 'tracking_scale_metres2'
OUTPUT_DIR_ARG_NAME = 'output_dir_name'

NUM_ROWS_HELP_STRING = (
    'Number of pixel rows in each storm-centered radar image.')
NUM_COLUMNS_HELP_STRING = (
    'Number of pixel columns in each storm-centered radar image.')
ROTATE_GRIDS_HELP_STRING = (
    'Boolean flag.  If 1, each grid will be rotated so that storm motion is in '
    'the +x-direction; thus, storm-centered grids will be equidistant.  If '
    'False, each storm-centered grid will be a contiguous rectangle extracted '
    'from the full grid; thus, storm-centered grids will be lat-long.')
GRID_SPACING_HELP_STRING = (
    '[used only if `{0:s}` = 1] Spacing between grid points in adjacent rows or'
    ' columns.'
).format(ROTATE_GRIDS_ARG_NAME)
RADAR_FIELD_NAMES_HELP_STRING = (
    'List with names of radar fields.  For more details, see documentation for'
    ' `{0:s}`.').format(SPC_DATE_ARG_NAME)
RADAR_HEIGHTS_HELP_STRING = (
    'List of radar heights (metres above sea level).  These apply only to the '
    'field "{0:s}" (all other fields are 2-D).  For more details, see '
    'documentation for `{1:s}`.').format(radar_utils.REFL_NAME,
                                         SPC_DATE_ARG_NAME)
SPC_DATE_HELP_STRING = (
    'SPC (Storm Prediction Center) date in format "yyyymmdd".  An image will be'
    ' created for each field, height, and storm object on this date.  Fields '
    'and heights are determined by defaults in `storm_images.'
    'extract_storm_images_myrorss_or_mrms`.')
TARRED_MYRORSS_DIR_HELP_STRING = (
    'Name of top-level directory with tarred MYRORSS data (one tar file per SPC'
    ' date).')
UNTARRED_MYRORSS_DIR_HELP_STRING = (
    'Name of top-level directory for untarred MYRORSS data.  Tar files will be '
    'temporarily extracted here, but extracted contents will be deleted at the '
    'end of the script.')
TRACKING_DIR_HELP_STRING = (
    'Name of top-level directory with storm-tracking data.')
TRACKING_SCALE_HELP_STRING = (
    'Tracking scale (minimum storm area).  This argument is used to find the '
    'specific tracking files in `{0:s}`.').format(TRACKING_DIR_ARG_NAME)
OUTPUT_DIR_HELP_STRING = (
    'Name of top-level directory for storm-centered radar images.')

DEFAULT_TARRED_DIR_NAME = '/condo/swatcommon/common/myrorss'
DEFAULT_UNTARRED_DIR_NAME = '/condo/swatwork/ralager/myrorss_temp'
DEFAULT_TRACKING_DIR_NAME = (
    '/condo/swatwork/ralager/myrorss_40dbz_echo_tops/echo_top_tracking/'
    'joined_across_spc_dates/smart_polygons')
DEFAULT_OUTPUT_DIR_NAME = (
    '/condo/swatwork/ralager/myrorss_40dbz_echo_tops/echo_top_tracking/'
    'joined_across_spc_dates/smart_polygons/storm_images')

DEFAULT_TRACKING_SCALE_METRES2 = int(numpy.round(
    echo_top_tracking.DUMMY_TRACKING_SCALE_METRES2))

INPUT_ARG_PARSER = argparse.ArgumentParser()
INPUT_ARG_PARSER.add_argument(
    '--' + NUM_ROWS_ARG_NAME, type=int, required=False,
    default=storm_images.DEFAULT_NUM_IMAGE_ROWS, help=NUM_ROWS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + NUM_COLUMNS_ARG_NAME, type=int, required=False,
    default=storm_images.DEFAULT_NUM_IMAGE_COLUMNS,
    help=NUM_COLUMNS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + ROTATE_GRIDS_ARG_NAME, type=int, required=False,
    default=1, help=ROTATE_GRIDS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + GRID_SPACING_ARG_NAME, type=float, required=False,
    default=storm_images.DEFAULT_ROTATED_GRID_SPACING_METRES,
    help=GRID_SPACING_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + RADAR_FIELD_NAMES_ARG_NAME, type=str, nargs='+', required=False,
    default=storm_images.DEFAULT_MYRORSS_MRMS_FIELD_NAMES,
    help=RADAR_FIELD_NAMES_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + REFL_HEIGHTS_ARG_NAME, type=int, nargs='+', required=False,
    default=storm_images.DEFAULT_RADAR_HEIGHTS_M_ASL,
    help=RADAR_HEIGHTS_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + SPC_DATE_ARG_NAME, type=str, required=True,
    help=SPC_DATE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + TARRED_MYRORSS_DIR_ARG_NAME, type=str, required=False,
    default=DEFAULT_TARRED_DIR_NAME, help=TARRED_MYRORSS_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + UNTARRED_MYRORSS_DIR_ARG_NAME, type=str, required=False,
    default=DEFAULT_UNTARRED_DIR_NAME, help=UNTARRED_MYRORSS_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + TRACKING_DIR_ARG_NAME, type=str, required=False,
    default=DEFAULT_TRACKING_DIR_NAME, help=TRACKING_DIR_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + TRACKING_SCALE_ARG_NAME, type=int, required=False,
    default=DEFAULT_TRACKING_SCALE_METRES2, help=TRACKING_SCALE_HELP_STRING)

INPUT_ARG_PARSER.add_argument(
    '--' + OUTPUT_DIR_ARG_NAME, type=str, required=False,
    default=DEFAULT_OUTPUT_DIR_NAME, help=OUTPUT_DIR_HELP_STRING)


def _extract_storm_images(
        num_image_rows, num_image_columns, rotate_grids,
        rotated_grid_spacing_metres, radar_field_names, refl_heights_m_asl,
        spc_date_string, tarred_myrorss_dir_name, untarred_myrorss_dir_name,
        top_tracking_dir_name, tracking_scale_metres2, top_output_dir_name):
    """Extracts storm-centered radar image for each field, height, storm object.

    :param num_image_rows: See documentation at top of file.
    :param num_image_columns: Same.
    :param rotate_grids: Same.
    :param rotated_grid_spacing_metres: Same.
    :param radar_field_names: Same.
    :param refl_heights_m_asl: Same.
    :param spc_date_string: Same.
    :param tarred_myrorss_dir_name: Same.
    :param untarred_myrorss_dir_name: Same.
    :param top_tracking_dir_name: Same.
    :param tracking_scale_metres2: Same.
    :param top_output_dir_name: Same.
    """

    # Untar files with azimuthal shear.
    az_shear_field_names = list(
        set(radar_field_names) & set(ALL_AZ_SHEAR_FIELD_NAMES))

    if len(az_shear_field_names):
        az_shear_tar_file_name = (
            '{0:s}/{1:s}/azimuthal_shear_only/{2:s}.tar'.format(
                tarred_myrorss_dir_name, spc_date_string[:4], spc_date_string))

        myrorss_io.unzip_1day_tar_file(
            tar_file_name=az_shear_tar_file_name,
            field_names=az_shear_field_names, spc_date_string=spc_date_string,
            top_target_directory_name=untarred_myrorss_dir_name)
        print SEPARATOR_STRING

    # Untar files with other fields.
    non_shear_field_names = list(
        set(radar_field_names) - set(ALL_AZ_SHEAR_FIELD_NAMES))

    if len(non_shear_field_names):
        non_shear_tar_file_name = '{0:s}/{1:s}/{2:s}.tar'.format(
            tarred_myrorss_dir_name, spc_date_string[:4], spc_date_string)

        myrorss_io.unzip_1day_tar_file(
            tar_file_name=non_shear_tar_file_name,
            field_names=non_shear_field_names, spc_date_string=spc_date_string,
            top_target_directory_name=untarred_myrorss_dir_name,
            refl_heights_m_asl=refl_heights_m_asl)
        print SEPARATOR_STRING

    # Read tracking data for the given SPC date.
    tracking_file_names, _ = tracking_io.find_processed_files_one_spc_date(
        spc_date_string=spc_date_string,
        data_source=tracking_utils.SEGMOTION_SOURCE_ID,
        top_processed_dir_name=top_tracking_dir_name,
        tracking_scale_metres2=tracking_scale_metres2)

    storm_object_table = tracking_io.read_many_processed_files(
        tracking_file_names)
    print SEPARATOR_STRING

    # Extract and write storm-centered radar images.
    storm_images.extract_storm_images_myrorss_or_mrms(
        storm_object_table=storm_object_table,
        radar_source=radar_utils.MYRORSS_SOURCE_ID,
        top_radar_dir_name=untarred_myrorss_dir_name,
        top_output_dir_name=top_output_dir_name, one_file_per_time_step=False,
        num_storm_image_rows=num_image_rows,
        num_storm_image_columns=num_image_columns, rotate_grids=rotate_grids,
        rotated_grid_spacing_metres=rotated_grid_spacing_metres,
        radar_field_names=radar_field_names,
        reflectivity_heights_m_asl=refl_heights_m_asl)
    print SEPARATOR_STRING

    # Remove MYRORSS data that were just untarred.
    myrorss_io.remove_unzipped_data_1day(
        spc_date_string=spc_date_string,
        top_directory_name=untarred_myrorss_dir_name,
        field_names=radar_field_names, refl_heights_m_asl=refl_heights_m_asl)
    print SEPARATOR_STRING


if __name__ == '__main__':
    INPUT_ARG_OBJECT = INPUT_ARG_PARSER.parse_args()

    _extract_storm_images(
        num_image_rows=getattr(INPUT_ARG_OBJECT, NUM_ROWS_ARG_NAME),
        num_image_columns=getattr(INPUT_ARG_OBJECT, NUM_COLUMNS_ARG_NAME),
        rotate_grids=bool(getattr(INPUT_ARG_OBJECT, ROTATE_GRIDS_ARG_NAME)),
        rotated_grid_spacing_metres=getattr(
            INPUT_ARG_OBJECT, GRID_SPACING_ARG_NAME),
        radar_field_names=getattr(INPUT_ARG_OBJECT, RADAR_FIELD_NAMES_ARG_NAME),
        refl_heights_m_asl=numpy.array(
            getattr(INPUT_ARG_OBJECT, REFL_HEIGHTS_ARG_NAME), dtype=int),
        spc_date_string=getattr(INPUT_ARG_OBJECT, SPC_DATE_ARG_NAME),
        tarred_myrorss_dir_name=getattr(
            INPUT_ARG_OBJECT, TARRED_MYRORSS_DIR_ARG_NAME),
        untarred_myrorss_dir_name=getattr(
            INPUT_ARG_OBJECT, UNTARRED_MYRORSS_DIR_ARG_NAME),
        top_tracking_dir_name=getattr(INPUT_ARG_OBJECT, TRACKING_DIR_ARG_NAME),
        tracking_scale_metres2=getattr(
            INPUT_ARG_OBJECT, TRACKING_SCALE_ARG_NAME),
        top_output_dir_name=getattr(INPUT_ARG_OBJECT, OUTPUT_DIR_ARG_NAME))
