"""Solver local de GeeTest v4 slide (puro OpenCV, sem rede).

Portado do GEEKED/geeked/slide.py. Encontra a posicao da peca (slice) no
background (bg) via Canny edge detection + cv2.matchTemplate.

Uso:
    from slide_solver import SlideSolver
    left = SlideSolver(slice_bytes, bg_bytes).find_puzzle_piece_position()
    # left: offset x (px) onde a peca se encaixa no background
"""

import cv2
import numpy as np


class SlideSolver:
    def __init__(self, puzzle_piece, background):
        self.background = self._read_image(background)
        self.puzzle_piece = self._read_image(puzzle_piece)

    @staticmethod
    def _read_image(image_source):
        """Le imagem de bytes (JPEG/PNG)."""
        if isinstance(image_source, bytes):
            return cv2.imdecode(np.frombuffer(image_source, np.uint8), cv2.IMREAD_ANYCOLOR)
        elif hasattr(image_source, "read"):
            return cv2.imdecode(np.frombuffer(image_source.read(), np.uint8), cv2.IMREAD_ANYCOLOR)
        else:
            raise TypeError("Invalid image source type. Must be bytes or a file-like object.")

    def find_puzzle_piece_position(self):
        """Encontra a posicao de encaixe da peca no background.

        Retorna o x (px) do lado esquerdo do encaixe (center_x - 41),
        mesmo contrato do GEEKED original.
        """
        edge_puzzle_piece = cv2.Canny(self.puzzle_piece, 100, 200)
        edge_background = cv2.Canny(self.background, 100, 200)

        edge_puzzle_piece_rgb = cv2.cvtColor(edge_puzzle_piece, cv2.COLOR_GRAY2RGB)
        edge_background_rgb = cv2.cvtColor(edge_background, cv2.COLOR_GRAY2RGB)

        res = cv2.matchTemplate(edge_background_rgb, edge_puzzle_piece_rgb, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        top_left = max_loc
        h, w = edge_puzzle_piece.shape[:2]

        center_x = top_left[0] + w // 2

        return center_x - 41
