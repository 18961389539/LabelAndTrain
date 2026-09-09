from .__base__.yolo import YOLO


class YOLO26(YOLO):
    class Meta(YOLO.Meta):
        widgets = [
            "button_run",
            "input_conf",
            "edit_conf",
        ]
