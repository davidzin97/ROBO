# captchasonic_client.py - Cliente CaptchaSonic para SSBROWSER (app/)
#
# Baseado em https://captchasonic.com/en/docs  e  /en/docs/clients-sdks/python
# Cobre Token Services e Recognition Services com polling automatico.
# IMPORTANTE: o gRPC default falha atras de firewall/proxy corporativo (SSL ALERT).
# Este modulo usa HTTP/REST por padrao; para gRPC use transport="grpc".
#
# Uso rapido:
#   from captchasonic_client import CaptchaSonicClient
#   client = CaptchaSonicClient(api_key="sonic_...")  # ou env CAPTCHASONIC_API_KEY
#   print(client.get_balance())
#   tiles = CaptchaSonicClient.split_geetest_nine_image("tiles.jpg")
#   ans = client.solve_geetest_v4_nine(captcha_id="fb563cdbdef8b3ab730527afa51db3d8", images=tiles)
#
# Auto (sempre que captcha aparecer):
#   from captchasonic_client import attach_geetest_watcher
#   attach_geetest_watcher(driver, api_key="sonic_...")  # thread polling a cada 1.5s
#
# Diagnostico: se o servidor retorna code 12 ERROR_CAPTCHA_UNSOLVABLE o modelo
# nao tem cobertura para este camouflage GeeTest v4 (ex: bet595 telephone).
# Nesse caso use GeeTestTask com proxy ou troque de provedor.

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore

try:
    import config as _cfg  # type: ignore
except ImportError:
    try:
        from app import config as _cfg  # type: ignore
    except ImportError:
        _cfg = None  # type: ignore


def _debug_log(msg: str) -> None:
    pass


# --- Pool fixo de API keys (round-robin) ---
# Definido pelo usuario em 2026-08-26; usado quando nenhum api_key explicito e passado.
CAPTCHASONIC_API_KEYS: List[str] = [
    "sonic_a654d0aaa0a0f8b5454ccac8_3",
    "sonic_1a024c472d0b498ccc517138_2",
    "sonic_42d427047552f2ca0304a494",
]

import threading as _th
_rr_lock = _th.Lock()
_rr_index = 0

def get_next_api_key() -> str:
    """Retorna proxima API key em round-robin (thread-safe)."""
    global _rr_index
    # prioriza env var se o usuario sobrescrever externamente
    env = (os.environ.get("CAPTCHASONIC_API_KEY") or os.environ.get("CAPTCHASONIC_KEY") or "").strip()
    if env:
        return env
    with _rr_lock:
        if not CAPTCHASONIC_API_KEYS:
            return ""
        key = CAPTCHASONIC_API_KEYS[_rr_index % len(CAPTCHASONIC_API_KEYS)]
        _rr_index += 1
        return key

def get_all_api_keys() -> List[str]:
    env = (os.environ.get("CAPTCHASONIC_API_KEY") or "").strip()
    if env:
        return [env]
    return list(CAPTCHASONIC_API_KEYS)


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------

class CaptchaSonicError(Exception):
    def __init__(self, message: str, error_id: int | None = None, payload: Any = None):
        super().__init__(message)
        self.error_id = error_id
        self.payload = payload


class InvalidApiKeyError(CaptchaSonicError): pass
class InsufficientBalanceError(CaptchaSonicError): pass
class DailyLimitExceededError(CaptchaSonicError): pass
class RateLimitedError(CaptchaSonicError): pass
class QuotaExceededError(CaptchaSonicError): pass
class PlanExpiredError(CaptchaSonicError): pass
class CaptchaUnsolvableError(CaptchaSonicError): pass
class BadParametersError(CaptchaSonicError): pass
class ServiceUnavailableError(CaptchaSonicError): pass
class PollTimeoutError(CaptchaSonicError): pass


_ERROR_MAP = {
    1: InvalidApiKeyError,
    2: ServiceUnavailableError,  # NO_SLOT_AVAILABLE
    3: InsufficientBalanceError,  # ZERO_BALANCE
    10: BadParametersError,
    12: CaptchaUnsolvableError,
    14: PlanExpiredError,
    16: RateLimitedError,
    17: DailyLimitExceededError,
    18: QuotaExceededError,
    21: ServiceUnavailableError,
}


def _raise_for_code(code: int, msg: str, payload: Any = None) -> None:
    exc_cls = _ERROR_MAP.get(code, CaptchaSonicError)
    raise exc_cls(f"[{code}] {msg}", error_id=code, payload=payload)


# ---------------------------------------------------------------------------
# Helpers base64
# ---------------------------------------------------------------------------

ImageInput = Union[str, Path, bytes, bytearray]

def _to_base64(inp: ImageInput) -> str:
    """Converte ImageInput (path/bytes) para base64 string sem prefixo data:."""
    if isinstance(inp, (bytes, bytearray)):
        return base64.b64encode(bytes(inp)).decode("utf-8")
    p = Path(str(inp))
    if p.exists() and p.is_file():
        return base64.b64encode(p.read_bytes()).decode("utf-8")
    # tenta tratar como base64 ja pronto (sem validacao rigida)
    s = str(inp).strip()
    # se veio com data: prefix, remove
    if s.startswith("data:"):
        try:
            s = s.split(",", 1)[1]
        except IndexError:
            pass
    # validacao rapida: se so tem chars base64, retorna como esta
    # senao, tenta como path fallback
    return s


def _to_base64_list(items: List[ImageInput]) -> List[str]:
    return [_to_base64(x) for x in items]


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------

class CaptchaSonicClient:
    """Cliente REST para https://api.captchasonic.com.

    Suporta tanto tarefas de reconhecimento (resposta imediata com ``answers``)
    quanto tarefas de token (polling via ``getTaskResult``/``getResponse``).

    Docs: https://captchasonic.com/en/docs
      - Recognition: GeetestImage (gtv 3/4), ReCaptchaV2Image, OcrImage, etc.
      - Token: GeeTestTask, AntiTurnstileTask, etc.
      - Balance: GET /balance?apiKey=...
    """

    DEFAULT_BASE_URL = "https://api.captchasonic.com"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        polling_interval: float = 2.0,
        polling_timeout: float = 120.0,
    ) -> None:
        # round-robin: se nenhum api_key passado e nenhum env, usa CAPTCHASONIC_API_KEYS
        if not api_key:
            api_key = get_next_api_key()
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)
        self.polling_interval = float(polling_interval)
        self.polling_timeout = float(polling_timeout)
        self._session = None
        if requests is not None:
            self._session = requests.Session()
            self._session.trust_env = False
            if certifi is not None:
                self._session.verify = certifi.where()

    # -- internals --

    def _require_key(self) -> str:
        if not self.api_key:
            raise InvalidApiKeyError("API key nao configurada. Defina CAPTCHASONIC_API_KEY ou passe api_key no construtor.", error_id=1)
        return self.api_key

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if requests is None:
            raise CaptchaSonicError("Dependencia 'requests' nao instalada. Instale com: py -3.13 -m pip install requests")
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        _debug_log(f"POST {url} keys={list(payload.keys())}")
        resp = self._session.post(
            url,
            json=payload,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"},
        )
        # tenta json sempre
        try:
            data = resp.json()
        except Exception:
            raise CaptchaSonicError(f"Resposta nao-JSON ({resp.status_code}): {resp.text[:500]}", payload=resp.text)
        _debug_log(f"RESP {resp.status_code} {json.dumps(data)[:800]}")
        return data

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if requests is None:
            raise CaptchaSonicError("Dependencia 'requests' nao instalada.")
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        _debug_log(f"GET {url} params={params}")
        resp = self._session.get(url, params=params, timeout=self.timeout)
        try:
            data = resp.json()
        except Exception:
            raise CaptchaSonicError(f"Resposta nao-JSON ({resp.status_code}): {resp.text[:500]}", payload=resp.text)
        _debug_log(f"RESP {resp.status_code} {json.dumps(data)[:800]}")
        return data

    # -- balance --

    def get_balance(self) -> Dict[str, Any]:
        """GET /balance?apiKey=... -> dict com balance/plan."""
        key = self._require_key()
        data = self._get("balance", {"apiKey": key})
        if isinstance(data, dict) and data.get("status") == "ok":
            return data
        # alguns endpoints retornam errorId
        if isinstance(data, dict) and data.get("errorId") not in (None, 0):
            _raise_for_code(int(data.get("errorId", 10)), str(data.get("errorDescription") or data.get("msg") or "balance error"), payload=data)
        return data

    # -- createTask / getTaskResult --

    def create_task(self, task: Dict[str, Any], extra_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """POST /createTask {apiKey, task, ...extra} -> resposta bruta.

        Retorna o JSON bruto. Se for tarefa de reconhecimento, pode ja vir
        com ``answers``/``code``. Se for tarefa de token, vira ``taskId``.
        `extra_payload` permite enviar campos de topo como source/version/appID/websiteURL
        iguais ao da extensao (necessario para Geetest v4).
        """
        key = self._require_key()
        payload: Dict[str, Any] = {"apiKey": key, "task": task}
        if extra_payload:
            payload.update(extra_payload)
        return self._post("createTask", payload)

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        """POST /getTaskResult {apiKey, taskId}."""
        key = self._require_key()
        # tenta POST primeiro (documentado), fallback GET
        try:
            return self._post("getTaskResult", {"apiKey": key, "taskId": task_id})
        except Exception:
            return self._post("getResponse", {"apiKey": key, "taskId": task_id})

    def poll_task(self, task_id: str, interval: float | None = None, timeout: float | None = None) -> Dict[str, Any]:
        """Poll ate status == completed/failed ou timeout."""
        wait = float(interval if interval is not None else self.polling_interval)
        deadline = time.time() + float(timeout if timeout is not None else self.polling_timeout)
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            last = self.get_task_result(task_id)
            status = str(last.get("status") or "").lower()
            if status in ("completed", "ready", "solved"):
                return last
            if status in ("failed", "error"):
                desc = last.get("errorDescription") or last.get("msg") or last.get("error") or "task failed"
                code = last.get("errorId") or last.get("code") or 10
                try:
                    code_i = int(code)
                except Exception:
                    code_i = 10
                _raise_for_code(code_i, str(desc), payload=last)
            # Alguns endpoints usam errorId !=0 para falha
            if last.get("errorId") not in (None, 0, "0"):
                _raise_for_code(int(last.get("errorId")), str(last.get("errorDescription") or last.get("msg") or "task error"), payload=last)
            # fallback: se ja veio answers sem polling
            if "answers" in last or "solution" in last:
                return last
            time.sleep(wait)
        raise PollTimeoutError(f"Timeout apos {self.polling_timeout}s aguardando task {task_id}", payload=last)

    def solve_task(self, task: Dict[str, Any], poll: bool | None = None) -> Dict[str, Any]:
        """Cria tarefa e resolve o ciclo completo.

        - Se a resposta ja contem ``answers``/``solution`` retorna direto.
        - Se contem ``taskId`` faz polling ate completar (a menos que poll=False).
        """
        data = self.create_task(task)
        # respostas imediatas (Recognition)
        if isinstance(data, dict) and ("answers" in data or "solution" in data):
            # checa erro embutido
            code = data.get("code")
            if code is not None and int(code) != 200:
                _raise_for_code(int(code), str(data.get("msg") or "error"), payload=data)
            if data.get("errorId") not in (None, 0, "0"):
                _raise_for_code(int(data.get("errorId")), str(data.get("errorDescription") or data.get("msg") or "error"), payload=data)
            return data
        # erros diretos
        if isinstance(data, dict) and data.get("errorId") not in (None, 0, "0"):
            _raise_for_code(int(data.get("errorId")), str(data.get("errorDescription") or data.get("msg") or "createTask error"), payload=data)
        # fluxo async com taskId
        task_id = data.get("taskId") or data.get("task_id")
        if not task_id:
            # pode ser que endpoint retornou code 200 sem taskId mas com status idle
            if data.get("status") == "idle" and not task_id:
                raise CaptchaSonicError(f"createTask retornou sem taskId: {data}", payload=data)
            return data
        if poll is False:
            return data
        return self.poll_task(str(task_id))

    # ------------------------------------------------------------------
    # Recognition helpers (resposta imediata)
    # ------------------------------------------------------------------

    def solve_geetest_v4(
        self,
        question: str,
        captcha_id: str,
        queries: List[ImageInput] | None = None,
        examples: List[ImageInput] | None = None,
        **extra: Any,
    ) -> List[Any]:
        """Geetest v4 generico (Recognition - GeetestImage gtv=4).

        question: slide | icon | nine | match | winlinze
        - slide: queries=[BG_BGR64, SLIDER_B64]
        - icon: queries=[MAIN_B64], examples=[TARGET_B64,...]
        - nine: queries=[IMG1..IMG9] (grid 3x3)
        - winlinze: queries=[25 imagens]

        Retorna ``answers`` (lista de indices ou coordenadas).
        Docs: /en/docs/recognition/geetest-v4
        """
        task: Dict[str, Any] = {
            "type": "GeetestImage",
            "gtv": 4,
            "question": question,
            "captchaId": captcha_id,
        }
        if queries is not None:
            task["queries"] = _to_base64_list(queries)
        if examples is not None:
            task["examples"] = _to_base64_list(examples)
        task.update(extra)
        res = self.solve_task(task)
        return list(res.get("answers") or res.get("solution") or [])

    def solve_geetest_v4_nine(
        self,
        captcha_id: str,
        images: List[ImageInput],
        question: str | None = None,
        examples: List[ImageInput] | None = None,
        website_url: str | None = None,
        **extra: Any,
    ) -> List[int]:
        """Atalho para Geetest v4 nine-grid (caso do bet595.press).

        Replica o que a extensao oficial faz (content-scripts/geetest4.js: L):
          task={type:GeetestImage, captchaId, queries:[9 tiles base64], examples:[prompt base64],
                question:"geetest_nine:Selecione  3  imagens correspondentes", websiteURL}
          + top-level source:"chrome", version:"0.3.3", appID:0

        - captcha_id: ex. fb563cdbdef8b3ab730527afa51db3d8
        - images: 9 imagens do grid (ordem 0..8 linha-major) como Path/bytes/b64.
                  No bet595 o grid vem fatiado de um unico JPG via background-position;
                  use split_geetest_nine_image() para recortar.
        - question: se None usa o texto padrao da extensao (geetest_nine:Selecione  3  ...)
        - examples: [prompt_image] - se None e question contem geetest_nine, o servidor pode
                    retornar unsolvable; passe o PNG do telefone/pasta.
        Retorna indices 0-based. Se o servidor retornar [false,true,...] converte para indices.
        """
        if len(images) != 9:
            raise BadParametersError(f"nine espera 9 imagens, recebeu {len(images)}", error_id=10)
        q = question or "geetest_nine:Selecione  3  imagens correspondentes"
        # garante prefixo geetest_nine:
        if not q.startswith("geetest_"):
            q = f"geetest_nine:{q}"
        task: Dict[str, Any] = {
            "type": "GeetestImage",
            "captchaId": captcha_id,
            "queries": _to_base64_list(images),
            "question": q,
        }
        if examples is not None:
            task["examples"] = _to_base64_list(examples)
        if website_url:
            task["websiteURL"] = website_url
        task.update(extra)
        # payload estilo extensao precisa de source/version/appID no nivel topo
        extra_payload: Dict[str, Any] = {}
        # se website_url fornecido, ja esta no task, mas extensao tambem envia no top? nao, so task
        # adiciona source/version para roteamento correto (sem isso o solver erra)
        for k in ("source", "version", "appID"):
            if k in extra:
                extra_payload[k] = extra.pop(k)
        # defaults da extensao
        if "source" not in extra_payload:
            extra_payload["source"] = "chrome"
        if "version" not in extra_payload:
            extra_payload["version"] = "0.3.3"
        if "appID" not in extra_payload:
            extra_payload["appID"] = 0
        data = self.create_task(task, extra_payload=extra_payload)
        # normaliza answers -> indices
        raw = data.get("answers")
        if raw is None:
            raw = data.get("solution") or []
        # servidor pode retornar [false,true,...] - converter
        if raw and isinstance(raw[0], bool):
            return [i for i, v in enumerate(raw) if bool(v)]
        return [int(x) for x in (raw or [])]

    def solve_geetest_v4_slide(
        self,
        captcha_id: str,
        background: ImageInput,
        slider: ImageInput,
        **extra: Any,
    ) -> List[int]:
        """Geetest v4 slide -> retorna [x, y]."""
        ans = self.solve_geetest_v4(question="slide", captcha_id=captcha_id, queries=[background, slider], **extra)
        return [int(x) for x in ans]

    def solve_geetest_v4_icon(
        self,
        captcha_id: str,
        main_image: ImageInput,
        targets: List[ImageInput],
        **extra: Any,
    ) -> List[Any]:
        """Geetest v4 icon-click -> retorna coordenadas."""
        return self.solve_geetest_v4(question="icon", captcha_id=captcha_id, queries=[main_image], examples=targets, **extra)

    def solve_geetest_v3(
        self,
        question: str,
        queries: List[ImageInput],
        captcha_id: str | None = None,
        **extra: Any,
    ) -> List[Any]:
        """Geetest v3 (gtv=3) - slide/icon/nine/match."""
        task: Dict[str, Any] = {"type": "GeetestImage", "gtv": 3, "question": question, "queries": _to_base64_list(queries)}
        if captcha_id:
            task["captchaId"] = captcha_id
        # alias gt/challenge se fornecidos
        for k in ("gt", "challenge", "captchaId", "proxy"):
            if k in extra:
                task[k] = extra.pop(k)
        task.update(extra)
        res = self.solve_task(task)
        return list(res.get("answers") or res.get("solution") or [])

    def solve_recaptcha_v2_image(
        self,
        question: str,
        images: List[ImageInput],
    ) -> List[int]:
        """ReCaptcha v2 grid (Recognition - ReCaptchaV2Image).

        question ex: 'Select all crosswalks', images = tiles base64
        Retorna indices 0-based para clicar.
        """
        res = self.solve_task({"type": "ReCaptchaV2Image", "question": question, "queries": _to_base64_list(images)})
        return [int(x) for x in (res.get("answers") or [])]

    def solve_ocr(
        self,
        images: List[ImageInput],
        module: str | None = None,
        numeric: bool | None = None,
        case_sensitive: bool | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> List[str]:
        """OCR / ImageToText (OcrImage).

        Retorna lista de textos reconhecidos.
        """
        task: Dict[str, Any] = {"type": "OcrImage", "queries": _to_base64_list(images)}
        if module is not None:
            task["module"] = module
        if numeric is not None:
            task["numeric"] = bool(numeric)
        if case_sensitive is not None:
            task["case"] = bool(case_sensitive)
        if min_length is not None:
            task["minLength"] = int(min_length)
        if max_length is not None:
            task["maxLength"] = int(max_length)
        res = self.solve_task(task)
        return [str(x) for x in (res.get("answers") or [])]

    # ------------------------------------------------------------------
    # Token helpers (polling)
    # ------------------------------------------------------------------

    def solve_geetest_token(
        self,
        website_url: str,
        captcha_id: str,
        proxy: str,
        geetest_api_server_subdomain: str | None = None,
    ) -> Dict[str, Any]:
        """GeeTest Token (GeeTestTask) - requer proxy.

        Retorna solution {captcha_id, lot_number, pass_token, gen_time, captcha_output}
        que deve ser injetado no form alvo.
        Docs: /en/docs/token/geetest-task
        """
        task: Dict[str, Any] = {"type": "GeeTestTask", "websiteURL": website_url, "captchaId": captcha_id, "proxy": proxy}
        if geetest_api_server_subdomain:
            task["geetestApiServerSubdomain"] = geetest_api_server_subdomain
        res = self.solve_task(task)
        return dict(res.get("solution") or res)

    def solve_turnstile_token(
        self,
        website_url: str,
        website_key: str,
        proxy: str | None = None,
        action: str | None = None,
        cdata: str | None = None,
    ) -> str:
        """AntiTurnstileTask -> retorna token cf-turnstile-response."""
        task: Dict[str, Any] = {"type": "AntiTurnstileTask", "websiteURL": website_url, "websiteKey": website_key}
        if proxy:
            task["proxy"] = proxy
        meta: Dict[str, Any] = {}
        if action:
            meta["action"] = action
        if cdata:
            meta["cdata"] = cdata
        if meta:
            task["metadata"] = meta
        res = self.solve_task(task)
        sol = res.get("solution") or res
        # diferentes shapes: token / gRecaptchaResponse / cf-turnstile-response
        for k in ("token", "gRecaptchaResponse", "cf-turnstile-response", "captcha_output", "pass_token"):
            if k in sol:
                return str(sol[k])
        # fallback: stringify
        return json.dumps(sol) if isinstance(sol, dict) else str(sol)

    def solve_recaptcha_v2_token(
        self,
        website_url: str,
        website_key: str,
        proxy: str | None = None,
    ) -> str:
        task: Dict[str, Any] = {"type": "RecaptchaV2Task", "websiteURL": website_url, "websiteKey": website_key}
        if proxy:
            task["proxy"] = proxy
        res = self.solve_task(task)
        sol = res.get("solution") or res
        return str(sol.get("token") or sol.get("gRecaptchaResponse") or json.dumps(sol))

    def solve_hcaptcha_token(
        self,
        website_url: str,
        website_key: str,
        proxy: str | None = None,
    ) -> str:
        task: Dict[str, Any] = {"type": "HCaptchaTask", "websiteURL": website_url, "websiteKey": website_key}
        if proxy:
            task["proxy"] = proxy
        res = self.solve_task(task)
        sol = res.get("solution") or res
        return str(sol.get("token") or json.dumps(sol))

    # ------------------------------------------------------------------
    # Util para bet595.press (caso concreto visto via CDP 9222)
    # ------------------------------------------------------------------

    @staticmethod
    def split_geetest_nine_image(combined: ImageInput, out_dir: str | Path | None = None) -> List[bytes]:
        """Recorta um JPG combinado 3x3 do GeeTest v4 em 9 tiles (bytes JPEG).

        O SSBrowser recebe o grid como um unico JPG fatiado via CSS
        background-position (ver screenshot bet595). Este helper gera os
        9 arquivos necessarios para ``solve_geetest_v4_nine``.

        Se out_dir for informado, salva arquivos 0.jpg..8.jpg la.
        """
        from PIL import Image  # Pillow ja e dependencia do projeto
        import io

        if isinstance(combined, (bytes, bytearray)):
            im = Image.open(io.BytesIO(bytes(combined)))
        else:
            p = Path(str(combined))
            if p.exists():
                im = Image.open(str(p))
            else:
                # tenta base64
                raw = base64.b64decode(_to_base64(combined))
                im = Image.open(io.BytesIO(raw))

        im = im.convert("RGB")
        w, h = im.size
        tile_w, tile_h = w // 3, h // 3
        tiles: List[bytes] = []
        for row in range(3):
            for col in range(3):
                x0, y0 = col * tile_w, row * tile_h
                x1, y1 = x0 + tile_w, y0 + tile_h
                crop = im.crop((x0, y0, x1, y1))
                buf = io.BytesIO()
                crop.save(buf, format="JPEG", quality=92)
                data = buf.getvalue()
                tiles.append(data)
                if out_dir is not None:
                    d = Path(out_dir)
                    d.mkdir(parents=True, exist_ok=True)
                    idx = row * 3 + col
                    (d / f"{idx}.jpg").write_bytes(data)
        return tiles


# ------------------------------------------------------------------
# Auto-watcher: dispara CaptchaSonic sempre que GeeTest aparecer
# ------------------------------------------------------------------

def _cdp_extract_geetest(driver, timeout: float = 5.0) -> dict | None:
    """Extrai captchaId, tiles url e bounds via DrissionPage/CDP.

    Retorna dict com keys: captchaId, tiles_url, prompt_url, items (x,y,w,h) ou None se invisivel.
    Checa .geetest_box (popup real) e nao so .geetest_captcha (container 0-height).
    """
    try:
        js = r'''( () => {
          const capBox = document.querySelector('.geetest_captcha');
          if (!capBox) return null;
          const capSt = getComputedStyle(capBox);
          if (capSt.display === 'none' || capSt.visibility === 'hidden' || parseFloat(capSt.opacity||'1') < 0.05) return null;
          // popup real pode ser .geetest_box (340x386) e nao o container externo (719x0)
          const box = document.querySelector('.geetest_box');
          const win = document.querySelector('.geetest_window');
          let visibleBox = null;
          for (const el of [box, win, capBox]) {
            if (!el) continue;
            const st = getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity||'1') < 0.05) continue;
            const r = el.getBoundingClientRect();
            if (r && r.width > 30 && r.height > 30) { visibleBox = el; break; }
          }
          if (!visibleBox) return null;
          // garante que tem 9 itens visiveis
          const items = Array.from(document.querySelectorAll('.geetest_item'));
          if (items.length < 9) return null;
          let visCount = 0;
          for (const it of items) {
            const r = it.getBoundingClientRect();
            if (r && r.width > 20 && r.height > 20) visCount++;
          }
          if (visCount < 3) return null;
          const scripts = Array.from(document.querySelectorAll('script[src]')).map(s=>s.src);
          const cap = scripts.filter(s=>s.includes('captcha_id')).join(' ');
          const m = cap.match(/captcha_id=([a-z0-9]+)/);
          const m2 = cap.match(/challenge=([a-z0-9\-]+)/);
          const prompt = document.querySelector('.geetest_ques_tips img');
          const tiles = items.map((el,i)=>{
            const rc = el.getBoundingClientRect();
            return {i, x:rc.x, y:rc.y, w:rc.width, h:rc.height};
          });
          return JSON.stringify({captchaId: m?m[1]:null, challenge: m2?m2[1]:null, promptSrc: prompt?prompt.src:null, tiles, visible:true});
        })()'''
        # DrissionPage precisa de 'return' explicito para retornar valor (testado: sem return -> None)
        val = driver.run_js(f"return {js}")
        if not val:
            return None
        import json as _j
        obj = _j.loads(val) if isinstance(val, str) else val
        return obj
    except Exception:
        return None


def _solve_current_geetest_via_cdp(driver, client: "CaptchaSonicClient", dpr: float | None = None) -> list[int] | None:
    """Captura 9 tiles (ou slide) via split do JPEG (igual a extensao) e chama Solver.

    Suporta nine-grid e slide (detecta via .geetest_bg/.geetest_slice_bg).
    Usa o fluxo da extensao oficial (content-scripts/geetest4.js: L):
      J(F) -> 9 slices JPEG, fetchBase64Image(prompt), question="geetest_nine:<texto>",
      task={type:GeetestImage, captchaId, queries:[9], examples:[prompt], question, websiteURL}
      top-level source:chrome version:0.3.3 appID:0
    Retorna indices para nine ou [x,y] para slide.
    """
    try:
        import re as _re
        import urllib.request as _ur

        info = _cdp_extract_geetest(driver)
        if not info or not info.get("tiles"):
            return None

        # pega websiteURL atual
        website_url = "https://bet595.press/"
        try:
            website_url = driver.run_js("return location.href;") or website_url
        except Exception:
            pass

        # pega texto do tips (ex: "Selecione  3  imagens correspondentes" com double space)
        question_text = "Selecione  3  imagens correspondentes"
        try:
            qt = driver.run_js("return document.querySelector('.geetest_text_tips')?.textContent?.trim()||'';")
            if qt and len(qt) > 5:
                question_text = str(qt).strip()
        except Exception:
            pass
        question = f"geetest_nine:{question_text}"

        # pega prompt image (telefone/pasta)
        prompt_b64: str | None = None
        try:
            prompt_src = info.get("promptSrc") or driver.run_js("return document.querySelector('.geetest_ques_tips img')?.src||'';")
            if prompt_src:
                # fetch via urllib (igual a extensao fetchBase64Image)
                # usa GET direto; background script da extensao faz via chrome.runtime, mas aqui fazemos http
                data = _ur.urlopen(prompt_src, timeout=10).read()
                prompt_b64 = _to_base64(data)
        except Exception as e:
            _debug_log(f"prompt fetch fail {e}")

        # pega tiles_url do backgroundImage (.geetest_item_img)
        tiles_url = None
        try:
            tiles_url = driver.run_js("return document.querySelector('.geetest_item_img')?.style?.backgroundImage||'';")
            m = _re.search(r'url\("([^"]+)"\)', tiles_url or "")
            if m:
                tiles_url = m.group(1)
            else:
                tiles_url = None
        except Exception:
            tiles_url = None

        if not tiles_url:
            _debug_log("tiles_url nao encontrado")
            return None

        # baixa JPEG combinado e splita em 9 via canvas JPEG (igual a J(F) da extensao)
        try:
            data = _ur.urlopen(tiles_url, timeout=10).read()
            clips = CaptchaSonicClient.split_geetest_nine_image(data)
            _debug_log(f"tiles 9 slices ok cid={info.get('captchaId')} q={question} prompt={'ok' if prompt_b64 else 'none'}")
        except Exception as e:
            _debug_log(f"split fail {e}")
            return None

        if len(clips) != 9:
            _debug_log(f"clips incompletos {len(clips)}/9")
            return None

        cid = info.get("captchaId") or "fb563cdbdef8b3ab730527afa51db3d8"
        examples = [prompt_b64] if prompt_b64 else None
        if examples is None:
            _debug_log("sem prompt, tentativa sem examples pode dar unsolvable")
        try:
            ans = client.solve_geetest_v4_nine(captcha_id=cid, images=clips, question=question, examples=examples, website_url=website_url)
            if ans:
                _debug_log(f"geetest nine -> {ans}")
                return [int(x) for x in ans]
            # fallback: tenta sem texto (so geetest_nine) se o texto estiver errado
            if question_text:
                ans2 = client.solve_geetest_v4_nine(captcha_id=cid, images=clips, question="geetest_nine", examples=examples, website_url=website_url)
                if ans2:
                    _debug_log(f"geetest nine fallback -> {ans2}")
                    return [int(x) for x in ans2]
        except CaptchaUnsolvableError as e:
            _debug_log(f"geetest nine unsolvable {e} - tenta match fallback")
            # fallback legacy match (nao usa prompt) - pode retornar errado mas tenta
            try:
                ans = client.solve_geetest_v4(captcha_id=cid, question="geetest_match", queries=clips, websiteURL=website_url)
                # normaliza bool->indices se vier
                if ans and isinstance(ans[0], bool):
                    ans = [i for i, v in enumerate(ans) if bool(v)]
                if ans:
                    return [int(x) for x in ans]
            except Exception:
                pass
        except Exception as e:
            _debug_log(f"geetest nine error {e}")
        return None
    except Exception as e:
        _debug_log(f"_solve_current_geetest_via_cdp error {e}")
        return None


def _click_geetest_indices(driver, indices: list[int]) -> bool:
    """Clica nos indices 0..8 do grid GeeTest (replica geetest4.js: Z)."""
    try:
        for idx in indices:
            # extensao clica no ghost overlay: .geetest_ghost_<idx> dentro de .geetest_<idx>
            ghost_sel = f".geetest_ghost_{idx}"
            ghost = None
            try:
                ghost = driver.ele(ghost_sel, timeout=0.5)
            except Exception:
                ghost = None
            if ghost:
                ghost.click()
            else:
                # fallback: tenta via JS direto (cobre hash _f89d8ead)
                try:
                    driver.run_js(f'document.querySelector(".geetest_ghost_{idx}")?.click()')
                except Exception:
                    # ultimo fallback: clica no item
                    el = driver.ele(f".geetest_{idx}", timeout=0.5)
                    if el:
                        el.click()
            time.sleep(0.32)
        time.sleep(0.4)
        # GeeTest v4 nine nao tem botao commit - valida no clique do 3o; mas tenta igual
        for sel in (".geetest_commit", ".geetest_btn", "button[class*='commit']", ".geetest_submit"):
            try:
                btn = driver.ele(sel, timeout=0.5)
                if btn:
                    btn.click()
                    break
            except Exception:
                continue
        return True
    except Exception as e:
        _debug_log(f"_click_geetest_indices fail {e}")
        return False


def attach_geetest_watcher(driver, api_key: str | None = None, poll_interval: float = 1.5, auto_click: bool = True) -> dict:
    """Anexa thread watcher que dispara CaptchaSonic sempre que GeeTest ficar visivel.

    Uso no SSBROWSER (app/main.py ou browser_creator):
      from captchasonic_client import attach_geetest_watcher
      info["_geetest_watcher"] = attach_geetest_watcher(driver, api_key="sonic_...")

    Retorna dict com thread e stop flag. Para parar: info['_geetest_watcher']['stop']=True
    """
    import threading
    # se api_key explicito, usa so ele; senao usa pool round-robin das 3 fixas
    if api_key:
        keys_to_check = [api_key.strip()]
    else:
        keys_to_check = get_all_api_keys()
    if not keys_to_check or not any(k.strip() for k in keys_to_check):
        raise InvalidApiKeyError("attach_geetest_watcher precisa api_key ou CAPTCHASONIC_API_KEYS", error_id=1)
    # sem validacao de saldo (usuario pediu para nao validar)
    client = CaptchaSonicClient(api_key=keys_to_check[0])

    stop = {"stop": False, "solving": False}
    info: dict = {"stop": stop, "client": client}

    def _loop():
        _debug_log(f"watcher iniciado poll={poll_interval}s auto_click={auto_click}")
        consec_unsolvable = 0
        last_challenge = None
        last_prompt = None
        empty_polls = 0
        was_visible = False
        while not stop["stop"]:
            try:
                if stop.get("solving"):
                    time.sleep(poll_interval)
                    continue
                g = _cdp_extract_geetest(driver)
                if not g:
                    if was_visible:
                        # captcha fechou - limpa deduplicacao para permitir segunda tentativa com mesmo challenge
                        _debug_log("captcha fechou, limpando deduplicacao para retry")
                        last_challenge = None
                        last_prompt = None
                    was_visible = False
                    empty_polls += 1
                    if empty_polls % 7 == 0:
                        _debug_log("watcher poll sem captcha")
                    time.sleep(poll_interval)
                    continue
                was_visible = True
                empty_polls = 0
                cur_chal = g.get("challenge") or g.get("captchaId") or ""
                cur_prompt = g.get("promptSrc") or ""
                # so ignora duplicado se for MESMO challenge+prompt e ainda dentro de 2s e ainda nao fechou
                is_same = (cur_chal and cur_chal == last_challenge and cur_prompt == last_prompt)
                if is_same and stop.get("last_solve_ts") and (time.time() - stop["last_solve_ts"] < 2.0):
                    _debug_log("captcha ja resolvido ha <2s, ignorando duplicado")
                    time.sleep(poll_interval)
                    continue
                last_challenge = cur_chal
                last_prompt = cur_prompt
                _debug_log("GeeTest detectado, chamando Solver...")
                stop["solving"] = True
                # round-robin: pega proxima key a cada solve
                rr_key = get_next_api_key()
                try:
                    client.api_key = rr_key
                except Exception:
                    pass
                _debug_log(f"usando key {rr_key[:14]}...")
                indices = _solve_current_geetest_via_cdp(driver, client)
                # se falhar por rate/balance, tenta proxima key imediatamente
                if indices is None and len(keys_to_check) > 1:
                    for _ in range(len(keys_to_check) - 1):
                        rr2 = get_next_api_key()
                        if rr2 == rr_key:
                            continue
                        _debug_log(f"retry com key {rr2[:14]}...")
                        try:
                            client.api_key = rr2
                            indices = _solve_current_geetest_via_cdp(driver, client)
                            if indices is not None:
                                break
                        except Exception as e2:
                            _debug_log(f"retry fail {e2}")
                            continue
                stop["last_solve_ts"] = time.time()
                if indices is None:
                    consec_unsolvable += 1
                    _debug_log(f"unsolvable ({consec_unsolvable}x) - tentando refresh")
                    # clica refresh para novo desafio
                    try:
                        btn = driver.ele(".geetest_refresh", timeout=1)
                        if btn:
                            btn.click()
                    except Exception:
                        pass
                    if consec_unsolvable >= 3:
                        _debug_log("3 unsolvables seguidos, pausa 10s")
                        time.sleep(10)
                        consec_unsolvable = 0
                else:
                    consec_unsolvable = 0
                    _debug_log(f"solucao {indices} - clicando...")
                    if auto_click:
                        _click_geetest_indices(driver, indices)
                    # marca no drivers_info se existir
                    try:
                        # tenta setar flags de captcha em progresso (compativel com main.py)
                        pass
                    except Exception:
                        pass
                stop["solving"] = False
            except Exception as e:
                _debug_log(f"watcher loop error {e}")
                stop["solving"] = False
            time.sleep(poll_interval)
        _debug_log("watcher parado")

    t = threading.Thread(target=_loop, daemon=True, name="solver-watcher")
    t.start()
    info["thread"] = t
    return info


# Alias compativel com docs que usam `CaptchaSonic`
CaptchaSonic = CaptchaSonicClient

__all__ = [
    "CaptchaSonicClient",
    "CaptchaSonic",
    "CaptchaSonicError",
    "InvalidApiKeyError",
    "InsufficientBalanceError",
    "DailyLimitExceededError",
    "RateLimitedError",
    "QuotaExceededError",
    "PlanExpiredError",
    "CaptchaUnsolvableError",
    "BadParametersError",
    "ServiceUnavailableError",
    "PollTimeoutError",
    "_to_base64",
    "attach_geetest_watcher",
]


if __name__ == "__main__":
    # Smoke test: checa balance e mostra como resolver bet595 nine-grid
    import argparse

    parser = argparse.ArgumentParser(description="Teste CaptchaSonicClient")
    parser.add_argument("--balance", action="store_true", help="consulta saldo")
    parser.add_argument("--nine", nargs=3, metavar=("CAPTCHA_ID", "TILES_JPG", "API_KEY"), help="teste nine-grid: CAPTCHA_ID TILES.jpg [API_KEY opcional]")
    args = parser.parse_args()

    key = os.environ.get("CAPTCHASONIC_API_KEY") or ""
    client = CaptchaSonicClient(api_key=key)
    if args.balance:
        try:
            print(json.dumps(client.get_balance(), indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"balance error: {e}")
    if args.nine:
        cid, jpg, *rest = args.nine
        k = rest[0] if rest else key
        c = CaptchaSonicClient(api_key=k)
        tiles = CaptchaSonicClient.split_geetest_nine_image(jpg)
        print(f"tiles={len(tiles)} captcha_id={cid}")
        try:
            ans = c.solve_geetest_v4_nine(captcha_id=cid, images=tiles)
            print(f"answers={ans}")
        except Exception as e:
            print(f"solve error: {e}")

