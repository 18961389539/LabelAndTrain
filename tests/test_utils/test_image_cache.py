"""The decoded-image LRU: hit, invalidation, eviction and the widget hook."""

import base64

import pytest

from jllabeling.views.labeling.utils import image_cache

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _FakeImage:
    def __init__(self, size, null=False):
        self._size = size
        self._null = null

    def isNull(self):
        return self._null

    def sizeInBytes(self):
        return self._size


@pytest.fixture(autouse=True)
def _empty_cache():
    image_cache.clear_decoded_images()
    yield
    image_cache.clear_decoded_images()


def test_key_tracks_path_mtime_and_size(tmp_path):
    image = tmp_path / "frame.png"
    image.write_bytes(b"one")
    key = image_cache.cache_key_for_file(str(image))
    assert key is not None

    image.write_bytes(b"two-longer")
    changed = image_cache.cache_key_for_file(str(image))
    assert changed != key
    assert (
        image_cache.cache_key_for_file(str(tmp_path / "missing.png")) is None
    )
    assert image_cache.cache_key_for_file("") is None


def test_put_and_get_round_trip():
    image = _FakeImage(10)
    key = ("a", 1, 2)
    image_cache.put_decoded_image(key, image)
    assert image_cache.get_decoded_image(key) is image
    assert image_cache.get_decoded_image(("b", 1, 2)) is None


def test_null_and_oversized_images_are_not_cached():
    image_cache.put_decoded_image(("null", 0, 0), _FakeImage(10, null=True))
    assert image_cache.get_decoded_image(("null", 0, 0)) is None

    huge = _FakeImage(image_cache.MAX_IMAGE_BYTES + 1)
    image_cache.put_decoded_image(("huge", 0, 0), huge)
    assert image_cache.get_decoded_image(("huge", 0, 0)) is None


def test_the_lru_evicts_the_oldest_entry():
    cache = image_cache.DecodedImageCache(max_entries=2)
    cache.put(("old", 0, 0), _FakeImage(10))
    cache.put(("middle", 0, 0), _FakeImage(10))
    cache.get(("old", 0, 0))  # touch: middle becomes the eviction candidate
    cache.put(("new", 0, 0), _FakeImage(10))

    assert cache.get(("old", 0, 0)) is not None
    assert cache.get(("middle", 0, 0)) is None
    assert cache.get(("new", 0, 0)) is not None


def test_the_byte_budget_evicts_before_the_entry_limit():
    cache = image_cache.DecodedImageCache(max_entries=5, max_total_bytes=100)
    cache.put(("one", 0, 0), _FakeImage(60))
    cache.put(("two", 0, 0), _FakeImage(60))

    assert cache.get(("one", 0, 0)) is None
    assert cache.get(("two", 0, 0)) is not None


def test_replacing_a_key_updates_the_byte_total():
    cache = image_cache.DecodedImageCache(max_entries=5, max_total_bytes=100)
    cache.put(("same", 0, 0), _FakeImage(60))
    cache.put(("same", 0, 0), _FakeImage(10))
    cache.put(("other", 0, 0), _FakeImage(60))

    assert len(cache) == 2
    assert cache.get(("same", 0, 0)) is not None


def test_decode_hook_reuses_the_cached_qimage(monkeypatch):
    from jllabeling.views.labeling.label_widget import LabelingWidget

    monkeypatch.setattr(
        "jllabeling.views.labeling.label_widget.utils.img_data_to_qimage",
        lambda data, name=None: _FakeImage(4),
    )
    key = ("frame.png", 1, 2)
    stub = object()

    first, _ = LabelingWidget._decode_image_data(
        stub, PNG_BYTES, "frame.png", cache_key=key
    )
    second, _ = LabelingWidget._decode_image_data(
        stub, PNG_BYTES, "frame.png", cache_key=key
    )

    assert first is second
    assert image_cache.get_decoded_image(key) is first
