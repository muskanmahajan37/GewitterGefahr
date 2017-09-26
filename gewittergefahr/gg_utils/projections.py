"""Methods for handling map projections.

Specifically, this file contains methods for initializing a projection,
converting from lat-long to projection (x-y) coordinates, and converting from
x-y back to lat-long.
"""

import numpy
from pyproj import Proj
from gewittergefahr.gg_utils import error_checking
from gewittergefahr.gg_utils import longitude_conversion as lng_conversion

EARTH_RADIUS_METRES = 6370997.


def init_lambert_conformal_projection(standard_latitudes_deg,
                                      central_longitude_deg):
    """Initializes Lambert conformal projection.

    :param standard_latitudes_deg: length-2 numpy array with standard parallels
        (deg N).  standard_latitudes_deg[0] is the first standard parallel;
        standard_latitudes_deg[1] is the second standard parallel.
    :param central_longitude_deg: central meridian (deg E).
    :return: projection_object: object created by `pyproj.Proj`, specifying the
        Lambert conformal projection.
    """

    error_checking.assert_is_numpy_array(standard_latitudes_deg,
                                         exact_dimensions=numpy.array([2]))
    for this_latitude_deg in standard_latitudes_deg:
        error_checking.assert_is_valid_latitude(this_latitude_deg)

    central_longitude_deg = lng_conversion.convert_lng_positive_in_west(
        central_longitude_deg)

    return Proj(proj='lcc', lat_1=standard_latitudes_deg[0],
                lat_2=standard_latitudes_deg[1], lon_0=central_longitude_deg,
                rsphere=EARTH_RADIUS_METRES, ellps='sphere')


def init_azimuthal_equidistant_projection(central_latitude_deg,
                                          central_longitude_deg):
    """Initializes azimuthal equidistant projection.

    :param central_latitude_deg: Central latitude (deg N).
    :param central_longitude_deg: Central longitude (deg E).
    :return: projection_object: object created by `pyproj.Proj`, specifying the
        Lambert conformal projection.
    """

    error_checking.assert_is_valid_latitude(central_latitude_deg)
    central_longitude_deg = lng_conversion.convert_lng_positive_in_west(
        central_longitude_deg)

    return Proj(proj='aeqd', lat_0=central_latitude_deg,
                lon_0=central_longitude_deg)


def project_latlng_to_xy(latitudes_deg, longitudes_deg, projection_object=None,
                         false_easting_metres=0., false_northing_metres=0.):
    """Converts from lat-long to projection (x-y) coordinates.

    S = shape of coordinate arrays.

    :param latitudes_deg: numpy array of latitudes (deg N) with shape S.
    :param longitudes_deg: numpy array of longitudes (deg E) with shape S.
    :param projection_object: Projection object created by `pyproj.Proj`.
    :param false_easting_metres: False easting.  Will be added to all x-
        coordinates.
    :param false_northing_metres: False northing.  Will be added to all y-
        coordinates.
    :return: x_coords_metres: numpy array of x-coordinates with shape S.
    :return: y_coords_metres: numpy array of y-coordinates with shape S.
    """

    error_checking.assert_is_numpy_array(latitudes_deg)
    for _, this_latitude_deg in numpy.ndenumerate(latitudes_deg):
        if numpy.isnan(this_latitude_deg):
            continue
        error_checking.assert_is_valid_latitude(this_latitude_deg)

    shape_of_coord_arrays = latitudes_deg.shape
    error_checking.assert_is_numpy_array(
        longitudes_deg, exact_dimensions=numpy.asarray(shape_of_coord_arrays))
    longitudes_deg = lng_conversion.convert_lng_positive_in_west(longitudes_deg)

    error_checking.assert_is_not_nan(false_easting_metres)
    error_checking.assert_is_not_nan(false_northing_metres)

    nan_flags = numpy.logical_or(numpy.isnan(latitudes_deg),
                                 numpy.isnan(longitudes_deg))
    nan_indices = numpy.where(nan_flags)[0]

    x_coords_metres, y_coords_metres = projection_object(longitudes_deg,
                                                         latitudes_deg)
    x_coords_metres[nan_indices] = numpy.nan
    y_coords_metres[nan_indices] = numpy.nan

    return (x_coords_metres + false_easting_metres,
            y_coords_metres + false_northing_metres)


def project_xy_to_latlng(x_coords_metres, y_coords_metres,
                         projection_object=None, false_easting_metres=0.,
                         false_northing_metres=0.):
    """Converts from projection (x-y) to lat-long coordinates.

    P = number of points

    :param x_coords_metres: length-P numpy array of x-coordinates.
    :param y_coords_metres: length-P numpy array of y-coordinates.
    :param projection_object: Projection object created by `pyproj.Proj`.
    :param false_easting_metres: False easting.  Will be subtracted from all x-
        coordinates before conversion.
    :param false_northing_metres: False northing.  Will be subtracted from all
        y-coordinates before conversion.
    :return: latitudes_deg: length-P numpy array of latitudes (deg N).
    :return: longitudes_deg: length-P numpy array of longitudes (deg E).
    """

    error_checking.assert_is_numpy_array(x_coords_metres)
    error_checking.assert_is_real_number_array(x_coords_metres)

    shape_of_coord_arrays = x_coords_metres.shape
    error_checking.assert_is_numpy_array(
        y_coords_metres, exact_dimensions=numpy.asarray(shape_of_coord_arrays))
    error_checking.assert_is_real_number_array(y_coords_metres)

    error_checking.assert_is_not_nan(false_easting_metres)
    error_checking.assert_is_not_nan(false_northing_metres)

    nan_flags = numpy.logical_or(numpy.isnan(x_coords_metres),
                                 numpy.isnan(y_coords_metres))
    nan_indices = numpy.where(nan_flags)[0]

    (longitudes_deg, latitudes_deg) = projection_object(
        x_coords_metres - false_easting_metres,
        y_coords_metres - false_northing_metres, inverse=True)
    latitudes_deg[nan_indices] = numpy.nan
    longitudes_deg[nan_indices] = numpy.nan

    return latitudes_deg, lng_conversion.convert_lng_positive_in_west(
        longitudes_deg)
