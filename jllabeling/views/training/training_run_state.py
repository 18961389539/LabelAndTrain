"""The state of one training run, kept in one place.

``UltralyticsDialog`` used to carry these nine fields as loose attributes set
in ``__init__`` and then mutated from five different methods (start, resume,
event handling, dataset preparation, status display). Reading "what is the
current run?" meant reading the whole dialog, and a test that wanted to
exercise the event path had to construct one.

The dialog still exposes the three names its collaborators read
(``current_project_path`` for the export helpers, ``training_status`` and
``_dataset_report`` for the dataset-preparation mixin) as properties, but
every write inside the dialog goes through this object.
"""

from dataclasses import dataclass, field


@dataclass
class TrainingRunState:
    """Everything a run carries between callbacks."""

    #: Directory the run writes into (``<project>/<name>``).
    project_path: str | None = None
    #: idle / preparing / training / completed / error / stop.
    status: str = "idle"
    current_epochs: int = 0
    #: 100 until the args or the first event say otherwise, so the progress
    #: bar can render before any epoch has been reported.
    total_epochs: int = 100
    #: Set when the user picked "resume": the run continues from its own
    #: last.pt, so the tuning comes from the checkpoint, not the form.
    resume_from: str | None = None
    resume_info: dict | None = None
    #: Kept for run_meta.json: the payload file the worker reads is deleted
    #: when the process ends, so this is the only record of the arguments.
    last_train_args: dict = field(default_factory=dict)
    last_dataset_manifest: dict | None = None
    #: Report from the dataset builder (checked / skipped / seed source).
    dataset_report: dict = field(default_factory=dict)

    def forget_previous_run(self):
        """Drop the checkpoint and argument record of the last run."""
        self.resume_from = None
        self.resume_info = None
        self.last_train_args = {}
        self.last_dataset_manifest = None

    def begin_run(self, args, manifest, epochs):
        """Record what the run is about to do, before the worker starts."""
        self.last_train_args = dict(args)
        self.last_dataset_manifest = manifest
        self.total_epochs = epochs

    def report_epoch(self, epoch_rows):
        """Called from the training event stream with the completed rows."""
        self.current_epochs = epoch_rows
