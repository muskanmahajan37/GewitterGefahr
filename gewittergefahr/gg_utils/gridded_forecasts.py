"""Methods to create gridded spatial forecasts from storm-cell-based ones."""

import copy
import numpy
import pandas
from gewittergefahr.gg_utils import storm_tracking_utils as tracking_utils
from gewittergefahr.gg_utils import projections
from gewittergefahr.gg_utils import polygons
from gewittergefahr.gg_utils import grids
from gewittergefahr.gg_utils import interp
from gewittergefahr.gg_utils import nwp_model_utils
from gewittergefahr.gg_utils import grid_smoothing_2d
from gewittergefahr.gg_utils import geodetic_utils
from gewittergefahr.gg_utils import time_conversion
from gewittergefahr.gg_utils import number_rounding as rounder
from gewittergefahr.gg_utils import error_checking
from gewittergefahr.deep_learning import prediction_io

# TODO(thunderhoser): This file needs to be cleaned up a bit.  I used to allow
# each init time to have its own grid, and some of the code for this is still
# hanging around.

MINOR_SEPARATOR_STRING = '\n\n' + '-' * 50 + '\n\n'

MAX_STORM_SPEED_M_S01 = 60.
LOG_MESSAGE_TIME_FORMAT = '%Y-%m-%d-%H%M%S'

GAUSSIAN_SMOOTHING_METHOD = 'gaussian'
CRESSMAN_SMOOTHING_METHOD = 'cressman'
VALID_SMOOTHING_METHODS = [GAUSSIAN_SMOOTHING_METHOD, CRESSMAN_SMOOTHING_METHOD]

DEFAULT_PROJECTION_OBJECT = nwp_model_utils.init_projection(
    nwp_model_utils.RAP_MODEL_NAME)

DEFAULT_LEAD_TIME_RES_SECONDS = 60
DEFAULT_GRID_SPACING_METRES = 1000.
DEFAULT_GRID_SPACING_DEG = 0.01
DEFAULT_PROB_RADIUS_FOR_GRID_METRES = 1e4
DEFAULT_SMOOTHING_E_FOLDING_RADIUS_METRES = 5000.
DEFAULT_SMOOTHING_CUTOFF_RADIUS_METRES = 15000.

LATLNG_POLYGON_COLUMN_PREFIX = tracking_utils.BUFFER_COLUMN_PREFIX
XY_POLYGON_COLUMN_PREFIX = 'polygon_object_xy_buffer'
FORECAST_COLUMN_PREFIX = 'forecast_probability_buffer'
GRID_ROWS_IN_POLYGON_COLUMN_PREFIX = 'grid_rows_in_buffer'
GRID_COLUMNS_IN_POLYGON_COLUMN_PREFIX = 'grid_columns_in_buffer'

COLUMN_PREFIXES = [
    LATLNG_POLYGON_COLUMN_PREFIX, XY_POLYGON_COLUMN_PREFIX,
    FORECAST_COLUMN_PREFIX, GRID_ROWS_IN_POLYGON_COLUMN_PREFIX,
    GRID_COLUMNS_IN_POLYGON_COLUMN_PREFIX
]

LATLNG_POLYGON_COLUMN_TYPE = 'latlng'
XY_POLYGON_COLUMN_TYPE = 'xy'
FORECAST_COLUMN_TYPE = 'forecast'
GRID_ROWS_IN_POLYGON_COLUMN_TYPE = 'grid_rows_in_polygon'
GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE = 'grid_columns_in_polygon'

COLUMN_TYPES = [
    LATLNG_POLYGON_COLUMN_TYPE, XY_POLYGON_COLUMN_TYPE, FORECAST_COLUMN_TYPE,
    GRID_ROWS_IN_POLYGON_COLUMN_TYPE, GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE
]

SPEED_COLUMN = 'speed_m_s01'
GEOGRAPHIC_BEARING_COLUMN = 'geographic_bearing_deg'


def _check_smoothing_method(smoothing_method):
    """Ensures that smoothing method is valid.

    :param smoothing_method: String name for smoothing method.
    :raises: ValueError: if `smoothing_method not in VALID_SMOOTHING_METHODS`.
    """

    error_checking.assert_is_string(smoothing_method)

    if smoothing_method not in VALID_SMOOTHING_METHODS:
        error_string = (
            '\n{0:s}\nValid smoothing methods (listed above) do not include '
            '"{1:s}".'
        ).format(str(VALID_SMOOTHING_METHODS), smoothing_method)

        raise ValueError(error_string)


def _column_name_to_buffer(column_name):
    """Parses distance buffer from column name.

    If distance buffer cannot be found in column name, returns None for all
    outputs.

    :param column_name: Name of column.  This column may contain x-y polygons,
        lat-long polygons, or forecast probabilities.
    :return: min_buffer_dist_metres: Minimum buffer distance.
    :return: max_buffer_dist_metres: Maximum buffer distance.
    """

    this_column_name = copy.deepcopy(column_name)
    for this_prefix in COLUMN_PREFIXES:
        this_column_name = this_column_name.replace(
            this_prefix, LATLNG_POLYGON_COLUMN_PREFIX)

    return tracking_utils.column_name_to_buffer(this_column_name)


def _buffer_to_column_name(
        min_buffer_dist_metres, max_buffer_dist_metres, column_type):
    """Generates column name for distance buffer.

    :param min_buffer_dist_metres: Minimum buffer distance.
    :param max_buffer_dist_metres: Max buffer distance.
    :param column_type: Column type (may be any string in `COLUMN_TYPES`).
    :return: column_name: Name of column.
    """

    column_name = tracking_utils.buffer_to_column_name(
        min_distance_metres=min_buffer_dist_metres,
        max_distance_metres=max_buffer_dist_metres)

    if column_type == LATLNG_POLYGON_COLUMN_TYPE:
        return column_name

    if column_type == XY_POLYGON_COLUMN_TYPE:
        return column_name.replace(
            LATLNG_POLYGON_COLUMN_PREFIX, XY_POLYGON_COLUMN_PREFIX)

    if column_type == FORECAST_COLUMN_TYPE:
        return column_name.replace(
            LATLNG_POLYGON_COLUMN_PREFIX, FORECAST_COLUMN_PREFIX)

    if column_type == GRID_ROWS_IN_POLYGON_COLUMN_TYPE:
        return column_name.replace(
            LATLNG_POLYGON_COLUMN_PREFIX, GRID_ROWS_IN_POLYGON_COLUMN_PREFIX)

    if column_type == GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE:
        return column_name.replace(
            LATLNG_POLYGON_COLUMN_PREFIX, GRID_COLUMNS_IN_POLYGON_COLUMN_PREFIX)

    return None


def _get_distance_buffer_columns(storm_object_table, column_type):
    """Returns all column names corresponding to distance buffers.

    :param storm_object_table: pandas DataFrame.
    :param column_type: Column type (may be any string in `COLUMN_TYPES`).
    :return: dist_buffer_column_names: 1-D list of column names corresponding to
        distance buffers.  If there are no columns with distance buffers,
        returns None.
    """

    column_names = list(storm_object_table)
    dist_buffer_column_names = None

    for this_column_name in column_names:
        if (column_type == XY_POLYGON_COLUMN_TYPE
                and XY_POLYGON_COLUMN_PREFIX not in this_column_name):
            continue

        if (column_type == LATLNG_POLYGON_COLUMN_TYPE
                and LATLNG_POLYGON_COLUMN_PREFIX not in this_column_name):
            continue

        if (column_type == FORECAST_COLUMN_TYPE
                and FORECAST_COLUMN_PREFIX not in this_column_name):
            continue

        if (column_type == GRID_ROWS_IN_POLYGON_COLUMN_TYPE
                and GRID_ROWS_IN_POLYGON_COLUMN_PREFIX not in this_column_name):
            continue

        if (column_type == GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE
                and GRID_COLUMNS_IN_POLYGON_COLUMN_PREFIX not in
                this_column_name):
            continue

        _, this_max_distance_metres = _column_name_to_buffer(
            this_column_name)
        if this_max_distance_metres is None:
            continue

        if dist_buffer_column_names is None:
            dist_buffer_column_names = [this_column_name]
        else:
            dist_buffer_column_names.append(this_column_name)

    return dist_buffer_column_names


def _check_distance_buffers(min_distances_metres, max_distances_metres):
    """Ensures that distance buffers are unique and abutting.

    B = number of distance buffers

    :param min_distances_metres: length-B numpy array of minimum buffer
        distances.
    :param max_distances_metres: length-B numpy array of max buffer distances.
    :raises: ValueError: if distance buffers are non-unique or non-abutting.
    """

    error_checking.assert_is_numpy_array(
        min_distances_metres, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(
        min_distances_metres, 0., allow_nan=True)

    num_buffers = len(min_distances_metres)
    these_expected_dim = numpy.array([num_buffers], dtype=int)
    error_checking.assert_is_numpy_array(
        max_distances_metres, exact_dimensions=these_expected_dim)

    sort_indices = numpy.argsort(max_distances_metres)
    sorted_min_distances_metres = numpy.round(
        min_distances_metres[sort_indices]
    )
    sorted_max_distances_metres = numpy.round(
        max_distances_metres[sort_indices]
    )

    for j in range(num_buffers):
        if numpy.isnan(sorted_min_distances_metres[j]):
            error_checking.assert_is_geq(sorted_max_distances_metres[j], 0.)
        else:
            error_checking.assert_is_greater(
                sorted_max_distances_metres[j], sorted_min_distances_metres[j]
            )

        if (j != 0 and sorted_min_distances_metres[j]
                != sorted_max_distances_metres[j - 1]):
            error_string = (
                'Minimum distance for {0:d}th buffer ({1:d} m) does not equal '
                'max distance for {2:d}th buffer ({3:d} m).  This means the two'
                ' distance buffers are not abutting.'
            ).format(
                j + 1, int(sorted_min_distances_metres[j]), j,
                int(sorted_max_distances_metres[j - 1])
            )

            raise ValueError(error_string)


def _polygons_from_latlng_to_xy(
        storm_object_table, projection_object=DEFAULT_PROJECTION_OBJECT):
    """Projects distance buffers around each storm object from lat-long to x-y.

    N = number of storm objects
    B = number of distance buffers around each storm object

    :param storm_object_table: N-row pandas DataFrame.  Each row contains the
        polygons for distance buffers around one storm object.  For the [j]th
        distance buffer, required column is given by the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="latlng")
    :param projection_object: See doc for `polygons.project_latlng_to_xy`.
    :return: storm_object_table: Same as input but with additional columns.  For
        the [j]th distance buffer, new column is given by the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")
    """

    buffer_column_names_latlng = _get_distance_buffer_columns(
        storm_object_table=storm_object_table,
        column_type=LATLNG_POLYGON_COLUMN_TYPE)

    num_buffers = len(buffer_column_names_latlng)
    min_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    max_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    buffer_column_names_xy = [''] * num_buffers

    for j in range(num_buffers):
        min_buffer_distances_metres[j], max_buffer_distances_metres[j] = (
            _column_name_to_buffer(buffer_column_names_latlng[j])
        )

        buffer_column_names_xy[j] = _buffer_to_column_name(
            min_buffer_distances_metres[j], max_buffer_distances_metres[j],
            column_type=XY_POLYGON_COLUMN_TYPE)

    num_storm_objects = len(storm_object_table.index)
    object_array = numpy.full(num_storm_objects, numpy.nan, dtype=object)

    for j in range(num_buffers):
        storm_object_table = storm_object_table.assign(**{
            buffer_column_names_xy[j]: object_array
        })

    for i in range(num_storm_objects):
        for j in range(num_buffers):
            storm_object_table[buffer_column_names_xy[j]].values[i], _ = (
                polygons.project_latlng_to_xy(
                    polygon_object_latlng=storm_object_table[
                        buffer_column_names_latlng[j]
                    ].values[i],
                    projection_object=projection_object,
                    false_easting_metres=0., false_northing_metres=0.)
            )

    return storm_object_table


def _create_default_xy_grid(x_spacing_metres, y_spacing_metres):
    """Creates default x-y grid.

    M = number of rows in grid
    N = number of columns in grid

    :param x_spacing_metres: Spacing between adjacent grid points in x-direction
        (i.e., between adjacent columns).
    :param y_spacing_metres: Spacing between adjacent grid points in y-direction
        (i.e., between adjacent rows).
    :return: grid_points_x_metres: length-N numpy array with x-coordinates of
        grid points.
    :return: grid_points_y_metres: length-M numpy array with y-coordinates of
        grid points.
    """

    rap_x_coords_metres, rap_y_coords_metres = (
        nwp_model_utils.get_xy_grid_points(
            model_name=nwp_model_utils.RAP_MODEL_NAME,
            grid_name=nwp_model_utils.NAME_OF_130GRID)
    )

    false_easting_metres, false_northing_metres = (
        nwp_model_utils.get_false_easting_and_northing(
            model_name=nwp_model_utils.RAP_MODEL_NAME,
            grid_name=nwp_model_utils.NAME_OF_130GRID)
    )

    rap_x_coords_metres -= false_easting_metres
    rap_y_coords_metres -= false_northing_metres

    x_min_metres = rap_x_coords_metres[50]
    x_max_metres = rap_x_coords_metres[-30]
    y_min_metres = rap_y_coords_metres[40]
    y_max_metres = rap_y_coords_metres[-70]

    x_min_metres = rounder.floor_to_nearest(x_min_metres, x_spacing_metres)
    x_max_metres = rounder.ceiling_to_nearest(x_max_metres, x_spacing_metres)
    y_min_metres = rounder.floor_to_nearest(y_min_metres, y_spacing_metres)
    y_max_metres = rounder.ceiling_to_nearest(y_max_metres, y_spacing_metres)

    num_rows = 1 + int(numpy.round(
        (y_max_metres - y_min_metres) / y_spacing_metres
    ))
    num_columns = 1 + int(numpy.round(
        (x_max_metres - x_min_metres) / x_spacing_metres
    ))

    return grids.get_xy_grid_points(
        x_min_metres=x_min_metres, y_min_metres=y_min_metres,
        x_spacing_metres=x_spacing_metres, y_spacing_metres=y_spacing_metres,
        num_rows=num_rows, num_columns=num_columns)


def _create_xy_grid(storm_object_table, x_spacing_metres, y_spacing_metres,
                    max_lead_time_sec):
    """Creates x-y grid encompassing all storm objects.

    M = number of grid rows (unique grid-point y-coordinates)
    N = number of grid columns (unique grid-point x-coordinates)

    :param storm_object_table: pandas DataFrame.  Each row contains the polygons
        and forecast probabilities for distance buffers around one storm object.
        For the [j]th distance buffer, required columns are given by the
        following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")

    :param x_spacing_metres: Spacing between adjacent grid points in x-direction
        (i.e., between adjacent columns).
    :param y_spacing_metres: Spacing between adjacent grid points in y-direction
        (i.e., between adjacent rows).
    :param max_lead_time_sec: Max lead time for which gridded forecasts will be
        created.
    :return: grid_points_x_metres: length-N numpy array with x-coordinates of
        grid points.
    :return: grid_points_y_metres: length-M numpy array with y-coordinates of
        grid points.
    """

    buffer_column_names_xy = _get_distance_buffer_columns(
        storm_object_table=storm_object_table,
        column_type=XY_POLYGON_COLUMN_TYPE)

    x_min_metres = numpy.inf
    x_max_metres = -numpy.inf
    y_min_metres = numpy.inf
    y_max_metres = -numpy.inf

    num_buffers = len(buffer_column_names_xy)
    num_storm_objects = len(storm_object_table.index)

    for i in range(num_storm_objects):
        for j in range(num_buffers):
            this_polygon_object = storm_object_table[
                buffer_column_names_xy[j]
            ].values[i]

            these_x_metres = numpy.array(this_polygon_object.exterior.xy[0])
            these_y_metres = numpy.array(this_polygon_object.exterior.xy[1])

            x_min_metres = min([x_min_metres, numpy.min(these_x_metres)])
            x_max_metres = max([x_max_metres, numpy.max(these_x_metres)])
            y_min_metres = min([y_min_metres, numpy.min(these_y_metres)])
            y_max_metres = max([y_max_metres, numpy.max(these_y_metres)])

    x_min_metres = x_min_metres - MAX_STORM_SPEED_M_S01 * max_lead_time_sec
    x_max_metres = x_max_metres + MAX_STORM_SPEED_M_S01 * max_lead_time_sec
    y_min_metres = y_min_metres - MAX_STORM_SPEED_M_S01 * max_lead_time_sec
    y_max_metres = y_max_metres + MAX_STORM_SPEED_M_S01 * max_lead_time_sec

    x_min_metres = rounder.floor_to_nearest(x_min_metres, x_spacing_metres)
    x_max_metres = rounder.ceiling_to_nearest(x_max_metres, x_spacing_metres)
    y_min_metres = rounder.floor_to_nearest(y_min_metres, y_spacing_metres)
    y_max_metres = rounder.ceiling_to_nearest(y_max_metres, y_spacing_metres)

    num_rows = 1 + int(numpy.round(
        (y_max_metres - y_min_metres) / y_spacing_metres
    ))
    num_columns = 1 + int(numpy.round(
        (x_max_metres - x_min_metres) / x_spacing_metres
    ))

    return grids.get_xy_grid_points(
        x_min_metres=x_min_metres, y_min_metres=y_min_metres,
        x_spacing_metres=x_spacing_metres, y_spacing_metres=y_spacing_metres,
        num_rows=num_rows, num_columns=num_columns)


def _create_latlng_grid(
        grid_points_x_metres, grid_points_y_metres, latitude_spacing_deg,
        longitude_spacing_deg, projection_object=DEFAULT_PROJECTION_OBJECT):
    """Creates a lat-long grid encompassing the original x-y grid.

    M_xy = number of rows (unique grid-point y-coordinates) in original grid
    N_xy = number of columns (unique grid-point x-coordinates) in original grid
    M_ll = number of rows (unique grid-point latitudes) in new grid
    N_ll = number of columns (unique grid-point longitudes) in new grid

    :param grid_points_x_metres: numpy array (length N_xy) with x-coordinates of
        original grid points.
    :param grid_points_y_metres: numpy array (length M_xy) with y-coordinates of
        original grid points.
    :param latitude_spacing_deg: Spacing between latitudinally adjacent grid
        points (i.e., between adjacent rows).
    :param longitude_spacing_deg: Spacing between longitudinally adjacent grid
        points (i.e., between adjacent columns).
    :param projection_object: See doc for `projections.project_xy_to_latlng`.
    :return: grid_point_latitudes_deg: numpy array (length M_ll) with latitudes
        (deg N) of new grid points.
    :return: grid_point_longitudes_deg: numpy array (length N_ll) with
        longitudes (deg E) of new grid points.
    """

    grid_point_x_matrix_metres, grid_point_y_matrix_metres = (
        grids.xy_vectors_to_matrices(
            x_unique_metres=grid_points_x_metres,
            y_unique_metres=grid_points_y_metres)
    )

    latitude_matrix_deg, longitude_matrix_deg = (
        projections.project_xy_to_latlng(
            x_coords_metres=grid_point_x_matrix_metres,
            y_coords_metres=grid_point_y_matrix_metres,
            projection_object=projection_object,
            false_easting_metres=0., false_northing_metres=0.)
    )

    min_latitude_deg = rounder.floor_to_nearest(
        numpy.min(latitude_matrix_deg), latitude_spacing_deg
    )
    max_latitude_deg = rounder.ceiling_to_nearest(
        numpy.max(latitude_matrix_deg), latitude_spacing_deg
    )
    min_longitude_deg = rounder.floor_to_nearest(
        numpy.min(longitude_matrix_deg), longitude_spacing_deg
    )
    max_longitude_deg = rounder.ceiling_to_nearest(
        numpy.max(longitude_matrix_deg), longitude_spacing_deg
    )

    num_rows = 1 + int(numpy.round(
        (max_latitude_deg - min_latitude_deg) / latitude_spacing_deg
    ))
    num_columns = 1 + int(numpy.round(
        (max_longitude_deg - min_longitude_deg) / longitude_spacing_deg
    ))

    return grids.get_latlng_grid_points(
        min_latitude_deg=min_latitude_deg, min_longitude_deg=min_longitude_deg,
        lat_spacing_deg=latitude_spacing_deg,
        lng_spacing_deg=longitude_spacing_deg, num_rows=num_rows,
        num_columns=num_columns)


def _interp_probabilities_to_latlng_grid(
        probability_matrix_xy, grid_points_x_metres, grid_points_y_metres,
        latitude_spacing_deg, longitude_spacing_deg,
        projection_object=DEFAULT_PROJECTION_OBJECT):
    """Interpolates forecast probabilities from x-y to lat-long grid.

    M_xy = number of rows (unique grid-point y-coordinates) in original grid
    N_xy = number of columns (unique grid-point x-coordinates) in original grid
    M_ll = number of rows (unique grid-point latitudes) in new grid
    N_ll = number of columns (unique grid-point longitudes) in new grid

    :param probability_matrix_xy: numpy array (M_xy by N_xy) of forecast
        probabilities on original grid.
    :param grid_points_x_metres: numpy array (length N_xy) with x-coordinates of
        original grid points.
    :param grid_points_y_metres: numpy array (length M_xy) with y-coordinates of
        original grid points.
    :param latitude_spacing_deg: Spacing between latitudinally adjacent grid
        points (i.e., between adjacent rows).
    :param longitude_spacing_deg: Spacing between longitudinally adjacent grid
        points (i.e., between adjacent columns).
    :param projection_object: See doc for `projections.project_xy_to_latlng`.
    :return: probability_matrix_latlng: numpy array (M_ll by N_ll) of forecast
        probabilities on new grid.
    :return: grid_point_latitudes_deg: numpy array (length M_ll) with latitudes
        (deg N) of new grid points.
    :return: grid_point_longitudes_deg: numpy array (length N_ll) with
        longitudes (deg E) of new grid points.
    """

    grid_point_latitudes_deg, grid_point_longitudes_deg = _create_latlng_grid(
        grid_points_x_metres=grid_points_x_metres,
        grid_points_y_metres=grid_points_y_metres,
        projection_object=projection_object,
        latitude_spacing_deg=latitude_spacing_deg,
        longitude_spacing_deg=longitude_spacing_deg)

    grid_point_lat_matrix_deg, grid_point_lng_matrix_deg = (
        grids.latlng_vectors_to_matrices(
            unique_latitudes_deg=grid_point_latitudes_deg,
            unique_longitudes_deg=grid_point_longitudes_deg)
    )

    latlng_grid_x_matrix_metres, latlng_grid_y_matrix_metres = (
        projections.project_latlng_to_xy(
            grid_point_lat_matrix_deg, grid_point_lng_matrix_deg,
            projection_object=projection_object,
            false_easting_metres=0., false_northing_metres=0.)
    )

    num_latlng_grid_rows = len(grid_point_latitudes_deg)
    num_latlng_grid_columns = len(grid_point_longitudes_deg)
    num_latlng_grid_points = num_latlng_grid_rows * num_latlng_grid_columns

    latlng_grid_x_vector_metres = numpy.reshape(
        latlng_grid_x_matrix_metres, num_latlng_grid_points)
    latlng_grid_y_vector_metres = numpy.reshape(
        latlng_grid_y_matrix_metres, num_latlng_grid_points)

    probability_vector_latlng = interp.interp_from_xy_grid_to_points(
        input_matrix=probability_matrix_xy,
        sorted_grid_point_x_metres=grid_points_x_metres,
        sorted_grid_point_y_metres=grid_points_y_metres,
        query_x_coords_metres=latlng_grid_x_vector_metres,
        query_y_coords_metres=latlng_grid_y_vector_metres,
        method_string=interp.NEAREST_NEIGHBOUR_METHOD_STRING, extrapolate=True)

    probability_matrix_latlng = numpy.reshape(
        probability_vector_latlng,
        (num_latlng_grid_rows, num_latlng_grid_columns)
    )

    return (probability_matrix_latlng, grid_point_latitudes_deg,
            grid_point_longitudes_deg)


def _normalize_probs_by_polygon_area(
        storm_object_table, prob_radius_for_grid_metres):
    """Normalizes each forecast probability by area of the attached polygon.

    Specifically, this method applies the following equation:

    f_norm = 1 - (1 - f_polygon)^(pi * r^2 / A)

    f_polygon = forecast probability of event occurring within the polygon
    A = area of the polygon
    r = `prob_radius_for_grid_metres`
    f_norm = forecast probability of event occurring within radius r

    Also:

    N = number of storm objects
    B = number of distance buffers around each storm object

    :param storm_object_table: N-row pandas DataFrame.  Each row contains the
        polygons and forecast probabilities for distance buffers around one
        storm object.  For the [j]th distance buffer, required columns are given
        by the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="forecast")

    :param prob_radius_for_grid_metres: Effective radius for gridded
        probabilities.  For example, if the gridded value is "probability within
        10 km of a point," this should be 10 000.
    :return: storm_object_table: Same as input, except that probabilities are
        normalized.
    """

    buffer_column_names_xy = _get_distance_buffer_columns(
        storm_object_table=storm_object_table,
        column_type=XY_POLYGON_COLUMN_TYPE)

    num_buffers = len(buffer_column_names_xy)
    min_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    max_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    forecast_column_names = [''] * num_buffers

    for j in range(num_buffers):
        min_buffer_distances_metres[j], max_buffer_distances_metres[j] = (
            _column_name_to_buffer(buffer_column_names_xy[j])
        )

        forecast_column_names[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=FORECAST_COLUMN_TYPE)

    num_storm_objects = len(storm_object_table.index)
    prob_area_for_grid_metres2 = numpy.pi * prob_radius_for_grid_metres ** 2

    for j in range(num_buffers):
        these_areas_metres2 = numpy.array([
            storm_object_table[buffer_column_names_xy[j]].values[i].area
            for i in range(num_storm_objects)
        ])

        these_original_probs = storm_object_table[
            forecast_column_names[j]
        ].values

        these_normalized_probs = 1. - numpy.power(
            1. - these_original_probs,
            prob_area_for_grid_metres2 / these_areas_metres2
        )

        storm_object_table = storm_object_table.assign(**{
            forecast_column_names[j]: these_normalized_probs
        })

    return storm_object_table


def _storm_motion_from_uv_to_speed_direction(storm_object_table):
    """For each storm object, converts motion from u-v to speed-direction.

    N = number of storm objects

    :param storm_object_table: N-row pandas DataFrame with the following
        columns.
    storm_object_table.east_velocity_m_s01: Eastward velocity of storm object
        (metres per second).
    storm_object_table.north_velocity_m_s01: Northward velocity of storm object
        (metres per second).
    :return: storm_object_table: N-row pandas DataFrame with the following
        columns.
    storm_object_table.speed_m_s01: Storm speed (magnitude of velocity) in m/s.
    storm_object_table.geographic_bearing_deg: Storm bearing in geographic
        degrees (clockwise from due north).
    """

    storm_speeds_m_s01, geodetic_bearings_deg = (
        geodetic_utils.xy_to_scalar_displacements_and_bearings(
            x_displacements_metres=storm_object_table[
                tracking_utils.EAST_VELOCITY_COLUMN].values,
            y_displacements_metres=storm_object_table[
                tracking_utils.NORTH_VELOCITY_COLUMN].values)
    )

    storm_object_table = storm_object_table.assign(**{
        SPEED_COLUMN: storm_speeds_m_s01,
        GEOGRAPHIC_BEARING_COLUMN: geodetic_bearings_deg
    })

    return storm_object_table.drop(
        [tracking_utils.EAST_VELOCITY_COLUMN,
         tracking_utils.NORTH_VELOCITY_COLUMN],
        axis=1, inplace=False
    )


def _extrapolate_polygons(
        storm_object_table, lead_time_seconds,
        projection_object=DEFAULT_PROJECTION_OBJECT):
    """For each storm object, extrapolates distance buffers forward in time.

    N = number of storm objects

    :param storm_object_table: N-row pandas DataFrame.  Each row contains data
        for distance buffers around one storm object.  For the [j]th distance
        buffer, required columns are given by the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="latlng")

        Other required columns are listed below.

    storm_object_table.speed_m_s01: Storm speed (magnitude of velocity) in m/s.
    storm_object_table.geographic_bearing_deg: Storm bearing in geographic
        degrees (clockwise from due north).

    :param lead_time_seconds: Lead time.  Polygons will be extrapolated this far
        into the future.
    :param projection_object: See doc for `_polygons_from_latlng_to_xy`.
    :return: extrap_storm_object_table: N-row pandas DataFrame.  Each row
        contains extrapolated polygons for distance buffers around one storm
        object.  For the [j]th distance buffer, columns are given by the
        following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")
    """

    buffer_column_names_latlng = _get_distance_buffer_columns(
        storm_object_table=storm_object_table,
        column_type=LATLNG_POLYGON_COLUMN_TYPE)

    num_storm_objects = len(storm_object_table.index)
    object_array = numpy.full(num_storm_objects, numpy.nan, dtype=object)

    num_buffers = len(buffer_column_names_latlng)
    extrap_storm_object_table = None

    for j in range(num_buffers):
        if extrap_storm_object_table is None:
            extrap_storm_object_table = pandas.DataFrame.from_dict({
                buffer_column_names_latlng[j]: object_array
            })
        else:
            extrap_storm_object_table = extrap_storm_object_table.assign(**{
                buffer_column_names_latlng[j]: object_array
            })

    for j in range(num_buffers):
        these_first_vertex_lat_deg = [
            storm_object_table[buffer_column_names_latlng[j]].values[
                i].exterior.xy[1][0]
            for i in range(num_storm_objects)
        ]

        these_first_vertex_lng_deg = [
            storm_object_table[buffer_column_names_latlng[j]].values[
                i].exterior.xy[0][0]
            for i in range(num_storm_objects)
        ]

        these_first_vertex_lat_deg = numpy.array(these_first_vertex_lat_deg)
        these_first_vertex_lng_deg = numpy.array(these_first_vertex_lng_deg)

        these_extrap_lat_deg, these_extrap_lng_deg = (
            geodetic_utils.start_points_and_displacements_to_endpoints(
                start_latitudes_deg=these_first_vertex_lat_deg,
                start_longitudes_deg=these_first_vertex_lng_deg,
                scalar_displacements_metres=
                storm_object_table[SPEED_COLUMN].values * lead_time_seconds,
                geodetic_bearings_deg=
                storm_object_table[GEOGRAPHIC_BEARING_COLUMN].values)
        )

        these_lat_diffs_deg = these_extrap_lat_deg - these_first_vertex_lat_deg
        these_lng_diffs_deg = these_extrap_lng_deg - these_first_vertex_lng_deg

        for i in range(num_storm_objects):
            these_new_latitudes_deg = these_lat_diffs_deg[i] + numpy.array(
                storm_object_table[
                    buffer_column_names_latlng[j]].values[i].exterior.xy[1]
            )

            these_new_longitudes_deg = these_lng_diffs_deg[i] + numpy.array(
                storm_object_table[
                    buffer_column_names_latlng[j]].values[i].exterior.xy[0]
            )

            extrap_storm_object_table[
                buffer_column_names_latlng[j]
            ].values[i] = polygons.vertex_arrays_to_polygon_object(
                exterior_x_coords=these_new_longitudes_deg,
                exterior_y_coords=these_new_latitudes_deg)

    return _polygons_from_latlng_to_xy(
        storm_object_table=extrap_storm_object_table,
        projection_object=projection_object)


def _find_min_value_greater_or_equal(sorted_input_array, test_value):
    """Finds minimum value in array that is >= test value.

    :param sorted_input_array: Input array.  Must be sorted in ascending order.
    :param test_value: Test value (scalar).
    :return: min_value_geq_test: Minimum of value input_array that is >=
        test_value.
    :return: min_index_geq_test: Array index of min_value_geq_test in
        input_array.  If min_index_geq_test = i, this means that
        min_value_geq_test = sorted_input_array[i].
    """

    # TODO(thunderhoser): Put this method somewhere else.  It applies to many
    # more things than gridded forecasting.

    min_index_geq_test = numpy.searchsorted(
        sorted_input_array, numpy.array([test_value]), side='left'
    )[0]

    return sorted_input_array[min_index_geq_test], min_index_geq_test


def _find_max_value_less_than_or_equal(sorted_input_array, test_value):
    """Finds maximum value in array that is <= test value.

    :param sorted_input_array: Input array.  Must be sorted in ascending order.
    :param test_value: Test value (scalar).
    :return: max_value_leq_test: Max value of input_array that is <= test_value.
    :return: max_index_leq_test: Array index of max_value_leq_test in
        input_array.  If max_index_leq_test = i, this means that
        max_value_leq_test = sorted_input_array[i].
    """

    # TODO(thunderhoser): Put this method somewhere else.  It applies to many
    # more things than gridded forecasting.

    max_index_leq_test = -1 + numpy.searchsorted(
        sorted_input_array, numpy.array([test_value]), side='right'
    )[0]

    return sorted_input_array[max_index_leq_test], max_index_leq_test


def _find_grid_points_in_polygon(
        polygon_object_xy, grid_points_x_metres, grid_points_y_metres):
    """Finds grid points in polygon.

    M = number of rows (unique grid-point y-coordinates)
    N = number of columns (unique grid-point x-coordinates)
    P = number of grid points in polygon

    :param polygon_object_xy: Instance of `shapely.geometry.Polygon` with
        vertices in x-y coordinates (metres).
    :param grid_points_x_metres: length-N numpy array with x-coordinates of grid
        points.  Must be sorted in ascending order.
    :param grid_points_y_metres: length-M numpy array with y-coordinates of grid
        points.  Must be sorted in ascending order.
    :return: rows_in_polygon: length-P integer numpy array of rows in polygon.
    :return: columns_in_polygon: length-P integer numpy array of columns in
        polygon.
    """

    min_x_in_polygon_metres = numpy.min(numpy.array(
        polygon_object_xy.exterior.xy[0]
    ))
    max_x_in_polygon_metres = numpy.max(numpy.array(
        polygon_object_xy.exterior.xy[0]
    ))
    min_y_in_polygon_metres = numpy.min(numpy.array(
        polygon_object_xy.exterior.xy[1]
    ))
    max_y_in_polygon_metres = numpy.max(numpy.array(
        polygon_object_xy.exterior.xy[1]
    ))

    _, min_row_to_test = _find_min_value_greater_or_equal(
        grid_points_y_metres, min_y_in_polygon_metres)
    _, max_row_to_test = _find_max_value_less_than_or_equal(
        grid_points_y_metres, max_y_in_polygon_metres)
    _, min_column_to_test = _find_min_value_greater_or_equal(
        grid_points_x_metres, min_x_in_polygon_metres)
    _, max_column_to_test = _find_max_value_less_than_or_equal(
        grid_points_x_metres, max_x_in_polygon_metres)

    rows_in_polygon = []
    columns_in_polygon = []

    for this_row in range(min_row_to_test, max_row_to_test + 1):
        for this_column in range(min_column_to_test, max_column_to_test + 1):
            this_flag = polygons.point_in_or_on_polygon(
                polygon_object=polygon_object_xy,
                query_x_coordinate=grid_points_x_metres[this_column],
                query_y_coordinate=grid_points_y_metres[this_row]
            )

            if not this_flag:
                continue

            rows_in_polygon.append(this_row)
            columns_in_polygon.append(this_column)

    rows_in_polygon = numpy.array(rows_in_polygon, dtype=int)
    columns_in_polygon = numpy.array(columns_in_polygon, dtype=int)
    return rows_in_polygon, columns_in_polygon


def _polygons_to_grid_points(
        storm_object_table, grid_points_x_metres, grid_points_y_metres):
    """Finds grid points in each polygon.

    M = number of rows (unique grid-point y-coordinates)
    N = number of columns (unique grid-point x-coordinates)
    P = number of grid points in a given polygon

    :param storm_object_table: pandas DataFrame.  Each row contains the polygons
        for distance buffers around one storm object.  For the [j]th distance
        buffer, required column is given by the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")

    :param grid_points_x_metres: length-N numpy array with x-coordinates of grid
        points.  Must be sorted in ascending order.
    :param grid_points_y_metres: length-M numpy array with y-coordinates of grid
        points.  Must be sorted in ascending order.
    :return: storm_object_table: Same as input but with additional columns.  For
        the [j]th distance buffer, new columns are given by the following
        command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="grid_rows_in_polygon")
        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j],
            column_type="grid_columns_in_polygon")
    """

    xy_buffer_column_names = _get_distance_buffer_columns(
        storm_object_table=storm_object_table,
        column_type=XY_POLYGON_COLUMN_TYPE)

    num_buffers = len(xy_buffer_column_names)

    min_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    max_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    grid_rows_in_buffer_column_names = [''] * num_buffers
    grid_columns_in_buffer_column_names = [''] * num_buffers

    for j in range(num_buffers):
        min_buffer_distances_metres[j], max_buffer_distances_metres[j] = (
            _column_name_to_buffer(xy_buffer_column_names[j])
        )

        grid_rows_in_buffer_column_names[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=GRID_ROWS_IN_POLYGON_COLUMN_TYPE)

        grid_columns_in_buffer_column_names[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE)

    nested_array = storm_object_table[[
        xy_buffer_column_names[0], xy_buffer_column_names[0]
    ]].values.tolist()

    for j in range(num_buffers):
        storm_object_table = storm_object_table.assign(**{
            grid_rows_in_buffer_column_names[j]: nested_array
        })

        storm_object_table = storm_object_table.assign(**{
            grid_columns_in_buffer_column_names[j]: nested_array
        })

    num_storm_objects = len(storm_object_table.index)

    for i in range(num_storm_objects):
        for j in range(num_buffers):
            these_grid_rows, these_grid_columns = _find_grid_points_in_polygon(
                polygon_object_xy=storm_object_table[
                    xy_buffer_column_names[j]].values[i],
                grid_points_x_metres=grid_points_x_metres,
                grid_points_y_metres=grid_points_y_metres)

            storm_object_table[
                grid_rows_in_buffer_column_names[j]
            ].values[i] = these_grid_rows

            storm_object_table[
                grid_columns_in_buffer_column_names[j]
            ].values[i] = these_grid_columns

    return storm_object_table


def _extrap_polygons_to_grid_points(
        orig_storm_object_table, extrap_storm_object_table,
        grid_spacing_x_metres, grid_spacing_y_metres):
    """Finds grid points in each extrapolated polygon.

    M = number of rows (unique grid-point y-coordinates)
    N = number of columns (unique grid-point x-coordinates)
    P = number of grid points in a given polygon

    K = number of storm objects
    t_0 = initial time (valid time of all storm objects)
    t_L = lead time

    :param orig_storm_object_table: K-row pandas DataFrame.  Each row contains
        data for distance buffers around one storm object at t_0.  For the [j]th
        distance buffer, required columns are given by the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")
        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="grid_rows_in_polygon")
        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j],
            column_type="grid_columns_in_polygon")

    :param extrap_storm_object_table: K-row pandas DataFrame.  Each row contains
        polygons for distance buffers around one storm object, extrapolated to
        (t_0 + t_L).  For the [j]th distance buffer, required column is given by
        the following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="xy")

    :param grid_spacing_x_metres: Spacing between adjacent grid points in
        x-direction (i.e., between adjacent columns).
    :param grid_spacing_y_metres: Spacing between adjacent grid points in
        y-direction (i.e., between adjacent rows).
    :return: extrap_storm_object_table: Same as input but with additional
        columns.  For the [j]th distance buffer, new columns are given by the
        following command:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="grid_rows_in_polygon")
        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j],
            column_type="grid_columns_in_polygon")
    """

    xy_buffer_column_names = _get_distance_buffer_columns(
        storm_object_table=orig_storm_object_table,
        column_type=XY_POLYGON_COLUMN_TYPE)

    num_buffers = len(xy_buffer_column_names)

    min_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    max_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    grid_rows_in_buffer_column_names = [''] * num_buffers
    grid_columns_in_buffer_column_names = [''] * num_buffers

    for j in range(num_buffers):
        min_buffer_distances_metres[j], max_buffer_distances_metres[j] = (
            _column_name_to_buffer(xy_buffer_column_names[j]))

        grid_rows_in_buffer_column_names[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=GRID_ROWS_IN_POLYGON_COLUMN_TYPE)

        grid_columns_in_buffer_column_names[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE)

    nested_array = extrap_storm_object_table[[
        xy_buffer_column_names[0], xy_buffer_column_names[0]
    ]].values.tolist()

    for j in range(num_buffers):
        extrap_storm_object_table = extrap_storm_object_table.assign(**{
            grid_rows_in_buffer_column_names[j]: nested_array
        })

        extrap_storm_object_table = extrap_storm_object_table.assign(**{
            grid_columns_in_buffer_column_names[j]: nested_array
        })

    num_storm_objects = len(orig_storm_object_table.index)

    for i in range(num_storm_objects):
        for j in range(num_buffers):
            this_orig_polygon_object = orig_storm_object_table[
                xy_buffer_column_names[j]
            ].values[i]

            this_extrap_polygon_object = extrap_storm_object_table[
                xy_buffer_column_names[j]
            ].values[i]

            this_x_diff_metres = (
                numpy.array(this_extrap_polygon_object.exterior.xy[0])[0] -
                numpy.array(this_orig_polygon_object.exterior.xy[0])[0]
            )

            this_y_diff_metres = (
                numpy.array(this_extrap_polygon_object.exterior.xy[1])[0] -
                numpy.array(this_orig_polygon_object.exterior.xy[1])[0]
            )

            this_row_diff = int(numpy.round(
                this_y_diff_metres / grid_spacing_y_metres
            ))
            this_column_diff = int(numpy.round(
                this_x_diff_metres / grid_spacing_x_metres
            ))

            this_name = grid_rows_in_buffer_column_names[j]
            extrap_storm_object_table[this_name].values[i] = (
                orig_storm_object_table[this_name].values[i] + this_row_diff
            )

            this_name = grid_columns_in_buffer_column_names[j]
            extrap_storm_object_table[this_name].values[i] = (
                orig_storm_object_table[this_name].values[i] + this_column_diff
            )

    return extrap_storm_object_table


def create_forecast_grids(
        storm_object_table, min_lead_time_sec, max_lead_time_sec,
        lead_time_resolution_sec=DEFAULT_LEAD_TIME_RES_SECONDS,
        grid_spacing_x_metres=DEFAULT_GRID_SPACING_METRES,
        grid_spacing_y_metres=DEFAULT_GRID_SPACING_METRES,
        interp_to_latlng_grid=True,
        latitude_spacing_deg=DEFAULT_GRID_SPACING_DEG,
        longitude_spacing_deg=DEFAULT_GRID_SPACING_DEG,
        prob_radius_for_grid_metres=DEFAULT_PROB_RADIUS_FOR_GRID_METRES,
        smoothing_method=None,
        smoothing_e_folding_radius_metres=
        DEFAULT_SMOOTHING_E_FOLDING_RADIUS_METRES,
        smoothing_cutoff_radius_metres=DEFAULT_SMOOTHING_CUTOFF_RADIUS_METRES):
    """For each time with at least one storm object, creates grid of fcst probs.

    T = number of times with at least one storm object
      = number of forecast-initialization times

    M = number of rows in given forecast grid (different for each init time)
    N = number of columns in given forecast grid (different for each init time)

    :param storm_object_table: pandas DataFrame with columns listed below.  Each
        row corresponds to one storm object.  For the [j]th distance buffer,
        required columns are given by the following commands:

        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="latlng")
        _buffer_to_column_name(min_buffer_distances_metres[j],
            max_buffer_distances_metres[j], column_type="forecast")

    Other required columns are listed below.

    storm_object_table.full_id_string: Full storm ID.
    storm_object_table.valid_time_unix_sec: Valid time.
    storm_object_table.centroid_latitude_deg: Latitude (deg N) of storm
        centroid.
    storm_object_table.centroid_longitude_deg: Longitude (deg E) of storm
        centroid.
    storm_object_table.east_velocity_m_s01: Eastward velocity of storm cell
        (metres per second).
    storm_object_table.north_velocity_m_s01: Northward velocity of storm cell
        (metres per second).

    :param min_lead_time_sec: Minimum lead time.  For each time with at least
        one storm object, gridded probabilities will be event probabilities for
        `min_lead_time_sec`...`max_lead_time_sec` into the future.
    :param max_lead_time_sec: See documentation for `min_lead_time_sec`.
    :param lead_time_resolution_sec: Spacing between successive lead times.  For
        all lead times in {min_lead_time_sec,
        min_lead_time_sec + lead_time_resolution_sec,
        min_lead_time_sec + 2 * lead_time_resolution_sec, ...,
        max_lead_time_sec}, storm objects will be extrapolated along their
        respective motion vectors.  Lower values of `lead_time_resolution_sec`
        lead to smoother forecast grids.
    :param grid_spacing_x_metres: Spacing between adjacent grid points in
        x-direction (i.e., between adjacent columns).
    :param grid_spacing_y_metres: Spacing between adjacent grid points in
        y-direction (i.e., between adjacent rows).
    :param interp_to_latlng_grid: Boolean flag.  If True, the probability field
        for each initial time will be saved as both an x-y grid and a lat-long
        grid.
    :param latitude_spacing_deg: Spacing between meridionally adjacent grid
        points (i.e., between adjacent rows).
    :param longitude_spacing_deg: Spacing between zonally adjacent grid points
        (i.e., between adjacent columns).
    :param prob_radius_for_grid_metres: Effective radius for gridded
        probabilities.  For example, if the gridded value is "probability within
        10 km of a point," this should be 10 000.
    :param smoothing_method: Smoothing method.  For each initial time, smoother
        will be applied to the final forecast probability field.  Valid options
        are "gaussian", "cressman", and None.
    :param smoothing_e_folding_radius_metres: e-folding radius for Gaussian
        smoother.  See documentation for `grid_smoothing_2d.apply_gaussian`.
    :param smoothing_cutoff_radius_metres: Cutoff radius for Gaussian or
        Cressman smoother.  See documentation for
        `grid_smoothing_2d.apply_gaussian` or
        `grid_smoothing_2d.apply_cressman`.
    :return: gridded_forecast_dict: See doc for
        `prediction_io.write_gridded_predictions`.
    """

    # TODO(thunderhoser): Min and max lead time should be determined by params
    # for target variable.

    # TODO(thunderhoser): Effective radius should allow non-zero probs outside
    # of polygon buffer.  Or maybe allowing for uncertainty in the future track
    # would handle this.

    error_checking.assert_is_integer(min_lead_time_sec)
    error_checking.assert_is_geq(min_lead_time_sec, 0)
    error_checking.assert_is_integer(max_lead_time_sec)
    error_checking.assert_is_greater(max_lead_time_sec, min_lead_time_sec)
    error_checking.assert_is_integer(lead_time_resolution_sec)
    error_checking.assert_is_greater(lead_time_resolution_sec, 0)
    error_checking.assert_is_boolean(interp_to_latlng_grid)
    error_checking.assert_is_greater(prob_radius_for_grid_metres, 0.)

    if smoothing_method is not None:
        _check_smoothing_method(smoothing_method)

    num_lead_times = 1 + int(numpy.round(
        float(max_lead_time_sec - min_lead_time_sec) /
        lead_time_resolution_sec
    ))

    lead_times_seconds = numpy.linspace(
        min_lead_time_sec, max_lead_time_sec, num=num_lead_times, dtype=int)

    latlng_buffer_columns = _get_distance_buffer_columns(
        storm_object_table=storm_object_table,
        column_type=LATLNG_POLYGON_COLUMN_TYPE)

    num_buffers = len(latlng_buffer_columns)
    min_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)
    max_buffer_distances_metres = numpy.full(num_buffers, numpy.nan)

    xy_buffer_columns = [''] * num_buffers
    buffer_forecast_columns = [''] * num_buffers
    buffer_row_list_columns = [''] * num_buffers
    buffer_column_list_columns = [''] * num_buffers

    for j in range(num_buffers):
        min_buffer_distances_metres[j], max_buffer_distances_metres[j] = (
            _column_name_to_buffer(latlng_buffer_columns[j])
        )

        xy_buffer_columns[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=XY_POLYGON_COLUMN_TYPE)

        buffer_forecast_columns[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=FORECAST_COLUMN_TYPE)

        buffer_row_list_columns[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=GRID_ROWS_IN_POLYGON_COLUMN_TYPE)

        buffer_column_list_columns[j] = _buffer_to_column_name(
            min_buffer_dist_metres=min_buffer_distances_metres[j],
            max_buffer_dist_metres=max_buffer_distances_metres[j],
            column_type=GRID_COLUMNS_IN_POLYGON_COLUMN_TYPE)

    _check_distance_buffers(
        min_distances_metres=min_buffer_distances_metres,
        max_distances_metres=max_buffer_distances_metres)

    storm_object_table = _storm_motion_from_uv_to_speed_direction(
        storm_object_table)

    init_times_unix_sec = numpy.unique(
        storm_object_table[tracking_utils.TIME_COLUMN].values
    )
    init_time_strings = [
        time_conversion.unix_sec_to_string(t, LOG_MESSAGE_TIME_FORMAT)
        for t in init_times_unix_sec
    ]

    grid_point_x_coords_metres, grid_point_y_coords_metres = (
        _create_default_xy_grid(
            x_spacing_metres=grid_spacing_x_metres,
            y_spacing_metres=grid_spacing_y_metres)
    )

    num_xy_rows = len(grid_point_y_coords_metres)
    num_xy_columns = len(grid_point_x_coords_metres)
    num_init_times = len(init_time_strings)

    gridded_forecast_dict = {
        prediction_io.INIT_TIMES_KEY: init_times_unix_sec,
        prediction_io.MIN_LEAD_TIME_KEY: min_lead_time_sec,
        prediction_io.MAX_LEAD_TIME_KEY: max_lead_time_sec,
        prediction_io.GRID_X_COORDS_KEY: grid_point_x_coords_metres,
        prediction_io.GRID_Y_COORDS_KEY: grid_point_y_coords_metres,
        prediction_io.XY_PROBABILITIES_KEY: [None] * num_init_times,
        prediction_io.PROJECTION_KEY: DEFAULT_PROJECTION_OBJECT
    }

    if interp_to_latlng_grid:
        gridded_forecast_dict.update({
            prediction_io.LATLNG_PROBABILITIES_KEY: [None] * num_init_times
        })

    for i in range(num_init_times):
        this_storm_object_table = storm_object_table.loc[
            storm_object_table[tracking_utils.TIME_COLUMN] ==
            init_times_unix_sec[i]
        ]

        this_num_storm_objects = len(this_storm_object_table.index)

        this_storm_object_table = _polygons_from_latlng_to_xy(
            storm_object_table=this_storm_object_table)

        this_storm_object_table = _normalize_probs_by_polygon_area(
            storm_object_table=this_storm_object_table,
            prob_radius_for_grid_metres=prob_radius_for_grid_metres)

        this_storm_object_table = _polygons_to_grid_points(
            storm_object_table=this_storm_object_table,
            grid_points_x_metres=grid_point_x_coords_metres,
            grid_points_y_metres=grid_point_y_coords_metres)

        this_probability_matrix_xy = numpy.full(
            (num_xy_rows, num_xy_columns), 0.
        )
        this_num_forecast_matrix = numpy.full(
            (num_xy_rows, num_xy_columns), 0, dtype=int
        )

        for this_lead_time_sec in lead_times_seconds:
            print((
                'Updating forecast grid for initial time {0:s}, lead time {1:d}'
                ' seconds...'
            ).format(init_time_strings[i], this_lead_time_sec))

            this_extrap_storm_object_table = _extrapolate_polygons(
                storm_object_table=this_storm_object_table,
                lead_time_seconds=this_lead_time_sec)

            this_extrap_storm_object_table = _extrap_polygons_to_grid_points(
                orig_storm_object_table=this_storm_object_table,
                extrap_storm_object_table=this_extrap_storm_object_table,
                grid_spacing_x_metres=grid_spacing_x_metres,
                grid_spacing_y_metres=grid_spacing_y_metres)

            for j in range(num_buffers):
                for k in range(this_num_storm_objects):
                    these_rows = this_extrap_storm_object_table[
                        buffer_row_list_columns[j]
                    ].values[k]

                    if len(these_rows) == 0:  # Outside of grid.
                        continue

                    these_columns = this_extrap_storm_object_table[
                        buffer_column_list_columns[j]
                    ].values[k]

                    this_num_forecast_matrix[these_rows, these_columns] += 1

                    this_probability_matrix_xy[these_rows, these_columns] = (
                        this_probability_matrix_xy[these_rows, these_columns] +
                        this_storm_object_table[
                            buffer_forecast_columns[j]
                        ].values[k]
                    )

        this_probability_matrix_xy = (
            this_probability_matrix_xy / this_num_forecast_matrix
        )

        if smoothing_method is not None:
            print('Smoothing forecast grid for initial time {0:s}...'.format(
                init_time_strings[i]
            ))

            if smoothing_method == GAUSSIAN_SMOOTHING_METHOD:
                this_probability_matrix_xy = grid_smoothing_2d.apply_gaussian(
                    input_matrix=this_probability_matrix_xy,
                    grid_spacing_x=grid_spacing_x_metres,
                    grid_spacing_y=grid_spacing_y_metres,
                    e_folding_radius=smoothing_e_folding_radius_metres,
                    cutoff_radius=smoothing_cutoff_radius_metres)

            elif smoothing_method == CRESSMAN_SMOOTHING_METHOD:
                this_probability_matrix_xy = grid_smoothing_2d.apply_cressman(
                    input_matrix=this_probability_matrix_xy,
                    grid_spacing_x=grid_spacing_x_metres,
                    grid_spacing_y=grid_spacing_y_metres,
                    cutoff_radius=smoothing_cutoff_radius_metres)

        # gridded_forecast_dict[prediction_io.XY_PROBABILITIES_KEY][i] = (
        #     scipy.sparse.csr_matrix(this_probability_matrix_xy)
        # )

        gridded_forecast_dict[prediction_io.XY_PROBABILITIES_KEY][i] = (
            this_probability_matrix_xy
        )

        if not interp_to_latlng_grid:
            if i != num_init_times - 1:
                print(MINOR_SEPARATOR_STRING)

            continue

        print((
            'Interpolating forecast to lat-long grid for initial time '
            '{0:s}...'
        ).format(
            init_time_strings[i]
        ))

        if i != num_init_times - 1:
            print(MINOR_SEPARATOR_STRING)

        (this_prob_matrix_latlng, these_latitudes_deg, these_longitudes_deg
        ) = _interp_probabilities_to_latlng_grid(
            probability_matrix_xy=this_probability_matrix_xy,
            grid_points_x_metres=grid_point_x_coords_metres,
            grid_points_y_metres=grid_point_y_coords_metres,
            latitude_spacing_deg=latitude_spacing_deg,
            longitude_spacing_deg=longitude_spacing_deg)

        # gridded_forecast_dict[prediction_io.LATLNG_PROBABILITIES_KEY][i] = (
        #     scipy.sparse.csr_matrix(this_prob_matrix_latlng)
        # )

        gridded_forecast_dict[prediction_io.LATLNG_PROBABILITIES_KEY][i] = (
            this_prob_matrix_latlng
        )

        if i != 0:
            continue

        gridded_forecast_dict.update({
            prediction_io.GRID_LATITUDES_KEY: these_latitudes_deg,
            prediction_io.GRID_LONGITUDES_KEY: these_longitudes_deg
        })

    return gridded_forecast_dict
