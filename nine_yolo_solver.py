"""Solver LOCAL nine-grid GeeTest v4 — YOLO ONNX + lookup de prompt por hash.

Pipeline (zero chamadas externas):
  1. md5(prompt_bytes) -> classe-alvo (tabela hash->classe, vocabulario finito)
  2. YOLO ONNX no grid 3x3 inteiro -> (classe, conf) por tile
  3. resposta = 3 tiles com a classe-alvo (maior conf)

Se o hash do prompt for desconhecido, retorna indices vazios -> o chamador
cai no provider externo (Sonic) e a amostra pode entrar na tabela depois.

Interface compativel com geetest_nine_local: is_available() / solve_nine_local().
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if HERE.name == "app":
    # Modulo servido do pacote criptografado (caminho virtual app/);
    # os assets .enc ficam na raiz da distribuicao.
    HERE = HERE.parent
ONNX_PATH = Path(os.getenv(
    "NINE_YOLO_ONNX",
    HERE / "zefoy_nine_runs" / "nine_finetuned" / "weights" / "best.onnx",
))
ONNX_ENC_PATH = ONNX_PATH.with_name(ONNX_PATH.name + ".enc")
HASH_TABLE_PATH = Path(os.getenv(
    "NINE_HASH_TABLE",
    HERE / "nine_prompt_hashes.json",
))
HASH_TABLE_ENC_PATH = HASH_TABLE_PATH.with_name(HASH_TABLE_PATH.name + ".enc")
IMG_SIZE = 640
CONF_THRES = float(os.getenv("NINE_YOLO_CONF", "0.25"))
IOU_THRES = 0.45

_session = None
_names: list[str] = []
_hash2cls: dict[str, str] = {}


def _load_model_bytes(path: Path) -> Optional[bytes]:
    """Carrega o modelo descriptografando o pacote .enc em memoria."""
    if path.exists():
        return path.read_bytes()
    from _crypto import unseal

    enc_path = path.with_name(path.name + ".enc")
    if not enc_path.exists():
        raise FileNotFoundError(f"modelo ausente (aberto e .enc): {path}")
    return unseal(enc_path.read_text(encoding="ascii"))


def _load():
    global _session, _names, _hash2cls
    if _session is not None:
        return
    if not ONNX_PATH.exists() and not ONNX_ENC_PATH.exists():
        raise FileNotFoundError(f"ONNX nao encontrado: {ONNX_PATH}")
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.log_severity_level = 3
    model_bytes = _load_model_bytes(ONNX_PATH)
    _session = ort.InferenceSession(model_bytes, sess_options=so, providers=["CPUExecutionProvider"])

    meta = _session.get_modelmeta().custom_metadata_map
    if "names" in meta:
        # formato ultralytics: "{'0': 'ao', ...}"
        import ast
        raw = ast.literal_eval(meta["names"])
        _names = [raw[k] for k in sorted(raw, key=lambda k: int(k))]
    else:
        names_path = ONNX_PATH.with_suffix(".names.json")
        _names = json.loads(names_path.read_text())

    if HASH_TABLE_PATH.exists():
        _hash2cls = json.loads(HASH_TABLE_PATH.read_text(encoding="utf-8"))
    elif HASH_TABLE_ENC_PATH.exists():
        from _crypto import unseal

        _hash2cls = json.loads(unseal(HASH_TABLE_ENC_PATH.read_text(encoding="ascii")).decode("utf-8"))


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:
        return False


# NOTA: o solver e READ-ONLY em runtime (software distribuido portatil).
# A expansao da tabela hash->classe e do modelo e processo OFFLINE de
# release (build_prompt_dataset.py / build_hash_table.py / treino),
# nunca em producao.


# ------------------------------- inferencia -------------------------------

def _letterbox(im, new=IMG_SIZE):
    from PIL import Image
    w, h = im.size
    r = min(new / w, new / h)
    nw, nh = int(round(w * r)), int(round(h * r))
    im2 = im.resize((nw, nh))
    canvas = Image.new("RGB", (new, new), (114, 114, 114))
    canvas.paste(im2, ((new - nw) // 2, (new - nh) // 2))
    return canvas, r, (new - nw) // 2, (new - nh) // 2


def _nms(boxes, scores, iou_thres=IOU_THRES):
    import numpy as np
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        iou = (w * h) / (areas[i] + areas[order[1:]] - w * h + 1e-9)
        order = order[1:][iou <= iou_thres]
    return keep


def _predict_grid(grid_img) -> list[tuple[int, int, float]]:
    """Retorna [(tile 0-8, cls_id, conf)] — 1 deteccao (top) por tile."""
    import numpy as np

    _load()
    canvas, r, dw, dh = _letterbox(grid_img)
    x = np.asarray(canvas, dtype=np.float32) / 255.0
    x = np.transpose(x, (2, 0, 1))[None]

    out = _session.run(None, {_session.get_inputs()[0].name: x})[0]
    out = out[0].T  # (8400, 4+nc)
    boxes_xywh, cls_scores = out[:, :4], out[:, 4:]
    conf = cls_scores.max(axis=1)
    cls_id = cls_scores.argmax(axis=1)
    mask = conf >= CONF_THRES
    boxes_xywh, conf, cls_id = boxes_xywh[mask], conf[mask], cls_id[mask]
    if len(conf) == 0:
        return []

    cx, cy, w, h = boxes_xywh.T
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    keep = _nms(boxes, conf)
    boxes, conf, cls_id = boxes[keep], conf[keep], cls_id[keep]

    W, H = grid_img.size
    per_tile: dict[int, tuple[int, float]] = {}
    for (x1, y1, x2, y2), c, k in zip(boxes, conf, cls_id):
        bx = ((x1 + x2) / 2 - dw) / r
        by = ((y1 + y2) / 2 - dh) / r
        col = min(2, max(0, int(bx / (W / 3))))
        row = min(2, max(0, int(by / (H / 3))))
        t = row * 3 + col
        if t not in per_tile or c > per_tile[t][1]:
            per_tile[t] = (int(k), float(c))
    return [(t, k, c) for t, (k, c) in per_tile.items()]


def solve_nine_local(grid_bytes: bytes, prompt_bytes: bytes) -> Tuple[List[int], List[Tuple[int, float]]]:
    """Retorna (indices 0-based, scores [(tile, dist)]) — menor dist = melhor.

    indices vazio => prompt fora do vocabulario (caller usa fallback externo).
    """
    from PIL import Image

    _load()
    h = hashlib.md5(prompt_bytes).hexdigest()
    target = _hash2cls.get(h)
    if target is None or target not in _names:
        return [], []

    target_id = _names.index(target)
    grid = Image.open(io.BytesIO(grid_bytes)).convert("RGB")
    dets = _predict_grid(grid)

    cand = [(t, c) for t, k, c in dets if k == target_id]
    cand.sort(key=lambda x: -x[1])
    indices = sorted(t for t, _ in cand[:3])
    # scores no contrato "menor = melhor": dist = 1 - conf
    scores = [(t, 1.0 - c) for t, _, c in sorted(dets)]
    if len(indices) != 3:
        return [], scores
    return indices, scores


def prompt_md5(prompt_bytes: bytes) -> str:
    return hashlib.md5(prompt_bytes).hexdigest()


def known_hashes() -> dict[str, str]:
    _load()
    return dict(_hash2cls)
