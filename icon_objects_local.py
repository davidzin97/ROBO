"""Solver LOCAL icon-objects GeeTest v4 — port do pipeline da VPS (sem rede).

Pipeline identico ao /match da VPS (icon-match-api/main.py), tudo em
onnxruntime + numpy (sem torch em producao):

  1. detect_candidates: detector YOLOX generico (detector.onnx) -> top-N boxes
  2. embed_image: DINOv2-small ONNX (dinov2-small.onnx[.data]) -> CLS 384d
  3. matching: maior similaridade de cosseno, assignment guloso 1:1
  4. positions pixel-space (centro do box) -> unidades GeeTest (*33/*49)

Contrato compativel com RemoteIconMatcher.find_icon_position().
Read-only em runtime (distribuicao portatil).
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
if HERE.name == "app":
    # Modulo servido do pacote criptografado (caminho virtual app/);
    # os assets .enc ficam na raiz da distribuicao.
    HERE = HERE.parent
DETECTOR_ONNX = Path(os.getenv("ICON_DETECTOR_ONNX", HERE / "models" / "detector.onnx"))
DINO_ONNX = Path(os.getenv("ICON_DINO_ONNX", HERE / "models" / "dinov2-small.onnx"))

_det_sess = None
_dino_sess = None


class IconLocalUnavailable(Exception):
    pass


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
    global _det_sess, _dino_sess
    if _det_sess is not None and _dino_sess is not None:
        return
    if not DETECTOR_ONNX.exists() and not DETECTOR_ONNX.with_name(DETECTOR_ONNX.name + ".enc").exists():
        raise IconLocalUnavailable(f"detector ausente: {DETECTOR_ONNX}")
    if not DINO_ONNX.exists() and not DINO_ONNX.with_name(DINO_ONNX.name + ".enc").exists():
        raise IconLocalUnavailable(f"dinov2 ausente: {DINO_ONNX}")
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.log_severity_level = 3
    _det_sess = ort.InferenceSession(_load_model_bytes(DETECTOR_ONNX), sess_options=so, providers=["CPUExecutionProvider"])
    _dino_sess = ort.InferenceSession(_load_model_bytes(DINO_ONNX), sess_options=so, providers=["CPUExecutionProvider"])


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:
        return False


# --------------------------- detector (YOLOX) ---------------------------

_YOLO_ICON_ONNX = Path(os.getenv(
    "ICON_YOLO_ONNX",
    HERE / "icon_objects_runs" / "icon_yolo" / "weights" / "best.onnx",
))
_yolo_sess = None


def _get_yolo_session():
    global _yolo_sess
    if _yolo_sess is None:
        if not _YOLO_ICON_ONNX.exists() and not _YOLO_ICON_ONNX.with_name(_YOLO_ICON_ONNX.name + ".enc").exists():
            raise IconLocalUnavailable(f"icon-yolo ausente: {_YOLO_ICON_ONNX}")
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        _yolo_sess = ort.InferenceSession(_load_model_bytes(_YOLO_ICON_ONNX), sess_options=so, providers=["CPUExecutionProvider"])
    return _yolo_sess


def detect_candidates_yolo(im_rgb: np.ndarray, conf_thres=0.25, max_candidates=8, min_side=20):
    """Detector alternativo: YOLO11n treinado no dataset icon (110 classes).

    Mesmo contrato de detect_candidates (lista de boxes xyxy, top-N por conf),
    mas com decode YOLO11 (saida 1x(4+nc)x8400) e NMS agnostico (as classes
    nao importam aqui - so a localizacao dos objetos).
    """
    sess = _get_yolo_session()
    h0, w0 = im_rgb.shape[:2]
    # letterbox 640 (mesmo do nine_yolo_solver)
    im = Image.fromarray(im_rgb)
    r = min(640 / w0, 640 / h0)
    nw, nh = int(round(w0 * r)), int(round(h0 * r))
    im2 = im.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (640, 640), (114, 114, 114))
    canvas.paste(im2, ((640 - nw) // 2, (640 - nh) // 2))
    x = np.asarray(canvas, dtype=np.float32) / 255.0
    x = np.transpose(x, (2, 0, 1))[None]

    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0].T  # (8400, 4+nc)
    boxes_xywh, cls_scores = out[:, :4], out[:, 4:]
    conf = cls_scores.max(axis=1)
    mask = conf >= conf_thres
    boxes_xywh, conf = boxes_xywh[mask], conf[mask]
    if len(conf) == 0:
        return []

    cx, cy, w, h = boxes_xywh.T
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    keep = _nms(boxes, conf, 0.45)
    boxes, conf = boxes[keep], conf[keep]

    # desfaz letterbox
    dw, dh = (640 - nw) // 2, (640 - nh) // 2
    result = []
    order = conf.argsort()[::-1]
    for i in order:
        x1 = (boxes[i, 0] - dw) / r
        y1 = (boxes[i, 1] - dh) / r
        x2 = (boxes[i, 2] - dw) / r
        y2 = (boxes[i, 3] - dh) / r
        x_min, y_min = max(0, int(x1)), max(0, int(y1))
        x_max, y_max = min(w0, int(x2)), min(h0, int(y2))
        if min(x_max - x_min, y_max - y_min) < min_side:
            continue
        result.append([x_min, y_min, x_max, y_max])
        if len(result) >= max_candidates:
            break
    return result

def _preproc_detector(img: np.ndarray, input_size=(416, 416)):
    padded_img = np.ones((input_size[0], input_size[1], 3), dtype=np.uint8) * 114
    r = min(input_size[0] / img.shape[0], input_size[1] / img.shape[1])
    resized = np.array(
        Image.fromarray(img).resize(
            (int(img.shape[1] * r), int(img.shape[0] * r)), Image.BILINEAR
        ),
        dtype=np.uint8,
    )
    padded_img[: int(img.shape[0] * r), : int(img.shape[1] * r)] = resized
    padded_img = padded_img.transpose((2, 0, 1))
    return np.ascontiguousarray(padded_img, dtype=np.float32), r


def _decode_grid(outputs: np.ndarray, img_size):
    grids, expanded_strides = [], []
    strides = [8, 16, 32]
    hsizes = [img_size[0] // s for s in strides]
    wsizes = [img_size[1] // s for s in strides]
    for hsize, wsize, stride in zip(hsizes, wsizes, strides):
        xv, yv = np.meshgrid(np.arange(wsize), np.arange(hsize))
        grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((*grid.shape[:2], 1), stride))
    grids = np.concatenate(grids, 1)
    expanded_strides = np.concatenate(expanded_strides, 1)
    outputs[..., :2] = (outputs[..., :2] + grids) * expanded_strides
    outputs[..., 2:4] = np.exp(outputs[..., 2:4]) * expanded_strides
    return outputs


def _nms(boxes, scores, nms_thr):
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(ovr <= nms_thr)[0] + 1]
    return keep


def _multiclass_nms(boxes, scores, nms_thr, score_thr):
    cls_inds = scores.argmax(1)
    cls_scores = scores[np.arange(len(cls_inds)), cls_inds]
    valid = cls_scores > score_thr
    if valid.sum() == 0:
        return None
    keep = _nms(boxes[valid], cls_scores[valid], nms_thr)
    if not keep:
        return None
    v_boxes, v_scores, v_inds = boxes[valid], cls_scores[valid], cls_inds[valid]
    return np.concatenate([v_boxes[keep], v_scores[keep, None], v_inds[keep, None]], 1)


def detect_candidates(im_rgb: np.ndarray, score_thr=0.0005, max_candidates=8, min_side=20):
    _load()
    padded, ratio = _preproc_detector(im_rgb)
    input_name = _det_sess.get_inputs()[0].name
    output = _det_sess.run(None, {input_name: padded[None, :, :, :]})
    predictions = _decode_grid(output[0], (416, 416))[0]
    boxes = predictions[:, :4]
    scores = predictions[:, 4:5] * predictions[:, 5:]
    boxes_xyxy = np.ones_like(boxes)
    boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    boxes_xyxy /= ratio
    pred = _multiclass_nms(boxes_xyxy, scores, nms_thr=0.45, score_thr=score_thr)
    if pred is None:
        return []
    scored = sorted(zip(pred[:, :4].tolist(), pred[:, 4].tolist()), key=lambda t: -t[1])
    result = []
    h, w = im_rgb.shape[:2]
    for b, _s in scored:
        x_min, y_min = max(0, int(b[0])), max(0, int(b[1]))
        x_max, y_max = min(w, int(b[2])), min(h, int(b[3]))
        if min(x_max - x_min, y_max - y_min) < min_side:
            continue
        result.append([x_min, y_min, x_max, y_max])
        if len(result) >= max_candidates:
            break
    return result


# --------------------------- DINOv2 embed ---------------------------

# AutoImageProcessor(facebook/dinov2-small): resize shortest->256 (bilinear),
# center-crop 224, rescale 1/255, normalize ImageNet mean/std.
_DINO_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DINO_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _dino_preprocess(im: Image.Image) -> np.ndarray:
    im = im.convert("RGB")
    w, h = im.size
    scale = 256 / min(w, h)
    im = im.resize((round(w * scale), round(h * scale)), Image.BILINEAR)
    w, h = im.size
    left = (w - 224) // 2
    top = (h - 224) // 2
    im = im.crop((left, top, left + 224, top + 224))
    x = np.asarray(im, dtype=np.float32) / 255.0
    x = (x - _DINO_MEAN) / _DINO_STD
    return np.transpose(x, (2, 0, 1))[None].astype(np.float32)


def embed_image(im: Image.Image) -> np.ndarray:
    _load()
    x = _dino_preprocess(im)
    out = _dino_sess.run(None, {"pixel_values": x})[0]
    vec = out[0, 0]  # CLS token
    return vec / (np.linalg.norm(vec) + 1e-8)


def embed_batch(images: List[Image.Image]) -> np.ndarray:
    """Uma unica inferencia ONNX p/ N imagens (muito mais rapido que loop)."""
    _load()
    x = np.concatenate([_dino_preprocess(im) for im in images], axis=0)
    out = _dino_sess.run(None, {"pixel_values": x})[0]
    vecs = out[:, 0, :]  # CLS tokens
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8
    return vecs / norms


# --------------------------- solver (contrato RemoteIconMatcher) ---------------------------

def _flatten_on_white(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        return bg
    return im.convert("RGB")


def match_positions(main_img_bytes: bytes, prompt_bytes_list: List[bytes]) -> Optional[List[List[float]]]:
    """Retorna positions pixel-space (0-300, 0-200) na ordem dos prompts,
    ou None se nao localizar todos."""
    _load()
    scene_im = Image.open(io.BytesIO(main_img_bytes)).convert("RGB")
    scene_rgb = np.array(scene_im)

    candidate_boxes = detect_candidates(scene_rgb)
    n = len(prompt_bytes_list)
    if len(candidate_boxes) < n:
        return None

    pad = 4
    sw, sh = scene_im.size
    crops = [
        scene_im.crop((max(0, x1 - pad), max(0, y1 - pad), min(sw, x2 + pad), min(sh, y2 + pad)))
        for (x1, y1, x2, y2) in candidate_boxes
    ]
    prompt_ims = [
        _flatten_on_white(Image.open(io.BytesIO(pb)))
        for pb in prompt_bytes_list
    ]
    # batch: crops + prompts numa unica chamada ONNX
    all_vecs = embed_batch(crops + prompt_ims)
    candidate_embeds = all_vecs[: len(crops)]
    prompt_embeds = all_vecs[len(crops):]

    sim_matrix = np.zeros((n, len(candidate_boxes)))
    for i, pe in enumerate(prompt_embeds):
        for j, ce in enumerate(candidate_embeds):
            sim_matrix[i, j] = float(np.dot(pe, ce))

    triples = sorted(
        ((sim_matrix[i, j], i, j) for i in range(n) for j in range(len(candidate_boxes))),
        reverse=True,
    )
    assigned_i, assigned_j = set(), set()
    assignment = {}
    for s, i, j in triples:
        if i in assigned_i or j in assigned_j:
            continue
        assignment[i] = j
        assigned_i.add(i)
        assigned_j.add(j)

    positions = []
    for i in range(n):
        j = assignment.get(i)
        if j is None:
            return None
        x1, y1, x2, y2 = candidate_boxes[j]
        positions.append([round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1)])
    return positions


class IconObjectsLocalSolver:
    """Mesma interface de RemoteIconMatcher (prompt_urls -> baixa -> match)."""

    def __init__(self, main_img_bytes: bytes, prompt_urls: List[str], session=None) -> None:
        self.main_img_bytes = main_img_bytes
        self.prompt_urls = prompt_urls
        self._session = session

    def find_icon_position(self) -> List[List[float]]:
        import requests

        prompt_bytes_list = []
        http = self._session or requests
        for url in self.prompt_urls:
            r = http.get(url, timeout=8)
            r.raise_for_status()
            prompt_bytes_list.append(r.content)

        positions = match_positions(self.main_img_bytes, prompt_bytes_list)
        if positions is None:
            raise IconLocalUnavailable("nao localizou todos os prompts na cena")
        return [[px * 33, py * 49] for px, py in positions]


def solve_icon_objects_local(main_img_bytes: bytes, prompt_bytes_list: List[bytes]) -> Optional[List[List[float]]]:
    """Atalho sem HTTP: retorna coords GeeTest (*33/*49) ou None."""
    positions = match_positions(main_img_bytes, prompt_bytes_list)
    if positions is None:
        return None
    return [[px * 33, py * 49] for px, py in positions]
