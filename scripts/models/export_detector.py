from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DETECTOR_INPUT_SIZE = 640


def main() -> None:
    parser = argparse.ArgumentParser(description="Export RT-DETR bird detector to ONNX.")
    parser.add_argument("--model-id", default="PekingU/rtdetr_v2_r101vd")
    parser.add_argument("--output", default=str(ROOT / "models" / "bird_detector.onnx"))
    parser.add_argument("--opset", type=int, default=18)
    args = parser.parse_args()

    import torch
    from transformers import RTDetrV2ForObjectDetection

    model = RTDetrV2ForObjectDetection.from_pretrained(args.model_id).eval()

    class DetectorWrapper(torch.nn.Module):
        def __init__(self, wrapped):
            super().__init__()
            self.wrapped = wrapped


        def forward(self, pixel_values):
            output = self.wrapped(pixel_values=pixel_values)
            probs = output.logits.sigmoid()
            scores, labels = probs.max(dim=-1)
            boxes = center_to_corners(output.pred_boxes) * float(DETECTOR_INPUT_SIZE)
            return boxes, scores, labels


    def center_to_corners(boxes):
        cx, cy, w, h = boxes.unbind(-1)
        x0 = cx - 0.5 * w
        y0 = cy - 0.5 * h
        x1 = cx + 0.5 * w
        y1 = cy + 0.5 * h
        return torch.stack((x0, y0, x1, y1), dim=-1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros((1, 3, DETECTOR_INPUT_SIZE, DETECTOR_INPUT_SIZE), dtype=torch.float32)
    dynamic_axes = {
        "pixel_values": {0: "batch"},
        "boxes": {0: "batch"},
        "scores": {0: "batch"},
        "labels": {0: "batch"},
    }
    torch.onnx.export(DetectorWrapper(model), (dummy,), str(output), input_names=["pixel_values"], output_names=["boxes", "scores", "labels"], dynamic_axes=dynamic_axes, opset_version=args.opset, dynamo=False)

    try:
        from .sanitize_onnx import sanitize_file
    except ImportError:
        from sanitize_onnx import sanitize_file

    sanitize_file(output)
    print(output)


if __name__ == "__main__":
    main()
