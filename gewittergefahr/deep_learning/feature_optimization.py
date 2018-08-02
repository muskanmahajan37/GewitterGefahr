"""Helper methods for feature optimization.

--- REFERENCES ---

Olah, C., A. Mordvintsev, and L. Schubert, 2017: Feature visualization. Distill,
    doi:10.23915/distill.00007,
    URL https://distill.pub/2017/feature-visualization.
"""

import pickle
import numpy
from keras import backend as K
from gewittergefahr.gg_utils import file_system_utils
from gewittergefahr.gg_utils import error_checking

DEFAULT_IDEAL_LOGIT = 7.
DEFAULT_IDEAL_ACTIVATION = 2.

DEFAULT_LEARNING_RATE = 0.01
DEFAULT_NUM_ITERATIONS = 200

CLASS_COMPONENT_TYPE_STRING = 'class'
NEURON_COMPONENT_TYPE_STRING = 'neuron'
CHANNEL_COMPONENT_TYPE_STRING = 'channel'
VALID_COMPONENT_TYPE_STRINGS = [
    CLASS_COMPONENT_TYPE_STRING, NEURON_COMPONENT_TYPE_STRING,
    CHANNEL_COMPONENT_TYPE_STRING
]

MODEL_FILE_NAME_KEY = 'model_file_name'
NUM_ITERATIONS_KEY = 'num_iterations'
LEARNING_RATE_KEY = 'learning_rate'
COMPONENT_TYPE_KEY = 'component_type_string'
TARGET_CLASS_KEY = 'target_class'
OPTIMIZE_FOR_PROB_KEY = 'optimize_for_probability'
IDEAL_LOGIT_KEY = 'ideal_logit'
LAYER_NAME_KEY = 'layer_name'
IDEAL_ACTIVATION_KEY = 'ideal_activation'
NEURON_INDICES_KEY = 'neuron_index_matrix'
CHANNEL_INDICES_KEY = 'channel_indices'

STORM_ID_KEY = 'storm_id'
STORM_TIME_KEY = 'storm_time_unix_sec'
RETURN_PROBS_KEY = 'return_probs'


def _do_gradient_descent(
        model_object, loss_tensor, init_function, num_iterations,
        learning_rate):
    """Does gradient descent for feature optimization.

    :param model_object: Instance of `keras.models.Model`.
    :param loss_tensor: Keras tensor defining the loss function.
    :param init_function: See doc for `optimize_input_for_class`.
    :param num_iterations: Same.
    :param learning_rate: Same.
    :return: list_of_optimized_input_matrices: length-T list of optimized input
        matrices (numpy arrays), where T = number of input tensors to the model.
    """

    if isinstance(model_object.input, list):
        list_of_input_tensors = model_object.input
    else:
        list_of_input_tensors = [model_object.input]

    list_of_gradient_tensors = K.gradients(loss_tensor, list_of_input_tensors)
    num_input_tensors = len(list_of_input_tensors)
    for i in range(num_input_tensors):
        list_of_gradient_tensors[i] /= K.maximum(
            K.sqrt(K.mean(list_of_gradient_tensors[i] ** 2)),
            K.epsilon())

    inputs_to_loss_and_gradients = K.function(
        list_of_input_tensors + [K.learning_phase()],
        ([loss_tensor] + list_of_gradient_tensors))

    list_of_optimized_input_matrices = [None] * num_input_tensors
    for i in range(num_input_tensors):
        these_dimensions = numpy.array(
            [1] + list_of_input_tensors[i].get_shape().as_list()[1:], dtype=int)
        list_of_optimized_input_matrices[i] = init_function(these_dimensions)

    for j in range(num_iterations):
        these_outputs = inputs_to_loss_and_gradients(
            list_of_optimized_input_matrices + [0])

        if numpy.mod(j, 100) == 0:
            print 'Loss at iteration {0:d} of {1:d}: {2:.2e}'.format(
                j + 1, num_iterations, these_outputs[0])

        for i in range(num_input_tensors):
            list_of_optimized_input_matrices[i] -= (
                these_outputs[i + 1] * learning_rate)

    print 'Loss after all {0:d} iterations: {1:.2e}'.format(
        num_iterations, these_outputs[0])
    return list_of_optimized_input_matrices


def check_component_type(component_type_string):
    """Ensures that component type is valid.

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


def check_optimization_metadata(
        num_iterations, learning_rate, component_type_string,
        target_class=None, optimize_for_probability=None, ideal_logit=None,
        layer_name=None, ideal_activation=None, neuron_index_matrix=None,
        channel_indices=None):
    """Error-checks metadata for optimization.

    C = number of components (classes, neurons, or channels) for which model
        input was optimized

    :param num_iterations: Number of iterations used in optimization procedure.
    :param learning_rate: Learning rate used in optimization procedure.
    :param component_type_string: Component type (must be accepted by
        `check_component_type`).
    :param target_class: [used only if component_type_string = "class"]
        See doc for `optimize_input_for_class`.
    :param optimize_for_probability: Same.
    :param ideal_logit: Same.
    :param layer_name:
        [used only if component_type_string = "neuron" or "channel"]
        See doc for `optimize_input_for_neuron_activation` or
        `optimize_input_for_channel_activation`.
    :param ideal_activation: Same.
    :param neuron_index_matrix:
        [used only if component_type_string = "neuron"]
        C-by-? numpy array, where neuron_index_matrix[j, :] contains array
        indices of the [j]th neuron whose activation was maximized.
    :param channel_indices: [used only if component_type_string = "channel"]
        length-C numpy array, where channel_indices[j] is the index of the [j]th
        channel whose activation was maximized.
    :return: num_components: Number of model components (classes, neurons, or
        channels) whose activation was maximized.
    """

    error_checking.assert_is_integer(num_iterations)
    error_checking.assert_is_greater(num_iterations, 0)
    error_checking.assert_is_greater(learning_rate, 0.)
    error_checking.assert_is_less_than(learning_rate, 1.)
    check_component_type(component_type_string)

    if component_type_string == CLASS_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer(target_class)
        error_checking.assert_is_geq(target_class, 0)
        error_checking.assert_is_boolean(optimize_for_probability)
        num_components = 1

        if optimize_for_probability:
            ideal_logit = None
        if ideal_logit is not None:
            error_checking.assert_is_greater(ideal_logit, 0.)

    if component_type_string in [NEURON_COMPONENT_TYPE_STRING,
                                 CHANNEL_COMPONENT_TYPE_STRING]:
        error_checking.assert_is_string(layer_name)
        if ideal_activation is not None:
            error_checking.assert_is_greater(ideal_activation, 0.)

    if component_type_string == NEURON_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer_numpy_array(neuron_index_matrix)
        error_checking.assert_is_geq_numpy_array(neuron_index_matrix, 0)
        error_checking.assert_is_numpy_array(
            neuron_index_matrix, num_dimensions=2)
        num_components = neuron_index_matrix.shape[0]

    if component_type_string == CHANNEL_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer_numpy_array(channel_indices)
        error_checking.assert_is_geq_numpy_array(channel_indices, 0)
        num_components = len(channel_indices)

    return num_components


def check_activation_metadata(
        component_type_string, target_class=None, return_probs=None,
        layer_name=None, neuron_index_matrix=None, channel_indices=None):
    """Error-checks metadata for activation calculations.

    C = number of model components (classes, neurons, or channels) for which
        activations were computed

    :param component_type_string: Component type (must be accepted by
        `check_component_type`).
    :param target_class: [used only if component_type_string = "class"]
        See doc for `get_class_activation_for_examples`.
    :param return_probs: Same.
    :param layer_name:
        [used only if component_type_string = "neuron" or "channel"]
        See doc for `get_neuron_activation_for_examples` or
        `get_channel_activation_for_examples`.
    :param neuron_index_matrix: [used only if component_type_string = "neuron"]
        C-by-? numpy array, where neuron_index_matrix[j, :] contains array
        indices of the [j]th neuron whose activation was computed.
    :param channel_indices: [used only if component_type_string = "channel"]
        length-C numpy array, where channel_indices[j] is the index of the
        [j]th channel whose activation was computed.
    :return: num_components: Number of model components (classes, neurons, or
        channels) whose activation was computed.
    """

    check_component_type(component_type_string)
    if component_type_string == CLASS_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer(target_class)
        error_checking.assert_is_geq(target_class, 0)
        error_checking.assert_is_boolean(return_probs)
        num_components = 1

    if component_type_string in [NEURON_COMPONENT_TYPE_STRING,
                                 CHANNEL_COMPONENT_TYPE_STRING]:
        error_checking.assert_is_string(layer_name)

    if component_type_string == NEURON_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer_numpy_array(neuron_index_matrix)
        error_checking.assert_is_geq_numpy_array(neuron_index_matrix, 0)
        error_checking.assert_is_numpy_array(
            neuron_index_matrix, num_dimensions=2)
        num_components = neuron_index_matrix.shape[0]

    if component_type_string == CHANNEL_COMPONENT_TYPE_STRING:
        error_checking.assert_is_integer_numpy_array(channel_indices)
        error_checking.assert_is_geq_numpy_array(channel_indices, 0)
        num_components = len(channel_indices)

    return num_components

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


def create_gaussian_initializer(mean, standard_deviation):
    """Creates Gaussian initializer.

    :param mean: Mean of Gaussian distribution.
    :param standard_deviation: Standard deviation of Gaussian distribution.
    :return: init_function: Function (see below).
    """

    def init_function(array_dimensions):
        """Initializes numpy array with Gaussian distribution.

        :param array_dimensions: numpy array of dimensions.
        :return: array: Array with the given dimensions.  For example, if
            array_dimensions = [1, 5, 10], this array will be 1 x 5 x 10.
        """

        return numpy.random.normal(
            loc=mean, scale=standard_deviation, size=array_dimensions)

    return init_function


def create_uniform_random_initializer(min_value, max_value):
    """Creates uniform-random initializer.

    :param min_value: Minimum value in uniform distribution.
    :param max_value: Max value in uniform distribution.
    :return: init_function: Function (see below).
    """

    def init_function(array_dimensions):
        """Initializes numpy array with uniform distribution.

        :param array_dimensions: numpy array of dimensions.
        :return: array: Array with the given dimensions.
        """

        return numpy.random.uniform(
            low=min_value, high=max_value, size=array_dimensions)

    return init_function


def create_constant_initializer(constant_value):
    """Creates constant initializer.

    :param constant_value: Constant value with which to fill numpy array.
    :return: init_function: Function (see below).
    """

    def init_function(array_dimensions):
        """Initializes numpy array with constant value.

        :param array_dimensions: numpy array of dimensions.
        :return: array: Array with the given dimensions.
        """

        return numpy.full(array_dimensions, constant_value, dtype=float)

    return init_function


def create_climo_initializer(
        mean_radar_value_dict, mean_sounding_value_dict,
        sounding_field_names=None, sounding_pressures_mb=None,
        radar_field_names=None, radar_heights_m_asl=None,
        radar_field_name_by_channel=None, radar_height_by_channel_m_asl=None):
    """Creates climatological initializer.

    Specifically, this function initializes each value to a climatological mean.
    There is one mean for each radar field/height and each sounding
    field/pressure.

    F_s = number of sounding fields in model input
    H_s = number of vertical sounding levels (pressures) in model input

    The following letters are used only for 3-D radar images.

    F_r = number of radar fields in model input
    H_r = number of radar heights in model input

    The following letters are used only for 2-D radar images.

    C = number of radar channels (field/height pairs) in model input

    :param mean_radar_value_dict: See doc for
        `deep_learning_utils.write_climo_averages_to_file`.
    :param mean_sounding_value_dict: Same.
    :param sounding_field_names:
        [if model input does not contain soundings, leave this as `None`]
        List (length F_s) with names of sounding fields, in the order that they
        appear in the corresponding input tensor.
    :param sounding_pressures_mb:
        [if model input does not contain soundings, leave this as `None`]
        numpy array (length H_s) of sounding pressure levels, in the order that
        they appear in the corresponding input tensor.
    :param radar_field_names:
        [if model input does not contain 3-D radar images, leave this as `None`]
        List (length F_r) with names of radar fields, in the order that they
        appear in the corresponding input tensor.
    :param radar_heights_m_asl:
        [if model input does not contain 3-D radar images, leave this as `None`]
        numpy array (length H_r) of radar heights (metres above sea level), in
        the order that they appear in the corresponding input tensor.
    :param radar_field_name_by_channel:
        [if model input does not contain 2-D radar images, leave this as `None`]
        Length-C list of radar fields, in the order that they appear in the
        corresponding input tensor.
    :param radar_height_by_channel_m_asl:
        [if model input does not contain 2-D radar images, leave this as `None`]
        Length-C numpy array of radar heights (metres above sea level), in the
        order that they appear in the corresponding input tensor.
    :return: init_function: Function (see below).
    """

    if sounding_field_names is not None:
        error_checking.assert_is_string_list(sounding_field_names)
        error_checking.assert_is_numpy_array(
            numpy.array(sounding_field_names), num_dimensions=1)

        error_checking.assert_is_integer_numpy_array(sounding_pressures_mb)
        error_checking.assert_is_numpy_array(
            sounding_pressures_mb, num_dimensions=1)

    if radar_field_names is not None:
        error_checking.assert_is_string_list(radar_field_names)
        error_checking.assert_is_numpy_array(
            numpy.array(radar_field_names), num_dimensions=1)

        error_checking.assert_is_integer_numpy_array(radar_heights_m_asl)
        error_checking.assert_is_numpy_array(
            radar_heights_m_asl, num_dimensions=1)

    if radar_field_name_by_channel is not None:
        error_checking.assert_is_string_list(radar_field_name_by_channel)
        error_checking.assert_is_numpy_array(
            numpy.array(radar_field_name_by_channel), num_dimensions=1)

        error_checking.assert_is_integer_numpy_array(
            radar_height_by_channel_m_asl)
        error_checking.assert_is_numpy_array(
            radar_height_by_channel_m_asl,
            exact_dimensions=numpy.array([len(radar_field_name_by_channel)]))

    def init_function(array_dimensions):
        """Initializes numpy array with climatological means.

        If len(array_dimensions) = 3, this method assumes that the corresponding
        input tensor contains soundings.
        If len(array_dimensions) = 4 ... 2-D radar images.
        If len(array_dimensions) = 5 ... 3-D radar images.

        :param array_dimensions: numpy array of dimensions.
        :return: array: Array with the given dimensions.
        """

        array = numpy.full(array_dimensions, numpy.nan)
        if len(array_dimensions) == 5:
            for j in range(len(radar_field_names)):
                for k in range(len(radar_heights_m_asl)):
                    array[..., k, j] = mean_radar_value_dict[
                        radar_field_names[j], radar_heights_m_asl[k]]

            return array

        if len(array_dimensions) == 4:
            for j in range(len(radar_field_name_by_channel)):
                array[..., j] = mean_radar_value_dict[
                    radar_field_name_by_channel[j],
                    radar_height_by_channel_m_asl[j]]

            return array

        if len(array_dimensions) == 3:
            for j in range(len(sounding_field_names)):
                for k in range(len(sounding_pressures_mb)):
                    array[..., k, j] = mean_sounding_value_dict[
                        sounding_field_names[j], sounding_pressures_mb[k]]

            return array

        return None

    return init_function


def optimize_input_for_class(
        model_object, target_class, optimize_for_probability, init_function,
        num_iterations=DEFAULT_NUM_ITERATIONS,
        learning_rate=DEFAULT_LEARNING_RATE, ideal_logit=DEFAULT_IDEAL_LOGIT):
    """Finds an input that maximizes prediction of the target class.

    If `optimize_for_probability = True`, this method finds an input that maxxes
    the predicted probability of the target class.  This also minimizes the sum
    of predicted probabilities of the other classes, since all probabilities
    must sum to 1.

    If `optimize_for_probability = False`, this method finds an input that
    maxxes the logit for the target class.  Each input to the prediction layer's
    activation function is a logit, and each output is a probability, so logits
    can be viewed as "unnormalized probabilities".  Maxxing the logit for the
    target class does not necessarily minimize the sum of logits for the other
    classes, because the sum of all logits is unbounded.

    This leads to the following recommendations:

    [1] If you want to maximize prediction of the target class while minimizing
        the prediction of all other classes, set
        `optimize_for_probability = True`.
    [2] If you want to maximize prediction of the target class, regardless of
        how this affects predictions of the other classes, set
        `optimize_for_probability = False`.

    According to Olah et al. (2017), "optimizing pre-softmax logits produces
    images of better visual quality".  However, this was for a multiclass
    problem.  The same may not be true for a binary problem.

    :param model_object: Instance of `keras.models.Model`.
    :param target_class: Input will be optimized for this class.  Must be an
        integer in 0...(K - 1), where K = number of classes.
    :param optimize_for_probability: See general discussion above.
    :param init_function: Function used to initialize input tensors.  See
        `create_gaussian_initializer` for an example.
    :param num_iterations: Number of iterations for the optimization procedure.
        This is the number of times that the input tensors will be adjusted.
    :param learning_rate: Learning rate.  At each iteration, each input value x
        will be decremented by `learning_rate * gradient`, where `gradient` is
        the gradient of x with respect to the loss function.
    :param ideal_logit: [used only if `optimize_for_probability = False`]
        The loss function will be (logit[k] - ideal_logit) ** 2, where logit[k]
        is the logit for the target class.  If `ideal_logit is None`, the loss
        function will be -sign(logit[k]) * logit[k]**2, or the negative signed
        square of logit[k], so that loss always decreases as logit[k] increases.
    :return: list_of_optimized_input_matrices: See doc for
        `_do_gradient_descent`.
    :raises: TypeError: if `optimize_for_probability = False` and the output
        layer is not an activation layer.
    """

    check_optimization_metadata(
        num_iterations-num_iterations, learning_rate=learning_rate,
        component_type_string=CLASS_COMPONENT_TYPE_STRING,
        target_class=target_class,
        optimize_for_probability=optimize_for_probability,
        ideal_logit=ideal_logit)

    if optimize_for_probability:
        loss_tensor = K.mean(
            (model_object.layers[-1].output[..., target_class] - 1) ** 2)
    else:
        out_layer_type_string = type(model_object.layers[-1]).__name__
        if out_layer_type_string != 'Activation':
            error_string = (
                'If `optimize_for_probability = False`, the output layer must '
                'be an "Activation" layer (got "{0:s}" layer).  Otherwise, '
                'there is no way to access the pre-softmax logits (unnormalized'
                ' probabilities).'
            ).format(out_layer_type_string)
            raise TypeError(error_string)

        if ideal_logit is None:
            loss_tensor = -K.mean(
                K.sign(model_object.layers[-1].input[..., target_class]) *
                model_object.layers[-1].input[..., target_class] ** 2)
        else:
            loss_tensor = K.mean(
                (model_object.layers[-1].input[..., target_class] -
                 ideal_logit) ** 2)

    return _do_gradient_descent(
        model_object=model_object, loss_tensor=loss_tensor,
        init_function=init_function, num_iterations=num_iterations,
        learning_rate=learning_rate)


def optimize_input_for_neuron_activation(
        model_object, layer_name, neuron_indices, init_function,
        num_iterations=DEFAULT_NUM_ITERATIONS,
        learning_rate=DEFAULT_LEARNING_RATE,
        ideal_activation=DEFAULT_IDEAL_ACTIVATION):
    """Finds an input that maximizes the activation of one neuron in one layer.

    :param model_object: Instance of `keras.models.Model`.
    :param layer_name: Name of layer with neuron whose activation is to be
        maximized.
    :param neuron_indices: 1-D numpy array with indices of neuron whose
        activation is to be maximized.  If the layer output has K dimensions,
        `neuron_indices` must have length K - 1.  (The first dimension of the
        layer output is the example dimension, for which the index is 0 in this
        case.)
    :param init_function: See doc for `optimize_input_for_class`.
    :param num_iterations: Same.
    :param learning_rate: Same.
    :param ideal_activation: The loss function will be
        (neuron_activation - ideal_activation)** 2.  If
        `ideal_activation is None`, the loss function will be
        -sign(neuron_activation) * neuron_activation**2, or the negative signed
        square of neuron_activation, so that loss always decreases as
        neuron_activation increases.
    :return: list_of_optimized_input_matrices: See doc for
        `_do_gradient_descent`.
    """

    check_optimization_metadata(
        num_iterations=num_iterations, learning_rate=learning_rate,
        component_type_string=NEURON_COMPONENT_TYPE_STRING,
        layer_name=layer_name, ideal_activation=ideal_activation,
        neuron_index_matrix=numpy.expand_dims(neuron_indices, axis=0))

    neuron_indices_as_tuple = (0,) + tuple(neuron_indices)

    if ideal_activation is None:
        loss_tensor = -(
            K.sign(
                model_object.get_layer(name=layer_name).output[
                    neuron_indices_as_tuple]) *
            model_object.get_layer(name=layer_name).output[
                neuron_indices_as_tuple] ** 2
        )
    else:
        loss_tensor = (
            model_object.get_layer(name=layer_name).output[
                neuron_indices_as_tuple] -
            ideal_activation) ** 2

    return _do_gradient_descent(
        model_object=model_object, loss_tensor=loss_tensor,
        init_function=init_function, num_iterations=num_iterations,
        learning_rate=learning_rate)


def optimize_input_for_channel_activation(
        model_object, layer_name, channel_index, init_function,
        stat_function_for_neuron_activations,
        num_iterations=DEFAULT_NUM_ITERATIONS,
        learning_rate=DEFAULT_LEARNING_RATE,
        ideal_activation=DEFAULT_IDEAL_ACTIVATION):
    """Finds an input that maximizes the activation of one channel in one layer.

    :param model_object: Instance of `keras.models.Model`.
    :param layer_name: Name of layer with channel whose activation is to be
        maximized.
    :param channel_index: Index of channel whose activation is to be maximized.
        If `channel_index = c`, the activation of the [c]th channel in the
        layer will be maximized.
    :param init_function: See doc for `check_optimization_metadata`.
    :param stat_function_for_neuron_activations: Function used to process neuron
        activations.  In general, a channel contains many neurons, so there is
        an infinite number of ways to maximize the "channel activation," because
        there is an infinite number of ways to define "channel activation".
        This function must take a Keras tensor (containing neuron activations)
        and return a single number.  Some examples are `keras.backend.max` and
        `keras.backend.mean`.
    :param num_iterations: See doc for `check_optimization_metadata`.
    :param learning_rate: Same.
    :param ideal_activation: The loss function will be
        abs(stat_function_for_neuron_activations(neuron_activations) -
            ideal_activation).

        For example, if `stat_function_for_neuron_activations` is the mean,
        loss function will be abs(mean(neuron_activations) - ideal_activation).
        If `ideal_activation is None`, the loss function will be
        -1 * abs(stat_function_for_neuron_activations(neuron_activations) -
                 ideal_activation).

    :return: list_of_optimized_input_matrices: See doc for
        `_do_gradient_descent`.
    """

    check_optimization_metadata(
        num_iterations=num_iterations, learning_rate=learning_rate,
        component_type_string=CHANNEL_COMPONENT_TYPE_STRING,
        layer_name=layer_name, ideal_activation=ideal_activation,
        channel_indices=numpy.array([channel_index]))

    if ideal_activation is None:
        loss_tensor = -K.abs(stat_function_for_neuron_activations(
            model_object.get_layer(name=layer_name).output[
                0, ..., channel_index]))
    else:
        error_checking.assert_is_greater(ideal_activation, 0.)
        loss_tensor = K.abs(
            stat_function_for_neuron_activations(
                model_object.get_layer(name=layer_name).output[
                    0, ..., channel_index]) -
            ideal_activation)

    return _do_gradient_descent(
        model_object=model_object, loss_tensor=loss_tensor,
        init_function=init_function, num_iterations=num_iterations,
        learning_rate=learning_rate)


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


def get_class_activation_for_examples(
        model_object, target_class, return_probs, list_of_input_matrices):
    """Returns prediction of one class for each input example.

    If `return_probs = True`, this method returns the predicted probability of
    the target class for each example.

    If `return_probs = False`, returns the logit of the target class for each
    example.  Each input to the prediction layer's activation function is a
    logit, and each output is a probability, so logits can be viewed as
    "unnormalized probabilities".

    :param model_object: Instance of `keras.models.Model`.
    :param target_class: Predictions will be returned for this class.  Must be
        an integer in 0...(K - 1), where K = number of classes.
    :param return_probs: See general discussion above.
    :param list_of_input_matrices: length-T list of numpy arrays, comprising one
        or more examples (storm objects).  list_of_input_matrices[i] must have
        the same dimensions as the [i]th input tensor to the model.
    :return: activation_values: length-E numpy array, where activation_values[i]
        is the activation (prediction) of the given class for the [i]th example.
    :raises: TypeError: if `return_probs = False` and the output layer is not an
        activation layer.
    """

    check_activation_metadata(
        component_type_string=CLASS_COMPONENT_TYPE_STRING,
        target_class=target_class, return_probs=return_probs)

    if not return_probs:
        out_layer_type_string = type(model_object.layers[-1]).__name__
        if out_layer_type_string != 'Activation':
            error_string = (
                'If `return_probs = False`, the output layer must be an '
                '"Activation" layer (got "{0:s}" layer).  Otherwise, there is '
                'no way to access the pre-softmax logits (unnormalized '
                'probabilities).'
            ).format(out_layer_type_string)
            raise TypeError(error_string)

    if isinstance(model_object.input, list):
        list_of_input_tensors = model_object.input
    else:
        list_of_input_tensors = [model_object.input]

    if return_probs:
        activation_function = K.function(
            list_of_input_tensors + [K.learning_phase()],
            [model_object.layers[-1].output[..., target_class]])
    else:
        activation_function = K.function(
            list_of_input_tensors + [K.learning_phase()],
            [model_object.layers[-1].input[..., target_class]])

    return activation_function(list_of_input_matrices + [0])[0]


def get_neuron_activation_for_examples(
        model_object, layer_name, neuron_indices, list_of_input_matrices):
    """Returns activation of one neuron by each input example.

    T = number of input tensors to the model
    E = number of examples (storm objects)

    :param model_object: Instance of `keras.models.Model`.
    :param layer_name: Name of layer with neuron whose activation is to be
        computed.
    :param neuron_indices: 1-D numpy array with indices of neuron whose
        activation is to be computed.  If the layer output has K dimensions,
        `neuron_indices` must have length K - 1.  (The first dimension of the
        layer output is the example dimension, for which all indices from
        0...[E - 1] are used.)
    :param list_of_input_matrices: See doc for
        `get_class_activation_for_examples`.
    :return: activation_values: length-E numpy array, where activation_values[i]
        is the activation of the given neuron by the [i]th example.
    """

    check_activation_metadata(
        component_type_string=NEURON_COMPONENT_TYPE_STRING,
        layer_name=layer_name,
        neuron_index_matrix=numpy.expand_dims(neuron_indices, axis=0))

    if isinstance(model_object.input, list):
        list_of_input_tensors = model_object.input
    else:
        list_of_input_tensors = [model_object.input]

    activation_function = K.function(
        list_of_input_tensors + [K.learning_phase()],
        [model_object.get_layer(name=layer_name).output[..., neuron_indices]])

    return activation_function(list_of_input_matrices + [0])[0]


def get_channel_activation_for_examples(
        model_object, layer_name, channel_index, list_of_input_matrices,
        stat_function_for_neuron_activations):
    """Returns activation of one channel by each input example.

    :param model_object: Instance of `keras.models.Model`.
    :param layer_name: Name of layer with channel whose activation is to be
        computed.
    :param channel_index: Index of channel whose activation is to be computed.
        If `channel_index = c`, the activation of the [c]th channel in the
        layer will be computed.
    :param list_of_input_matrices: See doc for
        `get_class_activation_for_examples`.
    :param stat_function_for_neuron_activations: See doc for
        `optimize_input_for_channel_activation`.
    :return: activation_values: length-E numpy array, where activation_values[i]
        is stat_function_for_neuron_activations(channel activations) for the
        [i]th example.
    """

    check_activation_metadata(
        component_type_string=NEURON_COMPONENT_TYPE_STRING,
        layer_name=layer_name, channel_indices=numpy.array([channel_index]))

    if isinstance(model_object.input, list):
        list_of_input_tensors = model_object.input
    else:
        list_of_input_tensors = [model_object.input]

    activation_function = K.function(
        list_of_input_tensors + [K.learning_phase()],
        [stat_function_for_neuron_activations(
            model_object.get_layer(name=layer_name).output[..., channel_index])
        ]
    )

    return activation_function(list_of_input_matrices + [0])[0]


def write_optimized_input_to_file(
        pickle_file_name, list_of_optimized_input_matrices, model_file_name,
        num_iterations, learning_rate, component_type_string,
        target_class=None, optimize_for_probability=None, ideal_logit=None,
        layer_name=None, ideal_activation=None, neuron_index_matrix=None,
        channel_indices=None):
    """Writes optimized input data to Pickle file.

    :param pickle_file_name: Path to output file.
    :param list_of_optimized_input_matrices: length-T list of optimized input
        matrices (numpy arrays), where T = number of input tensors to the model.
    :param model_file_name: Path to file with trained model.
    :param num_iterations: See doc for `check_optimization_metadata`.
    :param learning_rate: Same.
    :param component_type_string: Same.
    :param target_class: Same.
    :param optimize_for_probability: Same.
    :param ideal_logit: Same.
    :param layer_name: Same.
    :param ideal_activation: Same.
    :param neuron_index_matrix: Same.
    :param channel_indices: Same.
    """

    num_components = check_optimization_metadata(
        num_iterations=num_iterations, learning_rate=learning_rate,
        component_type_string=component_type_string, target_class=target_class,
        optimize_for_probability=optimize_for_probability,
        ideal_logit=ideal_logit, layer_name=layer_name,
        ideal_activation=ideal_activation,
        neuron_index_matrix=neuron_index_matrix,
        channel_indices=channel_indices)

    error_checking.assert_is_string(model_file_name)
    error_checking.assert_is_list(list_of_optimized_input_matrices)

    for this_array in list_of_optimized_input_matrices:
        error_checking.assert_is_numpy_array(this_array)
        these_expected_dim = numpy.array(
            (num_components,) + this_array.shape[1:], dtype=int)
        error_checking.assert_is_numpy_array(
            this_array, exact_dimensions=these_expected_dim)

    metadata_dict = {
        MODEL_FILE_NAME_KEY: model_file_name,
        NUM_ITERATIONS_KEY: num_iterations,
        LEARNING_RATE_KEY: learning_rate,
        COMPONENT_TYPE_KEY: component_type_string,
        TARGET_CLASS_KEY: target_class,
        OPTIMIZE_FOR_PROB_KEY: optimize_for_probability,
        IDEAL_LOGIT_KEY: ideal_logit,
        LAYER_NAME_KEY: layer_name,
        IDEAL_ACTIVATION_KEY: ideal_activation,
        NEURON_INDICES_KEY: neuron_index_matrix,
        CHANNEL_INDICES_KEY: channel_indices,
    }

    file_system_utils.mkdir_recursive_if_necessary(file_name=pickle_file_name)
    pickle_file_handle = open(pickle_file_name, 'wb')
    pickle.dump(list_of_optimized_input_matrices, pickle_file_handle)
    pickle.dump(metadata_dict, pickle_file_handle)
    pickle_file_handle.close()


def read_optimized_inputs_from_file(pickle_file_name):
    """Reads optimized input data from Pickle file.

    :param pickle_file_name: Path to input file.
    :return: list_of_optimized_input_matrices: length-T list of optimized input
        matrices (numpy arrays), where T = number of input tensors to the model.
    :return: metadata_dict: Dictionary with the following keys.
    metadata_dict['model_file_name']: See doc for
        `write_optimized_inputs_to_file`.
    metadata_dict['num_iterations']: Same.
    metadata_dict['learning_rate']: Same.
    metadata_dict['component_type_string']: Same.
    metadata_dict['target_class']: Same.
    metadata_dict['optimize_for_probability']: Same.
    metadata_dict['ideal_logit']: Same.
    metadata_dict['layer_name']: Same.
    metadata_dict['ideal_activation']: Same.
    metadata_dict['neuron_index_matrix']: Same.
    metadata_dict['channel_indices']: Same.
    """

    pickle_file_handle = open(pickle_file_name, 'rb')
    list_of_optimized_input_matrices = pickle.load(pickle_file_handle)
    metadata_dict = pickle.load(pickle_file_handle)
    pickle_file_handle.close()

    return list_of_optimized_input_matrices, metadata_dict


def write_activations_to_file(
        pickle_file_name, activation_matrix, model_file_name,
        component_type_string, target_class=None, return_probs=None,
        layer_name=None, neuron_index_matrix=None, channel_indices=None):
    """Writes activations to Pickle file.

    E = number of examples (storm objects)
    C = number of model components (classes, neurons, or channels) for which
        activations were computed

    :param pickle_file_name: Path to output file.
    :param activation_matrix: E-by-C numpy array of activations, where
        activation_matrix[i, j] = activation of the [j]th model component for
        the [i]th example.
    :param model_file_name: Path to file with trained model.
    :param component_type_string: See doc for `check_activation_metadata`.
    :param target_class: Same.
    :param return_probs: Same.
    :param layer_name: Same.
    :param neuron_index_matrix: Same.
    :param channel_indices: Same.
    """

    num_components = check_activation_metadata(
        component_type_string=component_type_string, target_class=target_class,
        return_probs=return_probs, layer_name=layer_name,
        neuron_index_matrix=neuron_index_matrix,
        channel_indices=channel_indices)

    error_checking.assert_is_string(model_file_name)
    error_checking.assert_is_numpy_array_without_nan(activation_matrix)
    expected_dimensions = numpy.array(
        [activation_matrix.shape[0], num_components], dtype=int)
    error_checking.assert_is_numpy_array(
        activation_matrix, exact_dimensions=expected_dimensions)

    metadata_dict = {
        MODEL_FILE_NAME_KEY: model_file_name,
        COMPONENT_TYPE_KEY: component_type_string,
        TARGET_CLASS_KEY: target_class,
        RETURN_PROBS_KEY: return_probs,
        LAYER_NAME_KEY: layer_name,
        NEURON_INDICES_KEY: neuron_index_matrix,
        CHANNEL_INDICES_KEY: channel_indices,
    }

    file_system_utils.mkdir_recursive_if_necessary(file_name=pickle_file_name)
    pickle_file_handle = open(pickle_file_name, 'wb')
    pickle.dump(activation_matrix, pickle_file_handle)
    pickle.dump(metadata_dict, pickle_file_handle)
    pickle_file_handle.close()


def read_activations_from_file(pickle_file_name):
    """Reads activations from Pickle file.

    E = number of examples (storm objects)
    C = number of model components (classes, neurons, or channels) for which
        activations were computed

    :param pickle_file_name: Path to input file.
    :return: activation_matrix: E-by-C numpy array of activations, where
        activation_matrix[i, j] = activation of the [j]th model component for
        the [i]th example.
    :return: metadata_dict: Dictionary with the following keys.
    metadata_dict['model_file_name']: See doc for `write_activations_to_file`.
    metadata_dict['component_type_string']: Same.
    metadata_dict['target_class']: Same.
    metadata_dict['return_probs']: Same.
    metadata_dict['layer_name']: Same.
    metadata_dict['neuron_index_matrix']: Same.
    metadata_dict['channel_indices']: Same.
    """

    pickle_file_handle = open(pickle_file_name, 'rb')
    activation_matrix = pickle.load(pickle_file_handle)
    metadata_dict = pickle.load(pickle_file_handle)
    pickle_file_handle.close()

    return activation_matrix, metadata_dict
