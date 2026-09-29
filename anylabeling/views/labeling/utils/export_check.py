"""What an export is about to write -- and what it is about to drop.

The run already reports what it did, skips included, in the summary popup.
That is one batch too late for the two failures that cannot be taken back
once the first file has been written:

- shapes whose label is not in the exported class list, dropped silently and
  file after file;
- a label file that cannot be read at all, which raises out of the run and
  leaves a half-written output directory behind.

Both are detectable before the run starts, so this module gathers them in one
pass over the label files and hands back a plain dict.

The same dict is what :func:`write_manifest` drops into the export directory,
so "how was this batch made" stays answerable afterwards: the class list and
where it came from, the filters that were on, the shape counts the run
reported, and the state of the source data it read.

Deliberately self-contained rather than calling ``data_audit.audit_dataset``:
the export reads every label file anyway, so reusing the audit would mean a
second full pass (plus the uncertainty scoring the audit does) for the same
three answers. :mod:`tests.test_utils.test_export_check` pins the two
implementations to the same verdict on a shared fixture instead, so they
cannot drift apart quietly.
"""

import json
import os.path as osp
from datetime import datetime

from PyQt6.QtCore import QCoreApplication

from anylabeling.views.labeling.logger import logger

#: Written next to the exported labels when the dialog's record box is ticked.
MANIFEST_NAME = "export_manifest.json"


def _tr(text):
    """Translate from a module-level function.

    ``self.tr`` in a module-level function is dropped by pylupdate6, which is
    how the export dialogs ended up with untranslated strings; an explicit
    context keeps these extractable.
    """
    return QCoreApplication.translate("LabelingWidget", text)


def scan_source(image_list, label_file_for):
    """One pass over the label files behind ``image_list``.

    ``label_file_for`` maps an image path to its label file, the same callable
    the export run uses, so the check and the run look at identical files.

    Returns a dict with what an annotator can act on afterwards:
    ``label_counts`` (label -> shape count, empty files excluded),
    ``unlabeled`` (images with no label file), ``empty`` (label file with no
    shapes -- usually a deliberate negative sample) and ``corrupted`` (label
    file paths that could not be read).
    """
    label_counts = {}
    unlabeled = 0
    empty = 0
    corrupted = []
    for image_file in image_list:
        label_file = label_file_for(image_file)
        try:
            with open(label_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            unlabeled += 1
            continue
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            logger.warning(f"Export check: cannot read {label_file}: {e}")
            corrupted.append(label_file)
            continue
        if not isinstance(data, dict) or "shapes" not in data:
            # Same verdict as data_audit's: a json without a shape list is not
            # an empty label, it is a file the converter will raise on
            # (``data["shapes"]``), which is what "corrupted" has to mean here.
            corrupted.append(label_file)
            continue
        shapes = data.get("shapes") or []
        if not shapes:
            empty += 1
            continue
        for shape in shapes:
            # A shape whose label was cleared still counts: the converter
            # drops it too (``"" not in classes``), so leaving it out here
            # would make the check blind to a real drop path.
            label = (shape or {}).get("label") or ""
            label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "images": len(image_list),
        "label_counts": label_counts,
        "unlabeled": unlabeled,
        "empty": empty,
        "corrupted": corrupted,
    }


def check_export_readiness(image_list, label_file_for, classes):
    """Fold :func:`scan_source` into "what will this run lose".

    ``unknown_labels`` is the part only the export can know: a label the
    annotator drew that the chosen class list does not contain. The converter
    counts those per shape (``label not in classes: X``) and moves on, so a
    mismatch between the annotated labels and a hand-picked ``classes.txt``
    shows up as a quietly thinner dataset.
    """
    readiness = scan_source(image_list, label_file_for)
    known = {str(name) for name in (classes or [])}
    unknown = {
        label: count
        for label, count in readiness["label_counts"].items()
        if label not in known
    }
    readiness["unknown_labels"] = unknown
    readiness["unknown_shapes"] = sum(unknown.values())
    return readiness


def is_blocking(readiness):
    """Findings that cost data if the run starts anyway.

    An unknown label is dropped shape by shape without an error; an unreadable
    label file raises out of the run partway through. Everything else
    :func:`scan_source` finds -- no label file, an empty one -- is either
    legitimate (negative samples train as background) or already named in the
    run's own summary, so it must not stand in the way of an export.
    """
    return bool(readiness["unknown_shapes"] or readiness["corrupted"])


def format_readiness(readiness):
    """Dialog body: one headline per finding, then the entries under it.

    Returns an empty list when there is nothing worth interrupting for, so the
    caller can treat "no lines" as "do not show a dialog".
    """
    lines = []

    unknown = readiness["unknown_labels"]
    if unknown:
        lines.append(
            _tr("%d 个标注的类别不在导出类别表里，导出时会被逐条跳过。")
            % readiness["unknown_shapes"]
        )
        for label, count in sorted(
            unknown.items(), key=lambda item: (-item[1], item[0])
        ):
            lines.append(f"    {label or _tr('（未命名的标注）')}：{count}")

    corrupted = readiness["corrupted"]
    if corrupted:
        lines.append(
            _tr(
                "%d 个标注文件无法读取，导出会在它们上中断并留下不完整的目录。"
            )
            % len(corrupted)
        )
        for path in corrupted:
            lines.append(f"    {osp.basename(path)}")

    return lines


def build_manifest(
    *,
    mode,
    version,
    image_dir,
    label_dir,
    classes,
    classes_source,
    filters,
    result,
    readiness,
    generated_at=None,
):
    """The export's own record of itself, as a JSON-serializable dict.

    Everything here is a fact of this run: the class list and where it came
    from decide what a label *means* (the index in this list is the id in the
    ``.txt`` files), and the filters decide what was left out. Without that,
    a directory of ``.txt`` files is not reproducible a month later.
    """
    return {
        "generated_at": generated_at
        or datetime.now().isoformat(timespec="seconds"),
        "tool": "LabelingAndTrain",
        "version": version,
        "mode": mode,
        "source": {
            "image_dir": image_dir,
            "label_dir": label_dir,
            "images": readiness["images"],
        },
        "classes": {
            "source": classes_source,
            "count": len(classes or []),
            "names": list(classes or []),
        },
        "filters": dict(filters),
        "result": dict(result),
        "source_data": {
            "no_label_file": readiness["unlabeled"],
            "empty_labels": readiness["empty"],
            "unreadable_label_files": list(readiness["corrupted"]),
            "labels_not_in_classes": dict(readiness["unknown_labels"]),
        },
    }


def write_manifest(save_path, manifest):
    """Drop the manifest into the export directory.

    Returns the written path, or ``None`` when it could not be written: the
    export itself has already succeeded by this point, and a record that
    cannot be stored must not turn that into a failure the annotator sees.
    """
    target = osp.join(save_path, MANIFEST_NAME)
    try:
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as e:
        logger.warning(f"Could not write the export manifest: {e}")
        return None
    return target
