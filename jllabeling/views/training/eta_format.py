"""Remaining-time text for a running training job."""


def format_remaining(seconds, tr):
    """Human wording for a positive estimate; ``tr`` is the caller's tr()."""
    if seconds < 60:
        return tr("剩余不到 1 分钟")
    minutes = max(1, int(round(seconds / 60)))
    if minutes < 60:
        return tr("约剩余 %1 分钟").replace("%1", str(minutes))
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return (
            tr("约剩余 %1 小时 %2 分钟")
            .replace("%1", str(hours))
            .replace("%2", str(minutes))
        )
    return tr("约剩余 %1 小时").replace("%1", str(hours))
