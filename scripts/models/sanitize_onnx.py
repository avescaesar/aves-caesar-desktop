from __future__ import annotations

import argparse
from pathlib import Path

import onnx

DEBUG_METADATA_PREFIXES = (
    "pkg.torch.onnx.",
    "namespace",
)


def sanitize_model(model: onnx.ModelProto) -> None:
    model.doc_string = ""
    del model.metadata_props[:]
    _sanitize_graph(model.graph)
    for function in model.functions:
        del function.metadata_props[:]
        for node in function.node:
            _sanitize_node(node)


def sanitize_file(path: str | Path) -> None:
    p = Path(path)
    model = onnx.load(p)
    sanitize_model(model)
    onnx.save(model, p)


def _sanitize_graph(graph: onnx.GraphProto) -> None:
    graph.doc_string = ""
    for value in list(graph.input) + list(graph.output) + list(graph.value_info):
        value.doc_string = ""

    for node in graph.node:
        _sanitize_node(node)
        for attr in node.attribute:
            if attr.g.name:
                _sanitize_graph(attr.g)
            for subgraph in attr.graphs:
                _sanitize_graph(subgraph)


def _sanitize_node(node: onnx.NodeProto) -> None:
    node.doc_string = ""
    kept = [prop for prop in node.metadata_props if not prop.key.startswith(DEBUG_METADATA_PREFIXES)]
    del node.metadata_props[:]
    node.metadata_props.extend(kept)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove local debug metadata from an ONNX file.")
    parser.add_argument("onnx_path")
    args = parser.parse_args()
    sanitize_file(args.onnx_path)


if __name__ == "__main__":
    main()
