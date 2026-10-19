# -*- coding: utf-8 -*-
"""Solver LOCAL GeeTest v4 risk_type=icon (arrows via ONNX, classificacao de
variante pura). Sem dependencia do SSBROWSER e sem endpoint remoto de captcha:
tudo roda em onnxruntime + numpy + PIL no processo local.

Porta do caminho 100% HTTP do SSBROWSER/app/icon_solver.py (models identicos),
residenciada neste repo para o pipeline ficar autocontido:
  - arrows: detector YOLOX (models/detector.onnx, mesmo ddddocr common_det)
    + classificador 64x64 grayscale (models/geetest_v4_icon.onnx/charsets)
  - objects/unknown: resolvidos pelo chamador via icon_objects_local
    (detector + DINOv2-small, zero-shot)

Uso:
    from icon_solver import IconClassifier, classify_icon_variant
    variant = classify_icon_variant(ques_urls)
    coords = IconClassifier(main_img_bytes, prompt_urls).find_icon_position()
    # coords: [[x, y], ...] em unidades Geetest (escala fixa *33 / *49),
    # mesma escala usada no payload w (userresponse) do gcaptcha4.
"""
import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np

logger = logging.getLogger("icon_solver")

HERE = Path(__file__).resolve().parent
if HERE.name == "app":
    # Modulo servido do pacote criptografado (caminho virtual app/);
    # os assets .enc ficam na raiz da distribuicao.
    HERE = HERE.parent
MODELS_DIR = Path(os.getenv("ICON_MODELS_DIR", HERE / "models"))
_ONNX_PATH = Path(os.getenv("ICON_CLASSIFIER_ONNX", MODELS_DIR / "geetest_v4_icon.onnx"))
_CHARSETS_PATH = Path(os.getenv("ICON_CHARSETS_JSON", MODELS_DIR / "geetest_v4_icon_charsets.json"))
# Mesmo detector ONNX usado pelo icon_objects_local (byte-a-byte identico ao
# geetest_v4_icon_detector.onnx do SSBROWSER — ddddocr common_det).
_DETECTOR_ONNX_PATH = Path(os.getenv("ICON_DETECTOR_ONNX", MODELS_DIR / "detector.onnx"))


def _load_model_bytes(path: Path) -> Optional[bytes]:
    """Carrega o modelo descriptografando o pacote .enc em memoria."""
    if path.exists():
        return path.read_bytes()
    from _crypto import unseal

    enc_path = path.with_name(path.name + ".enc")
    if not enc_path.exists():
        raise FileNotFoundError(f"modelo ausente (aberto e .enc): {path}")
    return unseal(enc_path.read_text(encoding="ascii"))


def _load_json_enc(path: Path) -> Dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    from _crypto import unseal

    enc_path = path.with_name(path.name + ".enc")
    if not enc_path.exists():
        raise FileNotFoundError(f"arquivo ausente (aberto e .enc): {path}")
    return json.loads(unseal(enc_path.read_text(encoding="ascii")).decode("utf-8"))


def _icon_debug(msg: str) -> None:
    logger.debug("[icon_solver] %s", msg)


# Mapeamento nome-de-arquivo-do-prompt -> direcao (identico ao GeekedTest).
# Cobre apenas a variante "icon_arrows" (setas). A variante "objetos"
# (icon_pic/icon_20201215 com cursor/onibus/olho/etc) nao tem modelo
# classificador — o chamador roteia para icon_objects_local (DINOv2).
ICON_DIRECTION_MAP: Dict[str, str] = {
    "8da090c135ff029f3b5e19f4c44f73c8.png": "u",
    "cb0eaa639b2117a69a81af3d8c1496a1.png": "d",
    "315ce8665e781dabcd1eb09d3e604803.png": "l",
    "38bd9dda695098c7dfad74c921923a7d.png": "lu",
    "502e51dbabf411beba2dcd55fd38ebbd.png": "ld",
    "2b2387f566f6a03ed594d4d7cfda471f.png": "r",
    "78dc29045d587ad054c7353732df53c5.png": "ru",
    "23ef93e6b0e0df0e15b66667c99a5fb4.png": "rd",
}


class RemoteMatcherUnavailable(Exception):
    """Mantido por compatibilidade de interface: nao ha mais solver remoto."""


class RemoteIconMatcher:
    """Stub de compatibilidade — resolver remoto (VPS) removido.

    Redireciona para o solver local (icon_objects_local) sem rede.
    Mantido porque o geetest_solver.py do commit 24803e3 importa este nome.
    """

    def __init__(self, main_img_bytes: bytes, prompt_urls: List[str]) -> None:
        self.main_img_bytes = main_img_bytes
        self.prompt_urls = prompt_urls

    def find_icon_position(self) -> List[List[float]]:
        from icon_objects_local import is_available as _io_avail, match_positions

        if not _io_avail():
            raise RemoteMatcherUnavailable(
                "icon_objects_local indisponivel (assets DINOv2 ausentes)"
            )
        prompt_bytes_list = []
        for url in self.prompt_urls:
            import requests
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            prompt_bytes_list.append(resp.content)

        pos = match_positions(self.main_img_bytes, prompt_bytes_list)
        if not pos:
            raise RemoteMatcherUnavailable(
                "icon_objects_local retornou sem posicoes"
            )
        return [[px * 33, py * 49] for px, py in pos]


class IconModelUnavailable(Exception):
    """Prompts nao correspondem a variante icon_arrows (sem modelo local)."""


def is_available() -> bool:
    """Assets do icon arrows presentes (classificador + charset + detector)?"""
    return (
        (_ONNX_PATH.exists() or _ONNX_PATH.with_name(_ONNX_PATH.name + ".enc").exists())
        and (_CHARSETS_PATH.exists() or _CHARSETS_PATH.with_name(_CHARSETS_PATH.name + ".enc").exists())
        and (_DETECTOR_ONNX_PATH.exists() or _DETECTOR_ONNX_PATH.with_name(_DETECTOR_ONNX_PATH.name + ".enc").exists())
    )


def classify_icon_variant(target_urls_or_names: List[str]) -> str:
    """Classifica icon captcha como ``arrows``, ``objects`` ou ``unknown``.

    Arrows: targets batem em ICON_DIRECTION_MAP (8 setas direcionais ONNX).
    Objects: URL carrega evidencia explicita da familia ``original_icon_pic``
    (figuras complexas, resolvidas via DINOv2 local). Dados incompletos ou
    de uma CDN desconhecida permanecem ``unknown`` para nao escolher um
    solver incorreto por suposicao.

    Aceita URLs completas ou nomes de arquivo; extrai o basename automaticamente.

    Returns:
        ``arrows`` se qualquer target bater no mapa, ``objects`` se houver
        evidencia explicita de objects, ou ``unknown`` caso contrario.
    """
    if not isinstance(target_urls_or_names, (list, tuple)):
        return "unknown"

    saw_target = False
    for name in target_urls_or_names:
        value = str(name or "").strip()
        if not value:
            continue
        saw_target = True
        normalized = value.lower().split("?", 1)[0]
        basename = normalized.rsplit("/", 1)[-1]
        if basename in ICON_DIRECTION_MAP:
            return "arrows"

    if saw_target and any(
        marker in str(name or "").lower()
        for name in target_urls_or_names
        for marker in ("original_icon_pic", "/icon_pic/", "icon_20201215")
    ):
        return "objects"
    return "unknown"


class _OnnxClassifier:
    """Wrapper lazy em torno do onnxruntime, sem depender de ddddocr.

    Modelo espera entrada grayscale 64x64 (Gemm_24 do onnx exige flatten
    fixo de 6528 = 64*102 apos as camadas conv; validado empiricamente).
    """

    def __init__(self) -> None:
        self._session = None
        self._charset: List[str] = []

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort  # import tardio: dependencia pesada, so quando usada

        self._session = ort.InferenceSession(_load_model_bytes(_ONNX_PATH))
        self._charset = _load_json_enc(_CHARSETS_PATH)["charset"]

    def classify_crop(self, crop_bgr: np.ndarray) -> Optional[str]:
        """Classifica um recorte (BGR) em rotulo do charset (ex: 'car_lu') ou None."""
        self._ensure_loaded()
        try:
            from PIL import Image

            rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb).resize((64, 64)).convert("L")
            arr = np.array(image).astype(np.float32)
            arr = np.expand_dims(arr, 0) / 255.0
            arr = (arr - 0.456) / 0.224
            _out_scores, out_idx = self._session.run(
                None, {"input1": np.array([arr]).astype(np.float32)}
            )
            idx = int(out_idx[0]) if hasattr(out_idx, "__len__") else int(out_idx)
            if idx <= 0 or idx >= len(self._charset):
                return None
            return self._charset[idx]
        except Exception:
            return None


_classifier = _OnnxClassifier()


class _OnnxDetector:
    """Detector generico de objetos (YOLOX), mesmo modelo common_det.onnx do
    ddddocr (det=True), rodado via onnxruntime puro para evitar a dependencia
    incompativel com Python 3.13. Pre/pos-processamento portado 1:1 do
    ddddocr (letterbox 416x416, decode de grid multi-stride, NMS por classe).
    """

    def __init__(self) -> None:
        self._session = None

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        try:
            import onnxruntime as ort  # import tardio: dependencia pesada, so quando usada
        except ModuleNotFoundError as e:
            raise IconModelUnavailable(f"onnxruntime não instalado: {e}") from e

        self._session = ort.InferenceSession(_load_model_bytes(_DETECTOR_ONNX_PATH))

    @staticmethod
    def _preproc(img: np.ndarray, input_size):
        padded_img = np.ones((input_size[0], input_size[1], 3), dtype=np.uint8) * 114
        r = min(input_size[0] / img.shape[0], input_size[1] / img.shape[1])
        resized = cv2.resize(
            img, (int(img.shape[1] * r), int(img.shape[0] * r)),
            interpolation=cv2.INTER_LINEAR,
        ).astype(np.uint8)
        padded_img[: int(img.shape[0] * r), : int(img.shape[1] * r)] = resized
        padded_img = padded_img.transpose((2, 0, 1))
        return np.ascontiguousarray(padded_img, dtype=np.float32), r

    @staticmethod
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

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, nms_thr: float) -> List[int]:
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        order = scores.argsort()[::-1]
        keep: List[int] = []
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

    def _multiclass_nms(self, boxes: np.ndarray, scores: np.ndarray, nms_thr: float, score_thr: float):
        cls_inds = scores.argmax(1)
        cls_scores = scores[np.arange(len(cls_inds)), cls_inds]
        valid = cls_scores > score_thr
        if valid.sum() == 0:
            return None
        keep = self._nms(boxes[valid], cls_scores[valid], nms_thr)
        if not keep:
            return None
        v_boxes, v_scores, v_inds = boxes[valid], cls_scores[valid], cls_inds[valid]
        return np.concatenate(
            [v_boxes[keep], v_scores[keep, None], v_inds[keep, None]], 1
        )

    def detect(self, im_bgr: np.ndarray) -> List[List[int]]:
        """Retorna bounding boxes [x1, y1, x2, y2] dos objetos detectados."""
        self._ensure_loaded()
        try:
            padded, ratio = self._preproc(im_bgr, (416, 416))
            input_name = self._session.get_inputs()[0].name
            output = self._session.run(None, {input_name: padded[None, :, :, :]})
            predictions = self._decode_grid(output[0], (416, 416))[0]
            boxes = predictions[:, :4]
            scores = predictions[:, 4:5] * predictions[:, 5:]

            boxes_xyxy = np.ones_like(boxes)
            boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
            boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
            boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
            boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
            boxes_xyxy /= ratio

            pred = self._multiclass_nms(boxes_xyxy, scores, nms_thr=0.45, score_thr=0.1)
            if pred is None:
                return []
            result: List[List[int]] = []
            for b in pred[:, :4].tolist():
                x_min = max(0, int(b[0]))
                y_min = max(0, int(b[1]))
                x_max = min(int(im_bgr.shape[1]), int(b[2]))
                y_max = min(int(im_bgr.shape[0]), int(b[3]))
                result.append([x_min, y_min, x_max, y_max])
            return result
        except Exception:
            return []


_detector = _OnnxDetector()


class IconClassifier:
    """Resolve risk_type=icon (arrows) a partir da imagem principal + prompts.

    imgs: bytes JPEG da imagem principal (300x200), igual ao campo `imgs` do
          payload /load do GeeTest (ja resolvido para bytes pelo chamador).
    ques: lista de URLs completas dos prompts (.geetest_ques_tips img.src),
          na ORDEM exigida pelo desafio.
    """

    def __init__(self, imgs: Union[bytes, str], ques: List[str]):
        self.imgs = imgs if isinstance(imgs, bytes) else self._load_image(imgs)
        self.ques = ques

    @staticmethod
    def _load_image(url: str) -> bytes:
        import requests

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content

    def _direction_for(self, prompt_url: str) -> str:
        filename = prompt_url.split("/")[-1].split("?")[0]
        return ICON_DIRECTION_MAP.get(filename, "")

    def _match_boxes_to_directions(self) -> List[List[float]]:
        """Detecta+classifica objetos e casa com as direcoes esperadas, na
        ORDEM dos prompts. Retorna centros em pixel da imagem principal
        (espaco 300x200), sem escala aplicada.

        Levanta IconModelUnavailable se nenhum prompt bater com o mapeamento
        de setas conhecido (ou seja, e a variante "objetos", sem modelo).

        Degradacao graciosa identica ao IconSolver original: quando uma
        direcao esperada nao e classificada com confianca, usa uma caixa
        detectada mas nao-classificada (em vez de falhar a resolucao
        inteira) - o resultado pode errar aquele clique, mas sempre
        retorna algo, preservando o comportamento de origem.
        """
        directions = [self._direction_for(q) for q in self.ques]
        _icon_debug(f"ARROWS: ques={self.ques!r} -> directions={directions!r}")
        if not any(directions):
            _icon_debug("ARROWS: nenhuma direcao mapeada -> variante objects (IconModelUnavailable)")
            raise IconModelUnavailable(
                "Prompts nao correspondem a variante icon_arrows (sem modelo treinado)."
            )

        im = cv2.imdecode(np.frombuffer(self.imgs, dtype=np.uint8), cv2.IMREAD_COLOR)
        boxes = _detector.detect(im)
        _icon_debug(f"ARROWS: imagem decodificada shape={im.shape if im is not None else None} boxes_detectadas={boxes!r}")

        box_directions: List[Dict[str, Any]] = [{"direction": d} for d in directions]
        unused_boxes: List[List[float]] = []

        for box in boxes:
            x1, y1, x2, y2 = box
            crop = im[y1:y2, x1:x2]
            center = [x1 + (x2 - x1) / 2, y1 + (y2 - y1) / 2]
            label = _classifier.classify_crop(crop)
            direction = label.split("_", 1)[1] if label and "_" in label else None
            _icon_debug(f"ARROWS: box={box} center={center} label={label!r} direction={direction!r}")

            matched = False
            if direction in ICON_DIRECTION_MAP.values():
                for boxd in box_directions:
                    if boxd["direction"] == direction and "bbox" not in boxd:
                        boxd["bbox"] = center
                        matched = True
                        break
            if not matched:
                unused_boxes.append(center)

        results: List[List[float]] = []
        for boxd in box_directions:
            if "bbox" in boxd:
                results.append(boxd["bbox"])
            elif unused_boxes:
                fallback_center = unused_boxes.pop(random.randint(0, len(unused_boxes) - 1))
                _icon_debug(f"ARROWS: direcao {boxd['direction']!r} sem match direto - usando box nao-classificada {fallback_center!r}")
                results.append(fallback_center)
            else:
                _icon_debug(f"ARROWS: FALHA - nenhuma caixa disponivel para direcao {boxd['direction']!r}")
                raise IconModelUnavailable(
                    f"Nenhuma caixa detectada na imagem principal para a direcao '{boxd['direction']}'."
                )
        _icon_debug(f"ARROWS: resultado final (pixel-space, sem escala) = {results!r}")
        return results

    def find_icon_position(self) -> List[List[float]]:
        """Retorna coordenadas [x, y] em unidades Geetest (escala fixa
        *33/*49), na ordem dos prompts. Usado no payload w (userresponse).
        """
        return [[cx * 33, cy * 49] for cx, cy in self._match_boxes_to_directions()]
