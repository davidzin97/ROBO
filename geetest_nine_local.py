# -*- coding: utf-8 -*-
"""Solver local do GeeTest v4 nine (grid 3x3), sem provider externo.

Metodo: chamfer matching simetrico multiescala entre o contorno do icone do
prompt e o mapa de bordas de cada tile. Validado contra o gabarito visual em
debug_local_nine.py.

Tres detalhes sao essenciais e foram a causa da regressao anterior:

1. O PNG do prompt guarda o icone SOMENTE no canal alpha (RGB todo zero). Um
   convert("L") direto devolve imagem 100% preta -> gradiente morfologico
   vazio -> template sem bordas -> ranking aleatorio.
2. A escala do template precisa ser relativa ao TILE preservando aspect ratio.
   Assumir template de ~100px rejeita toda escala acima de 0.45 quando o prompt
   vem em 200px.
3. O chamfer precisa ser simetrico (max das duas direcoes). Só template->tile
   premia tiles saturados de textura: sempre existe alguma borda perto de cada
   ponto do template, entao clutter ganha score baixo sem casar com o icone.
"""
from __future__ import annotations

import io
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Faixa de escalas do template relativa ao lado do tile.
_SCALE_MIN = 0.35
_SCALE_MAX = 0.96
_SCALE_STEP = 0.05
# Passo da janela deslizante em pixels.
_STRIDE = 2
# Subamostragem de pontos de borda para custo previsivel.
_MAX_PTS = 400


def _pil_to_gray(data: bytes):
    import numpy as np
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    if im.mode in ("RGBA", "LA", "PA"):
        # Achata sobre branco preservando o alpha (ver nota 1 no docstring).
        im = im.convert("RGBA")
        flat = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(flat, im)
    return np.array(im.convert("L"))


def prompt_mask(prompt_bytes: bytes):
    """Silhueta binaria do icone do prompt (icone=255), recortada na bbox."""
    import cv2
    import numpy as np
    from PIL import Image

    im = Image.open(io.BytesIO(prompt_bytes))
    if im.mode in ("RGBA", "LA", "PA"):
        # Caminho preferido: o alpha ja E a silhueta exata do icone.
        alpha = np.array(im.convert("RGBA"))[:, :, 3]
        mask = ((alpha > 16).astype(np.uint8)) * 255
    else:
        gray = _pil_to_gray(prompt_bytes)
        _, mask = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise RuntimeError("prompt sem icone detectavel")
    return mask[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]


def prompt_outline(prompt_bytes: bytes):
    """Contorno do icone do prompt como mapa de bordas."""
    import cv2
    import numpy as np

    mask = prompt_mask(prompt_bytes)
    k = np.ones((3, 3), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, k)


def tile_edges(tile_bytes: bytes):
    """Mapa de bordas do tile com Canny de limiares adaptativos."""
    import cv2
    import numpy as np

    gray = _pil_to_gray(tile_bytes)
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    v = np.median(gray)
    lo = int(max(0, 0.66 * v))
    hi = int(min(255, 1.33 * v))
    return cv2.Canny(gray, lo, hi)


# Score sentinela para tiles sem match (sem bordas, template nao encaixa).
# Finito e alto: ordena por ultimo sem contaminar media/margem com inf/NaN
# (ver nota 4).
_NO_MATCH = 999.0


def chamfer_score(edges, tmpl) -> float:
    """Melhor (menor) chamfer simetrico do template sobre o tile, multiescala.

    Nota 4: tiles inteiramente lisos produzem Canny vazio. distanceTransform de
    uma imagem sem pixel-zero devolve valores enormes que estouram float32 no
    .mean() (RuntimeWarning: overflow in reduce) e envenenam o ranking com inf.
    Guardamos os dois lados (tile e template) e forcamos float64 no reduce, e
    devolvemos _NO_MATCH em vez de inf quando nenhuma escala encaixa.
    """
    import cv2
    import numpy as np

    # Tile sem nenhuma borda: distanceTransform seria degenerado. Nao ha o que
    # casar, entao e o pior candidato possivel (mas finito).
    if int(np.count_nonzero(edges)) == 0:
        return _NO_MATCH

    inv = cv2.bitwise_not(edges)
    dist = cv2.distanceTransform(inv, cv2.DIST_L2, 3).astype(np.float64)

    th, tw = edges.shape
    t_h, t_w = tmpl.shape
    best = float("inf")

    for scale in np.arange(_SCALE_MIN, _SCALE_MAX, _SCALE_STEP):
        # Escala relativa ao tile preservando aspect ratio (ver nota 2).
        fit = min((th * scale) / t_h, (tw * scale) / t_w)
        h = int(round(t_h * fit))
        w = int(round(t_w * fit))
        if h < 8 or w < 8 or h > th or w > tw:
            continue

        t = cv2.resize(tmpl, (w, h), interpolation=cv2.INTER_NEAREST)
        pts = np.column_stack(np.nonzero(t))
        if len(pts) < 20:
            continue
        if len(pts) > _MAX_PTS:
            idx = np.linspace(0, len(pts) - 1, _MAX_PTS).astype(int)
            pts = pts[idx]

        t_inv = cv2.bitwise_not(t)
        t_dist = cv2.distanceTransform(t_inv, cv2.DIST_L2, 3).astype(np.float64)
        diag = float(np.hypot(h, w))
        if diag == 0.0:
            continue

        for oy in range(0, th - h + 1, _STRIDE):
            for ox in range(0, tw - w + 1, _STRIDE):
                d = dist[pts[:, 0] + oy, pts[:, 1] + ox]
                fwd = float(d.mean()) / diag * 100.0
                if fwd >= best:
                    # max(fwd,bwd) >= fwd: ja nao melhora, poupa a direcao inversa.
                    continue
                win = edges[oy:oy + h, ox:ox + w]
                wpts = np.column_stack(np.nonzero(win))
                if len(wpts) == 0:
                    continue
                if len(wpts) > _MAX_PTS:
                    widx = np.linspace(0, len(wpts) - 1, _MAX_PTS).astype(int)
                    wpts = wpts[widx]
                bwd = float(t_dist[wpts[:, 0], wpts[:, 1]].mean()) / diag * 100.0
                score = max(fwd, bwd)  # simetrico (ver nota 3)
                if score < best:
                    best = score
    return best if np.isfinite(best) else _NO_MATCH


def solve_nine_local(
    grid_bytes: bytes,
    prompt_bytes: bytes,
    pick: int = 3,
) -> Tuple[List[int], List[Tuple[int, float]]]:
    """Retorna (indices escolhidos 0..8, scores por tile). Menor score = melhor."""
    from PIL import Image

    im = Image.open(io.BytesIO(grid_bytes)).convert("RGB")
    w, h = im.size
    tw, th = w // 3, h // 3
    tmpl = prompt_outline(prompt_bytes)

    scores: List[Tuple[int, float]] = []
    for idx in range(9):
        row, col = idx // 3, idx % 3
        crop = im.crop((col * tw, row * th, (col + 1) * tw, (row + 1) * th))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        scores.append((idx, chamfer_score(tile_edges(buf.getvalue()), tmpl)))

    ranked = sorted(scores, key=lambda x: x[1])
    return [i for i, _ in ranked[:pick]], scores


def is_available() -> bool:
    """True quando as dependencias de visao estao instaladas."""
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception as exc:
        logger.warning(f"[GeeTest-Local] dependencias ausentes: {exc}")
        return False
