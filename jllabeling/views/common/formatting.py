"""Small, testable formatters shared by user-facing dialogs."""

UNITS = ("B", "KB", "MB", "GB", "TB")


def format_size(num_bytes):
    """Adaptive byte size: ``512 B``, ``1.5 KB``, ``2.3 GB``.

    The training cleanup message used to print everything in MB, so a 512 KB
    leftover read as ``0.0 MB``.
    """
    size = float(max(0, num_bytes))
    if size < 1024:
        return f"{int(size)} B"
    for unit in UNITS[1:]:
        size /= 1024
        if size < 1024 or unit == UNITS[-1]:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"
