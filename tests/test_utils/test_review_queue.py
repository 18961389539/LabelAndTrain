import unittest

from anylabeling.views.labeling.utils.review_queue import (
    next_review_target,
    queue_position,
)


class TestReviewQueue(unittest.TestCase):

    QUEUE = ["b.jpg", "a.jpg", "c.jpg"]

    def test_empty_queue(self):
        self.assertEqual(next_review_target([], None), (None, None))

    def test_forward_from_unknown_current_goes_to_top(self):
        self.assertEqual(next_review_target(self.QUEUE, "z.jpg"), ("b.jpg", 0))

    def test_backward_from_unknown_current_goes_to_bottom(self):
        self.assertEqual(
            next_review_target(self.QUEUE, "z.jpg", forward=False),
            ("c.jpg", 2),
        )

    def test_forward_wraps_at_end(self):
        path, index = next_review_target(self.QUEUE, "c.jpg")
        self.assertEqual((path, index), ("b.jpg", 0))

    def test_forward_without_wrap_stops(self):
        path, index = next_review_target(self.QUEUE, "c.jpg", wrap=False)
        self.assertEqual((path, index), (None, None))

    def test_backward_goes_up(self):
        self.assertEqual(next_review_target(self.QUEUE, "a.jpg", forward=False),
                         ("b.jpg", 0))

    def test_queue_position(self):
        self.assertEqual(queue_position(self.QUEUE, "a.jpg"), 1)
        self.assertIsNone(queue_position(self.QUEUE, "zz.jpg"))
        self.assertIsNone(queue_position([], "a.jpg"))


if __name__ == "__main__":
    unittest.main()