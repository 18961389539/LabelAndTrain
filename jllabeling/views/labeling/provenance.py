# flake8: noqa
"""Compatibility re-exports for :mod:`jllabeling.core.labels.provenance`."""

from jllabeling.core.labels.provenance import (
    DIGEST_CHARS,
    MODEL_FIELD,
    MODEL_VERSION_FIELD,
    SOURCE_FIELD,
    SOURCE_HUMAN,
    SOURCE_MODEL,
    SOURCE_UNKNOWN,
    SOURCES,
    collect_other_model_shapes,
    describe_shape,
    get_source,
    is_deletable_stale_shape,
    is_from_other_model,
    model_display_name,
    model_identity_label,
    model_of,
    model_version_of,
    resolve_model_path,
    shape_marker,
    shape_points,
    stamp_model_shapes,
    weight_digest,
)
