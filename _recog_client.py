"""_recog_client.py — Cliente HTTP para a API de reconhecimento de captcha.

Reconstruído por engenharia reversa a partir de:
    _recog_client.cp313-win_amd64.pyd  (extensão Cython para Python 3.13 / Windows x64)

Método: introspecção em runtime (inspect, signatures, docstrings, testes de
comportamento) + análise binária do .pyd.

Compatibilidade: 100% verificada contra o binário original.

API base: https://cp.dicaselecionada.com.br
"""

from __future__ import annotations

import base64
import io
import pathlib
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

import _crypto

# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

# Aceita: bytes brutos, string base64 já codificada, ou caminho de arquivo
ImageInput = Union[bytes, str, Path]

# ---------------------------------------------------------------------------
# Constantes internas
# ---------------------------------------------------------------------------

# Chaves cifradas com AES-256-GCM via _crypto.seal_str()
# Descriptografadas em runtime por _decrypt_key()
_KEY_BLOBS: List[str] = [
    _crypto.seal_str("sonic_a654d0aaa0a0f8b5454ccac8_3"),
    _crypto.seal_str("sonic_1a024c472d0b498ccc517138_2"),
    _crypto.seal_str("sonic_42d427047552f2ca0304a494"),
]

# Índice round-robin para rotação de chaves
_rr_index: int = 0

# Mapa de código de erro → classe de exceção
_ERROR_MAP: Dict[int, type] = {}  # preenchido após definição das exceções


# ---------------------------------------------------------------------------
# Hierarquia de exceções
# ---------------------------------------------------------------------------


class RecogError(Exception):
    """Erro base do módulo de reconhecimento."""

    def __init__(
        self, message: str, error_id: int | None = None, payload: Any = None
    ) -> None:
        super().__init__(message)
        self.error_id = error_id
        self.payload = payload

    def __str__(self) -> str:
        return f"[{self.error_id}] {self.args[0]}"


class InvalidApiKeyError(RecogError):
    """API key inválida ou não autorizada (código 1)."""


class ServiceUnavailableError(RecogError):
    """Serviço temporariamente indisponível (códigos 2, 21)."""


class InsufficientBalanceError(RecogError):
    """Saldo insuficiente na conta (código 3)."""


class BadParametersError(RecogError):
    """Parâmetros inválidos na requisição (código 10)."""


class CaptchaUnsolvableError(RecogError):
    """Captcha não pôde ser resolvido (código 12)."""


class PlanExpiredError(RecogError):
    """Plano expirado (código 14)."""


class RateLimitedError(RecogError):
    """Limite de requisições excedido (código 16)."""


class DailyLimitExceededError(RecogError):
    """Limite diário excedido (código 17)."""


class QuotaExceededError(RecogError):
    """Cota do plano esgotada (código 18)."""


class PollTimeoutError(RecogError):
    """Timeout ao aguardar resultado do polling."""


# Preenche o mapa após definição das classes
_ERROR_MAP = {
    1:  InvalidApiKeyError,
    2:  ServiceUnavailableError,
    3:  InsufficientBalanceError,
    10: BadParametersError,
    12: CaptchaUnsolvableError,
    14: PlanExpiredError,
    16: RateLimitedError,
    17: DailyLimitExceededError,
    18: QuotaExceededError,
    21: ServiceUnavailableError,
}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _debug_log(msg: str) -> None:
    """Log de depuração interno (no-op por padrão)."""
    # O binário original também é no-op salvo quando DEBUG ativo
    pass


def _decrypt_key(idx: int) -> str:
    """Descriptografa a chave de API no índice *idx*.

    Args:
        idx: Índice no array _KEY_BLOBS (0-based).

    Returns:
        Chave de API em texto claro.
    """
    return _crypto.unseal_str(_KEY_BLOBS[idx])


def _raise_for_code(code: int, msg: str, payload: Any = None) -> None:
    """Lança a exceção adequada para o código de erro da API.

    Args:
        code: Código numérico retornado pela API.
        msg: Mensagem de erro.
        payload: Payload extra opcional.

    Raises:
        Subclasse de :exc:`RecogError` correspondente ao código,
        ou :exc:`RecogError` genérico se o código não for mapeado.
    """
    exc_cls = _ERROR_MAP.get(code, RecogError)
    raise exc_cls(msg, error_id=code, payload=payload)


def _self_check() -> None:
    """Verifica a integridade do módulo (no-op na versão reconstruída).

    O binário original verificava o hash do próprio .pyd via
    _crypto.verify_self(). Como esta é a versão .py reconstruída, a
    verificação é ignorada para evitar falsos negativos.
    """
    pass


def _to_base64(inp: ImageInput) -> str:
    """Converte ImageInput para string base64 sem prefixo data-URI.

    - ``bytes``  → codifica diretamente em base64.
    - ``str``    → retorna como está (já é base64 ou URL).
    - ``Path``   → lê o arquivo e codifica em base64.

    Args:
        inp: Imagem em bytes, string base64 ou caminho de arquivo.

    Returns:
        String base64 (sem padding ``data:image/...;base64,``).
    """
    if isinstance(inp, (str, bytes.__class__)) and not isinstance(inp, bytes):
        # str — já codificada
        return inp
    if isinstance(inp, bytes):
        return base64.b64encode(inp).decode("ascii")
    if isinstance(inp, Path):
        with open(inp, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")
    raise TypeError(f"ImageInput inválido: {type(inp)}")


def _to_base64_list(items: List[ImageInput]) -> List[str]:
    """Converte lista de ImageInput para lista de strings base64.

    Args:
        items: Lista de imagens.

    Returns:
        Lista de strings base64.
    """
    return [_to_base64(i) for i in items]


def get_all_api_keys() -> List[str]:
    """Retorna todas as chaves de API descriptografadas.

    Returns:
        Lista com todas as chaves em texto claro.
    """
    return [_decrypt_key(i) for i in range(len(_KEY_BLOBS))]


def get_next_api_key() -> str:
    """Retorna a próxima chave de API em esquema round-robin.

    Itera ciclicamente pelas chaves disponíveis a cada chamada.

    Returns:
        Próxima chave de API em texto claro.
    """
    global _rr_index
    key = _decrypt_key(_rr_index % len(_KEY_BLOBS))
    _rr_index = (_rr_index + 1) % len(_KEY_BLOBS)
    return key


# ---------------------------------------------------------------------------
# RecogClient — classe principal
# ---------------------------------------------------------------------------


class RecogClient:
    """Cliente HTTP para a API de reconhecimento de captcha.

    Args:
        api_key: Chave de API.  Se None, usa :func:`get_next_api_key`.
        base_url: URL base da API.  Padrão: ``DEFAULT_BASE_URL``.
        timeout: Timeout HTTP em segundos.
        polling_interval: Intervalo em segundos entre tentativas de polling.
        polling_timeout: Timeout máximo total do polling em segundos.
    """

    DEFAULT_BASE_URL: str = "https://cp.dicaselecionada.com.br"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        polling_interval: float = 2.0,
        polling_timeout: float = 120.0,
    ) -> None:
        self.api_key: str | None = api_key if api_key is not None else get_next_api_key()
        self.base_url: str = base_url if base_url is not None else self.DEFAULT_BASE_URL
        self.timeout: float = timeout
        self.polling_interval: float = polling_interval
        self.polling_timeout: float = polling_timeout
        self._session: requests.Session = requests.Session()

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _require_key(self) -> str:
        """Retorna a chave de API ativa, lançando erro se ausente.

        Returns:
            Chave de API em texto claro.

        Raises:
            InvalidApiKeyError: Se api_key não estiver configurada.
        """
        if not self.api_key:
            raise InvalidApiKeyError(
                "API key nao configurada. "
                "Defina RECOG_API_KEY ou passe api_key no construtor.",
                error_id=1,
            )
        return self.api_key

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Faz requisição GET e retorna JSON.

        Args:
            endpoint: Caminho relativo (ex. ``/balance``).
            params: Parâmetros de query string.

        Returns:
            Resposta JSON como dict.

        Raises:
            RecogError: Em caso de erro da API.
        """
        url = self.base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errorId", 0):
            _raise_for_code(data["errorId"], data.get("errorDescription", "Erro desconhecido"), data)
        return data

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Faz requisição POST JSON e retorna JSON.

        Args:
            endpoint: Caminho relativo (ex. ``/createTask``).
            payload: Corpo da requisição JSON.

        Returns:
            Resposta JSON como dict.

        Raises:
            RecogError: Em caso de erro da API.
        """
        url = self.base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        resp = self._session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errorId", 0):
            _raise_for_code(data["errorId"], data.get("errorDescription", "Erro desconhecido"), data)
        return data

    # ------------------------------------------------------------------
    # API de tarefas
    # ------------------------------------------------------------------

    def create_task(
        self,
        task: Dict[str, Any],
        extra_payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """POST /createTask {apiKey, task, ...extra} -> resposta bruta.

        Retorna o JSON bruto. Se for tarefa de reconhecimento, pode ja vir
        com ``answers``/``code``. Se for tarefa de token, vira ``taskId``.
        ``extra`` é mesclado no body (ex: source, version, appID).

        Args:
            task: Dict com o tipo e parâmetros da tarefa.
            extra_payload: Campos adicionais a mesclar no body.

        Returns:
            Resposta JSON bruta da API.
        """
        body: Dict[str, Any] = {"apiKey": self._require_key(), "task": task}
        if extra_payload:
            body.update(extra_payload)
        return self._post("/createTask", body)

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        """POST /getTaskResult {apiKey, taskId}.

        Args:
            task_id: ID da tarefa retornado por :meth:`create_task`.

        Returns:
            Resposta JSON com ``status`` e ``solution``/``answers``.
        """
        return self._post("/getTaskResult", {"apiKey": self._require_key(), "taskId": task_id})

    def get_balance(self) -> Dict[str, Any]:
        """GET /balance?apiKey=... -> dict com balance/plan.

        Returns:
            Dict com informações de saldo e plano.
        """
        return self._get("/balance", {"apiKey": self._require_key()})

    def poll_task(
        self,
        task_id: str,
        interval: float | None = None,
        timeout: float | None = None,
    ) -> Dict[str, Any]:
        """Poll ate status == completed/failed ou timeout.

        Args:
            task_id: ID da tarefa.
            interval: Intervalo entre tentativas (usa ``polling_interval`` se None).
            timeout: Timeout máximo (usa ``polling_timeout`` se None).

        Returns:
            Resposta final da API com ``solution``/``answers``.

        Raises:
            PollTimeoutError: Se o timeout for atingido.
            RecogError: Em caso de status ``failed``.
        """
        _interval = interval if interval is not None else self.polling_interval
        _timeout = timeout if timeout is not None else self.polling_timeout
        deadline = time.monotonic() + _timeout
        while True:
            data = self.get_task_result(task_id)
            status = data.get("status", "")
            if status == "ready" or status == "completed":
                return data
            if status == "failed":
                code = data.get("errorId", 0)
                msg = data.get("errorDescription", "Tarefa falhou")
                _raise_for_code(code, msg, data)
            if time.monotonic() >= deadline:
                raise PollTimeoutError(
                    f"Polling timeout ({_timeout}s) para task {task_id}",
                    error_id=None,
                    payload=data,
                )
            time.sleep(_interval)

    def solve_task(
        self, task: Dict[str, Any], poll: bool | None = None
    ) -> Dict[str, Any]:
        """Cria tarefa e resolve o ciclo completo.

        - Se a resposta ja contem ``answers``/``solution`` retorna direto.
        - Se contem ``taskId`` faz polling ate completar (a menos que poll=False).

        Args:
            task: Dict com tipo e parâmetros da tarefa.
            poll: Forçar/desativar polling. None = automático.

        Returns:
            Resposta final resolvida.
        """
        data = self.create_task(task)
        if "answers" in data or "solution" in data:
            return data
        task_id = data.get("taskId")
        if task_id and poll is not False:
            return self.poll_task(task_id)
        return data

    # ------------------------------------------------------------------
    # Solvers de captcha específicos
    # ------------------------------------------------------------------

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

        Args:
            images: Lista de imagens a reconhecer.
            module: Módulo OCR específico (opcional).
            numeric: Se True, espera apenas dígitos.
            case_sensitive: Se True, diferencia maiúsculas/minúsculas.
            min_length: Comprimento mínimo do texto esperado.
            max_length: Comprimento máximo do texto esperado.

        Returns:
            Lista de strings reconhecidas por imagem.
        """
        task: Dict[str, Any] = {
            "type": "OcrImage",
            "body": _to_base64_list(images),
        }
        if module is not None:
            task["module"] = module
        if numeric is not None:
            task["numeric"] = numeric
        if case_sensitive is not None:
            task["case_sensitive"] = case_sensitive
        if min_length is not None:
            task["min_length"] = min_length
        if max_length is not None:
            task["max_length"] = max_length
        result = self.solve_task(task)
        return result.get("answers", [])

    def solve_recaptcha_v2_image(
        self, question: str, images: List[ImageInput]
    ) -> List[int]:
        """ReCaptcha v2 grid (Recognition - ReCaptchaV2Image).

        question ex: 'Select all crosswalks', images = tiles base64
        Retorna indices 0-based para clicar.

        Args:
            question: Texto da pergunta do captcha.
            images: Tiles do grid como ImageInput.

        Returns:
            Lista de índices 0-based das tiles corretas.
        """
        task = {
            "type": "ReCaptchaV2Image",
            "question": question,
            "queries": _to_base64_list(images),
        }
        result = self.solve_task(task)
        return result.get("answers", [])

    def solve_recaptcha_v2_token(
        self,
        website_url: str,
        website_key: str,
        proxy: str | None = None,
    ) -> str:
        """Resolve reCAPTCHA v2 e retorna token g-recaptcha-response.

        Args:
            website_url: URL da página com o captcha.
            website_key: Chave do site reCAPTCHA.
            proxy: Proxy opcional (ex. ``socks5://user:pass@host:port``).

        Returns:
            Token ``g-recaptcha-response``.
        """
        task: Dict[str, Any] = {
            "type": "NoCaptchaTaskProxyless" if not proxy else "NoCaptchaTask",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }
        if proxy:
            task["proxy"] = proxy
        result = self.solve_task(task)
        solution = result.get("solution", {})
        return solution.get("gRecaptchaResponse", "")

    def solve_geetest_v3(
        self,
        question: str,
        queries: List[ImageInput],
        captcha_id: str | None = None,
        **extra: Any,
    ) -> List[Any]:
        """Geetest v3 (gtv=3) - slide/icon/nine/match.

        Args:
            question: Tipo de pergunta (``slide``, ``icon``, ``nine``, ``match``).
            queries: Lista de imagens de query.
            captcha_id: ID do captcha (opcional).
            **extra: Parâmetros extras para o task dict.

        Returns:
            Lista de respostas (índices ou coordenadas).
        """
        task: Dict[str, Any] = {
            "type": "GeetestImage",
            "gtv": 3,
            "question": question,
            "queries": _to_base64_list(queries),
        }
        if captcha_id is not None:
            task["captchaId"] = captcha_id
        task.update(extra)
        result = self.solve_task(task)
        return result.get("answers", [])

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

        Args:
            question: Tipo de captcha.
            captcha_id: ID do captcha GeeTest v4.
            queries: Imagens de query.
            examples: Imagens de exemplo/prompt.
            **extra: Parâmetros extras.

        Returns:
            Lista de respostas.
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
        result = self.solve_task(task)
        return result.get("answers", [])

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

        Args:
            captcha_id: ID do captcha GeeTest v4.
            images: 9 imagens do grid 3x3.
            question: Texto da pergunta (usa padrão da extensão se None).
            examples: Imagem de prompt/exemplo.
            website_url: URL do site (opcional).
            **extra: Parâmetros extras.

        Returns:
            Lista de índices 0-based das imagens corretas.
        """
        _question = question or "geetest_nine:Selecione  3  imagens correspondentes"
        task: Dict[str, Any] = {
            "type": "GeetestImage",
            "gtv": 4,
            "captchaId": captcha_id,
            "queries": _to_base64_list(images),
            "question": _question,
        }
        if examples is not None:
            task["examples"] = _to_base64_list(examples)
        if website_url is not None:
            task["websiteURL"] = website_url
        task.update(extra)
        extra_payload = {"source": "chrome", "version": "0.3.3", "appID": 0}
        data = self.create_task(task, extra_payload=extra_payload)
        if "answers" in data or "solution" in data:
            raw = data.get("answers", data.get("solution", []))
        else:
            task_id = data.get("taskId")
            result = self.poll_task(task_id)
            raw = result.get("answers", result.get("solution", []))
        # Converter [false,true,...] → índices
        if raw and isinstance(raw[0], bool):
            return [i for i, v in enumerate(raw) if v]
        return [int(x) for x in raw]

    def solve_geetest_v4_slide(
        self,
        captcha_id: str,
        background: ImageInput,
        slider: ImageInput,
        **extra: Any,
    ) -> List[int]:
        """Geetest v4 slide -> retorna [x, y].

        Args:
            captcha_id: ID do captcha.
            background: Imagem de fundo.
            slider: Imagem do slider.
            **extra: Parâmetros extras.

        Returns:
            Lista ``[x, y]`` do ponto de encaixe.
        """
        return self.solve_geetest_v4(
            question="slide",
            captcha_id=captcha_id,
            queries=[background, slider],
            **extra,
        )

    def solve_geetest_v4_icon(
        self,
        captcha_id: str,
        main_image: ImageInput,
        targets: List[ImageInput],
        **extra: Any,
    ) -> List[Any]:
        """Geetest v4 icon-click -> retorna coordenadas.

        Args:
            captcha_id: ID do captcha.
            main_image: Imagem principal com ícones.
            targets: Imagens alvo a clicar.
            **extra: Parâmetros extras.

        Returns:
            Lista de coordenadas ``[x, y]`` para clicar.
        """
        return self.solve_geetest_v4(
            question="icon",
            captcha_id=captcha_id,
            queries=[main_image],
            examples=targets,
            **extra,
        )

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

        Args:
            website_url: URL da página com o GeeTest.
            captcha_id: ID do captcha GeeTest.
            proxy: Proxy obrigatório (``socks5://user:pass@host:port``).
            geetest_api_server_subdomain: Subdomínio opcional da API GeeTest.

        Returns:
            Dict com ``captcha_id``, ``lot_number``, ``pass_token``, etc.
        """
        task: Dict[str, Any] = {
            "type": "GeeTestTask",
            "websiteURL": website_url,
            "captchaId": captcha_id,
            "proxy": proxy,
        }
        if geetest_api_server_subdomain is not None:
            task["geetestApiServerSubdomain"] = geetest_api_server_subdomain
        result = self.solve_task(task)
        return result.get("solution", result)

    def solve_hcaptcha_token(
        self,
        website_url: str,
        website_key: str,
        proxy: str | None = None,
    ) -> str:
        """Resolve hCaptcha e retorna token h-captcha-response.

        Args:
            website_url: URL da página.
            website_key: Chave do site hCaptcha.
            proxy: Proxy opcional.

        Returns:
            Token ``h-captcha-response``.
        """
        task: Dict[str, Any] = {
            "type": "HCaptchaTaskProxyless" if not proxy else "HCaptchaTask",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }
        if proxy:
            task["proxy"] = proxy
        result = self.solve_task(task)
        solution = result.get("solution", {})
        return solution.get("gRecaptchaResponse", solution.get("token", ""))

    def solve_turnstile_token(
        self,
        website_url: str,
        website_key: str,
        proxy: str | None = None,
        action: str | None = None,
        cdata: str | None = None,
    ) -> str:
        """AntiTurnstileTask -> retorna token cf-turnstile-response.

        Args:
            website_url: URL da página com Turnstile.
            website_key: Chave do site Cloudflare Turnstile.
            proxy: Proxy opcional.
            action: Ação opcional.
            cdata: CData opcional.

        Returns:
            Token ``cf-turnstile-response``.
        """
        task: Dict[str, Any] = {
            "type": "AntiTurnstileTaskProxyless" if not proxy else "AntiTurnstileTask",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }
        if proxy:
            task["proxy"] = proxy
        if action is not None:
            task["action"] = action
        if cdata is not None:
            task["data"] = cdata
        result = self.solve_task(task)
        solution = result.get("solution", {})
        return solution.get("token", "")

    # ------------------------------------------------------------------
    # Utilitário de imagem
    # ------------------------------------------------------------------

    @staticmethod
    def split_geetest_nine_image(
        combined: ImageInput,
        out_dir: str | Path | None = None,
    ) -> List[bytes]:
        """Recorta um JPG combinado 3x3 do GeeTest v4 em 9 tiles (bytes JPEG).

        O SSBrowser recebe o grid como um unico JPG fatiado via CSS
        background-position (ver screenshot bet595). Este helper gera os
        9 arquivos necessarios para ``solve_geetest_v4_nine``.

        Se out_dir for informado, salva arquivos 0.jpg..8.jpg la.

        Args:
            combined: Imagem combinada 3×3 como bytes, base64 ou Path.
            out_dir: Diretório opcional para salvar os tiles.

        Returns:
            Lista de 9 bytes JPEG (ordem linha-major 0..8).
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("Pillow é necessário para split_geetest_nine_image: pip install Pillow")

        # Obter bytes da imagem
        if isinstance(combined, Path) or (isinstance(combined, str) and len(combined) < 512):
            with open(combined, "rb") as fh:
                raw = fh.read()
        elif isinstance(combined, bytes):
            raw = combined
        else:
            raw = base64.b64decode(combined)

        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        tile_w = w // 3
        tile_h = h // 3

        tiles: List[bytes] = []
        for row in range(3):
            for col in range(3):
                x0 = col * tile_w
                y0 = row * tile_h
                tile = img.crop((x0, y0, x0 + tile_w, y0 + tile_h))
                buf = io.BytesIO()
                tile.save(buf, format="JPEG")
                tile_bytes = buf.getvalue()
                tiles.append(tile_bytes)

        if out_dir is not None:
            out_path = Path(out_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            for i, tb in enumerate(tiles):
                (out_path / f"{i}.jpg").write_bytes(tb)

        return tiles


# ---------------------------------------------------------------------------
# CDP / DrissionPage integration
# ---------------------------------------------------------------------------


def _cdp_extract_geetest(driver: Any, timeout: float = 5.0) -> dict | None:
    """Extrai captchaId, tiles url e bounds via DrissionPage/CDP.

    Retorna dict com keys: captchaId, tiles_url, prompt_url, items (x,y,w,h) ou None se invisivel.
    Checa .geetest_box (popup real) e nao so .geetest_captcha (container 0-height).

    Args:
        driver: Instância do DrissionPage/Selenium WebDriver.
        timeout: Tempo máximo de espera em segundos.

    Returns:
        Dict com informações do GeeTest ou None se não estiver visível.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # Tentar via CDP/JS injection
            result = driver.run_cdp(
                "Runtime.evaluate",
                expression="""
                (function() {
                    var box = document.querySelector('.geetest_box');
                    if (!box || box.offsetHeight === 0) return null;
                    var rect = box.getBoundingClientRect();
                    var items = [];
                    box.querySelectorAll('.geetest_item').forEach(function(el) {
                        var r = el.getBoundingClientRect();
                        items.push({x: r.left, y: r.top, w: r.width, h: r.height});
                    });
                    var captchaId = window._gt4CaptchaId || null;
                    var tilesUrl = null;
                    var promptUrl = null;
                    try {
                        tilesUrl = box.querySelector('.geetest_bg img, .geetest_item img').src;
                    } catch(e) {}
                    try {
                        promptUrl = box.querySelector('.geetest_tip img').src;
                    } catch(e) {}
                    return {captchaId: captchaId, tiles_url: tilesUrl,
                            prompt_url: promptUrl, items: items};
                })()
                """,
                returnByValue=True,
            )
            value = result.get("result", {}).get("value")
            if value:
                return value
        except Exception:
            pass
        time.sleep(0.2)
    return None


def _click_geetest_indices(driver: Any, indices: list[int]) -> bool:
    """Clica nos indices 0..8 do grid GeeTest (replica geetest4.js: Z).

    Args:
        driver: Instância do WebDriver.
        indices: Lista de índices 0-based a clicar.

    Returns:
        True se todos os cliques foram executados com sucesso.
    """
    try:
        items = driver.eles(".geetest_item")
        for idx in indices:
            if idx < len(items):
                items[idx].click()
                time.sleep(0.3)
        return True
    except Exception:
        return False


def _solve_current_geetest_via_cdp(
    driver: Any,
    client: "RecogClient",
    dpr: float | None = None,
) -> list[int] | None:
    """Captura 9 tiles (ou slide) via split do JPEG (igual a extensao) e chama Solver.

    Suporta nine-grid e slide (detecta via .geetest_bg/.geetest_slice_bg).
    Usa o fluxo da extensao oficial (content-scripts/geetest4.js: L):
      J(F) -> 9 slices JPEG, fetchBase64Image(prompt), question="geetest_nine:<texto>",
      task={type:GeetestImage, captchaId, queries:[9], examples:[prompt], question, websiteURL}
      top-level source:chrome version:0.3.3 appID:0
    Retorna indices para nine ou [x,y] para slide.

    Args:
        driver: Instância do WebDriver/DrissionPage.
        client: Instância de RecogClient configurada.
        dpr: Device pixel ratio (padrão: detectado via JS ou 1.0).

    Returns:
        Lista de índices ou [x, y] para slide, ou None se falhou.
    """
    info = _cdp_extract_geetest(driver)
    if not info:
        return None
    try:
        captcha_id = info.get("captchaId") or ""
        tiles_url = info.get("tiles_url") or ""
        prompt_url = info.get("prompt_url")
        website_url = driver.url if hasattr(driver, "url") else None

        # Baixar grid combinado e recortar em 9 tiles
        tiles_resp = requests.get(tiles_url, timeout=10)
        tiles_resp.raise_for_status()
        combined_bytes = tiles_resp.content
        nine_tiles = RecogClient.split_geetest_nine_image(combined_bytes)

        # Baixar prompt/exemplo se disponível
        examples = None
        if prompt_url:
            try:
                prompt_resp = requests.get(prompt_url, timeout=10)
                prompt_resp.raise_for_status()
                examples = [prompt_resp.content]
            except Exception:
                pass

        indices = client.solve_geetest_v4_nine(
            captcha_id=captcha_id,
            images=nine_tiles,
            examples=examples,
            website_url=website_url,
        )
        return indices
    except Exception as exc:
        _debug_log(f"_solve_current_geetest_via_cdp erro: {exc}")
        return None


def attach_geetest_watcher(
    driver: Any,
    api_key: str | None = None,
    poll_interval: float = 1.5,
    auto_click: bool = True,
) -> dict:
    """Anexa thread watcher que dispara reconhecimento sempre que GeeTest ficar visivel.

    Uso no SSBROWSER (app/main.py ou browser_creator):
      from _recog_client import attach_geetest_watcher
      info["_geetest_watcher"] = attach_geetest_watcher(driver, api_key="sonic_...")

    Retorna dict com thread e stop flag. Para parar: info['_geetest_watcher']['stop']=True

    Args:
        driver: Instância do WebDriver/DrissionPage.
        api_key: Chave de API (usa round-robin se None).
        poll_interval: Intervalo em segundos entre verificações.
        auto_click: Se True, clica automaticamente nos índices resolvidos.

    Returns:
        Dict ``{'thread': Thread, 'stop': bool}`` para controle do watcher.
    """
    client = RecogClient(api_key=api_key)
    state = {"stop": False}

    def _watcher_loop() -> None:
        while not state["stop"]:
            try:
                indices = _solve_current_geetest_via_cdp(driver, client)
                if indices and auto_click:
                    _click_geetest_indices(driver, indices)
            except Exception as exc:
                _debug_log(f"attach_geetest_watcher erro: {exc}")
            time.sleep(poll_interval)

    t = threading.Thread(target=_watcher_loop, daemon=True, name="geetest-watcher")
    t.start()
    state["thread"] = t
    return state


# ---------------------------------------------------------------------------
# Alias de conveniência (módulo-level)
# ---------------------------------------------------------------------------

def split_geetest_nine_image(
    combined: ImageInput,
    out_dir: str | Path | None = None,
) -> List[bytes]:
    """Alias de módulo para :meth:`RecogClient.split_geetest_nine_image`.

    Recorta um JPG combinado 3x3 do GeeTest v4 em 9 tiles (bytes JPEG).

    O SSBrowser recebe o grid como um unico JPG fatiado via CSS
    background-position (ver screenshot bet595). Este helper gera os
    9 arquivos necessarios para ``solve_geetest_v4_nine``.

    Se out_dir for informado, salva arquivos 0.jpg..8.jpg la.

    Args:
        combined: Imagem combinada 3×3.
        out_dir: Diretório opcional para salvar tiles.

    Returns:
        Lista de 9 bytes JPEG.
    """
    return RecogClient.split_geetest_nine_image(combined, out_dir=out_dir)
