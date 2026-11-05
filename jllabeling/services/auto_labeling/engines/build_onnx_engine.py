import os
import onnx
import onnxruntime as ort


class OnnxBaseModel:
    def __init__(
        self, model_path, device_type: str = "cpu", log_severity_level: int = 3
    ):
        self.sess_opts = ort.SessionOptions()
        self.sess_opts.log_severity_level = log_severity_level
        if "OMP_NUM_THREADS" in os.environ:
            self.sess_opts.inter_op_num_threads = int(
                os.environ["OMP_NUM_THREADS"]
            )

        self.providers = ["CPUExecutionProvider"]
        head, _, tail = str(device_type).strip().lower().partition(":")
        gpu_card = None
        if head == "gpu":
            # "gpu" or "gpu:N" both land on CUDA; the index picks the card.
            # Anything GPU-ish that is not a number keeps card 0 rather
            # than failing the session over a malformed string.
            gpu_card = int(tail) if tail.isdigit() else 0

        if gpu_card is not None:
            # ``(name, options)`` tuples are the documented way to pass a
            # device id; older wheels that reject them still get the plain
            # provider name (card 0) instead of a hard failure.
            try:
                self.ort_session = ort.InferenceSession(
                    model_path,
                    providers=[
                        ("CUDAExecutionProvider", {"device_id": gpu_card})
                    ],
                    sess_options=self.sess_opts,
                )
                self.providers = [
                    ("CUDAExecutionProvider", {"device_id": gpu_card})
                ]
                self.model_path = model_path
                return
            except (TypeError, ValueError):
                self.providers = ["CUDAExecutionProvider"]

        self.ort_session = ort.InferenceSession(
            model_path,
            providers=self.providers,
            sess_options=self.sess_opts,
        )
        self.model_path = model_path

    def get_ort_inference(
        self, blob=None, inputs=None, extract=True, squeeze=False
    ):
        if inputs is None:
            inputs = self.get_input_name()
            outs = self.ort_session.run(None, {inputs: blob})
        else:
            outs = self.ort_session.run(None, inputs)
        if extract:
            outs = outs[0]
        if squeeze:
            outs = outs.squeeze(axis=0)
        return outs

    def get_input_name(self):
        return self.ort_session.get_inputs()[0].name

    def get_input_shape(self):
        return self.ort_session.get_inputs()[0].shape

    def get_output_name(self):
        return [out.name for out in self.ort_session.get_outputs()]

    def get_metadata_info(self, field):
        model = onnx.load(self.model_path)
        metadata = model.metadata_props
        for prop in metadata:
            if prop.key == field:
                return prop.value
        return None
