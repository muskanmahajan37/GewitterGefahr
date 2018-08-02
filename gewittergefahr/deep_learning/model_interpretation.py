"""Helper methods for model interpretation."""

import numpy
from gewittergefahr.gg_utils import error_checking

CLASS_COMPONENT_TYPE_STRING = 'class'
NEURON_COMPONENT_TYPE_STRING = 'neuron'
CHANNEL_COMPONENT_TYPE_STRING = 'channel'
VALID_COMPONENT_TYPE_STRINGS = [
    CLASS_COMPONENT_TYPE_STRING, NEURON_COMPONENT_TYPE_STRING,
    CHANNEL_COMPONENT_TYPE_STRING
]


def check_component_type(component_type_string):
    """Ensures that model-component type is valid.

    :param component_type_string: Component type.
    :raises: ValueError: if
        `component_type_string not in VALID_COMPONENT_TYPE_STRINGS`.
    """

    error_checking.assert_is_string(component_type_string)
    if component_type_string not in VALID_COMPONENT_TYPE_STRINGS:
        error_string = (
            '\n\n{0:s}\nValid component types (listed above) do not include '
            '"{1:s}".'
        ).format(str(VALID_COMPONENT_TYPE_STRINGS), component_type_string)
        raise ValueError(error_string)


def check_component_metadata(
        component_type_string, target_class=None, layer_name=None,
        neuron_indices=None, channel_index=None):
    """Checks metadata for model component.

    :param component_type_string: Component type (must be accepted by
        `check_component_type`).
    :param target_class: [used only if component_type_string = "class"]
        Target class.  Integer from 0...(K - 1), where K = number of classes.
    :param layer_name:
        [used only if component_type_string = "neuron" or "channel"]
        Name of layer containing neuron or channel.
    :param neuron_indices: [used only if component_type_string = "neuron"]
        1-D numpy array with indices of neuron.
    :param channel_index: [used only if component_type_string = "channel"]
        Index of channel.
    """

    check_component_type(component_type_string)
    if component_type_string == CLASS_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer(target_class)
        error_checking.assert_is_geq(target_class, 0)

    if component_type_string in [NEURON_COMPONENT_TYPE_STRING,
                                 CHANNEL_COMPONENT_TYPE_STRING]:
        error_checking.assert_is_string(layer_name)

    if component_type_string == NEURON_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer_numpy_array(neuron_indices)
        error_checking.assert_is_geq_numpy_array(neuron_indices, 0)
        error_checking.assert_is_numpy_array(neuron_indices, num_dimensions=1)

    if component_type_string == CHANNEL_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer(channel_index)
        error_checking.assert_is_geq(channel_index, 0)


def model_component_to_string(
        component_type_string, target_class=None, layer_name=None,
        neuron_indices=None, channel_index=None):
    """Returns string descriptions for model component (class/neuron/channel).

    Specifically, this method creates two strings:

    - verbose string (to use in figure legends)
    - abbreviation (to use in file names)

    :param component_type_string: See doc for `check_component_metadata`.
    :param target_class: Same.
    :param layer_name: Same.
    :param neuron_indices: Same.
    :param channel_index: Same.
    :return: verbose_string: See general discussion above.
    :return: abbrev_string: See general discussion above.
    """

    check_component_metadata(
        component_type_string=component_type_string, target_class=target_class,
        layer_name=layer_name, neuron_indices=neuron_indices,
        channel_index=channel_index)

    if component_type_string == CLASS_COMPONENT_TYPE_STRING:
        verbose_string = 'Class {0:d}'.format(target_class)
        abbrev_string = 'class{0:d}'.format(target_class)
    else:
        verbose_string = 'Layer "{0:s}"'.format(layer_name)
        abbrev_string = 'layer={0:s}'.format(layer_name.replace('_', '-'))

    if component_type_string == CHANNEL_COMPONENT_TYPE_STRING:
        verbose_string += ', channel {0:d}'.format(channel_index)
        abbrev_string += '_channel{0:d}'.format(channel_index)

    if component_type_string == NEURON_COMPONENT_TYPE_STRING:
        this_neuron_string = ', '.join(
            ['{0:d}'.format(i) for i in neuron_indices])
        verbose_string += '; neuron ({0:s})'.format(this_neuron_string)

        this_neuron_string = ','.join(
            ['{0:d}'.format(i) for i in neuron_indices])
        abbrev_string += '_neuron{0:s}'.format(this_neuron_string)

    return verbose_string, abbrev_string


def sort_neurons_by_weight(model_object, layer_name):
    """Sorts neurons of the given layer in descending order by weight.

    K = number of dimensions in `weight_matrix`
    W = number of values in `weight_matrix`

    :param model_object: Instance of `keras.models.Model`.
    :param layer_name: Name of layer whose neurons are to be sorted.
    :return: weight_matrix: numpy array of weights, with the same dimensions as
        `model_object.get_layer(name=layer_name).get_weights()[0]`.

    If the layer is convolutional, dimensions of `weight_matrix` are as follows:

    - Last dimension = output channel
    - Second-last dimension = input channel
    - First dimensions = spatial dimensions

    For example, if the conv layer has a 3-by-5 kernel with 16 input channels
    and 32 output channels, `weight_matrix` will be 3 x 5 x 16 x 32.

    If the layer is dense (fully connected), `weight_matrix` is 1-D.

    :return: sort_indices_as_tuple: length-K tuple.  sort_indices_as_tuple[k] is
        a length-W numpy array, containing indices for the [k]th dimension of
        `weight_matrix`.  When these indices are applied to all dimensions of
        `weight_matrix` -- i.e., when sort_indices_as_tuple[k] is applied for
        k = 0...(K - 1) -- `weight_matrix` has been sorted in descending order.
    :raises: TypeError: if the given layer is neither dense nor convolutional.
    """

    layer_type_string = type(model_object.get_layer(name=layer_name)).__name__
    valid_layer_type_strings = ['Dense', 'Conv1D', 'Conv2D', 'Conv3D']
    if layer_type_string not in valid_layer_type_strings:
        error_string = (
            '\n\n{0:s}\nLayer "{1:s}" has type "{2:s}", which is not in the '
            'above list.'
        ).format(str(valid_layer_type_strings), layer_name, layer_type_string)
        raise TypeError(error_string)

    weight_matrix = model_object.get_layer(name=layer_name).get_weights()[0]
    sort_indices_linear = numpy.argsort(
        -numpy.reshape(weight_matrix, weight_matrix.size))
    sort_indices_as_tuple = numpy.unravel_index(
        sort_indices_linear, weight_matrix.shape)

    return weight_matrix, sort_indices_as_tuple
