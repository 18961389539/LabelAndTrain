# flake8: noqa
"""Compatibility re-exports for :mod:`jllabeling.core.labels.schema`."""

from jllabeling.app_info import __version__
from jllabeling.core.labels.schema import (
    REVIEW_CONFIRMED,
    REVIEW_NOTE_FIELD,
    REVIEW_REJECTED,
    REVIEW_STATES,
    REVIEW_UNCHECKED,
    XLABEL_BASIC_FIELDS,
    create_xlabel_template,
    is_review_confirmed,
    review_state_of,
)
