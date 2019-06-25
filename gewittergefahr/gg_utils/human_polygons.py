"""Handles polygons drawn interactively by a human."""

import numpy
import matplotlib.pyplot as pyplot
import netCDF4
from PIL import Image
from roipoly import MultiRoi
from gewittergefahr.gg_utils import polygons
from gewittergefahr.gg_utils import general_utils
from gewittergefahr.gg_utils import file_system_utils
from gewittergefahr.gg_utils import error_checking

IMAGE_FILE_KEY = 'orig_image_file_name'
POSITIVE_VERTEX_ROWS_KEY = 'positive_vertex_rows'
POSITIVE_VERTEX_COLUMNS_KEY = 'positive_vertex_columns'
NEGATIVE_VERTEX_ROWS_KEY = 'negative_vertex_rows'
NEGATIVE_VERTEX_COLUMNS_KEY = 'negative_vertex_columns'
POSITIVE_MASK_MATRIX_KEY = 'positive_mask_matrix'
POSITIVE_POLYGON_OBJECTS_KEY = 'positive_polygon_objects_rowcol'
NEGATIVE_MASK_MATRIX_KEY = 'negative_mask_matrix'
NEGATIVE_POLYGON_OBJECTS_KEY = 'negative_polygon_objects_rowcol'

ROW_DIMENSION_KEY = 'grid_row'
COLUMN_DIMENSION_KEY = 'grid_column'
POSITIVE_VERTEX_DIM_KEY = 'positive_polygon_vertex'
NEGATIVE_VERTEX_DIM_KEY = 'negative_polygon_vertex'


def _polygon_list_to_vertex_list(list_of_polygon_objects_rowcol):
    """Converts list of polygons to list of vertices.

    V = total number of vertices

    :param list_of_polygon_objects_rowcol: List of polygons created by
        `polygons_from_pixel_to_grid_coords`.
    :return: vertex_rows: length-V numpy array of row coordinates.
    :return: vertex_columns: length-V numpy array of column coordinates.
    """

    # TODO(thunderhoser): Write unit test.

    error_checking.assert_is_list(list_of_polygon_objects_rowcol)
    num_polygons = len(list_of_polygon_objects_rowcol)

    if num_polygons > 0:
        error_checking.assert_is_numpy_array(
            numpy.array(list_of_polygon_objects_rowcol, dtype=object),
            num_dimensions=1
        )

    vertex_rows = []
    vertex_columns = []

    for i in range(num_polygons):
        vertex_rows += list_of_polygon_objects_rowcol[i].exterior.xy[1]
        vertex_columns += list_of_polygon_objects_rowcol[i].exterior.xy[0]

        if i == num_polygons - 1:
            continue

        vertex_rows += [numpy.nan]
        vertex_columns += [numpy.nan]

    return numpy.array(vertex_rows), numpy.array(vertex_columns)


def _vertex_list_to_polygon_list(vertex_rows, vertex_columns):
    """This method is the inverse of `_polygon_list_to_vertex_list`.

    :param vertex_rows: See doc for `_polygon_list_to_vertex_list`.
    :param vertex_columns: Same.
    :return: list_of_polygon_objects_rowcol: Same.
    """

    # TODO(thunderhoser): Write unit test.

    if len(vertex_rows) == 0:
        return []

    vertex_rows_by_polygon = general_utils.split_array_by_nan(vertex_rows)
    vertex_columns_by_polygon = general_utils.split_array_by_nan(vertex_columns)

    num_polygons = len(vertex_rows_by_polygon)
    list_of_polygon_objects_rowcol = []

    for i in range(num_polygons):
        this_polygon_object = polygons.vertex_arrays_to_polygon_object(
            exterior_x_coords=vertex_columns_by_polygon[i],
            exterior_y_coords=vertex_rows_by_polygon[i]
        )

        list_of_polygon_objects_rowcol.append(this_polygon_object)

    return list_of_polygon_objects_rowcol


def capture_polygons(image_file_name, instruction_string=''):
    """This interactiv method allows you to draw polygons and captures vertices.

    N = number of polygons drawn

    :param image_file_name: Path to image file.  This method will display the
        image in a figure window and allow you to draw polygons on top.
    :param instruction_string: String with instructions for the user.
    :return: list_of_polygon_objects_xy: length-N list of polygons (instances of
        `shapely.geometry.Polygon`), each containing vertices in pixel
        coordinates.
    :return: num_pixel_rows: Number of pixel rows in the image.
    :return: num_pixel_columns: Number of pixel columns in the image.
    """

    error_checking.assert_file_exists(image_file_name)

    image_matrix = Image.open(image_file_name)
    num_pixel_columns, num_pixel_rows = image_matrix.size

    pyplot.imshow(image_matrix)
    pyplot.title(instruction_string)
    pyplot.show(block=False)

    multi_roi_object = MultiRoi()

    string_keys = list(multi_roi_object.rois.keys())
    integer_keys = numpy.array([int(k) for k in string_keys], dtype=int)

    sort_indices = numpy.argsort(integer_keys)
    integer_keys = integer_keys[sort_indices]
    string_keys = [string_keys[k] for k in sort_indices]

    num_polygons = len(integer_keys)
    list_of_polygon_objects_xy = []

    for i in range(num_polygons):
        this_roi_object = multi_roi_object.rois[string_keys[i]]

        these_x_coords = numpy.array(
            [this_roi_object.x[0]] + list(reversed(this_roi_object.x))
        )
        these_y_coords = numpy.array(
            [this_roi_object.y[0]] + list(reversed(this_roi_object.y))
        )

        this_polygon_object = polygons.vertex_arrays_to_polygon_object(
            exterior_x_coords=these_x_coords, exterior_y_coords=these_y_coords)

        list_of_polygon_objects_xy.append(this_polygon_object)

    return list_of_polygon_objects_xy, num_pixel_rows, num_pixel_columns


def polygons_from_pixel_to_grid_coords(
        list_of_polygon_objects_xy, num_grid_rows, num_grid_columns,
        num_pixel_rows, num_pixel_columns):
    """Converts polygons from pixel coordinates to grid coordinates.

    The input args `num_grid_rows` and `num_grid_columns` are the number of rows
    and columns in the data grid.  These are *not* the same as the number of
    pixel rows and columns in the image.  This method assumes that the image
    contains only the data grid, with absolutely no border around the data grid.
    This method also assumes that the data grid is not warped in pixel space.
    In other words, the transformation from pixel row to grid row, and pixel
    column to grid column, must be linear; and both these transformations must
    be constant throughout the image.

    N = number of polygons

    :param list_of_polygon_objects_xy: length-N list of polygons (instances of
        `shapely.geometry.Polygon`) with vertices in pixel coordinates, where
        the top-left corner is x = y = 0.
    :param num_grid_rows: Number of rows in grid.
    :param num_grid_columns: Number of columns in grid.
    :param num_pixel_rows: Number of pixel rows in image.
    :param num_pixel_columns: Number of pixel columns in image.
    :return: list_of_polygon_objects_rowcol: length-N list of polygons
        (instances of `shapely.geometry.Polygon`) with vertices in grid
        coordinates, where the bottom-left corner is x = y = 0.
    """

    error_checking.assert_is_integer(num_grid_rows)
    error_checking.assert_is_greater(num_grid_rows, 0)
    error_checking.assert_is_integer(num_grid_columns)
    error_checking.assert_is_greater(num_grid_columns, 0)
    error_checking.assert_is_integer(num_pixel_rows)
    error_checking.assert_is_greater(num_pixel_rows, 0)
    error_checking.assert_is_integer(num_pixel_columns)
    error_checking.assert_is_greater(num_pixel_columns, 0)
    error_checking.assert_is_list(list_of_polygon_objects_xy)

    num_polygons = len(list_of_polygon_objects_xy)
    if num_polygons == 0:
        return list_of_polygon_objects_xy

    error_checking.assert_is_numpy_array(
        numpy.array(list_of_polygon_objects_xy, dtype=object),
        num_dimensions=1
    )

    list_of_polygon_objects_rowcol = []

    for i in range(num_polygons):
        these_pixel_columns = 0.5 + numpy.array(
            list_of_polygon_objects_xy[i].exterior.xy[0]
        )

        error_checking.assert_is_geq_numpy_array(these_pixel_columns, 0.)
        error_checking.assert_is_leq_numpy_array(
            these_pixel_columns, num_pixel_columns)

        these_grid_columns = -0.5 + (
            these_pixel_columns * float(num_grid_columns) / num_pixel_columns
        )

        these_pixel_rows = num_pixel_rows - (
            0.5 + numpy.array(list_of_polygon_objects_xy[i].exterior.xy[1])
        )

        error_checking.assert_is_geq_numpy_array(these_pixel_rows, 0.)
        error_checking.assert_is_leq_numpy_array(
            these_pixel_rows, num_pixel_rows)

        these_grid_rows = -0.5 + (
            these_pixel_rows * float(num_grid_rows) / num_pixel_rows
        )

        this_polygon_object = polygons.vertex_arrays_to_polygon_object(
            exterior_x_coords=these_grid_columns,
            exterior_y_coords=these_grid_rows)

        list_of_polygon_objects_rowcol.append(this_polygon_object)

    return list_of_polygon_objects_rowcol


def polygons_to_mask(list_of_polygon_objects_rowcol, num_grid_rows,
                     num_grid_columns):
    """Converts list of polygons to gridded binary mask.

    M = number of rows in grid
    N = number of columns in grid

    :param list_of_polygon_objects_rowcol: See doc for
        `polygons_from_pixel_to_grid_coords`.
    :param num_grid_rows: Number of rows in grid.
    :param num_grid_columns: Number of columns in grid.
    :return: mask_matrix: M-by-N numpy array of Boolean flags.  If
        mask_matrix[i, j] == True, grid point [i, j] is in/on at least one of
        the input polygons.
    """

    error_checking.assert_is_integer(num_grid_rows)
    error_checking.assert_is_greater(num_grid_rows, 0)
    error_checking.assert_is_integer(num_grid_columns)
    error_checking.assert_is_greater(num_grid_columns, 0)

    mask_matrix = numpy.full(
        (num_grid_rows, num_grid_columns), False, dtype=bool
    )

    num_polygons = len(list_of_polygon_objects_rowcol)
    if num_polygons == 0:
        return mask_matrix

    # TODO(thunderhoser): This triple for-loop is probably inefficient.
    for k in range(num_polygons):
        these_grid_columns = numpy.array(
            list_of_polygon_objects_rowcol[k].exterior.xy[0]
        )

        error_checking.assert_is_geq_numpy_array(these_grid_columns, -0.5)
        error_checking.assert_is_leq_numpy_array(
            these_grid_columns, num_grid_columns - 0.5)

        these_grid_rows = numpy.array(
            list_of_polygon_objects_rowcol[k].exterior.xy[1]
        )

        error_checking.assert_is_geq_numpy_array(these_grid_rows, -0.5)
        error_checking.assert_is_leq_numpy_array(
            these_grid_rows, num_grid_rows - 0.5)

        for i in range(num_grid_rows):
            for j in range(num_grid_columns):
                if mask_matrix[i, j]:
                    continue

                mask_matrix[i, j] = polygons.point_in_or_on_polygon(
                    polygon_object=list_of_polygon_objects_rowcol[k],
                    query_x_coordinate=j, query_y_coordinate=i)

    return mask_matrix


def write_polygons(
        output_file_name, orig_image_file_name, positive_polygon_objects_rowcol,
        positive_mask_matrix, negative_polygon_objects_rowcol,
        negative_mask_matrix):
    """Writes human polygons for one image to NetCDF file.

    :param output_file_name: Path to output (NetCDF) file.
    :param orig_image_file_name: Path to original image file (over which the
        polygons were drawn).
    :param positive_polygon_objects_rowcol: List of polygons created by
        `polygons_from_pixel_to_grid_coords`, containing positive regions of
        interest.
    :param positive_mask_matrix: Mask matrix created by `polygons_to_mask`,
        corresponding to `positive_polygon_objects_rowcol`.
    :param negative_polygon_objects_rowcol: List of polygons created by
        `polygons_from_pixel_to_grid_coords`, containing negative regions of
        interest.
    :param negative_mask_matrix: Mask matrix created by `polygons_to_mask`,
        corresponding to `negative_polygon_objects_rowcol`.
    """

    error_checking.assert_is_string(orig_image_file_name)
    error_checking.assert_is_boolean_numpy_array(positive_mask_matrix)
    error_checking.assert_is_numpy_array(positive_mask_matrix, num_dimensions=2)

    error_checking.assert_is_boolean_numpy_array(negative_mask_matrix)
    error_checking.assert_is_numpy_array(
        negative_mask_matrix,
        exact_dimensions=numpy.array(positive_mask_matrix.shape, dtype=int)
    )

    positive_vertex_rows, positive_vertex_columns = (
        _polygon_list_to_vertex_list(positive_polygon_objects_rowcol)
    )

    negative_vertex_rows, negative_vertex_columns = (
        _polygon_list_to_vertex_list(negative_polygon_objects_rowcol)
    )

    file_system_utils.mkdir_recursive_if_necessary(file_name=output_file_name)
    dataset_object = netCDF4.Dataset(
        output_file_name, 'w', format='NETCDF3_64BIT_OFFSET')

    dataset_object.setncattr(IMAGE_FILE_KEY, orig_image_file_name)

    dataset_object.createDimension(
        ROW_DIMENSION_KEY, positive_mask_matrix.shape[0]
    )
    dataset_object.createDimension(
        COLUMN_DIMENSION_KEY, positive_mask_matrix.shape[1]
    )
    dataset_object.createDimension(
        POSITIVE_VERTEX_DIM_KEY, len(positive_vertex_rows)
    )
    dataset_object.createDimension(
        NEGATIVE_VERTEX_DIM_KEY, len(negative_vertex_rows)
    )

    dataset_object.createVariable(
        POSITIVE_VERTEX_ROWS_KEY, datatype=numpy.float32,
        dimensions=POSITIVE_VERTEX_DIM_KEY
    )
    dataset_object.variables[POSITIVE_VERTEX_ROWS_KEY][:] = positive_vertex_rows

    dataset_object.createVariable(
        POSITIVE_VERTEX_COLUMNS_KEY, datatype=numpy.float32,
        dimensions=POSITIVE_VERTEX_DIM_KEY
    )
    dataset_object.variables[POSITIVE_VERTEX_COLUMNS_KEY][:] = (
        positive_vertex_columns
    )

    dataset_object.createVariable(
        NEGATIVE_VERTEX_ROWS_KEY, datatype=numpy.float32,
        dimensions=NEGATIVE_VERTEX_DIM_KEY
    )
    dataset_object.variables[NEGATIVE_VERTEX_ROWS_KEY][:] = negative_vertex_rows

    dataset_object.createVariable(
        NEGATIVE_VERTEX_COLUMNS_KEY, datatype=numpy.float32,
        dimensions=NEGATIVE_VERTEX_DIM_KEY
    )
    dataset_object.variables[NEGATIVE_VERTEX_COLUMNS_KEY][:] = (
        negative_vertex_columns
    )

    dataset_object.createVariable(
        POSITIVE_MASK_MATRIX_KEY, datatype=numpy.int32,
        dimensions=(ROW_DIMENSION_KEY, COLUMN_DIMENSION_KEY)
    )
    dataset_object.variables[POSITIVE_MASK_MATRIX_KEY][:] = (
        positive_mask_matrix.astype(int)
    )

    dataset_object.createVariable(
        NEGATIVE_MASK_MATRIX_KEY, datatype=numpy.int32,
        dimensions=(ROW_DIMENSION_KEY, COLUMN_DIMENSION_KEY)
    )
    dataset_object.variables[NEGATIVE_MASK_MATRIX_KEY][:] = (
        negative_mask_matrix.astype(int)
    )

    dataset_object.close()


def read_polygons(netcdf_file_name):
    """Reads human polygons for one image from NetCDF file.

    :param netcdf_file_name: Path to input file.
    :return: polygon_dict: Dictionary with the following keys.
    polygon_dict['orig_image_file_name']: See input doc for `write_polygons`.
    polygon_dict['positive_polygon_objects_rowcol']: Same.
    polygon_dict['positive_mask_matrix']: Same.
    polygon_dict['negative_polygon_objects_rowcol']: Same.
    polygon_dict['negative_mask_matrix']: Same.
    """

    error_checking.assert_file_exists(netcdf_file_name)
    dataset_object = netCDF4.Dataset(netcdf_file_name)

    polygon_dict = {
        IMAGE_FILE_KEY: str(getattr(dataset_object, IMAGE_FILE_KEY)),
        POSITIVE_MASK_MATRIX_KEY: numpy.array(
            dataset_object.variables[POSITIVE_MASK_MATRIX_KEY][:], dtype=bool
        ),
        NEGATIVE_MASK_MATRIX_KEY: numpy.array(
            dataset_object.variables[NEGATIVE_MASK_MATRIX_KEY][:], dtype=bool
        )
    }

    positive_polygon_objects_rowcol = _vertex_list_to_polygon_list(
        vertex_rows=numpy.array(
            dataset_object.variables[POSITIVE_VERTEX_ROWS_KEY][:], dtype=float
        ),
        vertex_columns=numpy.array(
            dataset_object.variables[POSITIVE_VERTEX_COLUMNS_KEY][:],
            dtype=float
        )
    )

    negative_polygon_objects_rowcol = _vertex_list_to_polygon_list(
        vertex_rows=numpy.array(
            dataset_object.variables[NEGATIVE_VERTEX_ROWS_KEY][:], dtype=float
        ),
        vertex_columns=numpy.array(
            dataset_object.variables[NEGATIVE_VERTEX_COLUMNS_KEY][:],
            dtype=float
        )
    )

    dataset_object.close()

    polygon_dict[POSITIVE_POLYGON_OBJECTS_KEY] = positive_polygon_objects_rowcol
    polygon_dict[NEGATIVE_POLYGON_OBJECTS_KEY] = negative_polygon_objects_rowcol
    return polygon_dict