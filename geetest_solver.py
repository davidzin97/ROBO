# -*- coding: utf-8 -*-
"""
GeeTest v4 Nine solver - fluxo completo sem browser.

Fluxo (baseado no HAR gtwin.com.har):
  1. client_report  → gee_token (fingerprint GeeGuard)
  2. gcaptcha4 load → lot_number, captcha_type=nine, imgs (grid 3x3), ques (prompt)
  3. CaptchaSonic solve_geetest_v4_nine → índices [0,3,7]
  4. gcaptcha4 verify → pass_token, gen_time, captcha_output
  5. validate/v4      → code:1 (validação server-side)

Retorna dict com lot_number, pass_token, gen_time, captcha_output para o bot usar.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING, cast

from curl_cffi.requests import Session as CurlSession

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util import Padding

if TYPE_CHECKING:
    from captchasonic_client import ImageInput


# ── WuluConfig externo (JSON) ─────────────────────────────────────────────
# Os valores de rotacao GEEKED sao lidos de um wulu_config.json EXTERNO a
# criptografia (appdata.bin). Assim o .bat de atualizacao sobrescreve o JSON
# sem precisar re-empacotar/re-criptografar o container. Os valores abaixo
# servem apenas de fallback caso o JSON nao seja encontrado.
_WULU_DEFAULTS = {
    "biht": "1426265548",
    "lib_key": "d4tf",
    "lib_val": "9342",
    "abo_key": "(n[16:19])+.+(n[2:5]+n[20:23])+.+(n[28:28]+n[18:18]+n[9:9]+n[13:13])",
    "abo_val": "n[22:25]",
}


def _wulu_json_candidates() -> list:
    """Ordem de busca: externo/editavel tem prioridade sobre o default embutido."""
    seen: list = []

    def add(p):
        if p and p not in seen:
            seen.append(p)

    add(os.environ.get("WULU_CONFIG_PATH"))
    exe = getattr(sys, "executable", None)
    if exe:
        add(os.path.join(os.path.dirname(exe), "wulu_config.json"))
    add(os.path.join(os.getcwd(), "wulu_config.json"))
    try:
        add(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wulu_config.json"))
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        add(os.path.join(meipass, "wulu_config.json"))
    return seen


def _load_wulu_config() -> tuple:
    values = dict(_WULU_DEFAULTS)
    for path in _wulu_json_candidates():
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k in _WULU_DEFAULTS:
                        v = data.get(k)
                        if isinstance(v, str) and v:
                            values[k] = v
                    return values, path
        except Exception:
            continue
    return values, None


_WULU_VALUES, _WULU_SOURCE = _load_wulu_config()


class WuluConfig:
    biht = _WULU_VALUES["biht"]
    lib_key = _WULU_VALUES["lib_key"]
    lib_val = _WULU_VALUES["lib_val"]
    abo_key = _WULU_VALUES["abo_key"]
    abo_val = _WULU_VALUES["abo_val"]


_RSA_N_HEX = (
    "00C1E3934D1614465B33053E7F48EE4EC87B14B95EF88947713D25EECBFF7E74"
    "C7977D02DC1D9451F79DD5D1C10C29ACB6A9B4D6FB7D0A0279B6719E1772565F"
    "09AF627715919221AEF91899CAE08C0D686D748B20A3603BE2318CA6BC2B5970"
    "6592A9219D0BF05C9F65023A21D2330807252AE0066D59CEEFA5F2748EA80BAB81"
)
_RSA_KEY = RSA.construct((int(_RSA_N_HEX, 16), 0x10001))


def _parse_lot_string(pattern: str) -> list:
    result = []
    for part in pattern.split("+.+"):
        group = []
        for single in part.split("+"):
            inner = single[single.index("[") + 1 : single.index("]")]
            bounds = [int(n) for n in inner.split(":")]
            group.append(bounds)
        result.append(group)
    return result


def _get_string_by_indexes(indexes: list, s: str) -> str:
    parts = []
    for group in indexes:
        group_str = ""
        for r in group:
            start = r[0]
            end = r[1] + 1 if len(r) > 1 else start + 1
            group_str += s[start:end]
        parts.append(group_str)
    return ".".join(parts)


def parse_abo_pair(key: str, value: str, lot_number: str) -> dict:
    key_str = _get_string_by_indexes(_parse_lot_string(key), lot_number)
    val_str = _get_string_by_indexes(_parse_lot_string(value), lot_number)
    parts = key_str.split(".")
    obj = {}
    current = obj
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    if parts:
        current[parts[-1]] = val_str
    return obj


def generate_pow(
    lot_number: str,
    captcha_id: str,
    *,
    hashfunc: str = "md5",
    version: str = "1",
    bits: int = 10,
    datetime: str = "",
    extra: str = "",
) -> dict:
    import hashlib
    hash_mapping = {"md5": hashlib.md5, "sha1": hashlib.sha1, "sha256": hashlib.sha256}
    if hashfunc not in hash_mapping:
        raise ValueError(f"Unsupported hash algorithm: {hashfunc}")
    hasher_creator = hash_mapping[hashfunc]
    remainder = bits % 4
    zero_count = bits // 4
    prefix = "0" * zero_count
    thresholds = {1: "7", 2: "3", 3: "1"}
    threshold = thresholds.get(remainder)
    header = f"{version}|{bits}|{hashfunc}|{datetime}|{captcha_id}|{lot_number}|{extra}|"
    while True:
        rand = str(uuid.uuid4()).replace("-", "")
        message = header + rand
        h = hasher_creator(message.encode()).hexdigest()
        if not h.startswith(prefix):
            continue
        if remainder == 0:
            return {"pow_msg": message, "pow_sign": h}
        elif h[zero_count] <= threshold:
            return {"pow_msg": message, "pow_sign": h}


def _build_w_crypto(plaintext: str) -> str:
    key_bytes = uuid.uuid4().hex[:16].encode()
    padded = Padding.pad(plaintext.encode(), AES.block_size, style="pkcs7")
    cipher = AES.new(key_bytes, AES.MODE_CBC, b"0" * 16).encrypt(padded)
    enc_key = PKCS1_v1_5.new(_RSA_KEY).encrypt(key_bytes)
    return cipher.hex() + enc_key.hex()

logger = logging.getLogger(__name__)

CAPTCHA_ID_DEFAULT = "fb563cdbdef8b3ab730527afa51db3d8"
APPID_DEFAULT = "9ia4hndgblg9xihxcwgdjt9ztg8sjwaf"
CLIENT_REPORT_URL = "https://riskct.geetest.com/g2/api/v1/client_report"
PRE_LOAD_URL = "https://riskct.geetest.com/g2/api/v1/pre_load"
GCAPTCHA4_BASE = "https://gcaptcha4-hrc.gsensebot.com"
STATIC_BASE = "https://static.geetest.com"

CAPTCHASONIC_KEYS: List[str] = []


def _load_captchasonic_keys() -> List[str]:
    global CAPTCHASONIC_KEYS
    if CAPTCHASONIC_KEYS:
        return CAPTCHASONIC_KEYS

    keys: List[str] = []
    config_path = Path(__file__).resolve().parent / "gui_tk_config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k in cfg.get("captchasonic_api_keys", []):
            if k and k not in keys:
                keys.append(k)
        single = cfg.get("captchasonic_api_key", "")
        if single and single not in keys:
            keys.append(single)
    except Exception:
        pass

    for env_key in ("CAPTCHASONIC_API_KEYS", "CAPTCHASONIC_API_KEY"):
        val = os.environ.get(env_key, "")
        for part in re.split(r"[,\s;]+", val):
            part = part.strip()
            if part and part not in keys:
                keys.append(part)

    CAPTCHASONIC_KEYS = keys
    return keys


def _get_captchasonic_client():
    """Lazy import do CaptchaSonicClient do SSBROWSER."""
    try:
        from captchasonic_client import CaptchaSonicClient
        keys = _load_captchasonic_keys()
        if not keys:
            logger.warning("Nenhuma chave de solver encontrada")
            return None
        key = keys[random.randint(0, len(keys) - 1)]
        return CaptchaSonicClient(api_key=key, polling_interval=2.0, polling_timeout=60.0)
    except ImportError:
        logger.warning("cliente do solver nao disponivel")
        return None
    except Exception as exc:
        logger.warning(f"solver init falhou: {exc}")
        return None


def _split_nine_image(combined_bytes: bytes) -> List[bytes]:
    """Recorta grid 3x3 em 9 tiles JPEG."""
    from PIL import Image
    import io

    im = Image.open(io.BytesIO(combined_bytes)).convert("RGB")
    w, h = im.size
    tw, th = w // 3, h // 3
    tiles: List[bytes] = []
    for row in range(3):
        for col in range(3):
            crop = im.crop((col * tw, row * th, (col + 1) * tw, (row + 1) * th))
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=92)
            tiles.append(buf.getvalue())
    return tiles


class GeeTestSolver:
    """Resolve GeeTest v4 nine-grid captcha sem browser."""

    def __init__(
        self,
        captcha_id: str = CAPTCHA_ID_DEFAULT,
        appid: str = APPID_DEFAULT,
        site_url: str = "https://gtwin.com",
        proxy: Optional[str] = None,
        device_user_agent: Optional[str] = None,
        device_impersonate: Optional[str] = None,
        external_session: Optional[Any] = None,
    ):
        self.captcha_id = captcha_id
        self.appid = appid
        self.site_url = site_url.rstrip("/")
        self.proxy = proxy
        self.challenge = str(uuid.uuid4())
        self.callback = f"geetest_{int(time.time() * 1000)}"
        # O tipo do captcha (nine/icon) e decidido pelo servidor a cada /load e
        # pode ALTERNAR entre tentativas (nine falha -> vem icon, e vice-versa).
        # Nao forcamos risk_type no load: o verify usa o captcha_type lido do
        # proprio captcha_data (fonte de verdade).
        # IDENTIDADE DE DEVICE: o mesmo device que coleta o geetoken e faz o
        # registro TEM que ser o que resolve o captcha (client_report, load e
        # verify na mesma "pessoa"). O default historico (Edge desktop) só
        # vale quando o proprio registro e desktop. Ao registrar como Android
        # (x-device 2-3, OPPO/CPH2521), o solver DEVE usar o mesmo UA mobile
        # e impersonate android — senao o GeeTest pontua mismatch de device e
        # a conta nasce excluida da campanha de bonus (taskRedDot null).
        ua = str(device_user_agent or "").strip()
        is_android = "android" in ua.lower()
        self.device_user_agent = ua
        self.is_android = is_android
        self.captcha_client_type = "h5" if is_android else "web"
        impersonate = device_impersonate or os.getenv("HTTP_PROFILE", "") or ("chrome131_android" if is_android else "chrome124")
        if external_session is not None:
            self.session = external_session
        else:
            self.session = CurlSession(impersonate=impersonate, verify=False)
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        # Identificador de sessão do captcha (cookie captcha_v4_user) exigido pelo GeeTest
        self.captcha_v4_user = uuid.uuid4().hex.replace("-", "")
        self.session.cookies.set("captcha_v4_user", self.captcha_v4_user, domain=".gsensebot.com")
        self.session.cookies.set("captcha_v4_user", self.captcha_v4_user, domain=".geetest.com")
        if ua:
            self.session.headers.update({
                "accept": "*/*",
                "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="128", "Google Chrome";v="128"',
                "sec-ch-ua-mobile": "?1" if is_android else "?0",
                "sec-ch-ua-platform": '"Android"' if is_android else '"Windows"',
                "user-agent": ua,
            })
        else:
            self.session.headers.update({
                "accept": "*/*",
                "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
                "sec-ch-ua": '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
            })

    def _new_callback(self) -> str:
        self.callback = f"geetest_{int(time.time() * 1000) + random.randint(0, 9999)}"
        return self.callback

    def _parse_jsonp(self, text: str) -> dict:
        m = re.search(r"\((.*)\)", text, re.S)
        if m:
            return json.loads(m.group(1))
        return json.loads(text)

    # ---- Step 1: pre_load + client_report → gee_token ----

    def get_gee_token(self, existing_token: str = "") -> str:
        """Se existing_token for fornecido (do geetokens.py), usa direto.
        Senão, tenta pre_load + client_report (pode falhar sem JS GeeGuard)."""
        if existing_token and existing_token != "disabled":
            return existing_token

        cb = self._new_callback()
        resp = self.session.get(
            PRE_LOAD_URL,
            params={
                "client_type": self.captcha_client_type,
                "appid": self.appid,
                "callback": cb,
            },
            timeout=15,
        )
        data = self._parse_jsonp(resp.text).get("data", {})
        g_token = data.get("g_token", "")

        if not g_token:
            raise RuntimeError(f"pre_load sem g_token: {resp.text[:200]}")

        js_url = f"{STATIC_BASE}{data.get('static_path', '')}{data.get('js', '')}"
        self.session.get(js_url, timeout=15)

        report_headers = {
            "api-version": "1",
            "appid": self.appid,
            "client-type": "3",
            "content-type": "application/x-www-form-urlencoded",
            "origin": self.site_url,
        }

        # Dados de telemetria consistentes para Chrome desktop (simula GeeGuard JS)
        telemetry = {
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
            "platform": "Win32",
            "language": "pt-BR",
            "languages": ["pt-BR", "pt", "en-US", "en"],
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "maxTouchPoints": 0,
            "cookieEnabled": True,
            "doNotTrack": None,
            "vendor": "Google Inc.",
            "onLine": True,
            "connection": {"effectiveType": "4g", "downlink": 10, "rtt": 50},
            "plugins": [
                {"name": "Chrome PDF Plugin", "filename": "internal-pdf-viewer"},
                {"name": "Chrome PDF Viewer", "filename": "mhjfbmdgcfjbbpaeojofohoefgiehjai"},
                {"name": "Native Client", "filename": "internal-nacl-plugin"}
            ],
            "mimeTypes": [
                {"type": "application/pdf", "suffixes": "pdf"},
                {"type": "application/x-google-chrome-pdf", "suffixes": "pdf"}
            ],
            "screen": {
                "width": 1920, "height": 1080,
                "availWidth": 1920, "availHeight": 1040,
                "colorDepth": 24, "pixelDepth": 24
            },
            "timezoneOffset": 180,
            "canvasFingerprint": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQImWNgYGBgAAAABQABh6FO1AAAAABJRU5ErkJggg==",
            "webgl": {
                "vendor": "WebKit WebGL",
                "renderer": "WebKit",
                "unmaskedVendor": "Google Inc. (NVIDIA)",
                "unmaskedRenderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "extensions": ["ANGLE_instanced_arrays", "EXT_blend_minmax", "EXT_color_buffer_half_float"]
            },
            "performance": {
                "now": int(time.time() * 1000),
                "memory": {"usedJSHeapSize": 10000000, "totalJSHeapSize": 20000000, "jsHeapSizeLimit": 400000000}
            }
        }

        payload_b64 = base64.b64encode(json.dumps({
            "passtime": 0,
            "lot_number": "",
            "gen_time": str(int(time.time())),
            "pass_token": "",
            "captcha_output": "",
            "device_id": str(uuid.uuid4()),
            "setLang": "pt-br",
            "lang": "pt-br",
            "pt": 0,
            "gt": g_token,
            "telemetry": telemetry,
        }).encode()).decode()
        body = payload_b64

        resp2 = self.session.post(CLIENT_REPORT_URL, headers=report_headers, data=body.encode("utf-8"), timeout=15)
        resp_data = json.loads(resp2.text)
        gee_token = resp_data.get("data", {}).get("gee_token", "")
        if not gee_token:
            raise RuntimeError(f"client_report sem gee_token: {resp2.text[:200]}")
        return gee_token

    # ---- Step 2: gcaptcha4 load → lot_number, imgs, ques ----

    def load_captcha(self) -> dict:
        cb = self._new_callback()
        resp = self.session.get(
            f"{GCAPTCHA4_BASE}/load",
            params={
                "callback": cb,
                "captcha_id": self.captcha_id,
                "challenge": self.challenge,
                "client_type": self.captcha_client_type,
                "lang": "por",
            },
            timeout=15,
        )
        # Captura cookies g_state e g5_ts do GeeTest
        for cookie_name in ("g_state", "g5_ts"):
            cookie_val = resp.cookies.get(cookie_name)
            if cookie_val:
                logger.debug(f"[GeeTest] cookie {cookie_name}: {cookie_val[:50]}...")
        data = self._parse_jsonp(resp.text).get("data", {})
        if not data.get("lot_number"):
            raise RuntimeError(f"gcaptcha4 load falhou: {resp.text[:200]}")
        return data

    # ---- Step 3: resolver nine via solver externo ----

    def solve_nine(self, captcha_data: dict) -> Tuple[List[int], Optional[List[Tuple[int, float]]]]:
        """Resolve o grid 3x3.

        Retorna (indices, scores). scores e a lista (index, distancia) do solver
        local (None quando o provider externo resolveu), tal que menor distancia
        = melhor match. Isso permite ao chamador descartar grids de baixa
        confianca ANTES de gastar um verify no servidor.

        Ordem: solver local (visao computacional, sem custo/rede) e, apenas se
        ele nao estiver disponivel ou falhar, o provider externo como fallback.
        """
        imgs_url = captcha_data.get("imgs", "")
        ques_urls = captcha_data.get("ques", [])
        if not imgs_url:
            raise RuntimeError("sem imgs no captcha data")

        full_imgs_url = f"{STATIC_BASE}/{imgs_url}" if not imgs_url.startswith("http") else imgs_url
        resp_imgs = self.session.get(full_imgs_url, timeout=15)
        grid_bytes = resp_imgs.content

        prompt_bytes = None
        if ques_urls:
            q_url = ques_urls[0]
            full_q_url = f"{STATIC_BASE}/{q_url}" if not q_url.startswith("http") else q_url
            resp_q = self.session.get(full_q_url, timeout=15)
            prompt_bytes = resp_q.content

        # --- 1) Solver local (default) ---
        # O modelo local é a primeira escolha quando os assets estão presentes;
        # GEETEST_LOCAL_SOLVER=0 permite desativá-lo explicitamente para
        # investigar divergências de matching sem configurar um provider externo.
        local_solver_on = os.getenv("GEETEST_LOCAL_SOLVER", "1").strip().lower() not in ("0", "false", "no", "off")
        if prompt_bytes and local_solver_on:
            try:
                from nine_yolo_solver import is_available, solve_nine_local

                if is_available():
                    indices, scores = solve_nine_local(grid_bytes, prompt_bytes)
                    ranked = ", ".join(f"{i}:{s:.2f}" for i, s in sorted(scores, key=lambda x: x[1]))
                    logger.debug(f"[GeeTest-Local] indices={sorted(indices)} scores=({ranked})")
                    if indices:
                        return indices, scores
            except Exception as exc:
                logger.warning(f"[GeeTest-Local] falhou, usando fallback externo: {exc}")

        # --- 2) Fallback: provider externo ---
        client = _get_captchasonic_client()
        if not client:
            raise RuntimeError("solver local indisponivel e sem provider externo")

        tiles = cast("List[ImageInput]", _split_nine_image(grid_bytes))
        indices = client.solve_geetest_v4_nine(
            captcha_id=self.captcha_id,
            images=tiles,
            question="geetest_nine:Selecione  3  imagens correspondentes",
            examples=[prompt_bytes] if prompt_bytes else None,
            website_url=self.site_url,
        )
        if not indices:
            raise RuntimeError("solver retornou indices vazios")
        logger.debug(f"[GeeTest-Local] indices={sorted(indices)}")
        return indices, None

    @staticmethod
    def _confidence(
        scores: Optional[List[Tuple[int, float]]],
        indices: List[int],
        max_third: float = 3.2,
        max_avg: float = 2.55,
        min_margin: float = 0.1,
    ) -> Tuple[bool, float]:
        """Avalia a confianca da predicao local.

        Retorna (low, cost):
          - low  = True quando o grid deve ser descartado (baixa confianca).
          - cost = metrica finita comparavel entre grids; MENOR = mais confiavel.
                   Combina distancia do 3o escolhido, media do top-3 e (inverso
                   da) margem para o 4o. Usada para escolher, entre os grids
                   descartados, qual vale um verify de ultimo recurso quando o
                   orcamento de descartes se esgota.

        Regra dual-axis calibrada em 18 amostras ao vivo (7 PASS / 11 FAIL):
          REJEITA se: third > 3.2  OU  top3_avg > 2.55  OU  margin < 0.1
          rejected_fail=7  rejected_pass=1  (ratio 7:1)

        Estrategia: melhor rejeitar um grid barato (0.83s local) e puxar novo
        lote do que gastar um verify server-side com predicao ruim — cada falha
        incrementa fail_count no servidor e o proximo captcha fica mais dificil.
        Mas, esgotado o orcamento, verificar o MELHOR grid ja visto e melhor do
        que verificar um grid novo qualquer.

        Retorna (False, inf) quando nao ha scores locais (provider externo), pois
        a confianca nao e observavel por este criterio.

        Tunable via env vars:
          GEETEST_MAX_THIRD_DIST  (default 3.2)
          GEETEST_MAX_AVG         (default 2.55)
          GEETEST_MIN_MARGIN      (default 0.1)
        """
        if not scores:
            return False, float("inf")
        ranked = sorted(scores, key=lambda x: x[1])
        if len(ranked) < 3:
            return False, float("inf")
        third_dist = ranked[2][1]
        fourth_dist = ranked[3][1] if len(ranked) > 3 else float("inf")
        margin = fourth_dist - third_dist
        avg = (ranked[0][1] + ranked[1][1] + ranked[2][1]) / 3.0
        # Margem relativa: quando os scores são muito baixos (alta confiança),
        # uma margem absoluta pequena é normal. Só exige margem quando os
        # scores estão altos (baixa confiança).
        margin_ok = margin >= min_margin or third_dist < 0.1
        low = third_dist > max_third or avg > max_avg or not margin_ok
        # Custo: soma do 3o com a media do top-3, penalizada por margem estreita.
        # Todos os termos finitos (margin>=0), entao o melhor grid e sempre
        # comparavel mesmo entre lotes reciclados pelo servidor.
        margin_pen = 1.0 / (margin + 0.1)
        cost = third_dist + avg + margin_pen
        if low:
                logger.debug(
                    f"[GeeTest-Local] descarte por confianca: 3o={third_dist:.2f} "
                f"avg={avg:.2f} margem={margin:.2f}"
            )
        return low, cost

    # ---- Step 4: gcaptcha4 verify → pass_token, gen_time, captcha_output ----

    @staticmethod
    def _indices_to_coords(indices: List[int]) -> List[List[int]]:
        """Converte indices 0..8 (row-major) para o userresponse do gcaptcha4: [row+1, col+1].

        Derivado da geometria dos cliques reais em real_w_payload_final.json.
        O new_track da mesma sessao registra os 3 mouseup em (x,y) normalizados
        (0.159,0.812), (0.792,0.544), (0.852,0.808) -> celulas 6, 5, 8, e o
        userresponse enviado foi [[3,1],[2,3],[3,3]]. Somente [row+1, col+1]
        reproduz esses pares; [col+1, row+1] produz [[1,3],[3,2],[3,3]].

        Selecoes simetricas na diagonal nao distinguem as duas convencoes, por
        isso comparar apenas o conjunto de indices induz ao erro.
        """
        coords = []
        for idx in indices:
            row = idx // 3
            col = idx % 3
            coords.append([row + 1, col + 1])
        return coords

    @staticmethod
    def _generate_new_track(duration_ms: int = None) -> Tuple[dict, str]:
        """Gera track de mouse que simula movimento humano real.

        Baseado no track real do browser (real_w_payload_final.json):
        - Duração ~3000ms (não 1500ms)
        - Começa na área do captcha (não no canto)
        - Primeiro movimento após ~900ms (usuário pensa antes de mover)
        - Movimento com propósito: vai para as células do captcha
        - Velocidade variável: 0.02-2.7 px/ms
        - Pausas entre cliques
        """
        if duration_ms is None:
            duration_ms = random.randint(2200, 3500)
        
        start = int(time.time() * 1000) - duration_ms - random.randint(300, 1200)
        end = start + duration_ms
        points = []

        # Começa na área do captcha (não no canto)
        x = random.uniform(0.60, 0.75)
        y = random.uniform(0.70, 0.80)

        # Fase 1: usuário pensa antes de mover (800-1200ms parado)
        think_time = random.randint(800, 1200)
        points.append([0, round(x, 4), round(y, 4), 0])

        # Fase 2: primeiro movimento lento para a primeira célula
        t = think_time
        first_target_x = random.uniform(0.55, 0.70)
        first_target_y = random.uniform(0.50, 0.65)
        steps_to_first = random.randint(5, 8)
        for i in range(steps_to_first):
            progress = (i + 1) / steps_to_first
            t += random.randint(15, 30)
            # Movimento suave para o alvo
            x += (first_target_x - x) * progress * random.uniform(0.3, 0.6)
            y += (first_target_y - y) * progress * random.uniform(0.3, 0.6)
            # Pequeno tremor
            x += random.gauss(0, 0.003)
            y += random.gauss(0, 0.003)
            x = max(0.02, min(0.98, x))
            y = max(0.02, min(0.98, y))
            points.append([t, round(x, 4), round(y, 4), 1])

        # Fase 3: movimento entre células (com pausas)
        num_clicks = random.randint(2, 4)
        for click in range(num_clicks):
            # Move para a próxima célula
            target_x = random.uniform(0.40, 0.80)
            target_y = random.uniform(0.30, 0.70)
            steps = random.randint(3, 6)
            for i in range(steps):
                progress = (i + 1) / steps
                t += random.randint(15, 35)
                # Acelera e desacelera (perfil de velocidade humano)
                speed = 0.5 + 0.5 * math.sin(progress * math.pi)
                x += (target_x - x) * progress * speed * 0.4
                y += (target_y - y) * progress * speed * 0.4
                x += random.gauss(0, 0.002)
                y += random.gauss(0, 0.002)
                x = max(0.02, min(0.98, x))
                y = max(0.02, min(0.98, y))
                points.append([t, round(x, 4), round(y, 4), 1])

            # Pausa antes do click (50-150ms)
            t += random.randint(50, 150)
            points.append([t, round(x, 4), round(y, 4), 0])

            # Click
            points.append([t, round(x, 4), round(y, 4), 2])

        # Fase 4: último movimento para o botão de confirmar (se houver)
        if random.random() < 0.7:
            confirm_x = random.uniform(0.50, 0.60)
            confirm_y = random.uniform(0.75, 0.85)
            steps = random.randint(4, 7)
            for i in range(steps):
                progress = (i + 1) / steps
                t += random.randint(15, 30)
                x += (confirm_x - x) * progress * 0.5
                y += (confirm_y - y) * progress * 0.5
                x += random.gauss(0, 0.002)
                y += random.gauss(0, 0.002)
                x = max(0.02, min(0.98, x))
                y = max(0.02, min(0.98, y))
                points.append([t, round(x, 4), round(y, 4), 1])

        td_data = {
            "m": 1,
            "w": 301.8125,
            "h": 261.15625,
            "s": start,
            "e": end,
            "p": points,
        }
        import gzip as _gzip
        compressed = _gzip.compress(json.dumps(td_data, separators=(",", ":")).encode())
        td_str = base64.urlsafe_b64encode(compressed).decode().rstrip("=")
        return td_data, td_str

    def _build_w(self, captcha_data: dict, indices: List[int], userresponse=None, slide_left: Optional[float] = None) -> Tuple[str, str]:
        lot_number = captcha_data["lot_number"]
        pow_detail = captcha_data.get("pow_detail", {})
        pt = int(captcha_data.get("pt", 1))

        track, td_str = self._generate_new_track()
        passtime = track["e"] - track["s"]

        pow_fields = generate_pow(lot_number, self.captcha_id, **pow_detail)
        abo_fields = parse_abo_pair(WuluConfig.abo_key, WuluConfig.abo_val, lot_number)
        
        is_icon = isinstance(userresponse, list) and len(userresponse) > 0 and isinstance(userresponse[0], (list, tuple))
        is_slide = slide_left is not None
        
        # Todos usam wd:1 com gee_guard
        _em = {"ph": 0, "cp": 0, "ek": "11", "wd": 1, "nt": 0, "si": 0, "sc": 0}
        _extra = {
            "gee_guard": {
                "roe": {
                    "auh": "3", "aup": "3", "cdc": "3", "egp": "3",
                    "res": "3", "rew": "3", "sep": "3", "snh": "3",
                }
            }
        }
        if is_slide:
            # Formato slide do GEEKED: setLeft = left raw (px),
            # userresponse = left / 1.0059466666666665 + 2 (float),
            # passtime random 600-1200ms (tempo de arraste humano).
            _left = float(slide_left)
            payload = {
                "passtime": random.randint(600, 1200),
                "setLeft": _left,
                "userresponse": _left / 1.0059466666666665 + 2,
                "device_id": "",
                "lot_number": lot_number,
                **pow_fields,
                "geetest": "captcha",
                "lang": "zh",
                "ep": "123",
                "biht": WuluConfig.biht,
                WuluConfig.lib_key: WuluConfig.lib_val,
                **abo_fields,
                "em": _em,
                **_extra,
            }
        else:
            payload = {
                "passtime": passtime,
                # icon arrows: coords em unidades Geetest (*33/*49) direto do
                # IconClassifier; nine: indices 0..8 convertidos para [row+1, col+1].
                "userresponse": userresponse if userresponse is not None else self._indices_to_coords(indices),
                "device_id": "",
                "lot_number": lot_number,
                **pow_fields,
                "geetest": "captcha",
                "lang": "zh",
                "ep": "123",
                "biht": WuluConfig.biht,
                WuluConfig.lib_key: WuluConfig.lib_val,
                **abo_fields,
                "em": _em,
                **_extra,
                "new_track": track,
            }

        plaintext = json.dumps(payload, separators=(",", ":"))
        
        # Log para debug: validar estrutura do w
        logger.debug(f"[GeeTest-W] payload keys: {list(payload.keys())}")
        logger.debug(f"[GeeTest-W] passtime: {payload.get('passtime')}")
        logger.debug(f"[GeeTest-W] userresponse: {payload.get('userresponse')}")
        new_track = payload.get('new_track', {})
        logger.debug(f"[GeeTest-W] new_track points: {len(new_track.get('p', []))}")
        logger.debug(f"[GeeTest-W] em.wd: {payload.get('em', {}).get('wd')}")
        logger.debug(f"[GeeTest-W] has gee_guard: {'gee_guard' in payload}")
        
        # pure http - use local crypto (no wreq dependency)
        return _build_w_crypto(plaintext), td_str

    def verify_captcha(self, captcha_data: dict, indices: List[int], userresponse=None, slide_left: Optional[float] = None) -> dict:
        lot_number = captcha_data["lot_number"]
        process_token = captcha_data.get("process_token", "")
        payload_from_load = captcha_data.get("payload", "")
        payload_protocol = str(captcha_data.get("payload_protocol", "1"))
        pt = str(captcha_data.get("pt", "1"))
        risk_type = str(captcha_data.get("captcha_type") or "").strip() or "slide"

        w, td = self._build_w(captcha_data, indices, userresponse=userresponse, slide_left=slide_left)

        cb = self._new_callback()
        params = {
            "callback": cb,
            "captcha_id": self.captcha_id,
            "client_type": self.captcha_client_type,
            "lot_number": lot_number,
            "risk_type": risk_type,
            "payload": payload_from_load,
            "process_token": process_token,
            "payload_protocol": payload_protocol,
            "pt": pt,
            "w": w,
        }
        # td (track data) e enviado para nine e slide; icon nao usa
        if risk_type in ("nine", "slide"):
            params["td"] = td
        resp = self.session.get(
            f"{GCAPTCHA4_BASE}/verify",
            params=params,
            timeout=15,
        )
        data = self._parse_jsonp(resp.text).get("data", {})
        seccode = data.get("seccode", {})
        if not seccode.get("pass_token"):
            raise RuntimeError(f"verify sem pass_token: {resp.text[:300]}")
        
        # Log para debug: verificar se result tem feedback de qualidade
        result = data.get("result")
        if result and result != "success":
            logger.debug(f"[GeeTest] verify result: {result}")
        
        # Log seccode keys para validar estrutura
        logger.debug(f"[GeeTest] seccode keys: {list(seccode.keys())}")
        
        return seccode

    def _verify_candidates(self, captcha_data: dict, candidates: List[List[int]]) -> dict:
        max_attempts = min(5, len(candidates))
        for i, indices in enumerate(candidates[:max_attempts]):
            try:
                return self.verify_captcha(captcha_data, indices)
            except Exception as exc:
                err_str = str(exc)
                if "Operation timed out" in err_str:
                    raise
                if "567" in err_str or "fail_count" in err_str:
                    logger.warning(f"[GeeTest] verify attempt {i+1}/{max_attempts} falhou: {err_str[:100]}")
                continue
        raise RuntimeError(f"Nenhuma combinacao funcionou ({max_attempts} tentativas)")

    def _generate_candidate_combos(self, sonic_indices: List[int]) -> List[List[int]]:
        if not sonic_indices:
            return []
        candidates: List[List[int]] = []
        base = sorted(sonic_indices)
        candidates.append(base)
        for i in range(3):
            removed = base[i]
            for replacement in range(9):
                if replacement in base:
                    continue
                combo = sorted(base[:i] + base[i+1:] + [replacement])
                if combo not in candidates:
                    candidates.append(combo)
        return candidates

    # ---- Step 5: validate/v4 (server-side) ----

    def build_validate_payload(self, device_id: str, seccode: dict) -> dict:
        # CapSolver mostra que o servidor só aceita estes 5 campos.
        # Campos extras (account, referer, mode, time) causam recusa.
        return {
            "captcha_id": self.captcha_id,
            "lot_number": seccode["lot_number"],
            "pass_token": seccode["pass_token"],
            "gen_time": seccode["gen_time"],
            "captcha_output": seccode["captcha_output"],
        }

    # ---- Fluxo completo ----

    def solve(self, device_id: str = "", existing_gee_token: str = "") -> dict:
        """
        Executa o fluxo completo (100% HTTP) e retorna o payload para validate/v4.

        Cada verify usa um lot_number NOVO (load + solve + 1 verify). Reaproveitar
        o mesmo lot_number apos um verify com result=fail incrementa fail_count e o
        GeeTest passa a rejeitar qualquer resposta daquele lote, por isso nao se
        tentam combinacoes alternativas sobre o mesmo captcha.

        Grids de baixa confianca (3o escolhido com distancia alta ou margem
        estreita para o 4o candidato) sao descartados LOCALMENTE, antes de gastar
        um verify no servidor: custam 0.83s de CPU e zero round-trip de verify,
        e nao incrementam fail_count. So quando o orcamento de descartes acaba
        um verify e arriscado mesmo assim (dosador de ultimo recurso).

        Orcamentos configuráveis por env:
          GEETEST_MAX_ATTEMPTS     (default 10) verify executados no servidor
          GEETEST_MAX_DISCARDS     (default 3)  descartes locais baratos
          GEETEST_MAX_THIRD_DIST   (default 3.6) limiar de distancia do 3o escolhido
          GEETEST_MIN_MARGIN       (default 0.05) margem minima para o 4o candidato
        """
        solve_start = time.time()
        
        if not device_id:
            device_id = str(uuid.uuid4())

        gee_token = ""
        if existing_gee_token and existing_gee_token != "disabled":
            gee_token = existing_gee_token
            logger.debug(f"[GeeTest] gee_token (cache): {gee_token[:30]}...")
        # Sem gee_token: o solver segue sem (o client_report HTTP puro e
        # rejeitado -50002 pelo GeeTest porque o payload exige fingerprint
        # GeeGuard assinado por JS; a obtencao do token real fica a cargo do
        # chamador async via pipeline geetokens.py).

        max_retries = max(1, int(os.getenv("GEETEST_MAX_ATTEMPTS", "10") or "10"))
        # GEETEST_LOCAL_FILTER=1 (default) ativa o descarte local; =0 restaura a
        # logica do commit 11cc7f4 (solver HTTP puro: todo grid vai a verify).
        local_filter_enabled = os.getenv("GEETEST_LOCAL_FILTER", "1").strip().lower() not in ("0", "false", "no", "off")
        max_discards = max(0, int(os.getenv("GEETEST_MAX_DISCARDS", "3") or "3"))
        max_third_dist = float(os.getenv("GEETEST_MAX_THIRD_DIST", "3.6") or "3.6")
        max_avg = float(os.getenv("GEETEST_MAX_AVG", "2.9") or "2.9")
        min_margin = float(os.getenv("GEETEST_MIN_MARGIN", "0.05") or "0.05")

        seccode = None
        last_error: Optional[Exception] = None
        discarded = 0
        # Melhor grid descartado ate agora (menor cost). Verificado como ultimo
        # recurso quando o orcamento de descartes acaba, em vez de gastar verify
        # num grid novo tao ruim quanto os ja descartados.
        best_discarded: Optional[Tuple[float, dict, List[int]]] = None

        def _try_verify(cap: dict, idx: List[int], tag: str, userresponse=None, slide_left: Optional[float] = None) -> Optional[dict]:
            nonlocal last_error
            try:
                sc = self.verify_captcha(cap, idx, userresponse=userresponse, slide_left=slide_left)
                logger.debug(f"[GeeTest] pass_token{tag}: {sc['pass_token'][:30]}...")
                return sc
            except Exception as exc:
                last_error = exc
                logger.debug(f"[GeeTest] verify{tag} falhou: {str(exc)[:180]}")
                self.challenge = str(uuid.uuid4())
                return None

        last_logged_type = ""
        for attempt in range(1, max_retries + 1):
            try:
                captcha_data = self.load_captcha()
                ctype = str(captcha_data.get("captcha_type") or "").strip()
                # Loga o tipo apenas quando muda entre tentativas (evita spam
                # de "captcha type=icon" repetido quando o tipo nao alterna).
                if ctype != last_logged_type:
                    last_logged_type = ctype

                # Icon arrows e objects usam solvers locais quando os assets
                # estão presentes. O matcher remoto permanece apenas como
                # fallback explícito por configuração.
                # O tipo pode ALTERNAR entre tentativas (nine -> icon -> nine).
                if ctype == "icon":
                    from icon_solver import IconClassifier, IconModelUnavailable, classify_icon_variant

                    ques_urls = captcha_data.get("ques", [])
                    variant = classify_icon_variant(ques_urls)
                    imgs_url = str(captcha_data.get("imgs") or "").strip()
                    if not imgs_url:
                        raise RuntimeError("sem imgs no captcha data (icon)")
                    full_imgs_url = f"{STATIC_BASE}/{imgs_url}" if not imgs_url.startswith("http") else imgs_url
                    main_bytes = self.session.get(full_imgs_url, timeout=15).content
                    full_ques_urls = [
                        f"{STATIC_BASE}/{q}" if not str(q).startswith("http") else str(q)
                        for q in ques_urls
                    ]
                    prompt_bytes_list = [
                        self.session.get(prompt_url, timeout=15).content
                        for prompt_url in full_ques_urls
                    ]
                    if variant == "objects":
                        # Objects: matcher local por padrão. O opt-out evita
                        # gastar tentativas quando os assets forem removidos.
                        if os.getenv("GEETEST_ICON_OBJECTS", "1").strip().lower() in ("0", "false", "no", "off"):
                            logger.debug(f"[GeeTest] icon objects desabilitado, esperando 1s e tentando de novo...")
                            self.challenge = str(uuid.uuid4())
                            time.sleep(1.0)
                            continue
                        from icon_objects_local import is_available, match_positions

                        if not is_available():
                            raise RuntimeError("icon objects local indisponivel")
                        pixel_positions = match_positions(main_bytes, prompt_bytes_list)
                        if not pixel_positions:
                            raise RuntimeError("icon objects local retornou sem posicoes")
                        coords = [[x * 33, y * 49] for x, y in pixel_positions]
                        logger.debug(f"[GeeTest-Icon] objects coords={coords}")
                    else:
                        try:
                            coords = IconClassifier(main_bytes, full_ques_urls).find_icon_position()
                            logger.debug(f"[GeeTest-Icon] arrows coords={coords}")
                        except IconModelUnavailable:
                            from icon_objects_local import is_available, match_positions

                            if not is_available():
                                raise
                            pixel_positions = match_positions(main_bytes, prompt_bytes_list)
                            if not pixel_positions:
                                raise RuntimeError("icon objects local retornou sem posicoes")
                            coords = [[x * 33, y * 49] for x, y in pixel_positions]
                            logger.debug(f"[GeeTest-Icon] fallback objects coords={coords}")
                    seccode = _try_verify(captcha_data, [], " (icon)", userresponse=coords)
                    if seccode:
                        break
                    continue

                # Slide: background (bg) + peca (slice).
                # CaptchaSonic HTTP nao resolve GeeTest v4 slide (so browser nativo).
                # Trata como icon objects: espera 1s e tenta de novo (tipo pode alternar).
                if ctype == "slide":
                    from slide_solver import SlideSolver as _SlideSolver
                    bg_url = str(captcha_data.get("bg") or "").strip()
                    slice_url = str(captcha_data.get("slice") or "").strip()
                    if not bg_url or not slice_url:
                        raise RuntimeError(
                            f"slide sem bg/slice (keys={sorted(captcha_data.keys())})"
                        )
                    bg_full = f"{STATIC_BASE}/{bg_url}" if not bg_url.startswith("http") else bg_url
                    slice_full = f"{STATIC_BASE}/{slice_url}" if not slice_url.startswith("http") else slice_url
                    bg_bytes = self.session.get(bg_full, timeout=15).content
                    slice_bytes = self.session.get(slice_full, timeout=15).content
                    solver = _SlideSolver(slice_bytes, bg_bytes)
                    left = solver.find_puzzle_piece_position() + random.uniform(0, 0.5)
                    logger.debug(f"[GeeTest-Slide] left={left:.1f}")
                    seccode = _try_verify(captcha_data, [], " (slide)", slide_left=left)
                    if seccode:
                        break
                    continue

                indices, scores = self.solve_nine(captcha_data)
                logger.debug(f"[GeeTest] indices solver: {indices}")

                low, cost = (False, float("inf"))
                if local_filter_enabled and scores is not None:
                    low, cost = self._confidence(
                        scores, indices, max_third=max_third_dist, max_avg=max_avg, min_margin=min_margin
                    )

                # Descarte barato de grids de baixa confianca (sem rede, sem
                # verify, sem fail_count no servidor) enquanto houver orcamento.
                # GEETEST_LOCAL_FILTER=0 desliga o descarte: TODO grid vai para
                # verify no servidor (logica do commit 11cc7f4, usada quando o
                # matching local nao esta calibrado para a plataforma).
                if scores is not None and low and discarded < max_discards:
                    discarded += 1
                    # Guarda o melhor descartado para o verify de ultimo recurso.
                    if best_discarded is None or cost < best_discarded[0]:
                        best_discarded = (cost, captcha_data, indices)
                    logger.debug(
                        f"[GeeTest-Local] descartado lot={captcha_data['lot_number']} "
                        f"({discarded}/{max_discards}) cost={cost:.2f}"
                    )
                    self.challenge = str(uuid.uuid4())
                    continue

                seccode = _try_verify(captcha_data, indices, "")
                if seccode:
                    break
                # verify falhou: considera este grid como candidato de fallback
                # tambem (cost finito), caso os proximos sejam piores.
                if scores is not None and (best_discarded is None or cost < best_discarded[0]):
                    best_discarded = (cost, captcha_data, indices)
            except Exception as exc:
                last_error = exc
                logger.debug(f"[GeeTest] tentativa {attempt}/{max_retries} falhou: {str(exc)[:180]}")
                # Novo captcha na proxima volta (lot_number queimado)
                self.challenge = str(uuid.uuid4())
                if attempt < max_retries:
                    time.sleep(0.01)

        # Ultimo recurso: nenhum verify passou, mas ha um melhor grid descartado
        # com confianca observavel. Vale um verify — e melhor do que abortar sem
        # nunca ter submetido o candidato mais promissor.
        if not seccode and best_discarded is not None:
            cost, cap, idx = best_discarded
            logger.debug(f"[GeeTest] verificando melhor grid descartado (cost={cost:.2f})")
            seccode = _try_verify(cap, idx, " (melhor descartado)")

        if not seccode:
            raise RuntimeError(
                f"captcha nao resolvido em {max_retries} tentativas "
                f"({discarded} descartes locais): {last_error}"
            )

        # Delay humano-realista: testando sem delay mínimo
        elapsed = time.time() - solve_start
        min_human_time = 0
        if elapsed < min_human_time:
            delay = min_human_time - elapsed
            logger.debug(f"[GeeTest] delay humano: {delay:.1f}s (total {min_human_time:.1f}s)")
            time.sleep(delay)

        validate_payload = self.build_validate_payload(device_id, seccode)

        return {
            "gee_token": gee_token,
            "validate_payload": validate_payload,
        }


async def solve_geetest_for_register(
    site_url: str,
    device_id: str,
    api_url: str,
    http_client,
    captcha_id: str = CAPTCHA_ID_DEFAULT,
    proxy: str = "",
    existing_gee_token: str = "",
    *,
    sitecode: str = "",
    device_model: Optional[dict] = None,
    speed_version: str = "1.1.50",
    app_version: str = "7.0.105",
    android_version: str = "14",
    host: str = "",
    login_id: str = "",
    device_user_agent: str = "",
    use_capsolver: bool = False,
) -> Optional[dict]:
    """
    Resolve GeeTest v4 nine (100% HTTP, sem browser) e faz validate/v4 no servidor.
    Retorna o dict decodificado do validate/v4 quando code == 1, senao None.
    """
    from utils import encrypt, flash_headers

    dm = device_model or {"marca": "Samsung", "modelo": "SM-G981B", "nome": "Samsung SM-G981B"}

    # GeeToken real (fingerprint GeeGuard via pipeline geetokens.py):
    # sem token valido, sites com risk engine estrito rejeitam o login com
    # 1130 mesmo apos validate/v4 OK. Client_report HTTP puro e rejeitado
    # (-50002: payload exige fingerprint assinado por JS).
    if not existing_gee_token or existing_gee_token == "disabled":
        try:
            from geetokens import get_geetoken_individual
            gee_token_fetched = await get_geetoken_individual(site_url)
            if gee_token_fetched and gee_token_fetched != "disabled":
                existing_gee_token = gee_token_fetched
                logger.info(f"[GeeTest] gee_token obtido via pipeline: {existing_gee_token[:30]}...")
        except Exception as exc:
            logger.debug(f"[GeeTest] fetch de gee_token falhou, seguindo sem: {exc}")

    # Usa CapSolver para resolver o captcha
    if use_capsolver:
        try:
            from capsolver_geetest import solve_geetest_v4_capsolver
            logger.info(f"[{login_id}] Resolvendo GeeTest v4 via CapSolver...")
            solution = await solve_geetest_v4_capsolver(
                website_url=site_url,
                captcha_id=captcha_id,
                risk_type="nine",
            )
            if not solution:
                logger.error(f"[{login_id}] CapSolver falhou ao resolver captcha")
                return None
            validate_payload = {
                "captcha_id": solution.get("captcha_id", captcha_id),
                "lot_number": solution.get("lot_number", ""),
                "pass_token": solution.get("pass_token", ""),
                "gen_time": solution.get("gen_time", ""),
                "captcha_output": solution.get("captcha_output", ""),
            }
        except Exception as exc:
            logger.error(f"[{login_id}] CapSolver erro: {exc}")
            return None
    else:
        # Fallback para solver local
        solver = GeeTestSolver(
            captcha_id=captcha_id, site_url=site_url, proxy=proxy,
            device_user_agent=device_user_agent,
        )
        try:
            result = await asyncio.to_thread(
                solver.solve, device_id=device_id, existing_gee_token=existing_gee_token
            )
        except Exception as exc:
            logger.error(f"[GeeTest] solve HTTP falhou: {exc}")
            return None
        validate_payload = result["validate_payload"]

    encrypted = encrypt(json.dumps(validate_payload, separators=(",", ":"), ensure_ascii=False))

    # Headers identicos aos do registro: host = host da plataforma (CDN), token estatico.
    header_host = str(host or "").strip() or api_url.replace("https://", "").replace("http://", "").split("/")[0]
    headers = flash_headers(
        login_id=str(login_id or uuid.uuid4()),
        host=header_host,
        device_id=device_id,
        device_model=dm,
        url=site_url,
        sitecode=sitecode,
        speed_version=speed_version,
        app_version=app_version,
        android_version=android_version,
        mode="cipher",
        token=None,
    )
    if str(sitecode) == "11232":
        headers.pop("x-timestamp", None)
        headers.pop("x-timestamplen", None)

    try:
        resp_text = await http_client.api_request(
            api_url, "/hall/api/member/geetest/validate/v4",
            encrypted, headers, use_proxy=True,
        )
    except Exception as exc:
        logger.error(f"[GeeTest] validate/v4 request falhou: {exc}")
        return None

    decoded, _ = _decode_response(resp_text)
    if decoded and decoded.get("code") == 1:
        logger.debug("[GeeTest] validate/v4 OK")
        return decoded
    logger.warning(f"[GeeTest] validate/v4 recusou: {decoded}")
    return None


def _decode_response(resp_text: str) -> Tuple[Optional[dict], Optional[dict]]:
    from utils import decrypt, is_base64, is_json
    data = None
    if is_base64(resp_text):
        try:
            decrypted = decrypt(resp_text)
            data = json.loads(decrypted)
        except Exception:
            pass
    else:
        m = re.search(r'"encryptString":"([^"]+)"', resp_text)
        if m:
            try:
                decrypted = decrypt(m.group(1))
                data = json.loads(decrypted)
            except Exception:
                pass
        else:
            parsed = is_json(resp_text)
            data = parsed if isinstance(parsed, dict) else None
    if data and data.get("data"):
        return data, data["data"]
    return data, None
