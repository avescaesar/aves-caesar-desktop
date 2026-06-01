from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from PIL import Image


IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PADDING_COLOR = (114, 114, 114)
EXPAND_PIXELS = 5


@dataclass(frozen=True)
class BirdBox:
    box: list[float]
    score: float


@dataclass(frozen=True)
class ClassifierCropJob:
    image: Image.Image
    box: BirdBox


class BirdImagePreprocessor:
    @staticmethod
    def square_crops_from_boxes(image: Image.Image, boxes: list[BirdBox]) -> list[Image.Image]:
        width, height = image.width, image.height
        crops = []
        for item in boxes:
            crops.append(BirdImagePreprocessor._square_crop(image, item, width, height))

        return crops


    @staticmethod
    def classifier_batch(crops: list[Image.Image], crop_size: int) -> np.ndarray:
        if not crops:
            return np.empty((0, 3, crop_size, crop_size), dtype=np.float32)

        if len(crops) < 4:
            tensors = [BirdImagePreprocessor._classifier_tensor(crop, crop_size) for crop in crops]
        else:
            with ThreadPoolExecutor(max_workers=BirdImagePreprocessor._worker_count(len(crops))) as executor:
                tensors = list(executor.map(lambda crop: BirdImagePreprocessor._classifier_tensor(crop, crop_size), crops))

        return np.stack(tensors, axis=0).astype(np.float32)


    @staticmethod
    def classifier_batch_from_boxes(jobs: list[ClassifierCropJob], crop_size: int) -> np.ndarray:
        if not jobs:
            return np.empty((0, 3, crop_size, crop_size), dtype=np.float32)

        if len(jobs) < 4:
            tensors = [BirdImagePreprocessor._classifier_tensor_from_box(job, crop_size) for job in jobs]
        else:
            with ThreadPoolExecutor(max_workers=BirdImagePreprocessor._worker_count(len(jobs))) as executor:
                tensors = list(executor.map(lambda job: BirdImagePreprocessor._classifier_tensor_from_box(job, crop_size), jobs))

        return np.stack(tensors, axis=0).astype(np.float32)


    @staticmethod
    def detector_image(image: Image.Image, size: tuple[int, int] = (640, 640)) -> tuple[np.ndarray, tuple[int, int], tuple[float, float]]:
        original = (image.height, image.width)
        resized = image.resize(size, Image.Resampling.BICUBIC)
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = np.transpose(arr, (2, 0, 1))[None, :, :, :].astype(np.float32)
        scale_x = image.width / float(size[0])
        scale_y = image.height / float(size[1])
        return tensor, original, (scale_x, scale_y)


    @staticmethod
    def detector_batch(images: list[Image.Image], size: tuple[int, int] = (640, 640)) -> tuple[np.ndarray, list[tuple[float, float]]]:
        if not images:
            return np.empty((0, 3, size[1], size[0]), dtype=np.float32), []

        if len(images) < 3:
            prepared = [BirdImagePreprocessor.detector_image(image, size) for image in images]
        else:
            with ThreadPoolExecutor(max_workers=BirdImagePreprocessor._worker_count(len(images))) as executor:
                prepared = list(executor.map(lambda image: BirdImagePreprocessor.detector_image(image, size), images))

        tensors = [tensor[0] for tensor, _target_size, _scale in prepared]
        scales = [scale for _tensor, _target_size, scale in prepared]
        return np.stack(tensors, axis=0).astype(np.float32), scales


    @staticmethod
    def _classifier_tensor(crop: Image.Image, crop_size: int) -> np.ndarray:
        resized = crop.resize((crop_size, crop_size), Image.Resampling.BICUBIC)
        try:
            arr = np.asarray(resized, dtype=np.float32) / 255.0
            arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
            return np.transpose(arr, (2, 0, 1))
        finally:
            resized.close()


    @staticmethod
    def _classifier_tensor_from_box(job: ClassifierCropJob, crop_size: int) -> np.ndarray:
        crop = BirdImagePreprocessor._square_crop(job.image, job.box, job.image.width, job.image.height)
        try:
            return BirdImagePreprocessor._classifier_tensor(crop, crop_size)
        finally:
            crop.close()


    @staticmethod
    def _worker_count(item_count: int) -> int:
        cpu_count = os.cpu_count() or 1
        return max(1, min(item_count, cpu_count, 8))


    @staticmethod
    def _square_crop(image: Image.Image, item: BirdBox, width: int, height: int) -> Image.Image:
        x0, y0, x1, y1 = item.box
        x0 -= EXPAND_PIXELS
        y0 -= EXPAND_PIXELS
        x1 += EXPAND_PIXELS
        y1 += EXPAND_PIXELS
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        side = int(math.ceil(max(x1 - x0, y1 - y0, 1)))
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        sx0 = int(math.floor(center_x - side / 2))
        sy0 = int(math.floor(center_y - side / 2))
        sx1 = sx0 + side
        sy1 = sy0 + side
        pad_left = max(0, -sx0)
        pad_top = max(0, -sy0)
        crop_x0 = max(0, sx0)
        crop_y0 = max(0, sy0)
        crop_x1 = min(width, sx1)
        crop_y1 = min(height, sy1)
        square_img = Image.new("RGB", (side, side), PADDING_COLOR)
        patch = image.crop((crop_x0, crop_y0, crop_x1, crop_y1))
        try:
            square_img.paste(patch, (pad_left, pad_top))
        finally:
            patch.close()

        return square_img
