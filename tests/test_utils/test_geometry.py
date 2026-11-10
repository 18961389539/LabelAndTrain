"""Behaviour tests for the array helpers in :mod:`jllabeling.core.labels.geometry`.

These four functions moved out of the view layer without ever having a test
of their own -- they were reached only through the export paths.  The cases
below pin the parts a move can silently break: coordinate order, the
half-open extent of a mask, and the instance numbering.
"""

import numpy as np
import pytest

from jllabeling.core.labels.geometry import (
    masks_to_bboxes,
    rectangle_from_diagonal,
    shape_to_mask,
    shapes_to_label,
)


def test_rectangle_from_diagonal_orders_corners_clockwise():
    corners = rectangle_from_diagonal([[10, 20], [30, 40]])
    assert corners == [[10, 20], [30, 20], [30, 40], [10, 40]]


def test_rectangle_from_diagonal_accepts_any_diagonal_direction():
    """The second point may sit above/left of the first; the corner order is
    still top-left, top-right, bottom-right, bottom-left as written."""
    assert rectangle_from_diagonal([[30, 40], [10, 20]]) == [
        [30, 40],
        [10, 40],
        [10, 20],
        [30, 20],
    ]


def test_rectangle_mask_covers_the_pixels_inside_the_edges():
    # points are (x, y); the mask is indexed [row, column] = [y, x]
    mask = shape_to_mask((8, 8), [[2, 3], [5, 6]], "rectangle")
    assert mask.dtype == bool
    assert mask.shape == (8, 8)
    assert mask[3:7, 2:6].all(), "the inclusive Pillow rectangle must survive"
    assert mask.sum() == 16
    assert not mask[2, 3], "one row above the top edge"
    assert not mask[3, 1], "one column left of the left edge"


def test_circle_mask_radius_comes_from_the_second_point():
    mask = shape_to_mask((21, 21), [[10, 10], [15, 10]], "circle")
    assert mask[10, 10], "the centre is inside"
    assert mask[10, 14] and mask[10, 6]
    assert not mask[10, 16], "a 5px radius must not reach 6px"


def test_polygon_mask_is_the_union_of_its_vertices():
    mask = shape_to_mask((10, 10), [[1, 1], [1, 8], [8, 1]])
    assert mask[2, 2] and mask[1, 1] and mask[8, 1]
    assert not mask[8, 8], "the far corner is outside the triangle"


@pytest.mark.parametrize(
    "shape_type,points",
    [
        ("circle", [[0, 0]]),
        ("rectangle", [[0, 0]]),
        ("rotation", [[0, 0], [1, 1]]),
        ("quadrilateral", [[0, 0], [1, 1]]),
        ("line", [[0, 0]]),
        ("point", [[0, 0], [1, 1]]),
    ],
)
def test_wrong_point_count_for_a_shape_type_is_an_assertion(
    shape_type, points
):
    with pytest.raises(AssertionError):
        shape_to_mask((4, 4), points, shape_type)


def test_masks_to_bboxes_uses_exclusive_max():
    masks = np.zeros((2, 6, 6), dtype=bool)
    masks[0, 1:4, 2:5] = True
    masks[1, 0:2, 0:6] = True
    bboxes = masks_to_bboxes(masks).tolist()
    assert bboxes == [[1.0, 2.0, 4.0, 5.0], [0.0, 0.0, 2.0, 6.0]]


def test_masks_to_bboxes_rejects_the_wrong_rank():
    with pytest.raises(ValueError, match="ndim"):
        masks_to_bboxes(np.zeros((4, 4), dtype=bool))


def test_masks_to_bboxes_rejects_a_non_bool_mask():
    with pytest.raises(ValueError, match="dtype"):
        masks_to_bboxes(np.zeros((1, 4, 4), dtype=np.uint8))


def test_shapes_to_label_numbers_instances_per_group_id():
    shapes = [
        {
            "label": "cat",
            "points": [[0, 0], [3, 3]],
            "group_id": 7,
            "shape_type": "rectangle",
        },
        {
            "label": "cat",
            "points": [[5, 5], [8, 8]],
            "group_id": 8,
            "shape_type": "rectangle",
        },
        {
            "label": "cat",
            "points": [[0, 0], [3, 3]],
            "group_id": 7,
            "shape_type": "rectangle",
        },
    ]
    cls, ins = shapes_to_label((10, 10), shapes, {"cat": 1})
    assert cls.dtype == np.int32 and ins.dtype == np.int32
    assert set(np.unique(cls)) == {0, 1}, "0 is the background class"
    assert set(np.unique(ins)) == {0, 1, 2}, "0 is the background instance"
    assert ins[0, 0] == ins[3, 3], "the same group_id is one instance"
    assert ins[0, 0] != ins[5, 5]
