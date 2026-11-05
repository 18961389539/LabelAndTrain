"""Undo history that survives a file switch.

``canvas.reset_state()`` used to empty both stacks with the comment "undo
history does not survive a file switch", which is a plain statement of fact
rather than a design: the annotator pays for it the moment a wrong edit is
noticed after moving on. The history itself is small and cheap to keep, so
the stacks are banked per image and restored when that image comes back.

Two things make the restored stack behave the way the annotator expects:

* ``canvas.py`` stores the state *after* each edit, so ``undo()`` pops the
  top (the current state), discards it, and restores the one below. When a
  bank is restored, ``load_shapes()`` is about to push the file's on-disk
  state onto the stack -- which is the banked top, since an auto-save wrote
  it. The banked top is dropped on restore, otherwise the first Ctrl+Z would
  restore the state that is already on screen and read as "undo is broken".
* Buckets are bounded (``MAX_BUCKETS``) and evicted least-recently-used.
  This is a convenience for "I was just in that image"; the durable answer
  to "I broke this an hour ago" is the session snapshot on disk
  (``utils/session_snapshot.py``), which has no such bound.
"""

from collections import OrderedDict

#: How many images keep a live undo history at a time.
MAX_BUCKETS = 20


class ShapeHistoryStore:
    """The undo/redo stacks, keyed by the image they belong to."""

    def __init__(self):
        # Named *_stack because ``undo``/``redo`` are the methods that move
        # between the two; an attribute called ``undo`` would shadow one.
        self.undo_stack = []
        self.redo_stack = []
        self.key = None
        self._buckets = OrderedDict()

    # -- the stacks ------------------------------------------------------

    def push(self, snapshot, limit):
        """Record a state, drop the oldest beyond ``limit``, kill redo."""
        if len(self.undo_stack) > limit:
            del self.undo_stack[: len(self.undo_stack) - limit - 1]
        self.undo_stack.append(snapshot)
        # A new edit invalidates any pending redo branch.
        self.redo_stack.clear()

    def can_undo(self):
        # Two states are needed: the current one and the one before it.
        return len(self.undo_stack) >= 2

    def can_redo(self):
        return len(self.redo_stack) > 0

    def undo(self):
        """Return the state to show, keeping the discarded one for redo."""
        if not self.can_undo():
            return None
        self.redo_stack.append(self.undo_stack.pop())
        return self.undo_stack.pop()

    def redo(self):
        if not self.can_redo():
            return None
        return self.redo_stack.pop()

    # -- which image they belong to --------------------------------------

    def enter(self, key):
        """Point the live stacks at ``key``, restoring what was banked."""
        if self.key is not None and self.key != key:
            self.leave()
        if self.key == key:
            return
        self.key = key
        banked = self._buckets.pop(key, None)
        if banked is None:
            self.undo_stack, self.redo_stack = [], []
        else:
            self.undo_stack, self.redo_stack = banked
            if self.undo_stack:
                # load_shapes() is about to push this very state back.
                self.undo_stack.pop()
        self._buckets[key] = (self.undo_stack, self.redo_stack)

    def leave(self):
        """Bank the live stacks under the current key and clear them."""
        if self.key is not None:
            self._buckets[self.key] = (self.undo_stack, self.redo_stack)
            self._buckets.move_to_end(self.key)
            while len(self._buckets) > MAX_BUCKETS:
                self._buckets.popitem(last=False)
        self.key = None
        self.undo_stack = []
        self.redo_stack = []


class ShapeHistoryMixin:
    """Keeps the attribute names Canvas has always exposed.

    ``shapes_backups`` / ``shapes_redo_backups`` are read, mutated *and*
    assigned by callers outside the canvas (the label editor, the rotation
    mixin, the widget's undo/redo reload path), so the store is reached
    through properties rather than by renaming the attributes.
    """

    @property
    def shapes_backups(self):
        return self.shape_history.undo_stack

    @shapes_backups.setter
    def shapes_backups(self, value):
        self.shape_history.undo_stack = list(value)

    @property
    def shapes_redo_backups(self):
        return self.shape_history.redo_stack

    @shapes_redo_backups.setter
    def shapes_redo_backups(self, value):
        self.shape_history.redo_stack = list(value)
