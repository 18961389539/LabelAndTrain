from typing import Any, Dict, List, Optional

from anylabeling.app_info import __version__

REVIEW_UNCHECKED = "unchecked"
REVIEW_CONFIRMED = "confirmed"
REVIEW_REJECTED = "rejected"
REVIEW_STATES = (REVIEW_UNCHECKED, REVIEW_CONFIRMED, REVIEW_REJECTED)

#: Field the rework reason is written under. A first-class template field
#: (not ``other_data``) so it sits next to ``reviewed_at`` in the JSON head:
#: the file-list scanner reads only the head, and a reason parked after
#: ``shapes`` would force a full parse of every rejected file.
REVIEW_NOTE_FIELD = "review_note"

XLABEL_BASIC_FIELDS = [
    "version",
    "flags",
    "checked",
    "review_state",
    "reviewed_at",
    REVIEW_NOTE_FIELD,
    "shapes",
    "imagePath",
    "imageData",
    "imageHeight",
    "imageWidth",
]


def review_state_of(payload: Dict[str, Any]) -> str:
    """Explicit review state wins; legacy files fall back on ``checked``."""
    state = payload.get("review_state")
    if state in REVIEW_STATES:
        return state
    if payload.get("checked") is True:
        return REVIEW_CONFIRMED
    return REVIEW_UNCHECKED


def is_review_confirmed(state: str) -> bool:
    return state == REVIEW_CONFIRMED


def create_xlabel_template(
    version: str = __version__,
    flags: Optional[Dict[str, Any]] = None,
    checked: bool = False,
    review_state: str = REVIEW_UNCHECKED,
    reviewed_at: Optional[str] = None,
    review_note: Optional[str] = None,
    shapes: Optional[List[Dict[str, Any]]] = None,
    image_path: str = "",
    image_data: Optional[bytes] = None,
    image_height: int = -1,
    image_width: int = -1,
) -> Dict[str, Any]:
    return {
        "version": version,
        "flags": flags if flags is not None else {},
        "checked": checked,
        "review_state": review_state,
        "reviewed_at": reviewed_at,
        REVIEW_NOTE_FIELD: review_note,
        "shapes": shapes if shapes is not None else [],
        "imagePath": image_path,
        "imageData": image_data,
        "imageHeight": image_height,
        "imageWidth": image_width,
    }
