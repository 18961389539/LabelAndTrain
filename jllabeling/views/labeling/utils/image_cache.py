"""A tiny LRU for the last few decoded images.

Navigating back and forth re-reads and re-decodes the same frame every
time: ``load_file`` reads the bytes, then ``QImage.fromData`` inflates them
again.  A two-entry cache makes "next, then previous" free without holding
a folder's worth of pixels.  The key carries ``(mtime_ns, size)`` so editing
or replacing a file invalidates its entry, and the byte budget keeps a pair
of 16-megapixel frames (~65 MB each) from turning into an unbounded leak.

The cache is deliberately per-process and never persisted: decoded pixels
are cheap to rebuild and expensive to keep honest across sessions.
"""

import os
import os.path as osp
from collections import OrderedDict

#: Two entries cover the prev/next loop that costs the most decode time.
MAX_ENTRIES = 2
#: Never hold more than this in total; large industrial frames are skipped.
MAX_TOTAL_BYTES = 160 * 1024 * 1024
#: A single image larger than this is decoded every time, never cached.
MAX_IMAGE_BYTES = 96 * 1024 * 1024


def cache_key_for_file(path):
    """``(normalized path, mtime_ns, size)`` for an on-disk image, or None."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (
        osp.normcase(osp.abspath(str(path))),
        stat.st_mtime_ns,
        stat.st_size,
    )


class DecodedImageCache:
    """LRU keyed by ``cache_key_for_file``; values are QImage-like objects."""

    def __init__(
        self,
        max_entries=MAX_ENTRIES,
        max_total_bytes=MAX_TOTAL_BYTES,
        max_image_bytes=MAX_IMAGE_BYTES,
    ):
        self.max_entries = max_entries
        self.max_total_bytes = max_total_bytes
        self.max_image_bytes = max_image_bytes
        self._entries = OrderedDict()
        self._total_bytes = 0

    def get(self, key):
        if key is None or key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(self, key, image):
        if key is None or image is None or image.isNull():
            return
        size = int(image.sizeInBytes())
        if size <= 0 or size > self.max_image_bytes:
            # Too large to justify: make sure an older entry for this path
            # does not survive with stale pixels.
            self._discard(key)
            return
        self._discard(key)
        self._entries[key] = image
        self._total_bytes += size
        while (
            len(self._entries) > self.max_entries
            or self._total_bytes > self.max_total_bytes
        ):
            _, evicted = self._entries.popitem(last=False)
            self._total_bytes -= int(evicted.sizeInBytes())

    def _discard(self, key):
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._total_bytes -= int(previous.sizeInBytes())

    def clear(self):
        self._entries.clear()
        self._total_bytes = 0

    def __len__(self):
        return len(self._entries)


_decoded_images = DecodedImageCache()


def get_decoded_image(key):
    """The cached QImage for ``key``, or ``None``."""
    return _decoded_images.get(key)


def put_decoded_image(key, image):
    """Cache ``image`` under ``key`` (both may be None; then it is a no-op)."""
    _decoded_images.put(key, image)


def clear_decoded_images():
    """Drop every entry; tests use this between cases."""
    _decoded_images.clear()
