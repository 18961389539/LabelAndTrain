"""The stale cleanup summary must not hide skipped boxes."""

from anylabeling.views.labeling.utils import smart_stale


def _counts(**overrides):
    counts = {
        "deleted": 0,
        "files": 0,
        "backup_dir": None,
        "skipped_locked": 0,
        "skipped_changed": 0,
        "skipped_unavailable": 0,
    }
    counts.update(overrides)
    return counts


def test_deleted_message_names_the_backup_and_the_skips():
    message, icon, skipped = smart_stale.stale_cleanup_result(
        _counts(
            deleted=2,
            files=1,
            backup_dir="/data/.label_backups/run_1",
            skipped_locked=1,
            skipped_unavailable=2,
        ),
        [1],
    )

    assert "已删除 2 个框" in message
    assert "run_1" in message
    assert "Ctrl+Z" in message
    assert "3 个框被跳过" in message
    assert icon == "copy-green"
    assert skipped == 3


def test_an_all_skipped_selection_says_why_nothing_was_deleted():
    message, icon, skipped = smart_stale.stale_cleanup_result(
        _counts(skipped_changed=2), []
    )

    assert "没有框被删除" in message
    assert "2 个框被跳过" in message
    assert icon == "warning"
    assert skipped == 2


def test_nothing_selected_or_skipped_reads_plainly():
    message, icon, skipped = smart_stale.stale_cleanup_result(_counts(), [])

    assert message == "没有框被删除。"
    assert icon == "warning"
    assert skipped == 0
