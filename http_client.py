# -*- coding: utf-8 -*-
"""
Cliente HTTP assíncrono usando curl_cffi
Baseado em navegador.php

- Suporte a proxy condicional (apenas para endpoints específicos)
- Cookies persistentes por sessão
- Headers customizados
- Retry automático com backoff exponencial
- Impersonate realista com randomização de browser
"""
import asyncio
import logging
import random
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

from curl_cffi import CurlHttpVersion
from curl_cffi.requests import AsyncSession, Response

from config import PROXY_ENDPOINTS, BotConfig, ProxyConfig

logger = logging.getLogger(__name__)

# Configuração de retry
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1  # segundos (backoff: 1, 2, 4, 8, 16)
RETRYABLE_ERRORS = (
    "timeout",
    "connection",
    "timed out",
    "Connection refused",
    "Connection reset",
    "Connection aborted",
    "SSL",
    "curl:",
)

# ==================== CONFIGURAÇÃO DE BROWSERS ====================
# Cada browser tem: (impersonate_name, user_agent, weight)
# Weight define a probabilidade de ser escolhido (simula market share)

BROWSER_PROFILES: List[Tuple[str, str, int]] = [
    # Chrome Desktop (maior market share)
    (
        "chrome131",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        40,
    ),
    (
        "chrome124",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        25,
    ),
    (
        "chrome120",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        15,
    ),
    # Safari Desktop
    (
        "safari18_0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        10,
    ),
    # Edge
    (
        "edge101",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.53",
        10,
    ),
]

# Profiles para Android
BROWSER_PROFILES_ANDROID: List[Tuple[str, str, int]] = [
    (
        "chrome131_android",
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
        50,
    ),
    (
        "chrome99_android",
        "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.88 Mobile Safari/537.36",
        30,
    ),
    (
        "safari18_0_ios",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        20,
    ),
]

# Opções extra para TLS mais realista
EXTRA_FP_CHROME = {
    "tls_grease": True,                    # Extensões GREASE (Chrome faz isso)
    "tls_permute_extensions": True,        # Randomiza ordem das extensões TLS
    "tls_cert_compression": "brotli",      # Compressão de certificado
    "http2_stream_weight": 256,            # Peso do stream HTTP/2
    "http2_stream_exclusive": 1,           # Stream exclusivo
}

EXTRA_FP_SAFARI = {
    "tls_grease": False,                   # Safari não usa GREASE
    "tls_permute_extensions": False,       # Safari não randomiza
    "tls_cert_compression": "zlib",        # Safari usa zlib
    "http2_stream_weight": 256,
    "http2_stream_exclusive": 1,
}


def _select_browser_profile(profiles: List[Tuple[str, str, int]]) -> Tuple[str, str]:
    """
    Seleciona um perfil de browser baseado nos pesos (market share).
    
    Returns:
        Tuple[impersonate_name, user_agent]
    """
    total_weight = sum(p[2] for p in profiles)
    r = random.randint(1, total_weight)
    
    cumulative = 0
    for impersonate, user_agent, weight in profiles:
        cumulative += weight
        if r <= cumulative:
            return impersonate, user_agent
    
    # Fallback
    return profiles[0][0], profiles[0][1]


def _get_extra_fp(impersonate: str) -> Dict[str, Any]:
    """Retorna extra_fp baseado no tipo de browser"""
    if "safari" in impersonate.lower():
        return EXTRA_FP_SAFARI.copy()
    return EXTRA_FP_CHROME.copy()


class AsyncHttpClient:
    """
    Cliente HTTP assíncrono com curl_cffi.
    
    - Proxy aplicado APENAS em endpoints definidos em PROXY_ENDPOINTS
    - Suporte a cookies persistentes
    - Headers customizados por requisição
    - Impersonate realista com randomização
    """
    
    def __init__(
        self,
        proxy_config: Optional[ProxyConfig] = None,
        timeout: int = 30,
        user_agent: Optional[str] = None,
        use_android: bool = False,
    ):
        self.proxy_config = proxy_config
        self.timeout = timeout
        self._use_android = use_android
        
        # Seleciona perfil de browser
        profiles = BROWSER_PROFILES_ANDROID if use_android else BROWSER_PROFILES
        self._impersonate, self._browser_user_agent = _select_browser_profile(profiles)
        
        # User-agent: usa o passado ou o do browser selecionado
        self.user_agent = user_agent or self._browser_user_agent
        #print(self.user_agent)
        # Extra fingerprint para TLS realista
        self._extra_fp = _get_extra_fp(self._impersonate)
        
        # Sessão será criada no primeiro uso
        self._session: Optional[AsyncSession] = None
        
        logger.debug(f"Browser selecionado: {self._impersonate}")
    
    async def _get_session(self) -> AsyncSession:
        """Obtém ou cria sessão com configurações realistas"""
        if self._session is None:
            self._session = AsyncSession(
                timeout=self.timeout,
                verify=False,  # SSL verification desabilitado
                impersonate=self._impersonate,  # Browser selecionado
                extra_fp=self._extra_fp,  # Fingerprint TLS realista
            )
        return self._session
    
    @property
    def browser_name(self) -> str:
        """Retorna nome do browser sendo usado"""
        return self._impersonate
    
    def _should_use_proxy(self, url: str) -> bool:
        """Verifica se deve usar proxy para esta URL"""
        for endpoint in PROXY_ENDPOINTS:
            if endpoint in url:
                return True
        return False
    
    def _get_proxy_url(self, force: bool = False) -> Optional[str]:
        """Retorna URL do proxy se configurado
        
        Args:
            force: Se True, retorna URL da proxy mesmo se usar_proxy=False
        """
        if self.proxy_config:
            # Se force=True, ignora usar_proxy e retorna a URL
            if force or self.proxy_config.usar_proxy:
                return f"socks5://{self.proxy_config.username}:{self.proxy_config.password}@{self.proxy_config.host}:{self.proxy_config.port}"
        return None
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Verifica se o erro é retentável"""
        error_str = str(error).lower()
        for retryable in RETRYABLE_ERRORS:
            if retryable.lower() in error_str:
                return True
        return False

    async def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Union[str, Dict, bytes]] = None,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        use_proxy: Optional[bool] = None,
        timeout: Optional[int] = None,
        follow_redirects: bool = False,
        max_retries: int = MAX_RETRIES,
        http_version: Optional[CurlHttpVersion] = None,
    ) -> Response:
        """
        Faz requisição HTTP com retry automático.
        
        Args:
            url: URL da requisição
            method: Método HTTP (GET, POST, etc.)
            headers: Headers customizados
            data: Dados para POST (string, dict ou bytes)
            json_data: Dados JSON para POST
            params: Query parameters
            use_proxy: Força uso/não uso de proxy (None = automático)
            timeout: Timeout específico para esta requisição
            follow_redirects: Seguir redirecionamentos
            max_retries: Número máximo de tentativas (padrão: 5)
        
        Returns:
            Response object
        """
        session = await self._get_session()
        
        # Determina se usa proxy
        if use_proxy is None:
            use_proxy = self._should_use_proxy(url)
            force_proxy = False
        else:
            force_proxy = use_proxy  # Se foi explicitamente passado, força
        
        proxy = self._get_proxy_url(force=force_proxy) if use_proxy else None
        
        # Prepara headers com User-Agent do browser selecionado
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": self._get_sec_ch_ua(),
            "Sec-Ch-Ua-Mobile": "?1" if self._use_android else "?0",
            "Sec-Ch-Ua-Platform": '"Android"' if self._use_android else '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        if headers:
            request_headers.update(headers)
        
        # Prepara kwargs
        kwargs: Dict[str, Any] = {
            "headers": request_headers,
            "timeout": timeout or self.timeout,
            "allow_redirects": follow_redirects,
        }
        
        if proxy:
            kwargs["proxy"] = proxy
            logger.debug(f"Usando proxy para {url}")
        
        if params:
            kwargs["params"] = params
        
        if data is not None:
            kwargs["data"] = data
        
        if json_data is not None:
            kwargs["json"] = json_data
        
        if http_version is not None:
            kwargs["http_version"] = http_version
        
        last_error: Optional[Exception] = None
        proxy_error_text: Optional[str] = None
        
        for attempt in range(1, max_retries + 1):
            try:
                response = await session.request(method, url, **kwargs)
                logger.debug(f"{method} {url} -> {response.status_code}")
                return response
            except Exception as e:
                last_error = e
                err_lower = str(e).lower()
                is_proxy_error = bool(proxy) and (
                    "proxy" in err_lower
                    or "curl: (97)" in err_lower
                    or "curl:(97)" in err_lower
                )
                if is_proxy_error:
                    proxy_error_text = str(e)
                    try:
                        await self.close()
                    except Exception:
                        pass
                    session = await self._get_session()
                
                # Verifica se é um erro retentável
                if not self._is_retryable_error(e):
                    logger.error(f"Erro não retentável na requisição {method} {url}: {e}")
                    raise
                
                # Se ainda tem tentativas
                if attempt < max_retries:
                    # Backoff exponencial: 1, 2, 4, 8, 16 segundos
                    delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
        
        # Se chegou aqui, todas as tentativas falharam
        if proxy and force_proxy and proxy_error_text:
            try:
                return await self.request(
                    url=url,
                    method=method,
                    headers=headers,
                    data=data,
                    json_data=json_data,
                    params=params,
                    use_proxy=False,
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                    max_retries=1,
                )
            except Exception:
                pass
        raise last_error
    
    def _get_sec_ch_ua(self) -> str:
        """Gera header Sec-Ch-Ua baseado no browser"""
        if "chrome131" in self._impersonate:
            return '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
        elif "chrome124" in self._impersonate:
            return '"Google Chrome";v="124", "Chromium";v="124", "Not_A Brand";v="24"'
        elif "chrome120" in self._impersonate:
            return '"Google Chrome";v="120", "Chromium";v="120", "Not_A Brand";v="24"'
        elif "chrome99" in self._impersonate:
            return '"Google Chrome";v="99", "Chromium";v="99", ";Not A Brand";v="99"'
        elif "edge" in self._impersonate:
            return '"Microsoft Edge";v="101", "Chromium";v="101", ";Not A Brand";v="99"'
        elif "safari" in self._impersonate:
            return ""  # Safari não envia Sec-Ch-Ua
        return '"Chromium";v="124", "Not_A Brand";v="24"'
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict] = None,
        **kwargs,
    ) -> Response:
        """GET request"""
        return await self.request(url, "GET", headers=headers, params=params, **kwargs)
    
    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Union[str, Dict, bytes]] = None,
        json_data: Optional[Dict] = None,
        **kwargs,
    ) -> Response:
        """POST request"""
        return await self.request(
            url, "POST", headers=headers, data=data, json_data=json_data, **kwargs
        )
    
    async def post_form(
        self,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Response:
        """POST request com form data (application/x-www-form-urlencoded)"""
        form_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            form_headers.update(headers)
        
        encoded_data = urlencode(data)
        return await self.request(
            url, "POST", headers=form_headers, data=encoded_data, **kwargs
        )
    
    async def get_text(self, url: str, **kwargs) -> str:
        """GET request retornando texto"""
        response = await self.get(url, **kwargs)
        return response.text
    
    async def get_json(self, url: str, **kwargs) -> Any:
        """GET request retornando JSON"""
        response = await self.get(url, **kwargs)
        return response.json()
    
    async def post_json(
        self,
        url: str,
        data: Optional[Union[str, Dict]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Any:
        """POST request retornando JSON"""
        response = await self.post(url, headers=headers, data=data, **kwargs)
        return response.json()
    
    async def close(self):
        """Fecha a sessão"""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class BotHttpClient(AsyncHttpClient):
    """
    Cliente HTTP especializado para o bot.
    
    - Configuração automática de proxy e user-agent
    - Métodos específicos para API da plataforma
    - Impersonate realista baseado no device_model
    """
    
    def __init__(self, config: BotConfig, user_agent: str):
        # Detecta se é Android baseado no user_agent
        is_android = "Android" in user_agent or "Mobile" in user_agent
        
        super().__init__(
            proxy_config=config.proxy,
            timeout=config.request_timeout,
            user_agent=user_agent,
            use_android=is_android,
        )
        self.config = config
    
    async def api_request(
        self,
        api_url: str,
        endpoint: str,
        data: str,
        headers: Dict[str, str],
        use_proxy: Optional[bool] = None,
    ) -> str:
        """
        Requisição para API da plataforma.
        
        Args:
            api_url: URL base da API
            endpoint: Endpoint (ex: /hall/api/member/register)
            data: Dados criptografados
            headers: Headers da requisição
            use_proxy: Força uso/não uso de proxy
        
        Returns:
            Texto da resposta
        """
        url = f"{api_url}{endpoint}"
        
        # Determina proxy automaticamente se não especificado
        if use_proxy is None:
            use_proxy = self._should_use_proxy(endpoint)
        
        response = await self.post(
            url,
            headers=headers,
            data=data,
            use_proxy=use_proxy,
        )
        
        return response.text
    
    async def game_request(
        self,
        game_api: str,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        use_proxy: bool = False,
        http_version: Optional[CurlHttpVersion] = CurlHttpVersion.V1_1,
    ) -> Any:
        """
        Requisição para API do jogo.
        
        Args:
            game_api: URL da API do jogo
            endpoint: Endpoint
            data: Dados do POST
            headers: Headers customizados (opcional)
            use_proxy: Usar proxy (opcional)
        
        Returns:
            Resposta JSON
        """
        url = f"https://{game_api}{endpoint}"
        
        response = await self.post_form(
            url,
            data,
            headers=headers,
            use_proxy=use_proxy,
            follow_redirects=True,
            http_version=http_version,
        )
        
        try:
            return response.json()
        except:
            return response.text
