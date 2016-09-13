#!/usr/bin/env python

"""Contains measurement processing functions designed to be baked into the
move_capture function, along with the baker function to enable them to do
so."""

import time

import numpy as np


def baker(fun, args=None, kwargs=None, position_to_pass_through=(0, 0)):
    """Returns an object given by the function 'fun' with its arguments,
    known as a curried function or closure. These objects can be passed into
    other functions to be evaluated.

    :param fun: The function object without any arguments specified.
    :param args: A list of the positional arguments. Put any placeholder in
    the index that will not be baked into the function.
    :param kwargs: A list of keyword arguments.
    :param position_to_pass_through: A tuple specifying the index of
    positional arguments for the function 'fun' that will be skipped in
    baking. For example, (1,3) will skip positional arguments 1 through to
    3, so that the baked arguments in function 'fun' will be:
        fun(baked, unbaked, unbaked, unbaked, baked...).
    If a single position is to be skipped, enter an integer for this
    argument. For example, entering 1 will result in:
        fun(baked, unbaked, baked...).
    NOTE: Ensure the result can fill in the exact number of missing
    positional arguments!
    :return: The object containing the function with its arguments."""

    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}

    if type(position_to_pass_through) is int:
        position_to_pass_through = (position_to_pass_through,
                                    position_to_pass_through)
    elif type(position_to_pass_through) is not tuple:
        raise TypeError('The variable \'position_to_pass_through\' must be a '
                        'tuple or int.')

    def wrapped(*result):
        """Parameter position_to_pass_through specifies the index of the
        parameter 'result' in sequence of positional arguments for 'fun'."""
        return fun(*(args[:position_to_pass_through[0]] + list(result) + args[(
            position_to_pass_through[1]+1):]), **kwargs)

    return wrapped


def unchanged(arg):
    """Returns the single input argument; the default function for image
    post-processing to return the input array unchanged."""
    return arg


# Functions to process individual measurements.
def stop_on_nonzero(measurement):
    """Function to raise Exception if the measurement is non-zero."""
    if measurement[0] != 0:
        # The 0th element is the average value, and the 1st element the error.
        raise NonZeroReading
    return measurement


def saturation_reached(measurement, sensor_obj):
    """Function to raise Exception if measurements saturate, so that the
    user is recommended to turn down the gain setting, with an input requested.
    """
    if measurement[0] == 1023 and sensor_obj.gain >= 0:
        # This is the max value that the 10-bit serial port can provide.
        # Change if this is not the max value.
        if not sensor_obj.ignore_saturation:
            while True:
                answer = raw_input('Measurement saturation reached. The user '
                                   'is recommended to turn down the gain by '
                                   'one setting. Enter \'retry\' after you '
                                   'have turned down the gain, \'ignore\' if '
                                   'you have decided not to do so this time '
                                   'and \'ignore all\' if this is either not '
                                   'possible or you have decided not to do so '
                                   'for the entire remaining set of '
                                   'measurements: ')
                if answer == 'retry' or answer == 'ignore' \
                        or answer == 'ignore all':
                    if answer == 'retry':
                        # All measurements have to be taken again for this set.
                        sensor_obj.gain -= 10
                        raise Saturation
                    elif answer == 'ignore':
                        # Continue as if nothing is wrong.
                        break
                    elif answer == 'ignore all':
                        # Change this to ensure that all subsequent
                        # saturations for the duration of this move_capture
                        # function are ignored. That function changes
                        # ignore_saturation to False at the beginning and
                        # end of its run.
                        sensor_obj.ignore_saturation = True
                        break
    return measurement


# Generator functions to specify the order in which to visit each element in
# the array of positions.
def raster(x, y, z, initial_pos):
    """Generator to produce N x 3 array of all possible permutations of 1D
    arrays x, y and z, such that N = len(x) * len(y). For example x = [1,2] and
    y = [3, 4] yields [1, 3, 0], [1, 4, 0], [2, 3, 0], [2, 4, 0] respectively.
    This is added to [0, 0, 0] before being output."""
    i = 0
    while i < x .size:
        j = 0
        while j < y.size:
            k = 0
            while k < z.size:
                yield np.array([x[i], y[j], z[k]]) + initial_pos
                k += 1
            j += 1
        i += 1


def fixed_timer(x, y, z, initial_pos, count=5, t=1):
    """Generator to hold the stage at a fixed position (although it may
    still drift) and measure brightness repeatedly at each position before
    moving on. x, y, z, initial_pos defined as in raster. count is the total
    number of average measurements to take per position, and t the time
    interval to wait between each such measurement set."""
    rast = raster(x, y, z, initial_pos)
    while True:
        next_pos = next(rast)
        for i in range(count):
            try:
                yield next_pos
                time.sleep(t)
            except StopIteration:
                break


def yield_pos(positions):
    """A generator for each position in the positions to visit array.
    :param positions: Array of positions to visit."""
    for position in positions:
        yield np.array(position)


def revisit_check(results, proposed_pos, overlap_allowed):
    """Check visit of the positions in proposed_array have
    already been visited recently, and do not visit them again.
    :param results: The results list.
    :param proposed_pos: The array of positions to visit next,
    in the format [x column, y column, z column].
    :param overlap_allowed: Set to True to allow overlaps with already
    measured points."""
    proposed_pos = set(tuple(row) for row in proposed_pos)

    if (not results) or overlap_allowed:
        # If overlap is allowed, then all proposed positions will be visited.
        visited_pos = set()
    else:
        # Ensure results is not the empty list.
        visited_pos = set(
            tuple(row) for row in np.array(results)[:, 1:4])

    new_pos = proposed_pos - visited_pos
    return new_pos


# Functions to act on the final entire set of results.
def max_fifth_col(results_arr, scope_obj, initial_position):
    """Given a results array made of [[times], [x_pos], [y_pos], [z_pos],
    [quantity]] format, moves scope stage to the position with the
    maximum value of 'quantity' Recognises when there are multiple maxima
    and: if they are zero, moves to original position, if they are not zero,
    moves to the position of the first maximum."""
    if results_arr[np.argmax(results_arr[:, 4]), 4] == 0:
        print "No maximum detected, moving to original position."
        new_position = initial_position
    else:
        # There my be multiple non-zero maxima - move to the first one in
        # this case.
        new_position = results_arr[np.argmax(results_arr[:, 4]), :][1:4]
    print new_position
    scope_obj.stage.move_to_pos(new_position)
    print "Moved to " + str(new_position)
    return


def to_parmax(results_arr, scope_obj, axis, move=True):
    """Given a results array from move_capture, and an axis to look at,
    fits that axis's positions with the measured quantities to a parabola,
    returns the error and moves the scope_obj stage to the maximum point of the
    parabola. Experiment can only be performed on a single axis."""
    x = results_arr[:, ['x', 'y', 'z'].index(axis) + 1]
    x_range = (np.min(x), np.max(x))
    y = results_arr[:, 4]

    assert np.where(y == np.max(y)) != 0 and \
        np.where(y == np.max(y)) != len(y), 'Extrapolation occurred - ' \
                                            'measure over a wider range.'

    reg = np.polyfit(x, y, 2, full=True)
    coeffs = reg[0]
    residuals = reg[1]

    coeffs_deriv = np.array([2, 1]) * coeffs[:2]    # Simulate differentiation.
    x_stat = -coeffs_deriv[1] / coeffs_deriv[0]
    pred_y = coeffs[0]*x_stat**2 + coeffs[1]*x_stat + coeffs[2]
    new_pos = results_arr[0, 1:4]     # Get the values that stay the same.
    new_pos[['x', 'y', 'z'].index(axis)] = x_stat   # Overlay with max.
    print "new pos parmax", new_pos

    if move:
        scope_obj.stage.move_to_pos(new_pos)
        return
    else:
        return new_pos, pred_y, x_range, residuals, coeffs


class Saturation(Exception):
    """Raise when the gain causes the reading to saturate at 1023."""
    pass


class NonZeroReading(Exception):
    """Raise when the photodiode returns a non-zero reading."""
    pass


class NoisySignal(Exception):
    """Raise when excessive noise has been detected, so operation is
    terminated and raster scan is done instead."""
    pass


class Overlapped(Exception):
    """Raise when all positions to be visited by the do_not_revisit
    generator have already been visited."""
    pass


class ZeroSignal(Exception):
    """Raise when all of the readings are zero."""
    pass
