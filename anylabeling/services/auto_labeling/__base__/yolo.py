import ast
import os
import cv2
import numpy as np
from typing import Union, Tuple, List
from argparse import Namespace

from PyQt6 import QtCore
from PyQt6.QtCore import QCoreApplication

from anylabeling.views.common.device_manager import get_preferred_device
from anylabeling.views.labeling.shape import Shape
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.opencv import qt_img_to_rgb_cv_img
from ..model import Model
from ..engines import OnnxBaseModel
from ..types import AutoLabelingResult
from ..utils import (
    letterbox,
    scale_boxes,
    scale_coords,
    point_in_bbox,
    masks2segments,
    xyxy2xywh,
    non_max_suppression_v5,
    non_max_suppression_v8,
    non_max_suppression_end2end,
)


class YOLO(Model):
    class Meta:
        required_config_names = [
            "type",
            "name",
            "display_name",
            "model_path",
        ]
        widgets = [
            "button_run",
            "input_conf",
            "edit_conf",
            "input_iou",
            "edit_iou",
            "toggle_preserve_existing_annotations",
            "button_classes_filter",
        ]
        output_modes = {
            "point": QCoreApplication.translate("Model", "Point"),
            "polygon": QCoreApplication.translate("Model", "Polygon"),
            "rectangle": QCoreApplication.translate("Model", "Rectangle"),
        }
        default_output_mode = "rectangle"

    def __init__(self, model_config, on_message) -> None:
        # Run the parent class's init method
        super().__init__(model_config, on_message)

        model_abs_path = self.get_model_abs_path(self.config, "model_path")
        if not model_abs_path or not os.path.isfile(model_abs_path):
            raise FileNotFoundError(
                QCoreApplication.translate(
                    "Model",
                    f"Could not download or initialize {self.config['type']} model.",
                )
            )

        self.engine = self.config.get("engine", "ort")
        if self.engine.lower() == "dnn":
            from ..engines import DnnBaseModel

            self.net = DnnBaseModel(model_abs_path, get_preferred_device())
            self.input_width = self.config.get("input_width", 640)
            self.input_height = self.config.get("input_height", 640)
        elif self.engine.lower() == "trt":
            from ..engines import TrtBaseModel

            self.net = TrtBaseModel(model_abs_path, get_preferred_device())
            (
                _,
                _,
                self.input_height,
                self.input_width,
            ) = self.net.get_input_shape()
            if not isinstance(self.input_width, int):
                self.input_width = self.config.get("input_width", -1)
            if not isinstance(self.input_height, int):
                self.input_height = self.config.get("input_height", -1)
        else:
            self.net = OnnxBaseModel(model_abs_path, get_preferred_device())
            (
                _,
                _,
                self.input_height,
                self.input_width,
            ) = self.net.get_input_shape()
            if not isinstance(self.input_width, int):
                self.input_width = self.config.get("input_width", -1)
            if not isinstance(self.input_height, int):
                self.input_height = self.config.get("input_height", -1)

        self.replace = True
        self.model_type = self.config["type"]
        self.classes = self.config.get("classes", [])
        self.stride = self.config.get("stride", 32)
        self.anchors = self.config.get("anchors", None)
        self.agnostic = self.config.get("agnostic", False)
        self.show_boxes = self.config.get("show_boxes", False)
        self.epsilon_factor = self.config.get("epsilon_factor", 0.005)
        self.iou_thres = self.config.get("iou_threshold", 0.45)
        self.conf_thres = self.config.get("conf_threshold", 0.25)
        self.max_det = self.config.get("max_det", 300)
        self.filter_classes = self.config.get("filter_classes", None)
        self.nc = len(self.classes)
        self.input_shape = (self.input_height, self.input_width)
        if self.anchors:
            self.nl = len(self.anchors)
            self.na = len(self.anchors[0]) // 2
            self.grid = [np.zeros(1)] * self.nl
            self.stride = (
                np.array([self.stride // 4, self.stride // 2, self.stride])
                if not isinstance(self.stride, list)
                else np.array(self.stride)
            )
            self.anchor_grid = np.asarray(
                self.anchors, dtype=np.float32
            ).reshape(self.nl, -1, 2)
        if self.filter_classes:
            self.filter_classes = [
                i
                for i, item in enumerate(self.classes)
                if item in self.filter_classes
            ]

        if self.model_type in [
            "yolov8",
            "yolo26",
        ]:
            self.task = "det"
        if self.model_type in [
            "yolov8_seg",
            "yolo26_seg",
        ]:
            self.task = "seg"
        elif self.model_type in [
            "yolo26_pose",
        ]:
            self.task = "pose"
            self.keypoint_name = {}
            self.show_boxes = True
            self.has_visible = self.config.get("has_visible", True)
            self.kpt_thres = self.config.get("kpt_threshold", 0.1)
            self.classes = self.config.get("classes", {})
            for class_name, keypoints in self.classes.items():
                self.keypoint_name[class_name] = keypoints
            self.classes = list(self.classes.keys())
            kpt_shape_str = self.net.get_metadata_info("kpt_shape")
            if kpt_shape_str is not None:
                try:
                    kpt_shape = ast.literal_eval(kpt_shape_str)
                except (SyntaxError, ValueError, TypeError) as e:
                    raise ValueError(
                        f"Invalid 'kpt_shape' metadata in model "
                        f"'{model_abs_path}': {kpt_shape_str!r}"
                    ) from e
                if (
                    not isinstance(kpt_shape, (list, tuple))
                    or len(kpt_shape) != 2
                    or any(
                        type(value) is not int or value <= 0
                        for value in kpt_shape
                    )
                    or kpt_shape[1] not in (2, 3)
                ):
                    raise ValueError(
                        f"Invalid 'kpt_shape' metadata in model "
                        f"'{model_abs_path}': {kpt_shape_str!r}"
                    )
                self.kpt_shape = kpt_shape
            else:
                self.kpt_shape = None
            if self.kpt_shape is None:
                max_kpts = max(
                    len(num_kpts) for num_kpts in self.keypoint_name.values()
                )
                visible_flag = 3 if self.has_visible else 2
                self.kpt_shape = [max_kpts, visible_flag]

        if isinstance(self.classes, dict):
            self.classes = list(self.classes.values())

    def set_auto_labeling_conf(self, value):
        """set auto labeling confidence threshold"""
        if value > 0:
            self.conf_thres = value

    def set_auto_labeling_iou(self, value):
        """set auto labeling iou threshold"""
        if value > 0:
            self.iou_thres = value

    def set_auto_labeling_preserve_existing_annotations_state(self, state):
        """Toggle the preservation of existing annotations based on the checkbox state."""
        self.replace = not state

    def set_auto_labeling_filter_classes(self, class_names: List[str]) -> None:
        """
        Updates the active class filter from a list of class names.

        Args:
            class_names (List[str]): Selected class names. An empty list
                or a selection of all classes disables the filter (None).
        """
        if not class_names or len(class_names) == len(self.classes):
            self.filter_classes = None
        else:
            self.filter_classes = [
                i for i, c in enumerate(self.classes) if c in class_names
            ]

    def inference(self, blob):
        if self.engine == "dnn" and self.task in ["det", "seg", "track"]:
            outputs = self.net.get_dnn_inference(blob=blob, extract=False)
            if self.task == "det" and not isinstance(outputs, (tuple, list)):
                outputs = [outputs]
        else:
            outputs = self.net.get_ort_inference(blob=blob, extract=False)
        return outputs

    def preprocess(self, image, upsample_mode="letterbox"):
        self.img_height, self.img_width = image.shape[:2]
        # Upsample
        if upsample_mode == "resize":
            input_img = cv2.resize(
                image, (self.input_width, self.input_height)
            )
        elif upsample_mode == "letterbox":
            input_img = letterbox(image, self.input_shape)[0]
        elif upsample_mode == "centercrop":
            m = min(self.img_height, self.img_width)
            top = (self.img_height - m) // 2
            left = (self.img_width - m) // 2
            cropped_img = image[top : top + m, left : left + m]
            input_img = cv2.resize(
                cropped_img, (self.input_width, self.input_height)
            )
        elif upsample_mode == "scaleresize":
            ratio_width = self.input_shape[1] / self.img_width
            ratio_height = self.input_shape[0] / self.img_height
            input_img = cv2.resize(
                image,
                (0, 0),
                fx=ratio_width,
                fy=ratio_height,
                interpolation=cv2.INTER_LINEAR,
            )
        # Transpose
        input_img = input_img.transpose(2, 0, 1)
        # Expand
        input_img = input_img[np.newaxis, :, :, :].astype(np.float32)
        # Contiguous
        input_img = np.ascontiguousarray(input_img)
        # Norm
        blob = input_img / 255.0
        return blob

    def postprocess(self, preds):
        if self.model_type in [
            "yolov8",
            "yolov8_seg",
            "yolov8_sam2",
        ]:
            p = non_max_suppression_v8(
                preds[0],
                task=self.task,
                conf_thres=self.conf_thres,
                iou_thres=self.iou_thres,
                classes=self.filter_classes,
                agnostic=self.agnostic,
                multi_label=False,
                max_det=self.max_det,
                nc=self.nc,
            )
        elif self.model_type in [
            "yolo26",
            "yolo26_seg",
            "yolo26_pose",
        ]:
            # End-to-end models: determine nm for seg task, nkpt/ndim for pose task
            nm = 0
            nkpt = 0
            ndim = 3
            if self.task == "seg":
                proto = preds[1][0] if len(preds[1].shape) == 4 else preds[1]
                nm = proto.shape[0]
                self.mask_height, self.mask_width = proto.shape[1:]
            elif self.task == "pose":
                nkpt = self.kpt_shape[0]
                ndim = self.kpt_shape[1]
            p = non_max_suppression_end2end(
                preds[0],
                task=self.task,
                conf_thres=self.conf_thres,
                classes=self.filter_classes,
                max_det=self.max_det,
                nm=nm,
                nkpt=nkpt,
                ndim=ndim,
            )
        masks, keypoints = None, None
        img_shape = (self.img_height, self.img_width)
        is_end2end = self.model_type in [
            "yolo26",
            "yolo26_seg",
            "yolo26_pose",
        ]
        if self.task == "seg" and not is_end2end:
            proto = preds[1][-1] if len(preds[1]) == 3 else preds[1]
            self.mask_height, self.mask_width = proto.shape[2:]
        for i, pred in enumerate(p):
            if self.task == "seg":
                if np.size(pred) == 0:
                    continue
                if is_end2end:
                    # End-to-end seg: pred format is [x1,y1,x2,y2,score,class,mask_coeffs...]
                    proto = (
                        preds[1][0] if len(preds[1].shape) == 4 else preds[1]
                    )
                    masks = self.process_mask(
                        proto,
                        pred[:, 6:],
                        pred[:, :4],
                        self.input_shape,
                        upsample=True,
                    )
                    pred[:, :4] = scale_boxes(
                        self.input_shape, pred[:, :4], img_shape
                    )
                else:
                    masks = self.process_mask(
                        proto[i],
                        pred[:, 6:],
                        pred[:, :4],
                        self.input_shape,
                        upsample=True,
                    )  # HWC
            else:
                pred[:, :4] = scale_boxes(
                    self.input_shape, pred[:, :4], img_shape
                )

        if self.task == "pose":
            pred_kpts = pred[:, 6:]
            if pred.shape[0] != 0:
                pred_kpts = pred_kpts.reshape(
                    pred_kpts.shape[0], *self.kpt_shape
                )
            bbox = pred[:, :4]
            conf = pred[:, 4]
            clas = pred[:, 5]
            keypoints = scale_coords(
                self.input_shape, pred_kpts, self.image_shape
            )
        else:
            bbox = pred[:, :4]
            conf = pred[:, 4]
            clas = pred[:, 5]
        return (bbox, clas, conf, masks, keypoints)

    def predict_shapes(self, image, image_path=None):
        """
        Predict shapes from image
        """

        if image is None:
            return []

        try:
            image = qt_img_to_rgb_cv_img(image, image_path)
        except Exception as e:  # noqa
            logger.warning("Could not inference model")
            logger.warning(e)
            return []
        self.image_shape = image.shape
        blob = self.preprocess(image)
        outputs = self.inference(blob)
        boxes, class_ids, scores, masks, keypoints = self.postprocess(outputs)

        points = [[] for _ in range(len(boxes))]
        if self.task == "seg" and masks is not None:
            points = [
                scale_coords(self.input_shape, x, image.shape, normalize=False)
                for x in masks2segments(masks, self.epsilon_factor)
            ]
        track_ids = [[] for _ in range(len(boxes))]
        if keypoints is None:
            keypoints = [[] for _ in range(len(boxes))]

        shapes = []
        for i, (box, class_id, score, point, keypoint, track_id) in enumerate(
            zip(boxes, class_ids, scores, points, keypoints, track_ids)
        ):
            if self.task == "det" or self.show_boxes:
                shape = self.create_rectangle_shape(
                    box, score, i, class_id, track_id
                )
                shapes.append(shape)
            if self.task == "seg":
                if len(point) < 3:
                    continue
                shape = self.create_polygon_shape(
                    point, score, class_id, track_id
                )
                shapes.append(shape)
            if self.task == "pose":
                label = str(self.classes[int(class_id)])
                keypoint_name = self.keypoint_name[label]
                for j, kpt in enumerate(keypoint):
                    if len(kpt) == 2:
                        x, y, s = *kpt, 1.0
                    else:
                        x, y, s = kpt
                    inside_flag = point_in_bbox((x, y), box)
                    if (
                        (x == 0 and y == 0)
                        or not inside_flag
                        or s < self.kpt_thres
                    ):
                        continue
                    shape = self.create_keypoint_shape(
                        (x, y), keypoint_name, s, j, i, track_id
                    )
                    shapes.append(shape)
        result = AutoLabelingResult(shapes, replace=self.replace)

        return result

    def create_rectangle_shape(
        self,
        box: np.ndarray,
        score: Union[float, str],
        pose_id: Union[int, str],
        class_id: Union[int, str],
        track_id: Union[int, str],
    ) -> Shape:
        """
        Create a rectangle shape from a bounding box.

        Args:
            box (np.ndarray): A numpy array of shape (4,) representing the bounding box.
                The format of the bounding box is [x1, y1, x2, y2].
            score (Union[float, str]): The confidence score of the bounding box.
            pose_id (Union[int, str]): The pose ID of the bounding box.
            class_id (Union[int, str]): The class ID of the bounding box.
            track_id (Union[int, str]): The track ID of the bounding box.

        Returns:
            (Shape): A Shape object representing the rectangle.
        """
        x1, y1, x2, y2 = box.astype(float)
        shape = Shape(flags={})
        shape.add_point(QtCore.QPointF(x1, y1))
        shape.add_point(QtCore.QPointF(x2, y1))
        shape.add_point(QtCore.QPointF(x2, y2))
        shape.add_point(QtCore.QPointF(x1, y2))
        shape.shape_type = "rectangle"
        shape.closed = True
        shape.label = str(self.classes[int(class_id)])
        shape.score = float(score)
        shape.selected = False
        if self.task == "pose":
            shape.group_id = int(pose_id)
        return shape

    def create_polygon_shape(
        self,
        point: np.ndarray,
        score: Union[float, str],
        class_id: Union[int, str],
        track_id: Union[int, str],
    ) -> Shape:
        """
        Create a polygon shape from a list of points.

        Args:
            point (np.ndarray): A numpy array of shape (n, 2) representing the points of the polygon.
            score (Union[float, str]): The confidence score of the polygon.
            class_id (Union[int, str]): The class ID of the polygon.
            track_id (Union[int, str]): The track ID of the polygon.

        Returns:
            shape (Shape): A Shape object representing the polygon.
        """
        shape = Shape(flags={})
        for p in point:
            shape.add_point(QtCore.QPointF(int(p[0]), int(p[1])))
        shape.shape_type = "polygon"
        shape.closed = True
        shape.label = str(self.classes[int(class_id)])
        shape.score = float(score)
        shape.selected = False
        return shape

    def create_keypoint_shape(
        self,
        keypoint: Tuple[Union[int, float], Union[int, float]],
        keypoint_name: List[str],
        score: Union[float, str],
        pose_id: Union[int, str],
        class_id: Union[int, str],
        track_id: Union[int, str],
    ) -> Shape:
        """
        Create a keypoint shape from a keypoint.

        Args:
            keypoint (Tuple[Union[int, float], Union[int, float]]):
                A tuple of two integers or floats representing the keypoint.
            keypoint_name (List[str]): A list of strings representing the keypoint name.
            score (Union[float, str]): The confidence score of the keypoint.
            pose_id (Union[int, str]): The pose ID of the keypoint.
            class_id (Union[int, str]): The class ID of the keypoint.
            track_id (Union[int, str]): The track ID of the keypoint.

        Returns:
            (Shape): A Shape object representing the keypoint.
        """
        x, y = keypoint
        shape = Shape(flags={})
        shape.add_point(QtCore.QPointF(int(x), int(y)))
        shape.shape_type = "point"
        shape.difficult = False
        shape.group_id = int(class_id)
        shape.closed = True
        shape.label = keypoint_name[int(pose_id)]
        shape.score = float(score)
        shape.selected = False
        return shape

    @staticmethod
    def make_grid(nx=20, ny=20):
        """
        Create a grid of points.

        Args:
            nx (int): The number of points in the x-direction.
            ny (int): The number of points in the y-direction.

        Returns:
            (np.ndarray): A numpy array of shape (nx * ny, 2) representing the grid of points.
        """
        xv, yv = np.meshgrid(np.arange(ny), np.arange(nx))
        return np.stack((xv, yv), 2).reshape((-1, 2)).astype(np.float32)

    def scale_grid(self, outs):
        """Scale the grid of points."""
        outs = outs[0]
        row_ind = 0
        for i in range(self.nl):
            h = int(self.input_shape[0] / self.stride[i])
            w = int(self.input_shape[1] / self.stride[i])
            length = int(self.na * h * w)
            if self.grid[i].shape[2:4] != (h, w):
                self.grid[i] = self.make_grid(w, h)
            outs[row_ind : row_ind + length, 0:2] = (
                outs[row_ind : row_ind + length, 0:2] * 2.0
                - 0.5
                + np.tile(self.grid[i], (self.na, 1))
            ) * int(self.stride[i])
            outs[row_ind : row_ind + length, 2:4] = (
                outs[row_ind : row_ind + length, 2:4] * 2
            ) ** 2 * np.repeat(self.anchor_grid[i], h * w, axis=0)
            row_ind += length
        return outs[np.newaxis, :]

    def process_mask(self, protos, masks_in, bboxes, shape, upsample=False):
        """
        Apply masks to bounding boxes using the output of the mask head.

        Args:
            protos (np.ndarray): A tensor of shape [mask_dim, mask_h, mask_w].
            masks_in (np.ndarray): A tensor of shape [n, mask_dim], where n is the number of masks after NMS.
            bboxes (np.ndarray): A tensor of shape [n, 4], where n is the number of masks after NMS.
            shape (tuple): A tuple of integers representing the size of the input image in the format (h, w).
            upsample (bool): A flag to indicate whether to upsample the mask to the original image size. Default is False.

        Returns:
            (np.ndarray): A binary mask tensor of shape [n, h, w],
            where n is the number of masks after NMS, and h and w
            are the height and width of the input image.
            The mask is applied to the bounding boxes.
        """
        c, mh, mw = protos.shape
        ih, iw = shape
        masks = 1 / (
            1
            + np.exp(
                -np.dot(masks_in, protos.reshape(c, -1).astype(float)).astype(
                    float
                )
            )
        )
        masks = masks.reshape(-1, mh, mw)

        downsampled_bboxes = bboxes.copy()
        downsampled_bboxes[:, 0] *= mw / iw
        downsampled_bboxes[:, 2] *= mw / iw
        downsampled_bboxes[:, 3] *= mh / ih
        downsampled_bboxes[:, 1] *= mh / ih
        masks = self.crop_mask_np(masks, downsampled_bboxes)  # CHW
        if upsample:
            if masks.shape[0] == 1:
                masks_np = np.squeeze(masks, axis=0)
                masks_resized = cv2.resize(
                    masks_np,
                    (shape[1], shape[0]),
                    interpolation=cv2.INTER_LINEAR,
                )
                masks = np.expand_dims(masks_resized, axis=0)
            else:
                masks_np = np.transpose(masks, (1, 2, 0))
                masks_resized = cv2.resize(
                    masks_np,
                    (shape[1], shape[0]),
                    interpolation=cv2.INTER_LINEAR,
                )
                masks = np.transpose(masks_resized, (2, 0, 1))
        masks[masks > 0.5] = 1
        masks[masks <= 0.5] = 0

        return masks

    @staticmethod
    def crop_mask_np(masks, boxes):
        """
        It takes a mask and a bounding box, and returns a mask that is cropped to the bounding box.

        Args:
            masks (np.ndarray): [n, h, w] array of masks.
            boxes (np.ndarray): [n, 4] array of bbox coordinates in relative point form.

        Returns:
            (np.ndarray): The masks are being cropped to the bounding box.
        """
        n, h, w = masks.shape
        x1, y1, x2, y2 = np.hsplit(boxes[:, :, None], 4)
        r = np.arange(w, dtype=x1.dtype)[None, None, :]  # rows shape(1,1,w)
        c = np.arange(h, dtype=x1.dtype)[None, :, None]  # cols shape(1,h,1)

        return masks * ((r >= x1) & (r < x2) & (c >= y1) & (c < y2))

    @staticmethod
    def rescale_coords_v10(boxes, image_shape, input_shape):
        """
        Rescale the coordinates of the bounding boxes.

        Args:
            boxes (np.ndarray): [n, 4] array of bbox coordinates in relative point form.
            image_shape (tuple): A tuple of integers representing
                the size of the input image in the format (h, w).
            input_shape (tuple): A tuple of integers representing
                the size of the input image in the format (h, w).

        Returns:
            boxes (np.ndarray): [n, 4] array of bbox coordinates in relative point form.
        """
        image_height, image_width = image_shape
        input_height, input_width = input_shape

        scale = min(input_width / image_width, input_height / image_height)

        pad_w = (input_width - image_width * scale) / 2
        pad_h = (input_height - image_height * scale) / 2

        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_w) / scale
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_h) / scale

        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, image_width)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, image_height)

        return boxes

    def unload(self):
        del self.net
