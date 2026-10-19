# -*- coding: utf-8 -*-
"""
Lógica principal do Bot
Baseado em superbot.php

Etapas:
1. Obter configurações da plataforma
2. Registro (com proxy)
3. Configurar conta
4. Resgatar código Telegram
5. Jogar
"""
from tkinter import FALSE
import asyncio
import hashlib
import base64
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
from colorama import Fore, Style
from config import BotConfig, CONFIG_KEY_B64, runtime_config, get_cpf_from_file
from database import salvar_conta
import sys
from gee_token import get_gee_token, get_gee_token_individual, mark_gee_token_used, release_gee_token, get_gee_token_manager


def debug_log(message: str):
    """Log somente se DEBUG_MODE estiver ativo"""
    if runtime_config["DEBUG_MODE"]:
        try:
            logging.getLogger(__name__).debug(message)
        except UnicodeEncodeError:
            # Tenta imprimir apenas caracteres ASCII se houver erro de codificação
            try:
                msg_safe = str(message).encode('ascii', errors='replace').decode('ascii')
                logging.getLogger(__name__).debug(msg_safe)
            except:
                pass
from http_client import BotHttpClient
from utils import (
    SimpleMsgPack,
    buscar_jogo_pg,
    buscar_jogo_pg_aleatorio,
    calcular_jogada,
    codigo_pg,
    decrypt,
    decrypt_b64_aes128_ecb,
    decrypt_request,
    encrypt,
    encrypt_request,
    extract_options_pg,
    extract_value,
    flash_browsers,
    flash_headers,
    generate_android_version,
    generate_device_model,
    generate_wechat_id,
    gerar_celular,
    gerar_cpf,
    gerar_data_nascimento,
    gerar_email,
    gerar_nome_completo,
    gerar_senha,
    gerar_senha_segura,
    gerar_usuario_por_nome,
    gerar_usuario,
    is_base64,
    is_json,
    numero,
    postdata_register,
    postdata_validate,
    set_headers,
    uuid4,
    generate_key,
)
from game_gem_trava import game_gem_trava
from game_hood_vs_wolf_trava import game_hood_vs_wolf_trava
from services.pp_games import play_pp_recovery
from services.firestrike2 import game_firestrike_logic, firestrike_zerar
from services.fire88 import game_fire88_logic, fire88_zerar
from services.spirit_adventure import game_spirit_logic
from services.voodoo_magic import game_voodoo_logic
from services.muertos_multiplier import game_muertos_logic
from services.pure_platinum import game_pure_platinum_logic
from services.diamond_cluster import game_diamond_cluster_logic
from services.lucky_charm import game_lucky_charm_logic
from services.treasure_house import game_treasure_house_logic

logger = logging.getLogger(__name__)


@dataclass
class AccountData:
    """Dados da conta criada"""
    usuario: str = ""
    senha: str = ""
    senha_saque: str = ""
    email: str = ""
    cpf: str = ""
    telefone: str = ""
    nome_completo: str = ""
    pix: str = ""
    saldo: float = 0.0
    bonus: float = 0.0  # Valor do bônus coletado
    url: str = ""
    platform: str = ""  # Nome da plataforma
    sitecode: str = ""  # Código da plataforma
    token_login: str = ""
    success: bool = False
    error: str = ""
    bonus_travado: bool = False  # True se encontrou bônus no Gem Saviour
    x_device: str = ""  # x-device usado no registro


@dataclass
class PlatformConfig:
    """Configurações da plataforma"""
    url_domain: str = ""
    api_url: str = ""
    host: str = ""
    sitecode: str = ""
    speed_version: str = "1.1.50"
    app_version: str = "7.0.105"
    inviter_id: str = ""  # ID do convidador extraído da URL (ex: ?id=123456)


# Cache global de configurações de plataforma (em memória + arquivo)
_platform_config_cache: Dict[str, PlatformConfig] = {}
_platform_config_locks: Dict[str, asyncio.Lock] = {}
_platform_config_locks_lock = asyncio.Lock()  # Lock para criar locks
CACHE_DIR = "cache"


async def obter_config_plataforma(url: str, config: BotConfig) -> Optional[PlatformConfig]:
    """
    Obtém configurações da plataforma (função pública para usar antes de iniciar bots).
    Testa velocidade das APIs e salva em cache.

    Args:
        url: URL da plataforma
        config: Configuração do bot (para proxy, etc)

    Returns:
        PlatformConfig ou None se falhar
    """
    global _platform_config_cache, _platform_config_locks
    from urllib.parse import urlparse, parse_qs
    from http_client import BotHttpClient

    url = url.strip()
    parsed = urlparse(url)
    url_host = parsed.netloc

    # Verifica cache em memória
    if url in _platform_config_cache:
        cached = _platform_config_cache[url]
        # Atualiza inviter_id da URL atual
        query_params = parse_qs(parsed.query)
        inviter_id = query_params.get("id", [""])[0]
        if inviter_id:
            cached.inviter_id = inviter_id
        logging.info(f"⚙️ [CONFIG] Cache memória: {cached.sitecode} (API: {cached.api_url})")
        return cached

    # Obtém ou cria lock para esta URL
    async with _platform_config_locks_lock:
        if url not in _platform_config_locks:
            _platform_config_locks[url] = asyncio.Lock()
        lock = _platform_config_locks[url]

    async with lock:
        # Double-check após lock
        if url in _platform_config_cache:
            cached = _platform_config_cache[url]
            query_params = parse_qs(parsed.query)
            inviter_id = query_params.get("id", [""])[0]
            if inviter_id:
                cached.inviter_id = inviter_id
            return cached

        # Tenta carregar do arquivo
        if os.path.exists(CACHE_DIR):
            for cache_file in os.listdir(CACHE_DIR):
                if cache_file.endswith(".txt"):
                    sitecode = cache_file.replace(".txt", "")
                    cache_result = _load_platform_config_from_file(sitecode)

                    if cache_result:
                        cached_config, original_host = cache_result

                        if original_host == url_host or cached_config.host == url_host:
                            query_params = parse_qs(parsed.query)
                            inviter_id = query_params.get("id", [""])[0]
                            if inviter_id:
                                cached_config.inviter_id = inviter_id
                                #logging.info(f"[CONFIG] InviterId: {inviter_id}")

                            _platform_config_cache[url] = cached_config
                            #logging.info(f"[CONFIG] Cache arquivo: {sitecode}.txt (API: {cached_config.api_url})")
                            return cached_config

        # Busca via API (testa velocidade)
        logging.info(f"🔍 [CONFIG] Buscando config da plataforma...")
        logging.info(f"🌐 [CONFIG] URL: {url}")
        result = await _fetch_platform_config_standalone(url, config)

        if result:
            _platform_config_cache[url] = result
            _save_platform_config_to_file(result, url_host)
            logging.info(f"💾 [CONFIG] Salvo em cache: {result.sitecode}.txt (API: {result.api_url})")

        return result


async def _test_fastest_domain_standalone(
    http: 'BotHttpClient',
    domains: list,
    test_path: str = "/",
    label: str = "API",
    rounds: int = 3
) -> Optional[str]:
    """Testa múltiplos domínios em paralelo e retorna o mais rápido (standalone)"""
    if not domains:
        return None

    if len(domains) == 1:
        return domains[0]

    logging.info(f"🏎️ [CONFIG] === Testando {len(domains)} {label}s ({rounds}x cada) ===")

    domain_times: Dict[str, list] = {d: [] for d in domains}
    domain_status: Dict[str, str] = {d: "" for d in domains}

    async def test_domain_once(domain: str) -> Tuple[str, float, str]:
        try:
            start = time.time()
            test_url = f"{domain.rstrip('/')}{test_path}"
            response = await http.get(test_url, use_proxy=True, timeout=5, max_retries=1)
            elapsed = time.time() - start

            if response.status_code < 500:
                return (domain, elapsed, f"{response.status_code}")
            else:
                return (domain, float('inf'), f"HTTP {response.status_code}")
        except Exception:
            return (domain, float('inf'), "ERRO")

    for round_num in range(1, rounds + 1):
        logging.info(f"🔄 [CONFIG] Round {round_num}/{rounds}...")

        tasks = [test_domain_once(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, tuple):
                domain, elapsed, status = result
                domain_times[domain].append(elapsed)
                domain_status[domain] = status

    # Calcula média
    domain_avg: Dict[str, float] = {}
    for domain, times in domain_times.items():
        valid_times = [t for t in times if t != float('inf')]
        domain_avg[domain] = sum(valid_times) / len(valid_times) if valid_times else float('inf')

    sorted_domains = sorted(domain_avg.items(), key=lambda x: x[1])

    fastest = None
    fastest_avg = float('inf')

    logging.info(f"📊 [CONFIG] --- Resultados (média de {rounds} testes) ---")

    for domain, avg in sorted_domains:
        times = domain_times[domain]
        valid_times = [t for t in times if t != float('inf')]
        fails = len(times) - len(valid_times)
        status = domain_status[domain]

        if avg == float('inf'):
            avg_str = "  FAIL"
            min_str = "  -  "
            max_str = "  -  "
            marker = "  "
        else:
            avg_str = f"{avg*1000:>5.0f}ms"
            min_str = f"{min(valid_times)*1000:>5.0f}ms"
            max_str = f"{max(valid_times)*1000:>5.0f}ms"

            if fastest is None:
                fastest = domain
                fastest_avg = avg
                marker = ">>"
            else:
                marker = "  "

        fail_info = f" ({fails} falhas)" if fails > 0 else ""
        logging.info(f"   [CONFIG] {marker} AVG:{avg_str} | MIN:{min_str} | MAX:{max_str} | ({status}){fail_info} {domain}")

    if fastest:
        logging.info(f"✅ [CONFIG] >> Selecionada: {fastest} (média: {fastest_avg*1000:.0f}ms)")
    else:
        logging.info(f"❌ [CONFIG] !! Nenhuma {label} respondeu!")

    return fastest


async def _fetch_platform_config_standalone(url: str, config: BotConfig) -> Optional[PlatformConfig]:
    """Busca config da plataforma sem cache (standalone)"""
    from http_client import BotHttpClient
    from urllib.parse import urlparse, parse_qs

    http = BotHttpClient(config, "")

    try:
        response = await http.get(url, use_proxy=True)
        html = response.text

        cfg = None
        version_data = None
        domains = []

        # Método 1: preconnect link
        match = re.search(r'<link\s+rel=preconnect\s+href=([^\s>]+)\s+crossorigin="">', html, re.I)
        if match:
            base = match.group(1).rstrip("/")

            cfg_response = await http.get(f"{base}/cocos/config_data.json", use_proxy=True)
            cfg_text = cfg_response.text

            try:
                cfg = json.loads(cfg_text)
            except:
                cfg = json.loads(decrypt_b64_aes128_ecb(cfg_text, CONFIG_KEY_B64))

            ver_response = await http.get(
                f"{base}/hall/api/lobby/webapi/forceUpdate/getForceUpdate.json",
                use_proxy=True
            )
            ver_text = ver_response.text

            try:
                version_data = json.loads(ver_text)
            except:
                version_data = json.loads(decrypt_b64_aes128_ecb(ver_text, CONFIG_KEY_B64))

        # Método 2: fallback
        if not cfg:
            parsed = urlparse(url)
            host = parsed.netloc

            fallback_url = f"https://{host}/fapage/sd/{host}.json?t={int(time.time())}"
            fallback_response = await http.get(fallback_url, use_proxy=True)

            plain = decrypt_b64_aes128_ecb(fallback_response.text, CONFIG_KEY_B64)
            obj = json.loads(plain)

            rels = obj.get("data", {}).get("targetRelations", [])

            for rel in rels:
                rel = rel.rstrip("/")
                if not rel:
                    continue

                try:
                    cfg_response = await http.get(f"{rel}/cocos/config_data.json", use_proxy=True)
                    cfg_text = cfg_response.text

                    try:
                        cfg = json.loads(cfg_text)
                    except:
                        cfg = json.loads(decrypt_b64_aes128_ecb(cfg_text, CONFIG_KEY_B64))

                    if cfg:
                        oss = cfg.get("oss_url", [""])[0]
                        if oss:
                            force_url = oss.replace(
                                "/cocos/config_data.json",
                                "/hall/api/lobby/webapi/forceUpdate/getForceUpdate.json"
                            )
                            ver_response = await http.get(force_url, use_proxy=True)
                            try:
                                version_data = json.loads(ver_response.text)
                            except:
                                version_data = json.loads(decrypt_b64_aes128_ecb(ver_response.text, CONFIG_KEY_B64))
                        break
                except:
                    continue

        if not cfg:
            return None

        # Extrai domínios
        for key in ["non_ma_domain", "lobby_domain"]:
            for d in cfg.get(key, []):
                if d:
                    domains.append(d)

        if not domains:
            return None

        # Escolhe domínio CDN (prefere azure/cloud)
        url_domain = None
        for d in domains:
            if re.search(r"(azure|cloud)", d):
                url_domain = d
                break
        if not url_domain:
            url_domain = domains[0]

        # Testa qual API responde mais rápido
        api_domains = cfg.get("api_domain", [])
        if api_domains and len(api_domains) > 1:
            api_url = await _test_fastest_domain_standalone(http, api_domains, "/", label="API")
            if not api_url:
                api_url = api_domains[0]
        elif api_domains:
            api_url = api_domains[0]
        else:
            api_url = url_domain

        # Host e inviter_id
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        inviter_id = query_params.get("id", [""])[0]
        host = urlparse(url_domain).netloc

        if inviter_id:
            logging.info(f"👤 [CONFIG] InviterId: {inviter_id}")

        await http.close()

        return PlatformConfig(
            url_domain=url_domain,
            api_url=api_url,
            host=host,
            sitecode=str(cfg.get("siteCode", 0)),
            speed_version=version_data.get("data", {}).get("androidWebSpeedPkgVersion", "1.1.20") if version_data else "1.1.20",
            app_version=version_data.get("data", {}).get("androidPkgVersion", "6.1.150") if version_data else "6.1.150",
            inviter_id=inviter_id,
        )

    except Exception as e:
        logger.error(f"❌ [CONFIG] Erro ao obter config: {e}")
        return None
    finally:
        try:
            await http.close()
        except:
            pass


def _get_cache_file_path(sitecode: str) -> str:
    """Retorna o caminho do arquivo de cache para um sitecode"""
    return os.path.join(CACHE_DIR, f"{sitecode}.txt")


def _load_platform_config_from_file(sitecode: str) -> Optional[Tuple[PlatformConfig, str]]:
    """Carrega config da plataforma do arquivo de cache

    Returns:
        Tuple[PlatformConfig, original_host] ou None se não encontrado
    """
    cache_file = _get_cache_file_path(sitecode)

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = PlatformConfig(
            url_domain=data.get("url_domain", ""),
            api_url=data.get("api_url", ""),
            host=data.get("host", ""),
            sitecode=data.get("sitecode", ""),
            speed_version=data.get("speed_version", "1.1.20"),
            app_version=data.get("app_version", "6.1.150"),
            inviter_id=data.get("inviter_id", ""),
        )

        original_host = data.get("original_host", "")
        return config, original_host
    except Exception as e:
        logger.warning(f"⚠️ Erro ao carregar cache {cache_file}: {e}")
        return None


def _save_platform_config_to_file(config: PlatformConfig, original_host: str) -> None:
    """Salva config da plataforma no arquivo de cache (sem inviter_id)"""
    if not config.sitecode:
        return

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = _get_cache_file_path(config.sitecode)

    try:
        # Não salva inviter_id pois é dinâmico (vem da URL)
        data = {
            "url_domain": config.url_domain,
            "api_url": config.api_url,
            "host": config.host,
            "sitecode": config.sitecode,
            "speed_version": config.speed_version,
            "app_version": config.app_version,
            "original_host": original_host,
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        debug_log(f"Config salva em {cache_file}")
    except Exception as e:
        logger.warning(f"⚠️ Erro ao salvar cache {cache_file}: {e}")


class CPBrigProvider:
    """
    Motor de jogo para a provedora CPBrig (Sunshine Coast e outros)
    """
    
    def __init__(self, http_client, token: str, gid: int = 2240, sub_gid: str = "3070065", origin: str = None, referer: str = None):
        self.http = http_client
        self.token = token
        self.gid = gid
        self.sub_gid = sub_gid
        self.origin = origin or "https://d1r01cd7jv2fxe.cloudfront.net"
        self.referer = referer or "https://d1r01cd7jv2fxe.cloudfront.net/"
        self.base_url = "api.cpbrig.com"
        self.last_balance = 0.0
        self.expire_offset = 0 # Pode ser usado se houver dessincronização de horário
        self.secret = "3fZ8kL2qW9xA4pT7vJ1rQ6yB0sN5mX8h"

    def _md5(self, s: str) -> str:
        return hashlib.md5(s.encode()).hexdigest()
        
    def _get_timestamp_ms(self) -> int:
        return int((time.time() + self.expire_offset) * 1000)

    def _format_val(self, v: Any) -> str:
        """Formata valor para o hash seguindo o comportamento do JS toString()"""
        if isinstance(v, bool):
            return str(v).lower()
        if isinstance(v, (int, float)):
            # Se for um número inteiro em formato float (ex: 1.0), remove o .0
            if v == int(v):
                return str(int(v))
            # Senão usa representação padrão (ex: 0.05 -> "0.05")
            return str(v)
        return str(v)

    def _calculate_signapt(self, params: Dict[str, Any], expire: int) -> str:
        """
        Algoritmo real descoberto no main.idx:
        MD5(SecretKey + Expire + SortedJoinedParams + "aptsignature")
        Onde SortedJoinedParams é key1=val1:key2=val2... (ordenado por chave)
        """
        # Filtra campos que não entram no hash (signapt e o próprio expire da requisição final)
        keys_for_hash = sorted([k for k in params.keys() if k not in ["signapt", "expire"]])
        
        # Constrói a string key=value:key=value
        joined_params = ":".join(f"{k}={self._format_val(params[k])}" for k in keys_for_hash)
        
        # Concatena: Secret + Expire + Params + Salt
        full_str = f"{self.secret}{expire}{joined_params}aptsignature"
        
        return self._md5(full_str)

    def _get_headers(self) -> Dict[str, str]:
        """Headers obrigatórios para o Sunshine Coast / CPBrig baterem"""
        return {
            "Origin": self.origin,
            "Referer": self.referer,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }

    def _get_common_params(self, device_id: str) -> Dict[str, Any]:
        """Retorna o conjunto padrão de parâmetros que o CPBrig exige em todas as requisições"""
        return {
            "token": self.token,
            "mainVer": "",
            "subVer": "",
            "pkgName": "h5_client",
            "nativeVer": "0",
            "deviceid": device_id,
            "Type": "101",
            "source": "10",
            "os": "Windows",
            "ioswebclip": "0",
            "isShell": "0",
            "gid": str(self.gid),
            "sub_gid": self.sub_gid, 
            "ver_code": "undefined",
            "language": "pt-pt",
            "sys_version": "v2.0"
        }

    async def get_user_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Busca informações do usuário e sincroniza o token de sessão"""
        expire = self._get_timestamp_ms()
        params = self._get_common_params(device_id)
        params["signapt"] = self._calculate_signapt(params, expire)
        params["expire"] = str(expire)
        
        try:
            response = await self.http.game_request(
                self.base_url,
                "/account/getUserInfo",
                params,
                headers=self._get_headers()
            )
            
            if isinstance(response, dict):
                # Caso o motor retorne code 0 ou venha flat
                data = response.get("data", response)
                if not isinstance(data, dict):
                    data = {}
                
                # Sincroniza token e GID de retorno
                new_token = data.get("token")
                if new_token: self.token = new_token
                
                new_gid = data.get("gid")
                if new_gid:
                    try: self.gid = int(new_gid)
                    except: pass
                
                # Atualiza saldo (Nesta plataforma o valor já vem em Reais)
                for campo in ["gold", "balance", "user_gold", "amount"]:
                    val = data.get(campo)
                    if val is not None:
                        self.last_balance = float(val)
                        break
                
                # Guarda as apostas permitidas (se houver)
                self.available_bets = data.get("game_info", {}).get("bet_gold", [])
                
                return data
            else:
                logger.error(f"Erro no getUserInfo CPBrig: {response}")
                return None
        except Exception as e:
            logger.error(f"Exceção no getUserInfo CPBrig: {e}")
            return None

    async def spin(self, device_id: str, bet: float = 0.05, level: int = 1) -> Optional[Dict[str, Any]]:
        """Executa um giro no jogo usando o conjunto completo de parâmetros para o hash bater"""
        expire = self._get_timestamp_ms()
        params = self._get_common_params(device_id)
        
        # Se a lista de apostas do servidor estiver vazia, usamos o valor sugerido.
        # Caso contrário, tentamos bater com um valor da lista.
        bet_str = f"{bet:.2f}"
        
        # Parâmetros específicos do giro
        params["bet_gold"] = bet_str
        params["level"] = str(level)
        
        # Gera assinatura com os parâmetros ATUALIZADOS (incluindo o novo token e gid)
        params["signapt"] = self._calculate_signapt(params, expire)
        params["expire"] = str(expire)
        
        try:
            response = await self.http.game_request(
                self.base_url,
                "/single_game.Game/gameResult",
                params,
                headers=self._get_headers()
            )
            
            if isinstance(response, dict):
                # Captura o saldo correto do campo 'end_gold' dentro de 'data'
                # IMPORTANTE: usa 'is not None' para detectar end_gold=0.0 (conta zerada)
                data_inner = response.get("data", {})
                if isinstance(data_inner, dict):
                    # end_gold às vezes retorna os ganhos acumulados. Priorizar 'balance'.
                    for campo in ["balance", "after_gold", "cur_gold", "gold", "user_gold", "end_gold"]:
                        val = data_inner.get(campo)
                        if val is not None:
                            self.last_balance = float(val)
                            break
                
                # Caso venha com code 0 (padrão)
                if response.get("code") == 0:
                    return response.get("data", {})
                
                # Caso venha flat (conhecido no GID 2240 / Sunshine Coast)
                if "props" in response or "gold" in response or "end_gold" in response:
                    return response
                
                # Trata erros conhecidos - Silencia o log para manter o terminal limpo como na PG
                if response.get("code") == 2004:
                    logger.debug(f"CPBrig 2004: Aposta R$ {float(bet_str)*10:.2f} recusada (GID: {self.gid}).")
                
                return response
            else:
                logger.error(f"Resposta inválida no Spin CPBrig (não é dict): {response}")
                return None
        except Exception as e:
            logger.error(f"Exceção no Spin CPBrig: {e}")
            return None


class Bot:
    """
    Bot principal para automação.

    Executa todas as etapas:
    1. Obter config da plataforma
    2. Registro (com Proxy)
    3. Configuração da conta
    4. Resgate do código Telegram
    5. Jogo automático
    """

    def __init__(self, config: BotConfig):
        self.config = config

        # Dados gerados
        self.nome_completo = gerar_nome_completo()        
        self.usuario = gerar_usuario_por_nome(self.nome_completo)
        self.senha = gerar_senha_segura()
        self.senha_saque = "222221"
        self.email = gerar_email(config.game.dominio_email)
        self.cpf = gerar_cpf()
        self.telefone = gerar_celular()
        
        # Device info
        self.device_id = uuid4()
        self.login_id = uuid4()
        self.token = uuid4()
        self.device_model = generate_device_model()
        self.android_version = generate_android_version()

        # Platform config (preenchido depois)
        self.platform: Optional[PlatformConfig] = None

        # Login data (preenchido depois)
        self.data_login: Optional[Dict] = None
        self.key_request: Optional[str] = None

        # HTTP client (criado depois)
        self._http: Optional[BotHttpClient] = None
        self.user_agent = ""
        
        # x-device usado no registro
        self.x_device = ""
        
        # Rastreamento de jogos e trava (inicializado aqui para garantir disponibilidade)
        self._jogos_jogados: list = []
        self._tem_bonus_monstro: bool = False
        self._bonus_original: Optional[float] = None
        self._trava_tipo: str = ""

    async def sleep(self, seconds: float):
        """Dorme por N segundos, ou pula se o modo turbo estiver ativo"""
        if self.config.turbo_mode:
            # No modo turbo, reduzimos o delay drasticamente (ou zeramos)
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(seconds)

    async def _get_http(self) -> BotHttpClient:
        """Obtém cliente HTTP"""
        if self._http is None:
            self._http = BotHttpClient(self.config, self.user_agent)
        return self._http

    async def executar(self) -> AccountData:
        """
        Executa todas as etapas do bot.

        Returns:
            AccountData com resultado
        """
        result = AccountData(
            usuario=self.usuario,
            senha=self.senha,
            senha_saque=self.senha_saque,
            email=self.email,
            cpf=self.cpf,
            telefone=self.telefone,
            nome_completo=self.nome_completo,
            url=self.config.url,
        )

        try:
            # Etapa 1: Config da plataforma
            debug_log(f"[{self.usuario}] Obtendo config da plataforma...")
            platform = await self._obter_config_plataforma()
            if not platform:
                result.error = "Erro ao obter config da plataforma"
                return result

            self.platform = platform
            self.user_agent = flash_browsers(self.device_model, platform.speed_version)
            result.sitecode = platform.sitecode  # Salva código da plataforma
            if self.config.game.tipo_saque == "cpf" and getattr(self.config.game, "usar_cpf_arquivo", False):
                cpf_path = getattr(self.config.game, "cpf_arquivo", "cpfs.txt")
                cpf_lido = get_cpf_from_file(platform.sitecode, cpf_path)
                if cpf_lido:
                    self.cpf = cpf_lido
                    result.cpf = cpf_lido
                else:
                    result.error = f"Sem CPF disponível em '{cpf_path}'"
                    return result

            # Etapa 2: Busca jogo
            nome_busca = self.config.game.nome_jogo
            jogo = None
            if nome_busca == "aleatorio":
                jogo = buscar_jogo_pg_aleatorio()
            else:
                jogo = buscar_jogo_pg(nome_busca)

            # Se for Fire Strike 2 Trava, Spirit of Adventure, Voodoo Magic ou Muertos, o jogo pode ser nulo aqui pois será tratado no _jogar
            is_firestrike = getattr(self.config.game, "firestrike_trava", False)
            is_spirit = getattr(self.config.game, "spirit_trava", False)
            is_voodoo = getattr(self.config.game, "voodoo_trava", False)
            is_muertos = getattr(self.config.game, "muertos_trava", False)
            is_pure_platinum = getattr(self.config.game, "pure_platinum_trava", False)
            is_diamond = getattr(self.config.game, "diamond_trava", False)
            is_charm = getattr(self.config.game, "charm_trava", False)
            is_treasure_house = getattr(self.config.game, "treasure_house_trava", False)
            
            is_fire88 = getattr(self.config.game, "fire88_trava", False)
            
            if not is_firestrike and not is_fire88 and not is_spirit and not is_voodoo and not is_muertos and not is_pure_platinum and not is_diamond and not is_charm and not is_treasure_house and (not jogo or not jogo.get("name")):
                result.error = f"Jogo inválido: {self.config.game.nome_jogo}"
                return result

            # Garante um objeto jogo mínimo
            if is_firestrike and not jogo:
                jogo = {"name": "Fire Strike 2", "gameid": "3010002", "platfromid": "301"}
            elif is_fire88 and not jogo:
                jogo = {"name": "Fire 88", "gameid": "3010193", "platfromid": "301"}
            elif is_spirit and not jogo:
                jogo = {"name": "Spirit of Adventure", "gameid": "3010003", "platfromid": "301"}
            elif is_voodoo and not jogo:
                jogo = {"name": "Voodoo Magic", "gameid": "3010095", "platfromid": "301"}
            elif is_muertos and not jogo:
                jogo = {"name": "Muertos Multiplier Megaways", "gameid": "3010272", "platfromid": "301"}
            elif is_pure_platinum and not jogo:
                jogo = {"name": "Pure Platinum", "gameid": "3130115", "platfromid": "313"}
            elif is_diamond and not jogo:
                jogo = {"name": "Diamond Cluster Luck", "gameid": "3010389", "platfromid": "301"}
            elif is_charm and not jogo:
                jogo = {"name": "Lucky Charm", "gameid": "3010059", "platfromid": "301"}
            elif is_treasure_house and not jogo:
                jogo = {"name": "Treasure House", "gameid": "3010173", "platfromid": "301"}

            # Etapa 3: Obter geeToken (se habilitado)
            if self.config.gee_token.enabled:
                if not self.config.gee_token.individual:
                    # Token compartilhado: usa cache
                    debug_log(f"[{self.usuario}] Obtendo geeToken do cache...")
                    gee_token = await get_gee_token(platform.url_domain)
                #logger.info(f"[{self.usuario}] geeToken: {gee_token[:30]}..." if len(gee_token) > 30 else f"[{self.usuario}] geeToken: {gee_token}")
            else:
                gee_token = "disabled"
                debug_log(f"[{self.usuario}] geeToken desativado")

            # Etapa 4: Registro
            debug_log(f"[{self.usuario}] Registrando conta...")
            data_register = await self._registrar(gee_token)
            #print(data_register)
            #sys.exit(0)
            if not data_register:
                # Libera reserva do token para reutilização
                if gee_token != "disabled":
                    release_gee_token(platform.url_domain, gee_token)
                result.error = "Erro no registro"
                return result

            # Confirma uso do token após registro bem-sucedido
            if gee_token != "disabled":
                mark_gee_token_used(platform.url_domain, gee_token)

            self.data_login = data_register.get("userInfos", data_register)
            self.key_request = generate_key(
                self.data_login["session_key"],
                self.data_login["username"]
            )

            # Salva conta no banco de dados (se habilitado)
            self._db_sitecode = platform.sitecode
            self._db_account_id = None
            if self.config.save_to_db:
                # Converte device_model dict para string para salvar no banco
                device_model_str = self.device_model.get("nome", "") if isinstance(self.device_model, dict) else self.device_model
                self._db_account_id = salvar_conta(
                    sitecode=platform.sitecode,
                    platform=self.config.platform_name,
                    url=self.config.url,
                    usuario=self.usuario,
                    senha=self.senha,
                    senha_saque=self.senha_saque,
                    cpf=self.cpf,
                    telefone=self.telefone,
                    email=self.email,
                    nome_completo=self.nome_completo,
                    android_version=self.android_version,
                    device_id=self.device_id,
                    login_id=self.login_id,
                    device_model=device_model_str,
                    app_version=platform.app_version,
                    speed_version=platform.speed_version,
                    register_response=data_register,
                    inviter_id=platform.inviter_id,
                )
                debug_log(f"[{self.usuario}] Conta salva no banco {platform.sitecode}.db: ID={self._db_account_id}")

            # Etapa 5: Configurar conta
            debug_log(f"[{self.usuario}] Configurando conta...")
            await self._configurar_conta()

            if getattr(self.config, "sms", None) and getattr(self.config.sms, "verificar_sms", False):
                debug_log(f"[{self.usuario}] Iniciando fluxo SMS...")
                sms_ok = await self._executar_fluxo_sms()
                if sms_ok:
                    result.telefone = self.telefone

            # Etapa 6: Configurar saque
            debug_log(f"[{self.usuario}] Configurando saque...")
            await self._configurar_saque()

            # Etapa 7: Coletar bônus ou Resgatar código Telegram
            if self.config.telegram_code:
                debug_log(f"[{self.usuario}] Resgatando código Telegram: {self.config.telegram_code}")
                resgate_ok, resgate_msg = await self._resgatar_codigo_telegram(self.config.telegram_code)
                if not resgate_ok:
                    result.error = resgate_msg
                    # Para sem jogar em qualquer falha (código expirado, valor 0.00, inválido, etc.)
                    debug_log(f"[{self.usuario}] Código não resgatado: {resgate_msg}. Abortando sem jogar.")
                    result.saldo = 0.0
                    result.bonus = 0.0
                    result.success = True  # Marca como sucesso processado (mesmo sem bônus)
                    return result
            else:
                debug_log(f"[{self.usuario}] Coletando bônus padrão...")
                bonus_ok = await self._coletar_bonus()
                if bonus_ok is False:
                    # IP bloqueado — encerra sem jogar
                    result.saldo = 0.0
                    result.bonus = 0.0
                    result.success = True
                    return result

            # Etapa 8: Jogar
            debug_log(f"[{self.usuario}] Iniciando jogo...")
            bonus_valor, saldo_final, tem_bonus_monstro = await self._jogar(jogo)

            # Resultado
            result.bonus = bonus_valor
            result.saldo = saldo_final
            self._tem_bonus_monstro = tem_bonus_monstro  # Flag para nome do arquivo
            result.bonus_travado = tem_bonus_monstro  # Flag para estatísticas
            result.pix = self.cpf if self.config.game.tipo_saque == "cpf" else (
                self.telefone if self.config.game.tipo_saque == "telefone" else self.email
            )
            result.token_login = base64.b64encode(json.dumps({
                "session_key": self.data_login["session_key"],
                "jwt_token": "",
                "userkey": "",
            }).encode()).decode()
            result.x_device = self.x_device
            result.success = True

            # Lista de jogos jogados
            jogos_str = ", ".join(self._jogos_jogados) if hasattr(self, '_jogos_jogados') and self._jogos_jogados else "Nenhum"
            debug_log(f"[{self.usuario}] Finalizado! Saldo: R$ {saldo_final:.2f} | Jogos: {jogos_str}")

            # Salva em tempo real se atingiu a meta, tem bônus de monstro, ou saldo zerou com bonus ativo
            saldo_zerou_com_bonus = saldo_final < 0.30 and self.config.game.bonus
            if saldo_final >= self.config.game.subir_banca or tem_bonus_monstro or saldo_zerou_com_bonus:
                self._save_meta_account(result)

        except Exception as e:
            import traceback
            # Só mostra traceback completo se DEBUG estiver ativado
            if runtime_config["DEBUG_MODE"]:
                logger.error(f"❌ [{self.usuario}] Erro: {e}")
                logger.debug(traceback.format_exc())
            else:
                # Mostra apenas mensagem resumida
                debug_log(f"[{self.usuario}] Erro: {e}")
            result.error = str(e)

        finally:
            # Fecha HTTP client
            if self._http:
                await self._http.close()

        return result

    async def executar_criar_e_saque(self) -> "AccountData":
        """
        Fase 1 do modo --aguardar-codigo:
        Registra a conta e configura o saque. NÃO joga e NÃO resgata código.
        O Bot preserva seu estado interno (platform, data_login, key_request)
        para ser reutilizado nas fases seguintes.

        Returns:
            AccountData com success=True se conta criada, error preenchido caso contrário.
        """
        result = AccountData(
            usuario=self.usuario,
            senha=self.senha,
            senha_saque=self.senha_saque,
            email=self.email,
            cpf=self.cpf,
            telefone=self.telefone,
            nome_completo=self.nome_completo,
            url=self.config.url,
        )

        try:
            # Etapa 1: Config da plataforma
            platform = await self._obter_config_plataforma()
            if not platform:
                result.error = "Erro ao obter config da plataforma"
                return result

            self.platform = platform
            self.user_agent = flash_browsers(self.device_model, platform.speed_version)
            result.sitecode = platform.sitecode

            # Etapa 2: Busca jogo (só para saber qual jogo vai usar depois)
            nome_busca = self.config.game.nome_jogo
            if nome_busca == "aleatorio":
                self._jogo_aguardar = buscar_jogo_pg_aleatorio()
            else:
                self._jogo_aguardar = buscar_jogo_pg(nome_busca)

            # Etapa 3: geeToken
            if self.config.gee_token.enabled:
                if not self.config.gee_token.individual:
                    gee_token = await get_gee_token(platform.url_domain)
                else:
                    gee_token = "disabled"
            else:
                gee_token = "disabled"

            # Etapa 4: Registro
            debug_log(f"[{self.usuario}] [FASE1] Registrando conta...")
            data_register = await self._registrar(gee_token)
            if not data_register:
                if gee_token != "disabled":
                    release_gee_token(platform.url_domain, gee_token)
                result.error = "Erro no registro"
                return result

            if gee_token != "disabled":
                mark_gee_token_used(platform.url_domain, gee_token)

            self.data_login = data_register.get("userInfos", data_register)
            self.key_request = generate_key(
                self.data_login["session_key"],
                self.data_login["username"]
            )

            # Salva no banco
            self._db_sitecode = platform.sitecode
            self._db_account_id = None
            if self.config.save_to_db:
                device_model_str = self.device_model.get("nome", "") if isinstance(self.device_model, dict) else self.device_model
                self._db_account_id = salvar_conta(
                    sitecode=platform.sitecode,
                    platform=self.config.platform_name,
                    url=self.config.url,
                    usuario=self.usuario,
                    senha=self.senha,
                    senha_saque=self.senha_saque,
                    cpf=self.cpf,
                    telefone=self.telefone,
                    email=self.email,
                    nome_completo=self.nome_completo,
                    android_version=self.android_version,
                    device_id=self.device_id,
                    login_id=self.login_id,
                    device_model=device_model_str,
                    app_version=platform.app_version,
                    speed_version=platform.speed_version,
                    register_response=data_register,
                    inviter_id=platform.inviter_id,
                )

            # Etapa 5: Configurar conta
            debug_log(f"[{self.usuario}] [FASE1] Configurando conta...")
            await self._configurar_conta()

            # Etapa 6: Configurar saque
            debug_log(f"[{self.usuario}] [FASE1] Configurando saque...")
            await self._configurar_saque()

            result.success = True
            result.pix = self.cpf if self.config.game.tipo_saque == "cpf" else (
                self.telefone if self.config.game.tipo_saque == "telefone" else self.email
            )
            debug_log(f"[{self.usuario}] [FASE1] Conta criada e saque configurado com sucesso.")

        except Exception as e:
            import traceback
            if runtime_config["DEBUG_MODE"]:
                logger.error(f"❌ [{self.usuario}] [FASE1] Erro: {e}")
                logger.debug(traceback.format_exc())
            else:
                debug_log(f"[{self.usuario}] [FASE1] Erro: {e}")
            result.error = str(e)

        return result

    async def executar_resgatar_e_jogar(self, code: str) -> "AccountData":
        """
        Fase 3 do modo --aguardar-codigo:
        Resgata o código Telegram e joga. Presume que executar_criar_e_saque()
        já foi chamado e o estado interno (platform, data_login, key_request) está pronto.

        Args:
            code: Código de desconto do Telegram

        Returns:
            AccountData com resultado completo (bonus, saldo, etc.)
        """
        result = AccountData(
            usuario=self.usuario,
            senha=self.senha,
            senha_saque=self.senha_saque,
            email=self.email,
            cpf=self.cpf,
            telefone=self.telefone,
            nome_completo=self.nome_completo,
            url=self.config.url,
        )

        if self.platform:
            result.sitecode = self.platform.sitecode

        try:
            # Garante que temos jogo selecionado
            jogo = getattr(self, "_jogo_aguardar", None)
            is_firestrike = getattr(self.config.game, "firestrike_trava", False)
            is_fire88 = getattr(self.config.game, "fire88_trava", False)
            is_spirit = getattr(self.config.game, "spirit_trava", False)
            is_voodoo = getattr(self.config.game, "voodoo_trava", False)
            is_muertos = getattr(self.config.game, "muertos_trava", False)
            is_pure_platinum = getattr(self.config.game, "pure_platinum_trava", False)
            is_diamond = getattr(self.config.game, "diamond_trava", False)
            is_charm = getattr(self.config.game, "charm_trava", False)
            is_treasure_house = getattr(self.config.game, "treasure_house_trava", False)

            if is_firestrike and not jogo:
                jogo = {"name": "Fire Strike 2", "gameid": "3010002", "platfromid": "301"}
            elif is_fire88 and not jogo:
                jogo = {"name": "Fire 88", "gameid": "3010193", "platfromid": "301"}
            elif is_spirit and not jogo:
                jogo = {"name": "Spirit of Adventure", "gameid": "3010003", "platfromid": "301"}
            elif is_voodoo and not jogo:
                jogo = {"name": "Voodoo Magic", "gameid": "3010095", "platfromid": "301"}
            elif is_muertos and not jogo:
                jogo = {"name": "Muertos Multiplier Megaways", "gameid": "3010272", "platfromid": "301"}
            elif is_pure_platinum and not jogo:
                jogo = {"name": "Pure Platinum", "gameid": "3130115", "platfromid": "313"}
            elif is_diamond and not jogo:
                jogo = {"name": "Diamond Cluster Luck", "gameid": "3010389", "platfromid": "301"}
            elif is_charm and not jogo:
                jogo = {"name": "Lucky Charm", "gameid": "3010059", "platfromid": "301"}
            elif is_treasure_house and not jogo:
                jogo = {"name": "Treasure House", "gameid": "3010173", "platfromid": "301"}
            elif not jogo:
                jogo = buscar_jogo_pg_aleatorio()

            # Resgata código Telegram
            debug_log(f"[{self.usuario}] [FASE3] Resgatando código: {code}")
            resgate_ok, resgate_msg = await self._resgatar_codigo_telegram(code)
            if not resgate_ok:
                result.error = resgate_msg
                result.saldo = 0.0
                result.bonus = 0.0
                result.success = True  # Processado, mas sem bônus
                debug_log(f"[{self.usuario}] [FASE3] Código não resgatado: {resgate_msg}")
                return result

            # Joga
            debug_log(f"[{self.usuario}] [FASE3] Iniciando jogo...")
            bonus_valor, saldo_final, tem_bonus_monstro = await self._jogar(jogo)

            result.bonus = bonus_valor
            result.saldo = saldo_final
            self._tem_bonus_monstro = tem_bonus_monstro
            result.bonus_travado = tem_bonus_monstro
            result.pix = self.cpf if self.config.game.tipo_saque == "cpf" else (
                self.telefone if self.config.game.tipo_saque == "telefone" else self.email
            )
            result.token_login = base64.b64encode(json.dumps({
                "session_key": self.data_login["session_key"],
                "jwt_token": "",
                "userkey": "",
            }).encode()).decode()
            result.x_device = self.x_device
            result.success = True

            # Salva conta se atingiu meta ou travou bônus
            saldo_zerou_com_bonus = saldo_final < 0.30 and self.config.game.bonus
            if saldo_final >= self.config.game.subir_banca or tem_bonus_monstro or saldo_zerou_com_bonus:
                self._save_meta_account(result)

        except Exception as e:
            import traceback
            if runtime_config["DEBUG_MODE"]:
                logger.error(f"❌ [{self.usuario}] [FASE3] Erro: {e}")
                logger.debug(traceback.format_exc())
            else:
                debug_log(f"[{self.usuario}] [FASE3] Erro: {e}")
            result.error = str(e)

        finally:
            if self._http:
                await self._http.close()

        return result

    async def executar_jogar_direto(self) -> "AccountData":
        """
        Fase 3 do modo --aguardar-codigo:
        Apenas joga. NÃO resgata código (já foi resgatado na FASE 2).
        Presume que executar_criar_e_saque() já foi chamado e o Bot tem
        platform, data_login, key_request prontos.

        Returns:
            AccountData com resultado completo (bonus, saldo, etc.)
        """
        result = AccountData(
            usuario=self.usuario,
            senha=self.senha,
            senha_saque=self.senha_saque,
            email=self.email,
            cpf=self.cpf,
            telefone=self.telefone,
            nome_completo=self.nome_completo,
            url=self.config.url,
        )

        if self.platform:
            result.sitecode = self.platform.sitecode

        try:
            # Garante jogo selecionado
            jogo = getattr(self, "_jogo_aguardar", None)
            is_firestrike = getattr(self.config.game, "firestrike_trava", False)
            is_fire88    = getattr(self.config.game, "fire88_trava", False)
            is_spirit     = getattr(self.config.game, "spirit_trava", False)
            is_voodoo     = getattr(self.config.game, "voodoo_trava", False)
            is_muertos    = getattr(self.config.game, "muertos_trava", False)
            is_pure_platinum = getattr(self.config.game, "pure_platinum_trava", False)
            is_diamond = getattr(self.config.game, "diamond_trava", False)
            is_charm = getattr(self.config.game, "charm_trava", False)
            is_treasure_house = getattr(self.config.game, "treasure_house_trava", False)

            if is_firestrike and not jogo:
                jogo = {"name": "Fire Strike 2", "gameid": "3010002", "platfromid": "301"}
            elif is_fire88 and not jogo:
                jogo = {"name": "Fire 88", "gameid": "3010193", "platfromid": "301"}
            elif is_spirit and not jogo:
                jogo = {"name": "Spirit of Adventure", "gameid": "3010003", "platfromid": "301"}
            elif is_voodoo and not jogo:
                jogo = {"name": "Voodoo Magic", "gameid": "3010095", "platfromid": "301"}
            elif is_muertos and not jogo:
                jogo = {"name": "Muertos Multiplier Megaways", "gameid": "3010272", "platfromid": "301"}
            elif is_pure_platinum and not jogo:
                jogo = {"name": "Pure Platinum", "gameid": "3130115", "platfromid": "313"}
            elif is_diamond and not jogo:
                jogo = {"name": "Diamond Cluster Luck", "gameid": "3010389", "platfromid": "301"}
            elif is_charm and not jogo:
                jogo = {"name": "Lucky Charm", "gameid": "3010059", "platfromid": "301"}
            elif is_treasure_house and not jogo:
                jogo = {"name": "Treasure House", "gameid": "3010173", "platfromid": "301"}
            elif not jogo:
                jogo = buscar_jogo_pg_aleatorio()

            # ─── Joga direto (sem resgatar código novamente) ───
            debug_log(f"[{self.usuario}] [FASE3] Iniciando jogo direto (código já resgatado)...")
            bonus_valor, saldo_final, tem_bonus_monstro = await self._jogar(jogo)

            result.bonus = bonus_valor
            result.saldo = saldo_final
            self._tem_bonus_monstro = tem_bonus_monstro
            result.bonus_travado = tem_bonus_monstro
            result.pix = self.cpf if self.config.game.tipo_saque == "cpf" else (
                self.telefone if self.config.game.tipo_saque == "telefone" else self.email
            )
            result.token_login = base64.b64encode(json.dumps({
                "session_key": self.data_login["session_key"],
                "jwt_token": "",
                "userkey": "",
            }).encode()).decode()
            result.x_device = self.x_device
            result.success = True

            # Salva conta se atingiu meta ou travou bônus
            saldo_zerou_com_bonus = saldo_final < 0.30 and self.config.game.bonus
            if saldo_final >= self.config.game.subir_banca or tem_bonus_monstro or saldo_zerou_com_bonus:
                self._save_meta_account(result)

        except Exception as e:
            import traceback
            if runtime_config["DEBUG_MODE"]:
                logger.error(f"❌ [{self.usuario}] [FASE3] Erro no jogo: {e}")
                logger.debug(traceback.format_exc())
            else:
                debug_log(f"[{self.usuario}] [FASE3] Erro no jogo: {e}")
            result.error = str(e)

        finally:
            if self._http:
                await self._http.close()

        return result
    async def _obter_config_plataforma(self) -> Optional[PlatformConfig]:
        """Obtém configurações da plataforma (com cache em arquivo)"""
        global _platform_config_cache, _platform_config_locks

        url = self.config.url.strip()

        # Verifica cache em memória primeiro (sem lock)
        if url in _platform_config_cache:
            debug_log(f"[{self.usuario}] Usando config da plataforma em cache (memoria)")
            return _platform_config_cache[url]

        # Obtém ou cria lock para esta URL
        async with _platform_config_locks_lock:
            if url not in _platform_config_locks:
                _platform_config_locks[url] = asyncio.Lock()
            lock = _platform_config_locks[url]

        # Aguarda lock e busca config
        async with lock:
            # Double-check após obter lock
            if url in _platform_config_cache:
                debug_log(f"[{self.usuario}] Usando config da plataforma em cache (memoria)")
                return _platform_config_cache[url]

            # Tenta carregar do arquivo primeiro (busca por sitecode nos arquivos existentes)
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            url_host = parsed.netloc

            # Busca em todos os arquivos de cache
            if os.path.exists(CACHE_DIR):
                for cache_file in os.listdir(CACHE_DIR):
                    if cache_file.endswith(".txt"):
                        sitecode = cache_file.replace(".txt", "")
                        cache_result = _load_platform_config_from_file(sitecode)

                        if cache_result:
                            cached_config, original_host = cache_result

                            # Verifica se o host corresponde (original ou interno)
                            if original_host == url_host or cached_config.host == url_host:
                                # Atualiza inviter_id da URL atual
                                query_params = parse_qs(parsed.query)
                                inviter_id = query_params.get("id", [""])[0]
                                if inviter_id:
                                    cached_config.inviter_id = inviter_id
                                    debug_log(f"[{self.usuario}] InviterId: {inviter_id}")

                                _platform_config_cache[url] = cached_config
                                debug_log(f"[{self.usuario}] Cache carregado: {sitecode}.txt (API: {cached_config.api_url})")
                                return cached_config

            # Busca config da plataforma via API (testa APIs e seleciona a mais rápida)
            result = await self._fetch_platform_config(url)

            if result:
                _platform_config_cache[url] = result
                # Salva em arquivo com o host original
                _save_platform_config_to_file(result, url_host)
                debug_log(f"[{self.usuario}] Config salva em cache: {result.sitecode}.txt (API: {result.api_url})")

            return result

    async def _test_fastest_domain(
        self,
        http: BotHttpClient,
        domains: list,
        test_path: str = "/",
        label: str = "API",
        rounds: int = 5
    ) -> Optional[str]:
        """
        Testa múltiplos domínios em paralelo várias vezes e retorna o mais rápido.

        Args:
            http: Cliente HTTP
            domains: Lista de domínios para testar
            test_path: Path para testar (ex: "/" ou "/home")
            label: Rótulo para os logs (ex: "API", "CDN")
            rounds: Número de testes por domínio

        Returns:
            O domínio mais rápido ou None se todos falharem
        """
        if not domains:
            return None

        if len(domains) == 1:
            return domains[0]

        debug_log(f"[{self.usuario}] === Testando {len(domains)} {label}s ({rounds}x cada) ===")

        # Armazena todos os tempos de cada domínio
        domain_times: Dict[str, list] = {d: [] for d in domains}
        domain_status: Dict[str, str] = {d: "" for d in domains}

        async def test_domain_once(domain: str) -> Tuple[str, float, str]:
            """Testa um domínio uma vez"""
            try:
                start = time.time()
                url = f"{domain.rstrip('/')}{test_path}"
                response = await http.get(url, use_proxy=True, timeout=5, max_retries=1)
                elapsed = time.time() - start

                if response.status_code < 500:
                    return (domain, elapsed, f"{response.status_code}")
                else:
                    return (domain, float('inf'), f"HTTP {response.status_code}")
            except Exception as e:
                return (domain, float('inf'), f"ERRO")

        # Executa múltiplos rounds
        for round_num in range(1, rounds + 1):
            debug_log(f"[{self.usuario}] Round {round_num}/{rounds}...")

            # Testa todos em paralelo
            tasks = [test_domain_once(d) for d in domains]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, tuple):
                    domain, elapsed, status = result
                    domain_times[domain].append(elapsed)
                    domain_status[domain] = status

        # Calcula média de cada domínio (ignorando falhas)
        domain_avg: Dict[str, float] = {}
        for domain, times in domain_times.items():
            valid_times = [t for t in times if t != float('inf')]
            if valid_times:
                domain_avg[domain] = sum(valid_times) / len(valid_times)
            else:
                domain_avg[domain] = float('inf')

        # Ordena por média
        sorted_domains = sorted(domain_avg.items(), key=lambda x: x[1])

        fastest = None
        fastest_avg = float('inf')

        debug_log(f"[{self.usuario}] --- Resultados (média de {rounds} testes) ---")

        for i, (domain, avg) in enumerate(sorted_domains):
            times = domain_times[domain]
            valid_times = [t for t in times if t != float('inf')]
            fails = len(times) - len(valid_times)
            status = domain_status[domain]

            if avg == float('inf'):
                avg_str = "  FAIL"
                min_str = "  -  "
                max_str = "  -  "
                marker = "  "
            else:
                avg_str = f"{avg*1000:>5.0f}ms"
                min_str = f"{min(valid_times)*1000:>5.0f}ms"
                max_str = f"{max(valid_times)*1000:>5.0f}ms"

                if fastest is None:
                    fastest = domain
                    fastest_avg = avg
                    marker = ">>"
                else:
                    marker = "  "

            fail_info = f" ({fails} falhas)" if fails > 0 else ""
            debug_log(f"[{self.usuario}] {marker} AVG:{avg_str} | MIN:{min_str} | MAX:{max_str} | ({status}){fail_info} {domain}")

        if fastest:
            debug_log(f"[{self.usuario}] >> Selecionada: {fastest} (média: {fastest_avg*1000:.0f}ms)")
        else:
            debug_log(f"[{self.usuario}] !! Nenhuma {label} respondeu!")

        return fastest

    async def _fetch_platform_config(self, url: str) -> Optional[PlatformConfig]:
        """Busca config da plataforma (sem cache)"""
        http = await self._get_http()

        try:
            # Tenta obter HTML
            response = await http.get(url, use_proxy=True)
            html = response.text

            cfg = None
            version_data = None
            domains = []

            # Método 1: preconnect link
            match = re.search(r'<link\s+rel=preconnect\s+href=([^\s>]+)\s+crossorigin="">', html, re.I)
            if match:
                base = match.group(1).rstrip("/")

                # Config data
                cfg_response = await http.get(f"{base}/cocos/config_data.json", use_proxy=True)
                cfg_text = cfg_response.text

                try:
                    cfg = json.loads(cfg_text)
                except:
                    cfg = json.loads(decrypt_b64_aes128_ecb(cfg_text, CONFIG_KEY_B64))

                # Version data
                ver_response = await http.get(
                    f"{base}/hall/api/lobby/webapi/forceUpdate/getForceUpdate.json",
                    use_proxy=True
                )
                ver_text = ver_response.text

                try:
                    version_data = json.loads(ver_text)
                except:
                    version_data = json.loads(decrypt_b64_aes128_ecb(ver_text, CONFIG_KEY_B64))

            # Método 2: fallback
            if not cfg:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                host = parsed.netloc

                fallback_url = f"https://{host}/fapage/sd/{host}.json?t={int(time.time())}"
                fallback_response = await http.get(fallback_url, use_proxy=True)

                plain = decrypt_b64_aes128_ecb(fallback_response.text, CONFIG_KEY_B64)
                obj = json.loads(plain)

                rels = obj.get("data", {}).get("targetRelations", [])

                for rel in rels:
                    rel = rel.rstrip("/")
                    if not rel:
                        continue

                    try:
                        cfg_response = await http.get(f"{rel}/cocos/config_data.json", use_proxy=True)
                        cfg_text = cfg_response.text

                        try:
                            cfg = json.loads(cfg_text)
                        except:
                            cfg = json.loads(decrypt_b64_aes128_ecb(cfg_text, CONFIG_KEY_B64))

                        if cfg:
                            # Version data
                            oss = cfg.get("oss_url", [""])[0]
                            if oss:
                                force_url = oss.replace(
                                    "/cocos/config_data.json",
                                    "/hall/api/lobby/webapi/forceUpdate/getForceUpdate.json"
                                )
                                ver_response = await http.get(force_url, use_proxy=True)
                                try:
                                    version_data = json.loads(ver_response.text)
                                except:
                                    version_data = json.loads(decrypt_b64_aes128_ecb(ver_response.text, CONFIG_KEY_B64))
                            break
                    except:
                        continue

            if not cfg:
                return None

            # Extrai domínios
            for key in ["non_ma_domain", "lobby_domain"]:
                for d in cfg.get(key, []):
                    if d:
                        domains.append(d)

            if not domains:
                return None

            # Escolhe domínio CDN (prefere azure/cloud)
            url_domain = None
            for d in domains:
                if re.search(r"(azure|cloud)", d):
                    url_domain = d
                    break
            if not url_domain:
                url_domain = domains[0]

            # Testa qual API responde mais rápido
            api_domains = cfg.get("api_domain", [])
            if api_domains and len(api_domains) > 1:
                api_url = await self._test_fastest_domain(http, api_domains, "/", label="API")
                if not api_url:
                    api_url = api_domains[0]  # Fallback
            elif api_domains:
                api_url = api_domains[0]
            else:
                api_url = url_domain

            # Host
            from urllib.parse import urlparse, parse_qs
            host = urlparse(url_domain).netloc

            # Extrai inviter_id da URL original (ex: ?id=824213678)
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            inviter_id = query_params.get("id", [""])[0]

            if inviter_id:
                debug_log(f"[{self.usuario}] InviterId encontrado: {inviter_id}")

            return PlatformConfig(
                url_domain=url_domain,
                api_url=api_url,
                host=host,
                sitecode=str(cfg.get("siteCode", 0)),
                speed_version=version_data.get("data", {}).get("androidWebSpeedPkgVersion", "1.1.20") if version_data else "1.1.20",
                app_version=version_data.get("data", {}).get("androidPkgVersion", "6.1.150") if version_data else "6.1.150",
                inviter_id=inviter_id,
            )

        except Exception as e:
            logger.error(f"❌ Erro ao obter config: {e}")
            return None

    async def _registrar(self, gee_token: str) -> Optional[Dict]:
        """Registra nova conta"""
        http = await self._get_http()

        # Cria headers primeiro (necessário para geeToken individual)
        headers_cipher = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=None,
        )

        # Busca geeToken individual passando headers e user_agent
        if self.config.gee_token.individual:
            manager = get_gee_token_manager(proxy_config=self.config.proxy)
            gee_token = await manager._fetch_token_via_api(
                self.platform.url_domain,
                custom_headers=headers_cipher,
                user_agent=self.user_agent
            )
            if gee_token is None:
                return None

        # Prepara dados
        post_data = postdata_register(
            self.platform.url_domain,
            self.device_id,
            self.device_model,
            self.usuario,
            self.senha,
            self.cpf,
            "",
            self.nome_completo,
            self.platform.sitecode,
            speed_version=self.platform.speed_version,
            token=self.token,
            gee_token=gee_token,
            inviter_id=self.platform.inviter_id if self.platform.inviter_id else None,
        )

        # Headers para a requisição de registro
        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
        )
        
        # Salva x-device para logs
        self.x_device = headers.get("x-device", "N/A")
        
        # Requisição de registro (COM proxy)
        response = await http.api_request(
            self.platform.api_url,
            "/hall/api/member/register",
            post_data,
            headers,
            use_proxy=True,
        )
        debug_log(f"[Registro1] {response}")
        
        if is_base64(response):
            decrypted = decrypt(response)
            data = json.loads(decrypted)
            if data.get("data"):
                return data["data"]
        else:
            # Fallback para JSON com encryptString
            match = re.search(r'"encryptString":"([^"]+)"', response)
            if match:
                encrypted = match.group(1)
                decrypted = decrypt(encrypted)
                data = json.loads(decrypted)
                if data.get("data"):
                    return data["data"]

            # Tenta validação de captcha
            data = is_json(response)

        if data and len(data.get("msg", "")) == 32:
            captcha_id = data["msg"]
            # Resolve o GeeTest v4 nine-grid via HTTP puro (sem browser)
            try:
                from geetest_solver import solve_geetest_for_register
                
                # Obtém proxy em formato URL para o solver
                proxy_url = None
                try:
                    pc = self.config.proxy
                    if pc and pc.usar_proxy and pc.host:
                        proxy_url = f"http://{pc.username}:{pc.password}@{pc.host}:{pc.port}"
                except Exception:
                    pass

                debug_log(f"[{self.usuario}] resolvendo GeeTest v4 (HTTP)")
                
                _gee_token_val = gee_token if 'gee_token' in locals() else "disabled"
                validate_data = await solve_geetest_for_register(
                    site_url=self.platform.url_domain,
                    device_id=self.device_id,
                    api_url=self.platform.api_url,
                    http_client=http,
                    captcha_id=captcha_id,
                    proxy=proxy_url,
                    existing_gee_token=_gee_token_val,
                    sitecode=self.platform.sitecode,
                    device_model=self.device_model,
                    speed_version=self.platform.speed_version,
                    app_version=self.platform.app_version,
                    android_version=self.android_version,
                    host=self.platform.host,
                    login_id=self.usuario,
                    device_user_agent=self.user_agent,
                    use_capsolver=False
                )

            except Exception as _gee_err:
                debug_log(f"[GeeTestSolver] Erro ao resolver captcha: {_gee_err}")
                validate_data = None

            if validate_data and validate_data.get("code") == 1:
                debug_log(f"[{self.usuario}] GeeTest v4 validado (HTTP)")
                # Tenta registro novamente      
                headers["content-length"] = str(len(post_data))
                response = await http.api_request(
                    self.platform.api_url,
                    "/hall/api/member/register",
                    post_data,
                    headers,
                    use_proxy=True,
                )
                #print(json.dumps(headers))
                debug_log(f"[Registro2] {response}")
                
                if is_base64(response):
                    decrypted = decrypt(response)
                    data = json.loads(decrypted)
                    if data.get("data"):
                        return data["data"]
                else:
                    # Fallback para JSON com encryptString
                    match = re.search(r'"encryptString":"([^"]+)"', response)
                    if match:
                        encrypted = match.group(1)
                        decrypted = decrypt(encrypted)
                        data = json.loads(decrypted)
                        if data.get("data"):
                            return data["data"]


        x_device = headers.get("x-device", "N/A")
        #logger.error(f"❌ Registro falhou | Response: {response[:200]}")
        #logger.error(f"❌ Registro falhou | {x_device} | Response: {response[:100]}")
        return None

    async def _configurar_conta(self):
        """Configura dados da conta"""
        http = await self._get_http()

        # Data de nascimento e redes sociais
        modify_data = {
            "birthday": gerar_data_nascimento(),
            "facebook": f"1000{numero(10)}",
            "line": None,
            "email": self.email,
            "mineDisplayOptions": None,
            "nickname": None,
            "realName": None,
            "telegram": numero(10),
            "twitter": None,
            "wechat": generate_wechat_id(),
            "whatsapp": gerar_celular(),
            "zalo": None,
            "registerTime": self.data_login.get("register_time"),
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(modify_data), self.key_request)

        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
        )
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers:
            del headers["x-data-mode"]

        await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/settings/modifyinfo",
            encrypted,
            headers,
            use_proxy=False,
        )

        # Email simples
        email_data = {
            "email": self.email,
            "secondVerify": {"type": 6, "loginPass": self.senha},
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(email_data), self.key_request)

        await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/security/bindEmail",
            encrypted,
            headers,
            use_proxy=False,
        )

        # Pergunta secreta
        answer_data = {
            "id": 1,
            "answer": self.usuario,
            "secondVerify": {"type": 6, "loginPass": self.senha},
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(answer_data), self.key_request)

        await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/passQuint",
            encrypted,
            headers,
            use_proxy=False,
        )

    def _sms_normalize_phone_platform(self, phone: str, keep_dash: bool) -> str:
        if not phone:
            return phone
        p = str(phone).strip()
        if keep_dash:
            p = re.sub(r"[^+\d-]", "", p)
        else:
            p = re.sub(r"[^+\d]", "", p)
        if p.startswith("55") and not p.startswith("+"):
            p = "+" + p
        return p

    def _sms_normalize_phone_pix(self, phone: str) -> str:
        digits = re.sub(r"\D", "", str(phone or ""))
        if digits.startswith("55") and len(digits) > 11:
            digits = digits[2:]
        if len(digits) >= 11:
            digits = digits[-11:]
        return digits

    def _platform_headers_cipher(self) -> Dict[str, str]:
        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
        )
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers:
            del headers["x-data-mode"]
        return headers

    def _parse_platform_response(self, resp_text: str) -> Any:
        if not resp_text:
            return None
        s = str(resp_text).strip()
        if not s:
            return None
        if is_base64(s):
            try:
                decrypted = decrypt_request(s, self.key_request)
                try:
                    return json.loads(decrypted)
                except Exception:
                    return {"raw": decrypted}
            except Exception:
                return {"raw": s}
        parsed = is_json(s)
        if parsed:
            return parsed
        return {"raw": s}

    def _is_platform_ok(self, parsed: Any) -> bool:
        if not isinstance(parsed, dict):
            return True
        if parsed.get("success") is False:
            return False
        if "errorCode" in parsed:
            try:
                if int(parsed.get("errorCode") or 0) != 0:
                    return False
            except Exception:
                if parsed.get("errorCode") not in (None, "", 0, "0"):
                    return False
        if "code" in parsed:
            try:
                if int(parsed.get("code") or 0) not in (0, 1):
                    return False
            except Exception:
                pass
        return True

    async def _post_create_sms(self, phone_platform: str) -> bool:
        http = await self._get_http()
        payload = {
            "phone_number": phone_platform,
            "create_mode": 2,
            "time": int(time.time()),
        }
        encrypted = encrypt_request(json.dumps(payload), self.key_request)
        headers = self._platform_headers_cipher()
        resp = await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/security/createSms",
            encrypted,
            headers,
            use_proxy=False,
        )
        parsed = self._parse_platform_response(resp)
        return self._is_platform_ok(parsed)

    async def _post_verify_phone_code(self, phone_platform: str, code: str) -> bool:
        http = await self._get_http()
        payload = {
            "phone": phone_platform,
            "code": str(code),
            "username": str(self.data_login["username"]),
            "time": int(time.time()),
        }
        encrypted = encrypt_request(json.dumps(payload), self.key_request)
        headers = self._platform_headers_cipher()
        resp = await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/security/verifyPhoneCode",
            encrypted,
            headers,
            use_proxy=False,
        )
        parsed = self._parse_platform_response(resp)
        return self._is_platform_ok(parsed)

    async def _post_modify_phone(self, phone_platform: str, code: str) -> bool:
        http = await self._get_http()
        payload = {
            "phone": phone_platform,
            "phoneCode": str(code or ""),
            "secondVerify": {"type": 6, "loginPass": str(self.senha or "")},
            "time": int(time.time()),
        }
        encrypted = encrypt_request(json.dumps(payload), self.key_request)
        headers = self._platform_headers_cipher()
        resp = await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/security/modifyPhone",
            encrypted,
            headers,
            use_proxy=False,
        )
        parsed = self._parse_platform_response(resp)
        return self._is_platform_ok(parsed)

    async def _sms24h_request(self, api_key: str, params: str) -> str:
        url = f"https://api.sms24h.org/stubs/handler_api?api_key={api_key}&{params}"
        timeout = httpx.Timeout(20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
            r = await client.get(url)
            return r.text

    def _sms24h_normalize_status(self, raw: str) -> Optional[str]:
        if raw is None:
            return None
        s = str(raw).strip()
        s = s.lstrip("\ufeff").replace("\r", " ").replace("\n", " ").strip()
        if not s:
            return None
        try:
            if s.startswith("{") or s.startswith("["):
                j = json.loads(s)
                if isinstance(j, dict) and j.get("status") and j.get("code"):
                    return f"STATUS_OK: {j.get('code')}"
                return json.dumps(j)
        except Exception:
            pass
        return s

    async def _sms24h_create_order(self, api_key: str, service: str = "ot", country: int = 73, operator: int = 0) -> Dict[str, Any]:
        if operator and operator != 0:
            params = f"action=getNumber&service={service}&country={country}&operator={operator}"
        else:
            params = f"action=getNumber&service={service}&country={country}"
        resp = await self._sms24h_request(api_key, params)
        if not resp or not resp.startswith("ACCESS_NUMBER"):
            return {"ok": False, "raw": resp}
        parts = resp.split(":")
        if len(parts) < 3:
            return {"ok": False, "raw": resp, "error": "invalid_access_number"}
        return {"ok": True, "orderId": parts[1], "number": ":".join(parts[2:]), "raw": resp}

    async def _sms24h_get_status(self, api_key: str, order_id: str) -> Optional[str]:
        if not order_id:
            return None
        raw = await self._sms24h_request(api_key, f"action=getStatus&id={order_id}")
        return self._sms24h_normalize_status(raw)

    async def _sms24h_wait_code(self, api_key: str, order_id: str, timeout_ms: int = 60000, poll_ms: int = 3500) -> Dict[str, Any]:
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            await asyncio.sleep(poll_ms / 1000)
            status = await self._sms24h_get_status(api_key, order_id)
            if not status:
                continue
            s = status.strip()
            if re.search(r"STATUS_OK", s, flags=re.IGNORECASE):
                m = re.search(r"(\d{4,6})", s)
                if m:
                    return {"ok": True, "code": m.group(1), "raw": s}
                return {"ok": False, "error": "STATUS_OK sem código", "raw": s}
            if re.search(r"STATUS_CANCEL|STATUS_FINISH|STATUS_RETRY|NO_NUMBERS", s, flags=re.IGNORECASE):
                return {"ok": False, "error": s, "raw": s}
        return {"ok": False, "timeout": True}

    async def _executar_fluxo_sms(self) -> bool:
        if not self.platform or not self.data_login or not self.key_request:
            return False
        provider = str(getattr(self.config.sms, "provedora", "") or "").strip().lower()
        if provider and provider not in ("sms24h", "sms24"):
            return False
        api_key = (getattr(self.config.sms, "api_sms24h", "") or os.environ.get("SMS24_KEY") or "").strip()
        if not api_key:
            debug_log(f"[{self.usuario}] SMS ativado, mas SMS24_KEY/api_sms24h não configurado")
            return False

        order = await self._sms24h_create_order(api_key, service="ot", country=int(getattr(self.config.sms, "country", 73)), operator=0)
        if not order.get("ok"):
            debug_log(f"[{self.usuario}] SMS24h falhou ao obter número: {order.get('raw') or order.get('error')}")
            return False

        phone_raw = order.get("number")
        order_id = order.get("orderId")
        if not phone_raw or not order_id:
            return False

        phone_create = self._sms_normalize_phone_platform(phone_raw, keep_dash=False)
        if not await self._post_create_sms(phone_create):
            debug_log(f"[{self.usuario}] createSms falhou")
            return False

        code_res = await self._sms24h_wait_code(api_key, order_id, timeout_ms=60000, poll_ms=3500)
        if not code_res.get("ok"):
            debug_log(f"[{self.usuario}] Código SMS não chegou: {code_res.get('error') or code_res.get('timeout')}")
            return False

        code = str(code_res.get("code") or "").strip()
        if not code:
            return False

        phone_verify = self._sms_normalize_phone_platform(phone_raw, keep_dash=True)
        if not await self._post_verify_phone_code(phone_verify, code):
            debug_log(f"[{self.usuario}] verifyPhoneCode falhou")
            return False

        if not await self._post_modify_phone(phone_verify, code):
            debug_log(f"[{self.usuario}] modifyPhone falhou")
            return False

        pix_phone = self._sms_normalize_phone_pix(phone_raw)
        if pix_phone:
            self.telefone = pix_phone
        return True

    async def _configurar_saque(self):
        """Configura método de saque"""
        http = await self._get_http()

        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
            uid=self.data_login["username"]
        )
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers:
            del headers["x-data-mode"]

        # Senha de saque
        withdraw_data = {
            "withdraw_pass": self.senha_saque,
            "secondVerify": {"type": 0, "withdraw_pass": self.senha_saque},
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(withdraw_data), self.key_request)

        await http.api_request(
            self.platform.api_url,
            "/hall/api/member/user/security/modifyWithdrawPass",
            encrypted,
            headers,
            use_proxy=False,
        )

        # Verifica senha de saque
        verify_data = {
            "addWithdrawAccountType": 5,
            "withdrawalPassword": self.senha_saque,
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(verify_data), self.key_request)

        response = await http.api_request(
            self.platform.api_url,
            "/hall/api/finance/certify/verifyWithdrawalPasswordV2",
            encrypted,
            headers,
            use_proxy=False,
        )

        uuid_saque = None
        if is_base64(response):
            decrypted = decrypt_request(response, self.key_request)
            data = json.loads(decrypted)
            if data.get("code") == 1:
                uuid_saque = data.get("data", {}).get("key")

        if not uuid_saque:
            logger.warning("⚠️ Não foi possível obter UUID de saque")
            return

        # Adiciona método de saque (PIX)
        tipo_saque = self.config.game.tipo_saque
        chave_pix = self.cpf if tipo_saque == "cpf" else (
            self.telefone if tipo_saque == "telefone" else self.email
        )
        sub_type = "CPF" if tipo_saque == "cpf" else (
            "PHONE" if tipo_saque == "telefone" else "EMAIL"
        )

        pix_data = {
            "name": self.nome_completo,
            "account": chave_pix,
            "extendInfo": self.cpf,
            "cpf": self.cpf,
            "subType": sub_type,
            "accountType": 7,
            "subTypeExtend": {"bank": "", "branchBank": "", "companyName": ""},
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(pix_data), self.key_request)

        await http.api_request(
            self.platform.api_url,
            f"/hall/api/finance/certify/bindalipayV3?withdrawal_uuid={uuid_saque}",
            encrypted,
            headers,
            use_proxy=False,
        )

    async def _coletar_bonus(self):
        """Coleta bônus de missões"""
        http = await self._get_http()

        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
            uid=self.data_login["username"]
        )
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]

        # Save address
        for action_type in [1, 2]:
            address_data = {
                "address": self.device_id,
                "actionType": action_type,
                "time": int(time.time()),
            }
            encrypted = encrypt_request(json.dumps(address_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                "/hall/activetask/task_save_address",
                encrypted,
                headers,
                use_proxy=False,
            )
            debug_log(f"task_save_address - Response: {response}")

        # Newcomer benefit pop
        headers["x-data-mode"] = "chipher"
        await http.api_request(
            self.platform.api_url,
            "/hall/api/active/tasks/newcomer_benefit_pop",
            "",
            headers,
            use_proxy=False,
        )

        # Create Task Info
        create_task_data = {
            "template": 1,
            "bindType": 31,
            "time": int(time.time()),
        }
        encrypted_create = encrypt_request(json.dumps(create_task_data), self.key_request)
        await http.api_request(
            self.platform.api_url,
            "/hall/api/active/tasks/createTaskInfo",
            encrypted_create,
            headers,
            use_proxy=False,
        )

        # Lista missões
        task_data = {
            "taskId": 1,
            "template": 1,
            "time": int(time.time()),
        }

        encrypted = encrypt_request(json.dumps(task_data), self.key_request)

        response = await http.api_request(
            self.platform.api_url,
            "/hall/api/active/tasks/task",
            encrypted,
            headers,
            use_proxy=False,
        )
        debug_log(f"task - Response: {response}")

        if not is_base64(response):
            return

        decrypted = decrypt_request(response, self.key_request)
        data = json.loads(decrypted)

        if data.get("code") != 1:
            return

        # Coleta bônus
        rules = data.get("data", {}).get("rules", [])
        for rule in rules:
            receive_log_id = rule.get("receiveLogId", 0)
            if receive_log_id > 0:
                bonus_data = {
                    "template": 1,
                    "receiveLogIds": str(receive_log_id),
                    "time": int(time.time()),
                }

                encrypted = encrypt_request(json.dumps(bonus_data), self.key_request)

                response = await http.api_request(
                    self.platform.api_url,
                    "/hall/api/active/tasks/receiveOne",
                    encrypted,
                    headers,
                    use_proxy=True,
                )

                # Verifica valor do bonus coletado
                if is_base64(response):
                    try:
                        bonus_decrypted = decrypt_request(response, self.key_request)
                        bonus_response = json.loads(bonus_decrypted)
                        debug_log(f"receiveOne - Response: {bonus_response}")

                        # Detecta erro de limite de IP
                        msg_resp = str(bonus_response.get("msg") or "")
                        if ("limite de pessoas" in msg_resp.lower()
                                or "mesmo endereco ip" in msg_resp.lower()
                                or ("ip" in msg_resp.lower() and "reivindicada" in msg_resp.lower())):
                            return False

                        if bonus_response.get("code") == 1:
                            valor_bonus = float(bonus_response.get("data", {}).get("prize", 0) or 0)
                            if valor_bonus <= 0:
                                x_device = headers.get("x-device", "N/A")
                    except Exception:
                        pass
                else:
                    # Resposta nao criptografada - tenta verificar como JSON puro
                    try:
                        raw_json = json.loads(str(response))
                        msg_resp = str(raw_json.get("msg") or "")
                        if ("limite de pessoas" in msg_resp.lower()
                                or "mesmo endereco ip" in msg_resp.lower()
                                or ("ip" in msg_resp.lower() and "reivindicada" in msg_resp.lower())):
                            return False
                    except Exception:
                        pass

    async def _resgatar_codigo_telegram(self, code: str) -> Tuple[bool, str]:
        """Resgata bônus via código do Telegram (Discount Code)"""
        if not code:
            return False, "Código vazio"

        http = await self._get_http()
        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
            uid=self.data_login["username"]
        )
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        # A plataforma as vezes exige o x-data-mode como 'chipher' (com h) conforme visto no CURL
        headers["x-data-mode"] = "chipher"
        
        # Log dos headers para debug
        debug_log(f"[{self.login_id}] Headers resgate: {json.dumps(headers, indent=2)}")
        
        payload = {
            "discountCode": str(code),
            "activeId": self.config.active_id,
            "time": int(time.time()),
        }
        encrypted = encrypt_request(json.dumps(payload), self.key_request)
        
        response = await http.api_request(
            self.platform.api_url,
            "/hall/api/active/useDiscountCode",
            encrypted,
            headers,
            use_proxy=False,
        )

        if is_base64(response):
            try:
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                msg = data.get("data", {}).get("message") or data.get("msg") or ""
                # Aceita code==1 como sucesso (status pode ser 0 ou ausente dependendo da plataforma)
                # Também trata "返回成功" (Retorno bem-sucedido em chinês) como sucesso
                is_success = (
                    data.get("code") == 1
                    or "返回成功" in str(msg)
                )
                if is_success:
                    valor = data.get("data", {}).get("amount", 0) or 0
                    if float(valor) == 0.0:
                        # Valor 0.00 indica que o código não creditou saldo —
                        # provavelmente expirado, esgotado ou já resgatado.
                        # Captura o motivo real da resposta para exibir no log.
                        motivo = (
                            data.get("data", {}).get("message")
                            or data.get("msg")
                            or str(data)
                            or "Valor R$ 0.00 (código expirado/esgotado)"
                        )
                        debug_log(f"⚠️ [{self.usuario}] CÓDIGO com valor 0.00: {motivo}")
                        return False, str(motivo)
                    logger.info(f"✅ [{self.usuario}] CÓDIGO RESGATADO: {code} | Valor: R$ {float(valor):.2f}")
                    return True, "Sucesso"
                else:
                    debug_log(f"❌ [{self.usuario}] Erro no código: {msg}")
                    return False, str(msg)
            except Exception as e:
                debug_log(f"[{self.usuario}] Erro ao processar resposta do código: {e}")
                return False, f"Erro processamento: {e}"
        else:
            # Tenta decodificar como JSON puro caso não esteja em base64/criptografado
            try:
                data = json.loads(str(response))
                msg = data.get("data", {}).get("message") or data.get("msg")
                if msg:
                    debug_log(f"❌ [{self.usuario}] Erro no código (JSON): {msg}")
                    return False, str(msg)
            except:
                pass
            
            debug_log(f"[{self.usuario}] Resposta do código não está em base64: {response}")
            return False, "Resposta inválida (não base64)"

        return False, "Erro desconhecido"

    async def _jogar_sunshine_trava(self, jogo: Dict, target_bet: float) -> Tuple[float, float, bool]:
        """
        Lógica de TRAVA (Armar Bet) para Sunshine Coast (CPBrig)
        """
        http = await self._get_http()
        
        # Parâmetros dinâmicos do jogo e plataforma (Sincronizado com Sunshine Normal)
        sub_gid = str(jogo.get("gameid", "3070065"))
        gid = 2240 
        origin = self.platform.url_domain
        referer = f"{origin}/"
        
        nome_jogo = jogo.get("name", "Sunshine Coast")
        jogo_info, game_url = await self._login_jogo_hall(nome_jogo)
        
        # Extrai o token da URL
        game_token = self.data_login["session_key"]
        if game_url:
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(game_url)
                qs = parse_qs(parsed.query)
                if "token" in qs:
                    game_token = qs["token"][0]
                    debug_log(f"[{self.usuario}] Token CPBrig (Trava) extraído com sucesso.")
            except Exception as e:
                debug_log(f"[{self.usuario}] Erro ao extrair token na trava: {e}")

        provider = CPBrigProvider(
            http, 
            game_token, 
            gid=gid, 
            sub_gid=sub_gid,
            origin=origin,
            referer=referer
        )
        
        # Sincronização Inicial de Saldo (10 tentativas para garantir)
        saldo_atual = 0.0
        for i in range(10):
            info = await provider.get_user_info(self.device_id)
            saldo_atual = provider.last_balance
            if saldo_atual > 0:
                break
            await asyncio.sleep(3)
        
        saldo_atual = provider.last_balance
        if not hasattr(self, '_bonus_original') or self._bonus_original is None:
            self._bonus_original = saldo_atual
        bonus_inicial = self._bonus_original
        
        # Registra na lista de jogos jogados
        if "Sunshine Coast" not in self._jogos_jogados:
            self._jogos_jogados.append("Sunshine Coast")

        target_info = f"Bet Alvo: R$ {target_bet:.2f}" if not getattr(self.config.game, "sunshine_aleatoria", False) else f"Bet Aleatória (Mín: R$ {getattr(self.config.game, 'sunshine_min_bet', 15.0):.2f})"
        logging.info(f"[{self.usuario}] 🎯 MODO TRAVA: Sunshine Coast | {target_info} | Saldo: R$ {saldo_atual:.2f}")

        # Define os níveis de aposta expandidos (conforme JSON e requisição)
        BET_LEVELS = [
            (0.50, 0.05, 1), (1.00, 0.05, 2), (1.50, 0.05, 3), (2.00, 0.05, 4), (2.50, 0.05, 5),
            (3.00, 0.05, 6), (3.50, 0.05, 7), (4.00, 0.05, 8), (4.50, 0.05, 9), (5.00, 0.05, 10),
            (5.00, 0.50, 1), (10.00, 0.50, 2), (15.00, 0.50, 3), (20.00, 0.50, 4), (25.00, 0.50, 5),
            (30.00, 0.50, 6), (35.00, 0.50, 7), (40.00, 0.50, 8), (45.00, 0.50, 9), (50.00, 0.50, 10),
            (40.00, 4.00, 1), (80.00, 4.00, 2), (120.00, 4.00, 3), (160.00, 4.00, 4), (200.00, 4.00, 5),
            (240.00, 4.00, 6), (280.00, 4.00, 7), (320.00, 4.00, 8), (360.00, 4.00, 9), (400.00, 4.00, 10)
        ]
        
        BET_MIN_SALDO = BET_LEVELS[0][0]
        spin_count = 0
        is_trava_sunshine = True
        
        while saldo_atual >= BET_MIN_SALDO:
            try:
                # 1. Determina a Bet atual
                if getattr(self.config.game, "sunshine_aleatoria", False):
                    # MODO ALEATÓRIO (Banca 50% a 100%): Escolhe uma bet agressiva para armar na alta e zerar saldo
                    min_faixa = saldo_atual * 0.5
                    max_faixa = saldo_atual
                    
                    # Filtra bets que o saldo suporta, estão na faixa de 50-100% e abaixo da bet_maxima
                    possiveis = [b for b in BET_LEVELS if b[0] >= min_faixa and b[0] <= max_faixa and b[0] <= self.config.game.bet_maxima]
                    
                    if possiveis:
                        # Sorteia uma das bets altas encontradas
                        escolhida = random.choice(possiveis)
                        bet_ativa, b_level, b_total = escolhida[1], escolhida[2], escolhida[0]
                    else:
                        # Se nenhuma cair na faixa (saldo baixo), pega a maior possível para o "all-in" em bets
                        bet_ativa, b_level, b_total = BET_LEVELS[0][1], BET_LEVELS[0][2], BET_LEVELS[0][0]
                        for t_bet, g_gold, g_level in reversed(BET_LEVELS):
                            if t_bet <= saldo_atual:
                                bet_ativa, b_level, b_total = g_gold, g_level, t_bet
                                break
                else:
                    # MODO NORMAL: Determina a Bet atual (Limitada rigorosamente pela target_bet)
                    # target_bet é o seu teto (ex: 0.50). O robô nunca passará disso.
                    bet_ativa, b_level, b_total = BET_LEVELS[0][1], BET_LEVELS[0][2], BET_LEVELS[0][0]
                    
                    for t_bet, g_gold, g_level in reversed(BET_LEVELS):
                        if t_bet <= target_bet and t_bet <= saldo_atual:
                            bet_ativa, b_level, b_total = g_gold, g_level, t_bet
                            break
                
                current_total_bet = b_total
                spin_count += 1

                # 2. Executa o Giro (Modo persistente: não desiste por erro de rede)
                resp = None
                while True:
                    try:
                        resp = await provider.spin(self.device_id, bet=bet_ativa, level=b_level)
                        if resp and isinstance(resp, dict):
                            break # Sucesso no giro, segue o jogo
                        
                        debug_log(f"[{self.usuario}] Resposta inválida da plataforma, tentando novamente em 3s...")
                        await asyncio.sleep(3)
                    except Exception as e:
                        debug_log(f"[{self.usuario}] Erro de conexão no Sunshine ({e}), tentando novamente em 5s...")
                        await asyncio.sleep(5)
                
                saldo_atual = provider.last_balance
                game_type = resp.get("type", 1) # Type 3 = Free Spins / Bonus
                
                # 3. Log Padrão solicitado (Estilo Maycon + SPIN)
                # 3. Log Padrão solicitado (Estilo Maycon + SPIN)
                dt_str = time.strftime('%Y-%m-%d %H:%M:%S')
                spin_str = f"SPIN-{spin_count:02d}"
                status_color = Fore.LIGHTMAGENTA_EX
                tag = "ARMANDO" if is_trava_sunshine else "BONUS"
                
                log = (
                    f"{Fore.LIGHTWHITE_EX}[{dt_str}] | {Fore.LIGHTYELLOW_EX}{spin_str}{Fore.LIGHTWHITE_EX} | | {Fore.LIGHTCYAN_EX}Bot |  "
                    f"Usuário: {Fore.LIGHTWHITE_EX}{self.usuario:<20}{Style.RESET_ALL} {status_color}| "
                    f"{Fore.LIGHTMAGENTA_EX}🎯 MODO TRAVA: {Fore.LIGHTWHITE_EX}Sunshine Coast {status_color}| "
                    f"{Fore.LIGHTYELLOW_EX}Bet: {Fore.LIGHTWHITE_EX}R$ {current_total_bet:.2f} {status_color}| "
                    f"{Fore.LIGHTCYAN_EX}Saldo: {Fore.LIGHTWHITE_EX}R$ {saldo_atual:.2f}{Style.RESET_ALL}"
                )
                print(log)

                # 4. Verificação de TRAVA
                # Se type == 3 (Ganhou Free Spins)
                if game_type == 3:
                    # Só trava se a bet do bônus for >= target_bet
                    # Só trava se a bet do bônus for >= ao alvo/mínimo solicitado
                    min_bet_para_travar = getattr(self.config.game, "sunshine_min_bet", 15.0) if getattr(self.config.game, "sunshine_aleatoria", False) else target_bet
                    if current_total_bet >= min_bet_para_travar:
                        print(f"\n{Fore.LIGHTCYAN_EX} ══════════════════════════════════════════════════════════")
                        print(f"  {Fore.LIGHTMAGENTA_EX}BÔNUS TRAVADO - SUNSHINE COAST")
                        print(f"  {Fore.WHITE}Usuário: {self.usuario} | Senha: {self.senha}")
                        print(f"  {Fore.WHITE}Saque: {self.senha_saque}")
                        print(f"  {Fore.WHITE}BET TRAVADA: {Fore.LIGHTYELLOW_EX}R$ {current_total_bet:.2f}")
                        print(f"  {Fore.WHITE}SALDO ATUAL: {Fore.LIGHTGREEN_EX}R$ {saldo_atual:.2f}")
                        print(f"{Fore.LIGHTGREEN_EX} ══════════════════════════════════════════════════════════{Style.RESET_ALL}\n")
                        
                        # Armazena dados para o salvamento na pasta CP
                        self._tem_bonus_monstro = True
                        self._cp_last_bet = current_total_bet
                        self._is_cp_trava = True
                        self._trava_tipo = "SUNSHINE" # Define o tipo para o Telegram
                        
                        return bonus_inicial, saldo_atual, True # Retorna indicando bônus encontrado

                # No modo TRAVA, não paramos se bater a meta de saldo. 
                # Continuamos até o bônus vir na bet alvo ou o saldo acabar.

                await asyncio.sleep(0.1)

            except Exception as e:
                debug_log(f"[{self.usuario}] Erro na trava Sunshine: {e}")
                break
        
        return bonus_inicial, saldo_atual, False


    async def _jogar_cpbrig(self, jogo: Dict) -> Tuple[float, float, bool]:
        """
        Lógica dinâmica para provedora CPBrig (Sunshine Coast e outros)
        """
        http = await self._get_http()
        
        # Parâmetros dinâmicos do jogo e plataforma
        sub_gid = str(jogo.get("gameid", "3070065"))
        gid = 2240 # GID 2240 é o GID "Lobby/Account" padrão para CPBrig. Isso garante a detecção do saldo.
        
        # Origin/Referer dinâmicos baseados no domínio da plataforma
        origin = self.platform.url_domain
        referer = f"{origin}/"
        
        # Realiza login no jogo para obter o token real de sessão do provedor
        nome_jogo = jogo.get("name", "Sunshine Coast")
        jogo_info, game_url = await self._login_jogo_hall(nome_jogo)
        
        # Extrai o token da URL se disponível, senão usa o session_key da plataforma
        game_token = self.data_login["session_key"]
        if game_url:
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(game_url)
                qs = parse_qs(parsed.query)
                if "token" in qs:
                    game_token = qs["token"][0]
                    debug_log(f"[{self.usuario}] Token CPBrig extraído com sucesso.")
            except Exception as e:
                debug_log(f"[{self.usuario}] Erro ao extrair token da URL: {e}")

        provider = CPBrigProvider(
            http, 
            game_token, 
            gid=gid, 
            sub_gid=sub_gid,
            origin=origin,
            referer=referer
        )
        
        # Sincronização Inicial (Polling de até 30s para bônus)
        saldo_atual = 0.0
        for i in range(10):
            info = await provider.get_user_info(self.device_id)
            saldo_atual = provider.last_balance
            if saldo_atual > 0:
                break
            if i < 9:
                debug_log(f"[{self.usuario}] Saldo R$ 0.00 - Aguardando bônus (tentativa {i+1}/10)...")
                await asyncio.sleep(3)
        
        # Saldo inicial e bônus original
        saldo_atual = provider.last_balance
        if not hasattr(self, '_bonus_original') or self._bonus_original is None:
            self._bonus_original = saldo_atual
        bonus_inicial = self._bonus_original
        
        nome_exibicao = jogo.get("name", "Sunshine Coast")
        debug_log(f"[{self.usuario}] Iniciando loop CPBrig em {nome_exibicao} (GID: {gid}, SubGID: {sub_gid})")
        
        # Define os níveis de aposta expandidos
        BET_LEVELS = [
            (0.50, 0.05, 1), (1.00, 0.05, 2), (1.50, 0.05, 3), (2.00, 0.05, 4), (2.50, 0.05, 5),
            (3.00, 0.05, 6), (3.50, 0.05, 7), (4.00, 0.05, 8), (4.50, 0.05, 9), (5.00, 0.05, 10),
            (5.00, 0.50, 1), (10.00, 0.50, 2), (15.00, 0.50, 3), (20.00, 0.50, 4), (25.00, 0.50, 5),
            (30.00, 0.50, 6), (35.00, 0.50, 7), (40.00, 0.50, 8), (45.00, 0.50, 9), (50.00, 0.50, 10),
            (40.00, 4.00, 1), (80.00, 4.00, 2), (120.00, 4.00, 3), (160.00, 4.00, 4), (200.00, 4.00, 5),
            (240.00, 4.00, 6), (280.00, 4.00, 7), (320.00, 4.00, 8), (360.00, 4.00, 9), (400.00, 4.00, 10)
        ]
        
        BET_MIN_SALDO = BET_LEVELS[0][0]  # R$ 0.50
        bet_maxima_total = float(self.config.game.bet_maxima)
        spin_error_count = 0
        
        while saldo_atual >= BET_MIN_SALDO and saldo_atual < self.config.game.subir_banca:
            try:
                # Estratégia Greedy: maior aposta possível
                bet_gold, current_level = BET_LEVELS[0][1], BET_LEVELS[0][2]
                for total_bet, b_gold, b_level in reversed(BET_LEVELS):
                    if total_bet <= bet_maxima_total and saldo_atual >= total_bet:
                        bet_gold = b_gold
                        current_level = b_level
                        break
                
                # Executa o Giro
                resp = await provider.spin(self.device_id, bet=bet_gold, level=current_level)
                
                is_success = isinstance(resp, dict) and (resp.get("code") == 0 or "end_gold" in resp)
                
                if not is_success:
                    if isinstance(resp, dict) and resp.get("code") == 1001:
                        debug_log(f"[{self.usuario}] Token expirado CPBrig. Renovando...")
                        await self._configurar_conta()
                        continue
                    
                    spin_error_count += 1
                    if spin_error_count > 5:
                        debug_log(f"[{self.usuario}] Falhas consecutivas no CPBrig. Abortando.")
                        break
                    await asyncio.sleep(1)
                    continue
                
                spin_error_count = 0
                saldo_atual = provider.last_balance
                
                # Feedback visual no padrão 'bonitinho'
                is_meta = saldo_atual >= self.config.game.subir_banca
                tag = "META" if is_meta else "BONUS"
                
                if is_meta:
                    # Linha inteira VERDE se bater a meta
                    log = f"{Fore.LIGHTGREEN_EX}[{time.strftime('%Y-%m-%d %H:%M:%S')}] Maycon |  Usuário: {self.usuario:<20} | Senha: {self.senha:<15} | Saque: {self.senha_saque} | Bônus: R$ {bonus_inicial:.2f} | Saldo: R$ {saldo_atual:.2f}{Style.RESET_ALL}"
                else:
                    status_color = Fore.LIGHTYELLOW_EX
                    log = (
                        f"{Fore.LIGHTWHITE_EX}[{time.strftime('%Y-%m-%d %H:%M:%S')}]{Style.RESET_ALL}{Fore.LIGHTGREEN_EX} Maycon |  "
                        f"Usuário: {Fore.LIGHTWHITE_EX}{self.usuario:<20}{Style.RESET_ALL} {status_color}|"
                        f" {Fore.LIGHTGREEN_EX}Senha: {Fore.LIGHTWHITE_EX}{self.senha:<15}{Style.RESET_ALL} {status_color}|"
                        f" {Fore.LIGHTGREEN_EX}Saque: {Fore.LIGHTWHITE_EX}{self.senha_saque}{Style.RESET_ALL} {status_color}|"
                        f" {Fore.LIGHTYELLOW_EX}Bônus: {Fore.LIGHTWHITE_EX}R$ {bonus_inicial:.2f}{Style.RESET_ALL} {status_color}|"
                        f" {Fore.LIGHTGREEN_EX}Saldo: {Fore.LIGHTWHITE_EX}R$ {saldo_atual:.2f}{Style.RESET_ALL}"
                    )
                print(log)
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                debug_log(f"[{self.usuario}] Erro no loop de jogo: {e}")
                break

        # Sincronização final
        await provider.get_user_info(self.device_id)
        saldo_final = provider.last_balance
        
        return bonus_inicial, saldo_final, False

    async def _login_jogo_hall(self, nome_jogo: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Realiza o login no jogo via API do Hall/Plataforma.
        Retorna (jogo_data, game_url).
        """
        http = await self._get_http()
        
        # Headers para cipher
        headers_cipher = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
        )

        debug_log(f"[{self.usuario}] _login_jogo_hall: iniciando ({nome_jogo})")
        jogo_data = buscar_jogo_pg(nome_jogo)
        if not jogo_data:
            debug_log(f"[{self.usuario}] _login_jogo_hall: jogo não encontrado ({nome_jogo})")
            return None, None
            
        game_data = {k: v for k, v in jogo_data.items() if k != "name"}
        game_data["time"] = int(time.time())
        
        try:
            encrypted = encrypt_request(json.dumps(game_data), self.key_request)
            response = await asyncio.wait_for(
                http.api_request(
                    self.platform.api_url,
                    "/hall/api/gameCenter/gameApi/login",
                    encrypted,
                    headers_cipher,
                    use_proxy=False,
                ),
                timeout=max(5, int(self.config.request_timeout) + 5),
            )
            
            if not is_base64(response):
                return None, None

            decrypted = decrypt_request(response, self.key_request)
            data = json.loads(decrypted)
            
            if data.get("code") != 1:
                return None, None

            game_url = data.get("data", {}).get("game_url", "")
            return jogo_data, game_url
            
        except Exception as e:
            debug_log(f"[{self.usuario}] _login_jogo_hall: erro: {e}")
            return None, None

    async def _jogar(self, jogo: Dict) -> Tuple[float, float, bool]:
        """
        Executa jogo automático. Retorna (bonus, saldo_final, tem_bonus_monstro)

        Estratégia com LOOP:
        1. Fortune Ox/Tiger/Rabbit até saldo chegar entre 30-250
        2. Troca para Gem Saviour para tentar travar bônus
        3. Se saldo < 30 após Gem → Volta para Fortune
        4. Se saldo > 250 → Salva conta (meta atingida)
        5. Repete até saldo acabar ou atingir meta
        """
        # Redireciona para CPBrig especializada (Trava/Armar Bet) se solicitado
        if getattr(self.config.game, "sunshine_trava", False):
            target_bet = getattr(self.config.game, "sunshine_trava_bet", 0.5)
            return await self._jogar_sunshine_trava(jogo, target_bet)

        # Redireciona para Fire Strike 2 se solicitado
        if getattr(self.config.game, "firestrike_trava", False):
            target_bet = getattr(self.config.game, "firestrike_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta = await game_firestrike_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            # No Fire Strike 2 modo subir saldo, não consideramos 'trava' no sentido de bônus PG
            return bonus_valor, saldo_final, False

        # Redireciona para Fire 88 se solicitado
        if getattr(self.config.game, "fire88_trava", False):
            target_bet = getattr(self.config.game, "fire88_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta = await game_fire88_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            return bonus_valor, saldo_final, False

        # Redireciona para Spirit of Adventure se solicitado
        if getattr(self.config.game, "spirit_trava", False):
            target_bet = getattr(self.config.game, "spirit_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_spirit_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "SPIRIT"
                # Usa os dados da lógica, definindo a bet como a alvo travada
                self._spirit_last_bet = target_bet
                # Salva o ganho acumulado no bônus (pronto para coletar)
                self._spirit_ganho_bonus = ganho_bonus
                # Salva o total apostado
                self._spirit_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Spirit of Adventure")

            return bonus_valor, saldo_final, tem_meta

        # Redireciona para Voodoo Magic se solicitado
        if getattr(self.config.game, "voodoo_trava", False):
            target_bet = getattr(self.config.game, "voodoo_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_voodoo_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "VOODOO"
                self._spirit_last_bet = target_bet
                self._spirit_ganho_bonus = ganho_bonus
                self._spirit_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Voodoo Magic")
                
            return bonus_valor, saldo_final, tem_meta

        # Redireciona para Muertos Multiplier se solicitado
        if getattr(self.config.game, "muertos_trava", False):
            target_bet = getattr(self.config.game, "muertos_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_muertos_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "MUERTOS"
                self._spirit_last_bet = target_bet
                self._spirit_ganho_bonus = ganho_bonus
                self._spirit_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Muertos Multiplier Megaways")
                
            return bonus_valor, saldo_final, tem_meta

        # Redireciona para Pure Platinum (Microgaming) se solicitado
        if getattr(self.config.game, "pure_platinum_trava", False):
            target_bet = getattr(self.config.game, "pure_platinum_trava_bet", 2.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_pure_platinum_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance,
                telegram_bot_token=tg_token,
                telegram_chat_id=tg_chat,
                usuario=self.usuario,
                senha=self.senha,
            )
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "PURE_PLATINUM"
                self._spirit_last_bet = target_bet
                self._spirit_ganho_bonus = ganho_bonus
                self._spirit_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Pure Platinum")
            return bonus_valor, saldo_final, tem_meta

        # Redireciona para Diamond Cluster Luck se solicitado
        if getattr(self.config.game, "diamond_trava", False):
            target_bet = getattr(self.config.game, "diamond_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_diamond_cluster_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "DIAMOND_CLUSTER"
                self._spirit_last_bet = target_bet
                self._spirit_ganho_bonus = ganho_bonus
                self._spirit_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Diamond Cluster Luck")
            return bonus_valor, saldo_final, tem_meta

        # Redireciona para Lucky Charm se solicitado
        if getattr(self.config.game, "charm_trava", False):
            target_bet = getattr(self.config.game, "charm_trava_bet", 0.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_lucky_charm_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "LUCKY_CHARM"
                self._charm_last_bet = target_bet
                self._charm_ganho_bonus = ganho_bonus
                self._charm_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Lucky Charm")
            return bonus_valor, saldo_final, tem_meta

        # Redireciona para Treasure House se solicitado
        if getattr(self.config.game, "treasure_house_trava", False):
            target_bet = getattr(self.config.game, "treasure_house_trava_bet", 2.0)
            target_balance = self.config.game.subir_banca
            headers_cipher = self._platform_headers_cipher()
            bonus_valor, saldo_final, tem_meta, ganho_bonus, total_apostado = await game_treasure_house_logic(
                await self._get_http(),
                self.data_login,
                self.platform,
                self.key_request,
                headers_cipher,
                target_bet,
                target_balance
            )
            if tem_meta and getattr(self, '_trava_tipo', '') == '':
                self._trava_tipo = "TREASURE_HOUSE"
                self._treasure_house_last_bet = target_bet
                self._spirit_last_bet = target_bet
                self._spirit_ganho_bonus = ganho_bonus
                self._spirit_total_apostado = total_apostado
                if not hasattr(self, '_jogos_jogados'):
                    self._jogos_jogados = []
                self._jogos_jogados.append("Treasure House")
            return bonus_valor, saldo_final, tem_meta

        # Redireciona para CPBrig comum se for Sunshine Coast
        game_name_lower = str(jogo.get("name", "")).lower()
        if str(self.platform.sitecode) == "580" or str(jogo.get("gameid")) == "2240" or "sunshine" in game_name_lower:
            return await self._jogar_cpbrig(jogo)

        http = await self._get_http()

        # Flag para indicar se encontrou bônus de monstro
        tem_bonus_monstro = False
        
        # Lista de jogos jogados pelo usuário
        self._jogos_jogados = []

        # Faixa de saldo para trocar para Gem Saviour (gem_trava)
        SALDO_MIN_GEM = 15
        SALDO_MAX_GEM = 1000  # Faixa: R$ 15 a R$ 1000
        
        # Faixa de saldo para trocar para Hood vs Wolf (hood_trava)
        SALDO_MIN_HOOD = 15
        SALDO_MAX_HOOD = 1000  # Faixa: R$ 15 a R$ 1000
        
        # APIs do jogo PG (igual game_gem_trava.py)
        DEFAULT_API_SESSION = "api.nkjx8564m.com"
        DEFAULT_API_GAME = "api-ali-virginia-a.nkjx8564m.com"
        API_SESSION = DEFAULT_API_SESSION
        API_GAME = DEFAULT_API_GAME
        API_GAME_BASE = DEFAULT_API_SESSION

        api_session_cache: Dict[str, str] = {}

        # Obtém bet máxima configurada
        bet_maxima = self.config.game.bet_maxima

        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="plain",
            token=self.data_login["session_key"],
        )
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]

        # Headers para cipher
        headers_cipher = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.android_version,
            mode="cipher",
            token=self.data_login["session_key"],
        )
        headers_cipher["auth"] = self.data_login["userkey"]
        headers_cipher["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers_cipher:
            del headers_cipher["x-data-mode"]

        # Game logout - ver saldo
        logout_data = json.dumps({
            "callContext": json.dumps({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "scene": "clean up game; page: subGame; ifrme: null",
                "stack": "[]",
            }),
            "time": int(time.time()),
        })

        # Função auxiliar para obter saldo atual
        async def obter_saldo() -> float:
            # Atualiza timestamp para cada chamada
            current_logout_data = json.dumps({
                "callContext": json.dumps({
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "scene": "clean up game; page: subGame; ifrme: null",
                    "stack": "[]",
                }),
                "time": int(time.time()),
            })

            try:
                response = await http.api_request(
                    self.platform.api_url,
                    "/hall/api/gameCenter/gameApi/logout",
                    current_logout_data,
                    headers,
                    use_proxy=False,
                )
            except Exception as e:
                debug_log(f"[{self.usuario}] Erro ao obter saldo (proxy): {e} | tentando com proxy...")
                try:
                    response = await http.api_request(
                        self.platform.api_url,
                        "/hall/api/gameCenter/gameApi/logout",
                        current_logout_data,
                        headers,
                        use_proxy=True,
                    )
                except Exception as e2:
                    debug_log(f"[{self.usuario}] Erro ao obter saldo (sem proxy): {e2}")
                    return 0.0
            
            # Tenta descriptografar se for base64
            data = None
            if is_base64(response):
                try:
                    decrypted = decrypt_request(response, self.key_request)
                    data = json.loads(decrypted)
                except Exception:
                    pass
            
            # Fallback para JSON normal
            if data is None:
                data = is_json(response)
            
            if data and data.get("code") == 1:
                saldo = float(data.get("data", {}).get("totalGold", 0) or 0)
                debug_log(f"[{self.usuario}] Saldo obtido: R$ {saldo:.2f}")
                return saldo
            debug_log(f"[{self.usuario}] Erro ao obter saldo: {response}")
            return 0.0

        # Função auxiliar para login no jogo
        async def login_jogo(nome_jogo: str):
            #jogo_data = buscar_jogo_pg_aleatorio()
            inicio_login = time.perf_counter()
            debug_log(f"[{self.usuario}] login_jogo: iniciando ({nome_jogo})")
            jogo_data = buscar_jogo_pg(nome_jogo)
            if not jogo_data:
                debug_log(f"[{self.usuario}] login_jogo: jogo não encontrado ({nome_jogo})")
                return None, None
            game_data = {k: v for k, v in jogo_data.items() if k != "name"}
            game_data["time"] = int(time.time())
            encrypted = encrypt_request(json.dumps(game_data), self.key_request)
            debug_log(
                f"[{self.usuario}] login_jogo: jogo={jogo_data.get('name')} "
                f"gid={jogo_data.get('gameid')} pid={jogo_data.get('platfromid')} "
                f"payload_len={len(encrypted) if isinstance(encrypted, str) else 'n/a'}"
            )

            try:
                debug_log(f"[{self.usuario}] login_jogo: POST /hall/api/gameCenter/gameApi/login (proxy=on)")
                response = await asyncio.wait_for(
                    http.api_request(
                        self.platform.api_url,
                        "/hall/api/gameCenter/gameApi/login",
                        encrypted,
                        headers_cipher,
                        use_proxy=False,
                    ),
                    timeout=max(5, int(self.config.request_timeout) + 5),
                )
            except asyncio.TimeoutError:
                debug_log(f"[{self.usuario}] login_jogo: TIMEOUT na API login")
                return None, None
            except Exception as e:
                debug_log(f"[{self.usuario}] login_jogo: ERRO na API login: {e}")
                return None, None

            debug_log(
                f"[{self.usuario}] login_jogo: resposta recebida "
                f"(base64={is_base64(response)} len={len(response) if isinstance(response, str) else 'n/a'}) "
                f"em {time.perf_counter() - inicio_login:.2f}s"
            )

            if not is_base64(response):
                amostra = ""
                if isinstance(response, str) and response:
                    amostra = response[:200].replace("\n", "\\n").replace("\r", "\\r")
                debug_log(f"[{self.usuario}] login_jogo: resposta não-base64 (amostra={amostra})")
                return None, None

            try:
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
            except Exception as e:
                debug_log(f"[{self.usuario}] login_jogo: falha ao descriptografar/parsear resposta: {e}")
                return None, None

            if data.get("code") != 1:
                debug_log(f"[{self.usuario}] login_jogo: code inválido: {data.get('code')} msg={data.get('msg')}")
                return None, None

            game_url = data.get("data", {}).get("game_url", "")
            debug_log(
                f"[{self.usuario}] login_jogo: game_url recebido "
                f"(len={len(game_url) if isinstance(game_url, str) else 'n/a'})"
            )
            return jogo_data, game_url

        # Obtém saldo inicial
        saldo_atual = await obter_saldo()
        if saldo_atual <= 0:
            return 0.0, 0.0, False

        # Salva o bônus original (primeiro valor obtido) - NUNCA é modificado
        if not hasattr(self, '_bonus_original') or self._bonus_original is None:
            self._bonus_original = saldo_atual
        bonus_valor = self._bonus_original

        debug_log(f"[{self.usuario}] Saldo inicial: R$ {saldo_atual:.2f} | Bônus original: R$ {bonus_valor:.2f}")

        # ==================== LOOP PRINCIPAL ====================
        ciclo = 0
        MAX_CICLOS = 500 # Limite de segurança (ignorado se loop_infinito=True)
        fortune_open_failures = 0
        loop_infinito = self.config.game.loop_infinito

        while True:
            ciclo += 1
            if loop_infinito:
                debug_log(f"[{self.usuario}] === CICLO {ciclo} (INFINITO) === Saldo: R$ {saldo_atual:.2f}")
            else:
                debug_log(f"[{self.usuario}] === CICLO {ciclo}/{MAX_CICLOS} === Saldo: R$ {saldo_atual:.2f}")

            # CONDIÇÃO DE SAÍDA: Limite de ciclos atingido (apenas se não for loop infinito)
            if not loop_infinito and ciclo > MAX_CICLOS:
                logger.warning(f"⚠️ [{self.usuario}] Limite de {MAX_CICLOS} ciclos atingido. Finalizando.")
                break

            # CONDIÇÃO DE SAÍDA: Saldo zerou ou insuficiente para jogo normal (e recuperação desativada)
            limite_minimo = 0.10 if self.config.game.triple_tigers_recuperacao else 0.30
            if saldo_atual < limite_minimo:
                debug_log(f"[{self.usuario}] Saldo insuficiente (R$ {saldo_atual:.2f}). Finalizando.")
                break

            # Define se está na faixa de trava (para decidir se para na meta)
            gem_faixa = self.config.game.gem_trava and SALDO_MIN_GEM <= saldo_atual <= SALDO_MAX_GEM
            hood_faixa = self.config.game.hood_trava and SALDO_MIN_HOOD <= saldo_atual <= SALDO_MAX_HOOD

            # DEBUG: Log de faixa se hood_trava ou gem_trava estiverem ativos
            if self.config.game.hood_trava or self.config.game.gem_trava:
                gem_txt = f"GEM [{SALDO_MIN_GEM}-{SALDO_MAX_GEM}]" if self.config.game.gem_trava else "GEM off"
                hood_txt = f"HOOD [{SALDO_MIN_HOOD}-{SALDO_MAX_HOOD}]" if self.config.game.hood_trava else "HOOD off"
                debug_log(f"[{self.usuario}] Check Faixa: Saldo R$ {saldo_atual:.2f} | {gem_txt} | {hood_txt}")


            # ========== FASE GEM: Se saldo na faixa de trava, vai para Gem Saviour ==========
            if gem_faixa:
                saldo_antes_gem = saldo_atual
                self._saldo_antes_gem = saldo_atual
                debug_log(f"[{self.usuario}] Saldo R$ {saldo_atual:.2f} na faixa [{SALDO_MIN_GEM}, {SALDO_MAX_GEM}] - Indo para Gem Saviour!")

                jogo_gem, game_url_gem = await login_jogo("gem saviour")
                
                # Adiciona à lista de jogos jogados
                if "Gem Saviour" not in self._jogos_jogados:
                    self._jogos_jogados.append("Gem Saviour")

                # Se falhou login no Gem, volta para Fortune
                if not jogo_gem or not game_url_gem:
                    debug_log(f"[{self.usuario}] Falha ao entrar no Gem. Continuando...")
                    saldo_atual = await obter_saldo()
                    continue

                if jogo_gem and game_url_gem:
                    try:
                        bonus_encontrado, gem_spin_count, gem_last_bet, gem_vida_restante = await game_gem_trava(
                            http,
                            game_url_gem,
                            banca_minima=5.0,
                            bet_maxima_porcentagem=self.config.game.bet_maxima,
                            trava_bau_ativo=False,
                            apenas_uma_bet=True,
                            usuario=self.usuario,
                            senha=self.senha,
                        )
                        self._gem_spin_count = gem_spin_count
                        self._gem_last_bet = gem_last_bet
                        self._gem_vida_restante = gem_vida_restante

                        if bonus_encontrado:
                            tem_bonus_monstro = True
                            saldo_atual = await obter_saldo()
                            debug_log(f"[{self.usuario}] >>> BÔNUS TRAVADO! Spins: {gem_spin_count} | HP: {gem_vida_restante} <<<")
                            print(f"{Fore.LIGHTGREEN_EX}🏆 [TRAVA] 👤 {self.usuario} | 🔑 {self.senha} | 💳 {self.senha_saque} | 🎁 R$ {bonus_valor:.2f} | 💰 Entrada: R$ {saldo_antes_gem:.2f} | 💵 Atual: R$ {saldo_atual:.2f} | ❤️ HP: {gem_vida_restante}{Style.RESET_ALL}")
                            return bonus_valor, saldo_atual, tem_bonus_monstro

                    except Exception as e:
                        debug_log(f"[{self.usuario}] Erro no Gem Saviour: {e}")

                # Se bonus foi detectado no Gem (bonus=1), salvar conta mesmo com saldo zerado
                if tem_bonus_monstro:
                    try:
                        saldo_atual = await obter_saldo()
                    except Exception:
                        saldo_atual = 0.0
                    debug_log(f"[{self.usuario}] >>> BÔNUS TRAVADO (recuperado)! Saldo: R$ {saldo_atual:.2f} <<<")
                    return bonus_valor, saldo_atual, tem_bonus_monstro

                # NÃO travou - obtém saldo e continua
                saldo_atual = await obter_saldo()
                debug_log(f"[{self.usuario}] Sem trava. Saldo após Gem: R$ {saldo_atual:.2f}")

                # Se saldo ainda na faixa, tenta Gem de novo no próximo ciclo
                # Se saldo < 50, vai para Fortune
                # Se saldo > 250, vai para Hood vs Wolf (se ativo)
                continue

            # ========== FASE HOOD VS WOLF: Se saldo na faixa de trava, vai para Hood vs Wolf ==========
            if hood_faixa:
                logger.info(f"👤 {self.usuario} | 🔑 {self.senha} | 🎯 SALDO R$ {saldo_atual:.2f} NA FAIXA [{SALDO_MIN_HOOD}, {SALDO_MAX_HOOD}] - INDO PARA HOOD VS WOLF!")
                saldo_antes_hood = saldo_atual
                self._saldo_antes_hood = saldo_atual
                debug_log(f"[{self.usuario}] Saldo R$ {saldo_atual:.2f} na faixa [{SALDO_MIN_HOOD}, {SALDO_MAX_HOOD}] - Indo para Hood vs Wolf!")

                jogo_hood, game_url_hood = await login_jogo("hood vs wolf")
                
                # Adiciona à lista de jogos jogados
                if "Hood vs Wolf" not in self._jogos_jogados:
                    self._jogos_jogados.append("Hood vs Wolf")

                # Se falhou login no Hood, volta para Fortune
                if not jogo_hood or not game_url_hood:
                    debug_log(f"[{self.usuario}] Falha ao entrar no Hood vs Wolf. Continuando...")
                    saldo_atual = await obter_saldo()
                    continue

                if jogo_hood and game_url_hood:
                    try:
                        bonus_encontrado, hood_spin_count, hood_last_bet, hood_bonus_count = await game_hood_vs_wolf_trava(
                            http,
                            game_url_hood,
                            banca_minima=5.0,
                            bet_maxima_porcentagem=self.config.game.bet_maxima,
                            usuario=self.usuario,
                            senha=self.senha,
                        )
                        self._hood_spin_count = hood_spin_count
                        self._hood_last_bet = hood_last_bet
                        self._hood_bonus_count = hood_bonus_count

                        if bonus_encontrado:
                            tem_bonus_monstro = True
                            saldo_atual = await obter_saldo()
                            debug_log(f"[{self.usuario}] >>> BÔNUS HOOD TRAVADO! Spins: {hood_spin_count} | Símbolos: {hood_bonus_count} <<<")
                            if hood_bonus_count == 1:
                                hood_tipo = "NO 🐺 LOBO"
                            elif hood_bonus_count == 2:
                                hood_tipo = "NA 👧🏼 MENINA"
                            else:
                                hood_tipo = "❓ DESCONHECIDO"
                            print(f"{Fore.LIGHTGREEN_EX}🏆 [HOOD TRAVA] 👤 {self.usuario} | 🔑 {self.senha} | 💳 {self.senha_saque} | 🎁 R$ {bonus_valor:.2f} | 💰 Entrada: R$ {saldo_antes_hood:.2f} | 💵 Atual: R$ {saldo_atual:.2f} | BÔNUS TRAVADO {hood_tipo}{Style.RESET_ALL}")
                            return bonus_valor, saldo_atual, tem_bonus_monstro

                    except Exception as e:
                        debug_log(f"[{self.usuario}] Erro no Hood vs Wolf: {e}")

                # NÃO travou - obtém saldo e continua
                saldo_atual = await obter_saldo()
                debug_log(f"[{self.usuario}] Sem trava Hood. Saldo após Hood vs Wolf: R$ {saldo_atual:.2f}")

                # Se saldo ainda na faixa, tenta Hood de novo no próximo ciclo
                continue

            # Meta atingida (saldo >= target E fora da faixa de trava)
            is_trava_ativa = (
                self.config.game.double_fortune_trava or 
                self.config.game.ganesha_gold_trava or 
                self.config.game.emperor_favour_trava or
                self.config.game.journey_to_the_wealth_trava
            )
            
            if saldo_atual >= self.config.game.subir_banca and not gem_faixa and not hood_faixa and not is_trava_ativa:
                break
            
            # Se atingiu a meta MAS está na faixa de trava, não sai! (continua para tentar travar)
            if saldo_atual >= self.config.game.subir_banca:
                if gem_faixa:
                    debug_log(f"[{self.usuario}] Meta R$ {self.config.game.subir_banca:.2f} atingida, mas saldo R$ {saldo_atual:.2f} está na faixa GEM. Continuando...")
                if hood_faixa:
                    debug_log(f"[{self.usuario}] Meta R$ {self.config.game.subir_banca:.2f} atingida, mas saldo R$ {saldo_atual:.2f} está na faixa HOOD. Continuando...")

            # ========== FASE EMPEROR: Se emperor_favour_trava ativo, prioriza nome_jogo_escolhido = "Emperor's Favour" ==========
            # (A lógica de trava será executada no loop Fortune abaixo)

            # ========== FASE FORTUNE: Saldo < 30, joga Fortune ==========

            # Escolhe jogo Fortune baseado no saldo (do maior para menor)
            if self.config.game.nome_jogo != "aleatorio":
                nome_jogo_escolhido = self.config.game.nome_jogo
            elif saldo_atual >= 0.50:
                jogos_fortune = ["Fortune Ox", "Fortune Tiger", "Fortune Rabbit"]
                nome_jogo_escolhido = random.choice(jogos_fortune)
            elif saldo_atual >= 0.40:
                jogos_fortune = ["Fortune Dragon", "Fortune Ox", "Supermarket", "Lucky Piggy", "Lucky Neko", "Pinata Wins", "Emperor's Favour", "Wild Ape", "Cocktail Nights"]
                nome_jogo_escolhido = random.choice(jogos_fortune)
            elif saldo_atual >= 0.30:
                nome_jogo_escolhido = "Double Fortune"
            else:
                # Saldo < 0.30 - Tenta recuperação no Triple Tigers (PP) se habilitado via comando --10-cetavo
                if saldo_atual >= 0.10 and self.config.game.triple_tigers_recuperacao:
                    debug_log(f"[{self.usuario}] Saldo R$ {saldo_atual:.2f} < 0.30 - Tentando recuperação no Triple Tigers (Comando --10-cetavo ativo)...")
                    acc_info = {
                        'session_key': self.data_login.get('session_key'),
                        'jwt_token': self.data_login.get('jwt_token'),
                        'userkey': self.data_login.get('userkey'),
                        'device_id': self.device_id,
                        'username': self.usuario
                    }
                    rec_ok, novo_saldo = await play_pp_recovery(
                        http, 
                        acc_info, 
                        self.platform, 
                        'triple-tigers', 
                        self.key_request, 
                        headers_cipher, 
                        target_balance=0.30
                    )
                    saldo_atual = novo_saldo
                    if rec_ok:
                        debug_log(f"[{self.usuario}] Recuperação bem-sucedida! Novo saldo: R$ {saldo_atual:.2f}")
                        if "Triple Tigers" not in self._jogos_jogados:
                            self._jogos_jogados.append("Triple Tigers")
                        continue # Volta ao topo do loop para entrar no Double Fortune
                    else:
                        debug_log(f"[{self.usuario}] Falha na recuperação ou saldo insuficiente após jogo. Finalizando.")
                        break
                else:
                    # Saldo < 0.10 ou recuperação desativada - finaliza conta
                    jogos_str = ", ".join(self._jogos_jogados) if self._jogos_jogados else "Nenhum"
                    debug_log(f"[{self.usuario}] Saldo insuficiente (R$ {saldo_atual:.2f}) ou recuperação desativada - Finalizando conta | Jogos: {jogos_str}")
                    break

            debug_log(f"[{self.usuario}] Entrando em {nome_jogo_escolhido}...")
            
            # Adiciona à lista de jogos jogados
            if nome_jogo_escolhido not in self._jogos_jogados:
                self._jogos_jogados.append(nome_jogo_escolhido)

            jogo_fortune, game_url = await login_jogo(nome_jogo_escolhido)
            if not jogo_fortune or not game_url:
                debug_log(f"[{self.usuario}] Falha ao entrar no jogo Fortune")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: falha ao abrir {nome_jogo_escolhido} (login) tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            html_code = extract_value(game_url)
            if not html_code:
                debug_log(
                    f"[{self.usuario}] Fortune: extract_value falhou "
                    f"(game_url_len={len(game_url) if isinstance(game_url, str) else 'n/a'})"
                )
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: falha ao abrir {nome_jogo_escolhido} (extract_value) tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            # Decodifica dados do jogo
            try:
                binary_data = base64.b64decode(html_code)
                decoder = SimpleMsgPack(binary_data)
                game_decode = decoder.unpack()
                game_login_data = extract_options_pg(game_decode)
            except Exception as e:
                logger.error(f"❌ Erro ao decodificar dados do jogo: {e}")
                fortune_open_failures += 1
                await asyncio.sleep(0.2)
                continue

            if not game_login_data.get("host"):
                debug_log(
                    f"[{self.usuario}] Fortune: host não encontrado no decode "
                    f"(keys={list(game_login_data.keys()) if isinstance(game_login_data, dict) else type(game_login_data)})"
                )
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: falha ao abrir {nome_jogo_escolhido} (host ausente) tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            id_game = game_login_data.get("idGame")
            host_game = str(game_login_data.get("host") or "").split(":")[0].strip()
            base_domain = host_game
            if base_domain.startswith("m."):
                base_domain = base_domain[2:]
            elif base_domain.startswith("www."):
                base_domain = base_domain[4:]
            api_session_cache_key = base_domain or host_game
            game_request_headers: Dict[str, str] = {}
            if host_game:
                game_request_headers = {
                    "Origin": f"https://{host_game}",
                    "Referer": f"https://{host_game}/",
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                }
            if base_domain:
                API_SESSION = f"api.{base_domain}"
                API_GAME_BASE = f"api.{base_domain}"
                debug_log(f"[{self.usuario}] Fortune: API derivada host={host_game} api_session={API_SESSION} api_game_base={API_GAME_BASE}")
            debug_log(
                f"[{self.usuario}] Fortune: sessão do jogo "
                f"host={game_login_data.get('host')} idGame={id_game} "
                f"params_keys={list((game_login_data.get('params') or {}).keys())}"
            )

            # Game session (usa API_SESSION)
            session_data = {
                "btt": game_login_data["params"].get("btt"),
                "vc": 2,
                "pf": 1,
                "l": "pt",
                "gi": id_game,
                "os": game_login_data["params"].get("ops"),
                "otk": game_login_data["params"].get("ot"),
            }

            def _is_html_text(value: Any) -> bool:
                if not isinstance(value, str):
                    return False
                s = value.lstrip().lower()
                return s.startswith("<!doctype") or s.startswith("<html") or "<html" in s[:2000]

            def _extract_game_slug(geu_value: Any) -> str:
                raw = str(geu_value or "").strip().strip("/")
                if not raw:
                    return ""
                if raw.startswith("game-api/"):
                    raw = raw[len("game-api/"):]
                parts = [p for p in raw.split("/") if p]
                return parts[0] if parts else ""

            def _extract_host(value: Any) -> str:
                raw = str(value or "").strip()
                if not raw:
                    return ""
                raw = raw.replace("\\", "/")
                if raw.startswith("http://") or raw.startswith("https://"):
                    raw = raw.split("://", 1)[1]
                raw = raw.split("/", 1)[0]
                raw = raw.split(":", 1)[0]
                return raw.strip()

            api_session_hosts: List[str] = ["api.6pvx87oz6.com"]
            cached_api_session = api_session_cache.get(api_session_cache_key)
            if cached_api_session:
                api_session_hosts.append(cached_api_session)
            if API_SESSION:
                api_session_hosts.append(API_SESSION)
            api_session_hosts.append(DEFAULT_API_SESSION)
            api_session_hosts = list(dict.fromkeys([h for h in api_session_hosts if h]))

            trace_id = codigo_pg()
            verify_endpoints = [
                f"/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={trace_id}",
                f"/game-api/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={trace_id}",
            ]

            session_response: Any = None
            api_session_ok: Optional[str] = None
            verify_ok = False
            verify_used_proxy = False
            t0 = time.perf_counter()
            debug_log(f"[{self.usuario}] Fortune: verifyOperatorPlayerSession hosts={api_session_hosts}")
            for host in api_session_hosts:
                for endpoint in verify_endpoints:
                    for use_proxy in [False, True]:
                        try:
                            verify_timeout = min(max(5, int(self.config.request_timeout)), 10)
                            resp = await asyncio.wait_for(
                                http.game_request(host, endpoint, session_data, headers=game_request_headers, use_proxy=use_proxy),
                                timeout=verify_timeout,
                            )
                        except asyncio.TimeoutError:
                            debug_log(f"[{self.usuario}] Fortune: TIMEOUT verify host={host} {'(proxy)' if use_proxy else ''}")
                            continue
                        except Exception as e:
                            err = str(e)
                            if "Could not resolve host" in err or "curl: (6)" in err:
                                debug_log(f"[{self.usuario}] Fortune: host inválido ({host})")
                                break # Tenta próximo host
                            debug_log(f"[{self.usuario}] Fortune: ERRO verify host={host} {'(proxy)' if use_proxy else ''}: {e}")
                            continue

                        if isinstance(resp, dict) and not resp.get("err"):
                            session_response = resp
                            api_session_ok = host
                            verify_ok = True
                            verify_used_proxy = use_proxy
                            debug_log(f"[{self.usuario}] Fortune: verify OK host={host} endpoint={endpoint} {'(proxy)' if use_proxy else ''} em {time.perf_counter() - t0:.2f}s")
                            break

                        amostra = ""
                        if isinstance(resp, str) and resp:
                            amostra = resp[:200].replace("\n", "\\n").replace("\r", "\\r")
                        debug_log(
                            f"[{self.usuario}] Fortune: verify inválido host={host} endpoint={endpoint} "
                            f"{'(proxy) ' if use_proxy else ''}type={type(resp).__name__} html={_is_html_text(resp)} amostra={amostra}"
                        )
                    if verify_ok:
                        break
                if verify_ok:
                    break

            if not verify_ok or not isinstance(session_response, dict) or not api_session_ok:
                debug_log(f"[{self.usuario}] Fortune: falha verifyOperatorPlayerSession (tentativas esgotadas)")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: falha verifyOperatorPlayerSession jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.3)
                continue
            API_SESSION = api_session_ok
            api_session_cache[api_session_cache_key] = api_session_ok

            session_dt = session_response.get("dt", {})
            if not session_dt.get("tk") or not session_dt.get("geu"):
                debug_log(
                    f"[{self.usuario}] Fortune: sessão incompleta (tk/geu ausente) "
                    f"(dt_keys={list(session_dt.keys()) if isinstance(session_dt, dict) else type(session_dt)})"
                )
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: sessão incompleta jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue
            
            sdn = session_dt.get("sdn")
            lau_value = session_dt.get("lau")
            api_game_hosts: List[str] = []
            lau_host = _extract_host(lau_value)
            if lau_host:
                api_game_hosts.append(lau_host)

            api_game_domains: List[str] = []
            if isinstance(DEFAULT_API_SESSION, str) and DEFAULT_API_SESSION.startswith("api."):
                api_game_domains.append(DEFAULT_API_SESSION[4:])
            api_game_domains.append("6pvx87oz6.com")
            if isinstance(API_SESSION, str) and API_SESSION.startswith("api."):
                cand_domain = API_SESSION[4:]
                if cand_domain in api_game_domains:
                    api_game_domains.insert(0, cand_domain)
            api_game_domains = list(dict.fromkeys([d for d in api_game_domains if d]))

            if sdn and isinstance(sdn, str):
                sdn_clean = sdn.strip()
                if sdn_clean:
                    if "." in sdn_clean:
                        api_game_hosts.append(sdn_clean)
                    else:
                        for dom in api_game_domains:
                            api_game_hosts.append(f"{sdn_clean}.{dom}")
            api_game_hosts.insert(0, "api-ali-virginia-a.6pvx87oz6.com")
            api_game_hosts.append(DEFAULT_API_GAME)
            api_game_hosts = list(dict.fromkeys([h for h in api_game_hosts if h]))
            debug_log(
                f"[{self.usuario}] Fortune: session_dt keys={list(session_dt.keys()) if isinstance(session_dt, dict) else type(session_dt)} "
                f"sdn={sdn} lau_host={lau_host} api_game_hosts={api_game_hosts}"
            )

            async def _game_request_resiliente(endpoint: str, payload: Dict[str, Any]) -> Any:
                last_error: Exception = Exception("No hosts available")
                game_timeout = min(max(4, int(self.config.request_timeout)), 8)
                proxy_first = verify_used_proxy
                for host in api_game_hosts:
                    for use_proxy in ([True, False] if proxy_first else [False, True]):
                        try:
                            resp = await asyncio.wait_for(
                                http.game_request(host, endpoint, payload, headers=game_request_headers, use_proxy=use_proxy),
                                timeout=game_timeout,
                            )
                            if isinstance(resp, str) and (not resp.strip() or _is_html_text(resp)):
                                amostra = resp[:200].replace("\n", "\\n").replace("\r", "\\r")
                                debug_log( 
                                    f"[{self.usuario}] Fortune: resposta inválida host={host} (proxy={use_proxy} html={_is_html_text(resp)}) "
                                    f"amostra={amostra}"
                                )
                                last_error = ValueError("invalid_response")
                                continue
                            return resp
                        except asyncio.TimeoutError as e:
                            last_error = e
                            debug_log(f"[{self.usuario}] Fortune: TIMEOUT host={host} proxy={use_proxy} endpoint={endpoint}")
                            continue
                        except Exception as e:
                            last_error = e
                            err = str(e)
                            if "Could not resolve host" in err or "curl: (6)" in err:
                                debug_log(f"[{self.usuario}] Fortune: host inválido ({host}) tentando próximo...")
                                break
                            continue
                raise last_error

            debug_log(f"[{self.usuario}] Fortune: APIs sessão/jogo resolvidas api_session={API_SESSION}")
            game_slug = _extract_game_slug(session_dt.get("geu"))
            if not game_slug:
                debug_log(f"[{self.usuario}] Fortune: geu inválido (geu={session_dt.get('geu')})")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: geu inválido jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue
            debug_log(f"[{self.usuario}] Fortune: game_slug={game_slug}")

            # Game rule (usa API_SESSION)
            rule_data = {
                "btt": game_login_data["params"].get("btt"),
                "gid": id_game,
                "atk": session_dt.get("tk"),
                "pf": 1,
            }

            try:
                t0 = time.perf_counter()
                debug_log(f"[{self.usuario}] Fortune: GameRule/Get")
                
                # Tenta primeiro direto, depois com proxy se necessário (baseado em verify_used_proxy)
                for use_proxy in ([True, False] if verify_used_proxy else [False, True]):
                    try:
                        await asyncio.wait_for(
                            http.game_request(
                                API_SESSION,
                                f"/web-api/game-proxy/v2/GameRule/Get?traceId={codigo_pg()}",
                                rule_data,
                                headers=game_request_headers,
                                use_proxy=use_proxy
                            ),
                            timeout=max(5, int(self.config.request_timeout) + 5),
                        )
                        break
                    except (asyncio.TimeoutError, Exception) as e:
                        if use_proxy: # Se já falhou com proxy, desiste
                            raise e
                        debug_log(f"[{self.usuario}] Fortune: falha GameRule direto, tentando proxy...")
                
                debug_log(f"[{self.usuario}] Fortune: GameRule OK em {time.perf_counter() - t0:.2f}s")
            except asyncio.TimeoutError:
                debug_log(f"[{self.usuario}] Fortune: TIMEOUT GameRule/Get")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: TIMEOUT GameRule jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.3)
                continue
            except Exception as e:
                debug_log(f"[{self.usuario}] Fortune: ERRO GameRule/Get: {e}")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: ERRO GameRule jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            # Game info (usa API_GAME)
            info_data = {
                "eatk": session_dt.get("eatk"),
                "btt": game_login_data["params"].get("btt"),
                "atk": session_dt.get("tk"),
                "pf": 1,
            }

            try:
                t0 = time.perf_counter()
                debug_log(f"[{self.usuario}] Fortune: GameInfo/Get slug={game_slug}")
                info_response = await _game_request_resiliente(
                    f"/game-api/{game_slug}/v2/GameInfo/Get?traceId={codigo_pg()}",
                    info_data,
                )
                debug_log(f"[{self.usuario}] Fortune: GameInfo OK em {time.perf_counter() - t0:.2f}s")
            except asyncio.TimeoutError:
                debug_log(f"[{self.usuario}] Fortune: TIMEOUT GameInfo/Get")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: TIMEOUT GameInfo jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.3)
                continue
            except Exception as e:
                debug_log(f"[{self.usuario}] Fortune: ERRO GameInfo/Get: {e}")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: ERRO GameInfo jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            if not isinstance(info_response, dict):
                amostra = ""
                if isinstance(info_response, str) and info_response:
                    amostra = info_response[:200].replace("\n", "\\n").replace("\r", "\\r")
                debug_log(f"[{self.usuario}] Fortune: GameInfo inválido (type={type(info_response).__name__} amostra={amostra})")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: GameInfo inválido jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            info_dt = info_response.get("dt", {})
            cs_list = info_dt.get("cs", [])
            ml_list = info_dt.get("ml", [])
            mxl = info_dt.get("mxl", 1)

            if not cs_list:
                debug_log(f"[{self.usuario}] Fortune: cs_list vazio em GameInfo (dt_keys={list(info_dt.keys()) if isinstance(info_dt, dict) else type(info_dt)})")
                fortune_open_failures += 1
                if fortune_open_failures in (1, 3, 5):
                    debug_log(f"[{self.usuario}] Fortune: cs_list vazio jogo={nome_jogo_escolhido} tentativas={fortune_open_failures}")
                await asyncio.sleep(0.2)
                continue

            bet_minima = cs_list[0] * ml_list[0] * mxl if cs_list and ml_list else 1

            id_play = (
                info_dt.get("ls", {}).get("si", {}).get("sid") or
                info_dt.get("si", {}).get("sid") or
                0
            )

            debug_log(
                f"[{self.usuario}] Fortune: pronto para spin "
                f"bet_min={bet_minima} id_play={id_play} cs_len={len(cs_list)} ml_len={len(ml_list)} mxl={mxl}"
            )
            fortune_open_failures = 0

            bonus = self.config.game.bonus

            # Loop Fortune: joga até saldo entrar na faixa 30-250 ou atingir meta
            spin_count_trava = 0
            while True:
                # Saldo insuficiente
                if saldo_atual < bet_minima:
                    break

                # Saldo na faixa para Gem Saviour - PRIORIDADE (se gem_trava ativo)
                if self.config.game.gem_trava and SALDO_MIN_GEM <= saldo_atual <= SALDO_MAX_GEM:
                    logger.info(f"💎 [{self.usuario}] Saldo R$ {saldo_atual:.2f} na faixa [{SALDO_MIN_GEM}, {SALDO_MAX_GEM}] - Saindo do Fortune para Gem!")
                    break

                # Saldo na faixa para Hood vs Wolf - PRIORIDADE (se hood_trava ativo)
                if self.config.game.hood_trava and SALDO_MIN_HOOD <= saldo_atual <= SALDO_MAX_HOOD:
                    logger.info(f"🐺 [{self.usuario}] Saldo R$ {saldo_atual:.2f} na faixa [{SALDO_MIN_HOOD}, {SALDO_MAX_HOOD}] - Saindo do Fortune para Hood vs Wolf!")
                    break

                # Meta atingida (saldo >= target E fora da faixa de trava)
                is_trava_ativa = (
                    self.config.game.double_fortune_trava or 
                    self.config.game.ganesha_gold_trava or
                    self.config.game.emperor_favour_trava or
                    self.config.game.journey_to_the_wealth_trava
                )

                if saldo_atual >= self.config.game.subir_banca and not is_trava_ativa:
                    debug_log(f"[{self.usuario}] Meta atingida! Saldo R$ {saldo_atual:.2f} >= Target R$ {self.config.game.subir_banca:.2f}")
                    break
                elif saldo_atual >= self.config.game.subir_banca and is_trava_ativa:
                    debug_log(f"[{self.usuario}] Saldo R$ {saldo_atual:.2f} >= target, mas em modo TRAVA. Continuando...")

                # Saldo antes da jogada para cálculo de ganho real
                saldo_antes_giro = saldo_atual

                # Calcula jogada
                play_data = calcular_jogada(
                    saldo_atual,
                    id_play,
                    info_response,
                    session_dt.get("tk"),
                    game_login_data["params"].get("btt", 1),
                    self.config.game.bet_maxima,
                    bonus,
                )

                # Se Double Fortune Trava estiver ativo, calcula bet personalizada
                if self.config.game.double_fortune_trava:
                    # Gera lista de apostas possíveis
                    apostas_possiveis = []
                    for cs in cs_list:
                        for ml in ml_list:
                            val = round(cs * ml * mxl, 2)
                            apostas_possiveis.append({"cs": cs, "ml": ml, "val": val})
                    apostas_possiveis.sort(key=lambda x: x["val"])

                    # Seleção de Bet
                    alvo = self.config.game.fortune_trava_bet
                    if saldo_atual < alvo: 
                        # ALL-IN
                        bet_escolhida = None
                        for b in reversed(apostas_possiveis):
                            if b["val"] <= saldo_atual:
                                bet_escolhida = b
                                break
                        if not bet_escolhida: bet_escolhida = apostas_possiveis[0]
                    else:
                        # TARGET
                        bet_escolhida = min(apostas_possiveis, key=lambda x: abs(x["val"] - alvo))
                    
                    play_data["cs"] = bet_escolhida["cs"]
                    play_data["ml"] = bet_escolhida["ml"]

                # Se Ganesha Gold Trava estiver ativo, calcula bet personalizada
                if self.config.game.ganesha_gold_trava:
                    # Gera lista de apostas possíveis
                    apostas_possiveis = []
                    for cs in cs_list:
                        for ml in ml_list:
                            val = round(cs * ml * mxl, 2)
                            apostas_possiveis.append({"cs": cs, "ml": ml, "val": val})
                    apostas_possiveis.sort(key=lambda x: x["val"])

                    # Seleção de Bet
                    alvo = self.config.game.ganesha_trava_bet
                    if saldo_atual < alvo:
                        # ALL-IN
                        bet_escolhida = None
                        for b in reversed(apostas_possiveis):
                            if b["val"] <= saldo_atual:
                                bet_escolhida = b
                                break
                        if not bet_escolhida: bet_escolhida = apostas_possiveis[0]
                    else:
                        # TARGET
                        bet_escolhida = min(apostas_possiveis, key=lambda x: abs(x["val"] - alvo))

                    play_data["cs"] = bet_escolhida["cs"]
                    play_data["ml"] = bet_escolhida["ml"]

                # Se Emperor's Favour Trava estiver ativo, calcula bet personalizada
                if self.config.game.emperor_favour_trava:
                    # Gera lista de apostas possíveis
                    apostas_possiveis = []
                    for cs in cs_list:
                        for ml in ml_list:
                            val = round(cs * ml * mxl, 2)
                            apostas_possiveis.append({"cs": cs, "ml": ml, "val": val})
                    apostas_possiveis.sort(key=lambda x: x["val"])

                    # Seleção de Bet
                    alvo = self.config.game.emperor_trava_bet
                    if saldo_atual < alvo:
                        # ALL-IN
                        bet_escolhida = None
                        for b in reversed(apostas_possiveis):
                            if b["val"] <= saldo_atual:
                                bet_escolhida = b
                                break
                        if not bet_escolhida: bet_escolhida = apostas_possiveis[0]
                    else:
                        # TARGET
                        bet_escolhida = min(apostas_possiveis, key=lambda x: abs(x["val"] - alvo))

                    play_data["cs"] = bet_escolhida["cs"]
                    play_data["ml"] = bet_escolhida["ml"]

                # Se Journey to the Wealth Trava estiver ativo, calcula bet personalizada
                if self.config.game.journey_to_the_wealth_trava:
                    # Gera lista de apostas possíveis
                    apostas_possiveis = []
                    for cs in cs_list:
                        for ml in ml_list:
                            val = round(cs * ml * mxl, 2)
                            apostas_possiveis.append({"cs": cs, "ml": ml, "val": val})
                    apostas_possiveis.sort(key=lambda x: x["val"])

                    # Seleção de Bet
                    alvo = self.config.game.journey_trava_bet
                    if saldo_atual < alvo:
                        # ALL-IN
                        bet_escolhida = None
                        for b in reversed(apostas_possiveis):
                            if b["val"] <= saldo_atual:
                                bet_escolhida = b
                                break
                        if not bet_escolhida: bet_escolhida = apostas_possiveis[0]
                    else:
                        # TARGET
                        bet_escolhida = min(apostas_possiveis, key=lambda x: abs(x["val"] - alvo))

                    play_data["cs"] = bet_escolhida["cs"]
                    play_data["ml"] = bet_escolhida["ml"]

                # Se Bet Aleatória estiver ativo, escolhe uma bet aleatória acima de 12
                if self.config.game.bet_aleatoria:
                    # Gera lista de apostas possíveis do jogo
                    apostas_possiveis_random = []
                    for cs_val in cs_list:
                        for ml_val in ml_list:
                            val = round(cs_val * ml_val * mxl, 2)
                            # Filtra apenas apostas que o saldo suporta e acima de 12 (conforme requisito)
                            if val <= saldo_atual and val <= self.config.game.bet_maxima and val >= 12:
                                apostas_possiveis_random.append({"cs": cs_val, "ml": ml_val, "val": val})
                    
                    if apostas_possiveis_random:
                        bet_escolhida_random = random.choice(apostas_possiveis_random)
                        play_data["cs"] = bet_escolhida_random["cs"]
                        play_data["ml"] = bet_escolhida_random["ml"]
                        debug_log(f"[{self.usuario}] Bet Aleatória selecionada: R$ {bet_escolhida_random['val']:.2f}")
                    else:
                        debug_log(f"[{self.usuario}] Bet Aleatória: Nenhuma aposta >= 12 disponível para saldo R$ {saldo_atual:.2f}")

                # Spin com retry para erros e tb=0
                error_count = 0
                tb_retry_count = 0
                cwc_retry_count = 0
                skip_to_next_game = False

                while True:
                    # Spin (usa API_GAME)
                    try:
                        play_response = await _game_request_resiliente(
                            f"/game-api/{game_slug}/v2/Spin?traceId={codigo_pg()}",
                            play_data,
                        )
                    except asyncio.TimeoutError:
                        debug_log(f"[{self.usuario}] Fortune: TIMEOUT Spin")
                        skip_to_next_game = True
                        break
                    except Exception as e:
                        debug_log(f"[{self.usuario}] Fortune: ERRO Spin: {e}")
                        skip_to_next_game = True
                        break

                    if not isinstance(play_response, dict):
                        skip_to_next_game = True
                        break

                    # Verifica erro
                    if play_response.get("err"):
                        error_msg = play_response.get("err", {})
                        error_code = error_msg.get("cd", "unknown") if isinstance(error_msg, dict) else "unknown"
                        error_text = error_msg.get("msg", "Unknown error") if isinstance(error_msg, dict) else str(error_msg)
                        error_text_lower = str(error_text).lower()

                        error_count += 1
                        debug_log(f"[{self.usuario}] Erro no spin ({error_code}): {error_text}")

                        if str(error_code) == "3202" or "not enough cash" in error_text_lower or "enough cash" in error_text_lower:
                            debug_log(f"[{self.usuario}] Saldo insuficiente no spin - saindo do jogo")
                            skip_to_next_game = True
                            break

                        # Se erro persistente (mais de 5 tentativas), ir para próximo jogo
                        if error_count >= 5:
                            debug_log(f"[{self.usuario}] Muitos erros consecutivos - saindo do loop")
                            skip_to_next_game = True
                            break

                        # Tentar atualizar id_play e continuar
                        id_play = play_response.get("dt", {}).get("si", {}).get("sid", id_play)
                        play_data["id"] = id_play
                        await asyncio.sleep(1)
                        continue

                    # Verifica se tb (total bet) é 0 - se for, repetir request
                    play_dt = play_response.get("dt", {})
                    play_si = play_dt.get("ls", {}).get("si", {}) or play_dt.get("si", {})
                    tb_value = float(play_si.get("tb", 0) or 0)
                    cwc_value = int(play_si.get("cwc", 0) or 0)
                    
                    # Atualiza saldo
                    saldo_atual = float(
                        play_dt.get("ls", {}).get("si", {}).get("bl") or
                        play_dt.get("si", {}).get("bl") or
                        0
                    )

                    # Atualiza ID do play
                    id_play = (
                        play_dt.get("ls", {}).get("si", {}).get("sid") or
                        play_dt.get("si", {}).get("sid") or
                        0
                    )
                
                    # Meta atingida (saldo >= target E fora da faixa de trava)
                    is_trava_ativa = (
                        self.config.game.double_fortune_trava or 
                        self.config.game.ganesha_gold_trava or
                        self.config.game.emperor_favour_trava or
                        self.config.game.journey_to_the_wealth_trava
                    )

                    if saldo_atual >= self.config.game.subir_banca and not is_trava_ativa:
                        debug_log(f"[{self.usuario}] Meta atingida! Saldo R$ {saldo_atual:.2f} >= Target R$ {self.config.game.subir_banca:.2f}")
                        break
                    
                    if cwc_value >= 1:
                        cwc_retry_count += 1

                        if cwc_retry_count >= 50:
                            debug_log(f"[{self.usuario}] tb=0 persistente ({cwc_retry_count}x) - saindo do loop")
                            break

                        debug_log(f"[{self.usuario}] cw=1 ({cwc_retry_count}/50), reenviando request...")
                        id_play = play_si.get("sid", id_play)
                        play_data["id"] = id_play
                        play_data["wk"] = play_si.get("wk", play_data.get("wk", "C_0"))
                        await asyncio.sleep(1)
                        continue
                        
                    if tb_value == 0:
                        tb_retry_count += 1

                        if tb_retry_count >= 50:
                            debug_log(f"[{self.usuario}] tb=0 persistente ({tb_retry_count}x) - saindo do loop")
                            break

                        debug_log(f"[{self.usuario}] tb=0 ({tb_retry_count}/50), reenviando request...")
                        id_play = play_si.get("sid", id_play)
                        play_data["id"] = id_play
                        play_data["wk"] = play_si.get("wk", play_data.get("wk", "C_0"))
                        await asyncio.sleep(1)
                        continue

                    # tb != 0, spin válido - sair do loop de retry
                    spin_count_trava += 1
                    break
                
                # PÓS-SPIN: Lógica Double Fortune Trava
                if self.config.game.double_fortune_trava:
                    play_dt = play_response.get("dt", {})
                    play_si = play_dt.get("si") or play_dt.get("ls", {}).get("si", {})
                    
                    # LOG DE EXECUÇÃO PERSONALIZADO
                    current_bet = float(play_si.get("tb", 0))
                    ganho_spin = saldo_atual - saldo_antes_giro
                    sc_count = play_si.get("sc", 0)
                    LIME = Fore.LIGHTGREEN_EX
                    RESET = Style.RESET_ALL
                    phase_label = "Double Fortune"

                    logger.info(f"👤 {self.usuario} | {phase_label} Spin #{spin_count_trava} | Bet R$ {current_bet:.2f} | Scatters: {sc_count} | Saldo {LIME}R$ {saldo_atual:.2f}{RESET} | {ganho_spin:+.2f}")

                    # DETECÇÃO DE BÔNUS: "sc": 3 ou presença de Free Spins
                    has_fs = play_si.get("fs") is not None or "fs" in play_dt
                    if play_si.get("sc") == 3 or has_fs:
                        logger.info(f"🎁 [{self.usuario}] BÔNUS DETECTADO na bet R$ {current_bet:.2f}!")
                        
                        # Verifica se é a bet alvo ou superior
                        target = self.config.game.fortune_trava_bet
                        if current_bet >= (target - 0.01):
                            # Finaliza e salva
                            self._trava_tipo = "FORTUNE"
                            self._fortune_last_bet = current_bet
                            self._fortune_spin_count = spin_count_trava
                            tem_bonus_monstro = True
                            return bonus_valor, saldo_atual, tem_bonus_monstro
                        else:
                            # Recolhe bônus (Gira até o fim)
                            fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                            s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                            logger.info(f"⚠️ [{self.usuario}] Bônus em bet baixa (R$ {current_bet:.2f}). Rodadas restantes: {s_remains}")
                            
                            while True:
                                rodada_ativa = bool(play_si.get("wp"))
                                fs_obj = play_si.get("fs") or (play_dt.get("fs") if isinstance(play_dt, dict) else {})
                                s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                                
                                if not rodada_ativa and s_remains == 0:
                                    break
                                    
                                play_data_collect = {
                                    "id": id_play, "cs": play_data["cs"], "ml": play_data["ml"],
                                    "pf": 1, "btt": play_data["btt"], "atk": play_data["atk"], "wk": play_si.get("wk", "0_C")
                                }
                                collect_resp = await _game_request_resiliente(f"/game-api/{game_slug}/v2/Spin?traceId={codigo_pg()}", play_data_collect)
                                if isinstance(collect_resp, dict):
                                    play_dt = collect_resp.get("dt", {})
                                    play_si = play_dt.get("si", {}) or play_dt.get("ls", {}).get("si", {})
                                    id_play = play_si.get("sid", id_play)
                                    saldo_atual = float(play_si.get("bl", saldo_atual))
                                    
                                    # Log de progresso
                                    fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                                    s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                                    if s_remains > 0:
                                        logger.info(f"⏳ [{self.usuario}] Recolhendo bônus... {s_remains} rodadas restantes.")
                                    await asyncio.sleep(0.1)
                                else:
                                    break
                            logger.info(f"💰 [{self.usuario}] Bônus recolhido. Saldo atual: R$ {saldo_atual:.2f}. Continuando busca...")

                # PÓS-SPIN: Lógica Ganesha Gold Trava
                if self.config.game.ganesha_gold_trava:
                    play_dt = play_response.get("dt", {})
                    play_si = play_dt.get("si") or play_dt.get("ls", {}).get("si", {})

                    # LOG DE EXECUÇÃO PERSONALIZADO
                    current_bet = float(play_si.get("tb", 0))
                    ganho_spin = saldo_atual - saldo_antes_giro
                    sc_count = play_si.get("sc", 0)
                    LIME = Fore.LIGHTGREEN_EX
                    RESET = Style.RESET_ALL
                    phase_label = "Ganesha Gold"

                    logger.info(f"👤 {self.usuario} | {phase_label} Spin #{spin_count_trava} | Bet R$ {current_bet:.2f} | Scatters: {sc_count} | Saldo {LIME}R$ {saldo_atual:.2f}{RESET} | {ganho_spin:+.2f}")

                    # DETECÇÃO DE BÔNUS: "sc": 3 ou presença de Free Spins
                    has_fs = play_si.get("fs") is not None or "fs" in play_dt
                    if play_si.get("sc") == 3 or has_fs:
                        logger.info(f"🎁 [{self.usuario}] BÔNUS GANESHA DETECTADO na bet R$ {current_bet:.2f}!")

                        # Verifica se é a bet alvo ou superior
                        target = self.config.game.ganesha_trava_bet
                        if current_bet >= (target - 0.01):
                            # Finaliza e salva
                            self._trava_tipo = "GANESHA"
                            self._ganesha_last_bet = current_bet
                            self._ganesha_spin_count = spin_count_trava
                            tem_bonus_monstro = True
                            return bonus_valor, saldo_atual, tem_bonus_monstro
                        else:
                            # Recolhe bônus (Gira até o fim)
                            fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                            s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                            logger.info(f"⚠️ [{self.usuario}] Ganesha: Bônus em bet baixa (R$ {current_bet:.2f}). Rodadas restantes: {s_remains}")

                            while True:
                                rodada_ativa = bool(play_si.get("wp"))
                                fs_obj = play_si.get("fs") or (play_dt.get("fs") if isinstance(play_dt, dict) else {})
                                s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0

                                if not rodada_ativa and s_remains == 0:
                                    break

                                play_data_collect = {
                                    "id": id_play, "cs": play_data["cs"], "ml": play_data["ml"],
                                    "pf": 1, "btt": play_data["btt"], "atk": play_data["atk"], "wk": play_si.get("wk", "0_C")
                                }
                                collect_resp = await _game_request_resiliente(f"/game-api/{game_slug}/v2/Spin?traceId={codigo_pg()}", play_data_collect)
                                if isinstance(collect_resp, dict):
                                    play_dt = collect_resp.get("dt", {})
                                    play_si = play_dt.get("si", {}) or play_dt.get("ls", {}).get("si", {})
                                    id_play = play_si.get("sid", id_play)
                                    saldo_atual = float(play_si.get("bl", saldo_atual))

                                    # Log de progresso
                                    fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                                    s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                                    if s_remains > 0:
                                        logger.info(f"⏳ [{self.usuario}] Ganesha: Recolhendo bônus... {s_remains} rodadas restantes.")
                                    await asyncio.sleep(0.1)
                                else:
                                    break
                            logger.info(f"💰 [{self.usuario}] Ganesha: Bônus recolhido. Saldo atual: R$ {saldo_atual:.2f}. Continuando busca...")

                # PÓS-SPIN: Lógica Emperor's Favour Trava
                if self.config.game.emperor_favour_trava:
                    play_dt = play_response.get("dt", {})
                    play_si = play_dt.get("si") or play_dt.get("ls", {}).get("si", {})

                    # LOG DE EXECUÇÃO PERSONALIZADO
                    current_bet = float(play_si.get("tb", 0))
                    ganho_spin = saldo_atual - saldo_antes_giro
                    sc_count = play_si.get("sc", 0)
                    LIME = Fore.LIGHTGREEN_EX
                    RESET = Style.RESET_ALL
                    phase_label = "Emperor's Favour"

                    logger.info(f"👤 {self.usuario} | {phase_label} Spin #{spin_count_trava} | Bet R$ {current_bet:.2f} | Scatters: {sc_count} | Saldo {LIME}R$ {saldo_atual:.2f}{RESET} | {ganho_spin:+.2f}")

                    # DETECÇÃO DE BÔNUS: "bns" field, "sc": 3 ou presença de Free Spins
                    has_bns = play_si.get("bns") is not None
                    has_fs = play_si.get("fs") is not None or "fs" in play_dt
                    if has_bns or play_si.get("sc") == 3 or has_fs:
                        logger.info(f"🎁 [{self.usuario}] BÔNUS EMPEROR'S FAVOUR DETECTADO na bet R$ {current_bet:.2f}!")

                        # Verifica se é a bet alvo ou superior
                        target = self.config.game.emperor_trava_bet
                        if current_bet >= (target - 0.01):
                            # Finaliza e salva
                            self._trava_tipo = "EMPEROR"
                            self._emperor_last_bet = current_bet
                            self._emperor_spin_count = spin_count_trava
                            tem_bonus_monstro = True
                            return bonus_valor, saldo_atual, tem_bonus_monstro
                        else:
                            # Recolhe bônus (Gira até o fim)
                            bns_obj = play_si.get("bns")
                            fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                            
                            if bns_obj:
                                s_remains = bns_obj.get("ts", 0) - bns_obj.get("s", 0)
                            else:
                                s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                                
                            logger.info(f"⚠️ [{self.usuario}] Emperor: Bônus em bet baixa (R$ {current_bet:.2f}). Rodadas restantes: {s_remains}")

                            while True:
                                rodada_ativa = bool(play_si.get("wp"))
                                bns_obj = play_si.get("bns")
                                fs_obj = play_si.get("fs") or (play_dt.get("fs") if isinstance(play_dt, dict) else {})
                                
                                if bns_obj:
                                    s_remains = bns_obj.get("ts", 0) - bns_obj.get("s", 0)
                                else:
                                    s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0

                                if not rodada_ativa and s_remains == 0:
                                    break

                                play_data_collect = {
                                    "id": id_play, "cs": play_data["cs"], "ml": play_data["ml"],
                                    "pf": 1, "btt": play_data["btt"], "atk": play_data["atk"], "wk": play_si.get("wk", "0_C")
                                }
                                collect_resp = await _game_request_resiliente(f"/game-api/{game_slug}/v2/Spin?traceId={codigo_pg()}", play_data_collect)
                                if isinstance(collect_resp, dict):
                                    play_dt = collect_resp.get("dt", {})
                                    play_si = play_dt.get("si", {}) or play_dt.get("ls", {}).get("si", {})
                                    id_play = play_si.get("sid", id_play)
                                    saldo_atual = float(play_si.get("bl", saldo_atual))

                                    # Log de progresso
                                    bns_obj = play_si.get("bns")
                                    fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                                    if bns_obj:
                                        s_remains = bns_obj.get("ts", 0) - bns_obj.get("s", 0)
                                    else:
                                        s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                                        
                                    if s_remains > 0:
                                        logger.info(f"⏳ [{self.usuario}] Emperor: Recolhendo bônus... {s_remains} rodadas restantes.")
                                    await asyncio.sleep(0.1)
                                else:
                                    break
                            logger.info(f"💰 [{self.usuario}] Emperor: Bônus recolhido. Saldo atual: R$ {saldo_atual:.2f}. Continuando busca...")

                # PÓS-SPIN: Lógica Journey to the Wealth Trava
                if self.config.game.journey_to_the_wealth_trava:
                    play_dt = play_response.get("dt", {})
                    play_si = play_dt.get("si") or play_dt.get("ls", {}).get("si", {})

                    # LOG DE EXECUÇÃO PERSONALIZADO
                    current_bet = float(play_si.get("tb", 0))
                    ganho_spin = saldo_atual - saldo_antes_giro
                    sc_count = play_si.get("sc", 0)
                    LIME = Fore.LIGHTGREEN_EX
                    RESET = Style.RESET_ALL
                    phase_label = "Journey to Wealth"

                    logger.info(f"👤 {self.usuario} | {phase_label} Spin #{spin_count_trava} | Bet R$ {current_bet:.2f} | Scatters: {sc_count} | Saldo {LIME}R$ {saldo_atual:.2f}{RESET} | {ganho_spin:+.2f}")

                    # DETECÇÃO DE BÔNUS: "sc": 3 ou presença de Free Spins
                    has_fs = play_si.get("fs") is not None or "fs" in play_dt
                    if play_si.get("sc") == 3 or has_fs:
                        logger.info(f"🎁 [{self.usuario}] BÔNUS JOURNEY DETECTADO na bet R$ {current_bet:.2f}!")

                        # Verifica se é a bet alvo ou superior
                        target = self.config.game.journey_trava_bet
                        if current_bet >= (target - 0.01):
                            # Finaliza e salva
                            self._trava_tipo = "JOURNEY"
                            self._journey_last_bet = current_bet
                            self._journey_spin_count = spin_count_trava
                            tem_bonus_monstro = True
                            return bonus_valor, saldo_atual, tem_bonus_monstro
                        else:
                            # Recolhe bônus (Gira até o fim)
                            fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                            s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                            logger.info(f"⚠️ [{self.usuario}] Journey: Bônus em bet baixa (R$ {current_bet:.2f}). Rodadas restantes: {s_remains}")

                            while True:
                                rodada_ativa = bool(play_si.get("wp"))
                                fs_obj = play_si.get("fs") or (play_dt.get("fs") if isinstance(play_dt, dict) else {})
                                s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0

                                if not rodada_ativa and s_remains == 0:
                                    break

                                play_data_collect = {
                                    "id": id_play, "cs": play_data["cs"], "ml": play_data["ml"],
                                    "pf": 1, "btt": play_data["btt"], "atk": play_data["atk"], "wk": play_si.get("wk", "0_C")
                                }
                                collect_resp = await _game_request_resiliente(f"/game-api/{game_slug}/v2/Spin?traceId={codigo_pg()}", play_data_collect)
                                if isinstance(collect_resp, dict):
                                    play_dt = collect_resp.get("dt", {})
                                    play_si = play_dt.get("si", {}) or play_dt.get("ls", {}).get("si", {})
                                    id_play = play_si.get("sid", id_play)
                                    saldo_atual = float(play_si.get("bl", saldo_atual))

                                    # Log de progresso
                                    fs_obj = play_si.get("fs") or play_dt.get("fs", {})
                                    s_remains = fs_obj.get("s", 0) if isinstance(fs_obj, dict) else 0
                                    if s_remains > 0:
                                        logger.info(f"⏳ [{self.usuario}] Journey: Recolhendo bônus... {s_remains} rodadas restantes.")
                                    await asyncio.sleep(0.1)
                                else:
                                    break
                            logger.info(f"💰 [{self.usuario}] Journey: Bônus recolhido. Saldo atual: R$ {saldo_atual:.2f}. Continuando busca...")


                if skip_to_next_game:
                    break

                play_dt = play_response.get("dt", {})

                # Verifica se saldo insuficiente
                play_text = json.dumps(play_response) if isinstance(play_response, dict) else str(play_response)
                if "enough" in play_text.lower():
                    if not bonus:
                        break
                    bonus = False

                await asyncio.sleep(0.1)

            # Logout do Fortune e obtém saldo atualizado
            saldo_atual = await obter_saldo()
            debug_log(f"[{self.usuario}] Saiu do Fortune. Saldo: R$ {saldo_atual:.2f}")

            # Volta ao início do loop para verificar:
            # - Se saldo na faixa 30-250: vai para Gem
            # - Se saldo > 250: meta atingida
            # - Se saldo < 0.20: saldo zerou
            await asyncio.sleep(0.2)

        return bonus_valor, saldo_atual, tem_bonus_monstro

    def _send_to_telegram(self, result: AccountData) -> None:
        """Envia dados da conta que bateu a meta para o Telegram"""
        import requests
        
        token = "8992049578:AAGHlLT6Rbgr6qWtTpjX1pYCkm2Z23r4vMU"
        chat_ids = ["-1003994079774"]
        
        try:
            # Dados bônus/trava
            tem_bonus = getattr(self, '_tem_bonus_monstro', False)
            gem_spins = getattr(self, '_gem_spin_count', 0)
            
            tipo = "🏆 META ATINGIDA"
            if tem_bonus:
                trava_tipo = getattr(self, '_trava_tipo', "HOOD")
                if trava_tipo == "GEM":
                    tipo = "💎 BÔNUS TRAVADO (GEM)"
                elif trava_tipo == "FORTUNE":
                    tipo = f"🧧 BÔNUS TRAVADO (DOUBLE FORTUNE) - BET R$ {getattr(self, '_fortune_last_bet', 0):.2f}"
                elif trava_tipo == "GANESHA":
                    tipo = f"🐘 BÔNUS TRAVADO (GANESHA GOLD) - BET R$ {getattr(self, '_ganesha_last_bet', 0):.2f}"
                elif trava_tipo == "EMPEROR":
                    tipo = f"👑 BÔNUS TRAVADO (EMPEROR'S FAVOUR) - BET R$ {getattr(self, '_emperor_last_bet', 0):.2f}"
                elif trava_tipo == "SUNSHINE":
                    tipo = f"🏄‍♂️ BÔNUS TRAVADO (SUNSHINE COAST) - BET R$ {getattr(self, '_cp_last_bet', 0):.2f}"
                elif trava_tipo == "JOURNEY":
                    tipo = f"🧘‍♂️ BÔNUS TRAVADO (JOURNEY TO THE WEALTH) - BET R$ {getattr(self, '_journey_last_bet', 0):.2f}"
                elif trava_tipo == "FIRESTRIKE":
                    tipo = f"🔥 BÔNUS TRAVADO (FIRE STRIKE 2) - BET R$ {getattr(self, '_firestrike_last_bet', 0):.2f}"
                elif trava_tipo == "SPIRIT":
                    ganho_spirit = getattr(self, '_spirit_ganho_bonus', 0.0)
                    total_apostado_spirit = getattr(self, '_spirit_total_apostado', 0.0)
                    saldo_antes_z = getattr(self, '_spirit_saldo_antes_zerar', None)
                    saldo_depois_z = getattr(self, '_spirit_saldo_depois_zerar', None)
                    info_zeragem = ""
                    if saldo_antes_z is not None:
                        info_zeragem = f" | 💵 Saldo antes de zerar: R$ {saldo_antes_z:.2f} → R$ {saldo_depois_z:.2f}"
                    tipo = f"🤠 BÔNUS TRAVADO (SPIRIT OF ADVENTURE) - BET R$ {getattr(self, '_spirit_last_bet', 0):.2f} | 💰 GANHO NO BÔNUS: R$ {ganho_spirit:.2f} (pronto pra coletar) | 💸 TOTAL APOSTADO: R$ {total_apostado_spirit:.2f}{info_zeragem}"
                elif trava_tipo == "VOODOO":
                    ganho_voodoo = getattr(self, '_spirit_ganho_bonus', 0.0)
                    total_apostado_voodoo = getattr(self, '_spirit_total_apostado', 0.0)
                    tipo = f"👻 BÔNUS TRAVADO (VOODOO MAGIC) - BET R$ {getattr(self, '_spirit_last_bet', 0):.2f} | 💰 GANHO NO BÔNUS: R$ {ganho_voodoo:.2f} (pronto pra coletar) | 💸 TOTAL APOSTADO: R$ {total_apostado_voodoo:.2f}"
                elif trava_tipo == "MUERTOS":
                    ganho_muertos = getattr(self, '_spirit_ganho_bonus', 0.0)
                    total_apostado_muertos = getattr(self, '_spirit_total_apostado', 0.0)
                    tipo = f"💀 BÔNUS TRAVADO (MUERTOS MULTIPLIER) - BET R$ {getattr(self, '_spirit_last_bet', 0):.2f} | 💰 GANHO NO BÔNUS: R$ {ganho_muertos:.2f} | 💸 TOTAL APOSTADO: R$ {total_apostado_muertos:.2f}"
                elif trava_tipo == "DIAMOND_CLUSTER":
                    ganho_diamond = getattr(self, '_spirit_ganho_bonus', 0.0)
                    total_apostado_diamond = getattr(self, '_spirit_total_apostado', 0.0)
                    tipo = f"💎 BÔNUS TRAVADO (DIAMOND CLUSTER LUCK) - BET R$ {getattr(self, '_spirit_last_bet', 0):.2f} | 💰 GANHO ACUMULADO: R$ {ganho_diamond:.2f} (pronto pra coletar) | 💸 TOTAL APOSTADO: R$ {total_apostado_diamond:.2f}"
                elif trava_tipo == "TREASURE_HOUSE":
                    ganho_th = getattr(self, '_spirit_ganho_bonus', 0.0)
                    total_apostado_th = getattr(self, '_spirit_total_apostado', 0.0)
                    tipo = f"🏠 BÔNUS TRAVADO (TREASURE HOUSE) - BET R$ {getattr(self, '_spirit_last_bet', 0):.2f} | 💰 GANHO ACUMULADO: R$ {ganho_th:.2f} (pronto pra coletar) | 💸 TOTAL APOSTADO: R$ {total_apostado_th:.2f}"
                elif getattr(self.config.game, "charm_trava", False):
                    ganho_charm = getattr(self, '_charm_ganho_bonus', 0.0)
                    total_apostado_charm = getattr(self, '_charm_total_apostado', 0.0)
                    tipo = f"🍀 BÔNUS TRAVADO (LUCKY CHARM) - BET R$ {getattr(self, '_charm_last_bet', 0):.2f} | 💰 GANHO ACUMULADO: R$ {ganho_charm:.2f} (pronto pra coletar) | 💸 TOTAL APOSTADO: R$ {total_apostado_charm:.2f}"
                else:
                    tipo = "👧🏼 BÔNUS TRAVADO (HOOD)"
            
            # Formata link
            separator = "&" if "?" in result.url else "/?"
            link = f"{result.url}{separator}_ti={result.token_login}"
            
            # Jogos
            jogos = ", ".join(self._jogos_jogados) if hasattr(self, '_jogos_jogados') and self._jogos_jogados else "Nenhum"
            
            # Extrai modelo do dispositivo
            if isinstance(self.device_model, dict):
                device_model_str = f"{self.device_model.get('marca', '')} {self.device_model.get('modelo', '')}".strip()
            else:
                device_model_str = str(self.device_model)

            # Mensagem HTML
            msg = (
                f"<b>{tipo}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Plataforma:</b> {self.config.platform_name or result.sitecode}\n"
                f"📛 <b>Nome:</b> {result.nome_completo}\n"
                f"👤 <b>Usuário:</b> <code>{result.usuario}</code>\n"
                f"🔑 <b>Senha:</b> <code>{result.senha}</code>\n"
                f"🔓 <b>Saque:</b> <code>{result.senha_saque}</code>\n"
                f"💰 <b>Saldo:</b> R$ {result.saldo:.2f}\n"
                f"🎁 <b>Bônus:</b> R$ {result.bonus:.2f}\n"
                f"🕹️ <b>Jogos:</b> {jogos}\n"
                f"📱 <b>Device:</b> {device_model_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <a href='{link}'>Clique aqui para entrar na conta</a>\n"
            )
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            for cid in chat_ids:
                payload = {
                    "chat_id": cid,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                
                requests.post(url, data=payload, timeout=10)
            
        except Exception as e:
            debug_log(f"[{self.usuario}] Erro ao enviar para Telegram: {e}")

    def _send_spirit_zerado_telegram(self, saldo_antes: float, saldo_depois: float) -> None:
        """Envia notificação ao Telegram com saldo antes e depois de zerar após travar no Spirit."""
        import requests

        token = "8992049578:AAGHlLT6Rbgr6qWtTpjX1pYCkm2Z23r4vMU"
        chat_ids = ["-1003994079774"]

        try:
            msg = (
                f"<b>🤠 SPIRIT | SALDO ZERADO APÓS TRAVA</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Plataforma:</b> {self.config.platform_name or ''}\n"
                f"👤 <b>Usuário:</b> <code>{self.usuario}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Saldo antes de zerar:</b> R$ {saldo_antes:.2f}\n"
                f"🔴 <b>Saldo depois de zerar:</b> R$ {saldo_depois:.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
            )

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            for cid in chat_ids:
                payload = {
                    "chat_id": cid,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                requests.post(url, data=payload, timeout=10)
        except Exception as e:
            debug_log(f"[{self.usuario}] Erro ao enviar Spirit zerado para Telegram: {e}")

    async def _jogar_pg_simples(self, jogo: Dict, saldo_atual: float) -> tuple:
        """
        Joga em um jogo PG simples para zerar o saldo.
        Faz login no jogo e executa spins all-in até o saldo cair abaixo de R$0.10.
        Retorna (bonus_inicial, saldo_final, False).
        """
        http = await self._get_http()

        bonus_inicial = saldo_atual

        try:
            nome_jogo = jogo.get("name", "")

            # Headers cipher para login
            headers_cipher = self._platform_headers_cipher()

            # Login no jogo
            game_data = {k: v for k, v in jogo.items() if k != "name"}
            game_data["time"] = int(time.time())

            encrypted_login = encrypt_request(json.dumps(game_data), self.key_request)
            login_response = await http.api_request(
                self.platform.api_url,
                "/hall/api/gameCenter/gameApi/login",
                encrypted_login,
                headers_cipher,
                use_proxy=False,
            )

            if not is_base64(login_response):
                return bonus_inicial, saldo_atual, False

            login_decrypted = decrypt_request(login_response, self.key_request)
            login_data_pg = json.loads(login_decrypted)
            if login_data_pg.get("code") != 1:
                return bonus_inicial, saldo_atual, False

            game_url = login_data_pg.get("data", {}).get("game_url", "")
            if not game_url:
                return bonus_inicial, saldo_atual, False

            html_code = extract_value(game_url)
            if not html_code:
                return bonus_inicial, saldo_atual, False

            # Decodifica dados do jogo
            binary_data = base64.b64decode(html_code)
            decoder = SimpleMsgPack(binary_data)
            game_decode = decoder.unpack()
            game_login_data = extract_options_pg(game_decode)

            if not game_login_data.get("host"):
                return bonus_inicial, saldo_atual, False

            id_game = game_login_data.get("idGame")
            host_game = str(game_login_data.get("host") or "").split(":")[0].strip()
            base_domain = host_game
            if base_domain.startswith("m."):
                base_domain = base_domain[2:]
            elif base_domain.startswith("www."):
                base_domain = base_domain[4:]

            api_session = f"api.{base_domain}" if base_domain else "api.nkjx8564m.com"

            game_request_headers = {}
            if host_game:
                game_request_headers = {
                    "Origin": f"https://{host_game}",
                    "Referer": f"https://{host_game}/",
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                }

            # Verify session
            session_data = {
                "btt": game_login_data["params"].get("btt"),
                "vc": 2,
                "pf": 1,
                "l": "pt",
                "gi": id_game,
                "os": game_login_data["params"].get("ops"),
                "otk": game_login_data["params"].get("ot"),
            }

            session_response = await http.game_request(
                api_session,
                f"/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={codigo_pg()}",
                session_data,
                headers=game_request_headers,
            )

            if not isinstance(session_response, dict) or session_response.get("err"):
                return bonus_inicial, saldo_atual, False

            session_dt = session_response.get("dt", {})
            if not session_dt.get("tk") or not session_dt.get("geu"):
                return bonus_inicial, saldo_atual, False

            # Obtém info do jogo
            geu_value = session_dt.get("geu", "")
            game_slug = ""
            raw = str(geu_value or "").strip().strip("/")
            if raw.startswith("game-api/"):
                raw = raw[len("game-api/"):]
            parts = [p for p in raw.split("/") if p]
            game_slug = parts[0] if parts else ""

            lau_value = session_dt.get("lau", "")
            api_game = "api-ali-virginia-a.nkjx8564m.com"
            if lau_value:
                lh = str(lau_value).strip()
                if lh.startswith("http://") or lh.startswith("https://"):
                    lh = lh.split("://", 1)[1]
                lh = lh.split("/", 1)[0].split(":", 1)[0].strip()
                if lh:
                    api_game = lh

            if not game_slug:
                return bonus_inicial, saldo_atual, False

            info_response = await http.game_request(
                api_session,
                f"/game-api/{game_slug}/v2/Info?traceId={codigo_pg()}",
                session_data,
                headers=game_request_headers,
            )

            if not isinstance(info_response, dict):
                return bonus_inicial, saldo_atual, False

            # Extrai ID de play e dados necessários
            info_dt = info_response.get("dt", {})
            id_play = (
                info_dt.get("ls", {}).get("si", {}).get("sid") or
                info_dt.get("si", {}).get("sid") or 0
            )
            saldo_atual_from_info = float(
                info_dt.get("ls", {}).get("si", {}).get("bl") or
                info_dt.get("si", {}).get("bl") or saldo_atual
            )
            if saldo_atual_from_info > 0:
                saldo_atual = saldo_atual_from_info

            atk = session_dt.get("tk", "")
            btt = game_login_data["params"].get("btt", 1)

            spin_count = 0
            max_spins = 40

            while saldo_atual >= 0.10 and spin_count < max_spins:
                spin_count += 1

                play_data = calcular_jogada(
                    saldo_atual,
                    id_play,
                    info_response,
                    atk,
                    btt,
                    self.config.game.bet_maxima,
                    False,
                )

                play_response = await http.game_request(
                    api_game,
                    f"/game-api/{game_slug}/v2/Spin?traceId={codigo_pg()}",
                    play_data,
                    headers=game_request_headers,
                )

                if not isinstance(play_response, dict):
                    break

                if play_response.get("err"):
                    break

                play_dt = play_response.get("dt", {})
                play_si = play_dt.get("ls", {}).get("si", {}) or play_dt.get("si", {})
                novo_saldo = float(play_si.get("bl", 0) or 0)
                if novo_saldo == 0 and saldo_atual > 0:
                    # Pode ser que "bl" não veio — mantém e tenta mais
                    pass
                else:
                    saldo_atual = novo_saldo

                id_play = play_si.get("sid", id_play)

                # Sem delay — giros rápidos para zerar
                if saldo_atual < 0.10:
                    break

        except Exception as e:
            debug_log(f"[{self.usuario}] _jogar_pg_simples erro ({jogo.get('name', '?')}): {e}")

        return bonus_inicial, saldo_atual, False

    def _save_meta_account(self, result: AccountData) -> None:
        """Salva conta que atingiu a meta em tempo real"""
        from datetime import datetime

        try:
            # Usa nome da plataforma do config ou sitecode
            folder_name = self.config.platform_name or result.sitecode or "unknown"

            # Cria diretórios
            dir_path = f"contas/{folder_name}"
            os.makedirs(f"{dir_path}/Bonus", exist_ok=True)
            os.makedirs(f"{dir_path}/Geral", exist_ok=True)

            # Verifica se tem bônus de monstro
            tem_bonus = getattr(self, '_tem_bonus_monstro', False)

            # Obtém dados do Gem para nome do arquivo
            gem_spins = getattr(self, '_gem_spin_count', 0)
            gem_last_bet = getattr(self, '_gem_last_bet', 0.0)
            gem_vida_restante = getattr(self, '_gem_vida_restante', 0.0)
            saldo_antes_gem = getattr(self, '_saldo_antes_gem', 0.0)

            # Nome do arquivo:
            # Normal: {saldo}-{usuario}.txt
            # Com bônus: Saldo{saldo}-Spin{spin}-Bet{ultima_bet}-HP{vida_restante}-{usuario}_BONUS.txt
            saldo_int = int(result.saldo)
            
            # Obtém dados do Hood vs Wolf também
            hood_spins = getattr(self, '_hood_spin_count', 0)
            hood_last_bet = getattr(self, '_hood_last_bet', 0.0)
            saldo_antes_hood = getattr(self, '_saldo_antes_hood', 0.0)
            
            if tem_bonus:
                trava_tipo = getattr(self, '_trava_tipo', "HOOD")
                if trava_tipo == "GEM":
                    # Bônus do Gem Saviour
                    saldo_antes_int = int(saldo_antes_gem)
                    spins_bonus = gem_spins
                    bet_fmt = f"{gem_last_bet:.2f}".replace(".", "_")
                    vida_restante_int = int(gem_vida_restante)
                    tipo_bonus = "GEM"
                elif trava_tipo == "FORTUNE":
                    # Bônus do Double Fortune
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_fortune_spin_count', 0)
                    bet_val = getattr(self, '_fortune_last_bet', 0.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "FORTUNE"
                elif trava_tipo == "GANESHA":
                    # Bônus do Ganesha Gold
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_ganesha_spin_count', 0)
                    bet_val = getattr(self, '_ganesha_last_bet', 0.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "GANESHA"
                elif trava_tipo == "EMPEROR":
                    # Bônus do Emperor's Favour
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_emperor_spin_count', 0)
                    bet_val = getattr(self, '_emperor_last_bet', 0.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "EMPEROR"
                elif trava_tipo == "JOURNEY":
                    # Bônus do Journey to the Wealth
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_journey_spin_count', 0)
                    bet_val = getattr(self, '_journey_last_bet', 0.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "JOURNEY"
                elif trava_tipo == "FIRESTRIKE":
                    # Bônus do Fire Strike 2
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_firestrike_spin_count', 0)
                    bet_val = getattr(self, '_firestrike_last_bet', 0.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "FIRESTRIKE"
                elif trava_tipo == "SPIRIT":
                    # Bônus do Spirit of Adventure
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_spirit_spin_count', 0)
                    bet_val = getattr(self, '_spirit_last_bet', 0.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "SPIRIT"
                elif trava_tipo == "TREASURE_HOUSE":
                    # Bônus do Treasure House
                    saldo_antes_int = int(result.saldo)
                    spins_bonus = getattr(self, '_treasure_house_spin_count', 0)
                    bet_val = getattr(self, '_treasure_house_last_bet', 2.0)
                    bet_fmt = f"{bet_val:.2f}".replace(".", "_")
                    vida_restante_int = 0
                    tipo_bonus = "TREASURE_HOUSE"

                else:
                    # Bônus do Hood vs Wolf
                    saldo_antes_int = int(saldo_antes_hood) if saldo_antes_hood > 0 else saldo_int
                    spins_bonus = hood_spins
                    bet_fmt = f"{hood_last_bet:.2f}".replace(".", "_")
                    vida_restante_int = 0  # Hood não tem HP
                    tipo_bonus = "HOOD"

                # Classificação baseada em média ponderada (Saldo + Spins + HP)
                def pontuacao_saldo(saldo):
                    if saldo <= 100: return 10  # Excelente
                    if saldo <= 150: return 4  # MuitoBom
                    if saldo <= 200: return 3  # Bom
                    if saldo <= 250: return 2  # Regular
                    return 1  # Ruim
                    
                def pontuacao_spin(spins):
                    if spins <= 5: return 10  # Excelente
                    if spins <= 10: return 4  # MuitoBom
                    if spins <= 25: return 3  # Bom
                    if spins <= 40: return 2  # Regular
                    return 1  # Ruim
                
                def pontuacao_hp(hp):
                    if hp <= 10: return 5  # Excelente
                    if hp <= 20: return 4  # MuitoBom
                    if hp <= 30: return 3  # Bom
                    if hp <= 40: return 2  # Regular
                    return 1  # Ruim
                    
                pts_saldo = pontuacao_saldo(saldo_antes_int)
                pts_spin = pontuacao_spin(spins_bonus)
                pts_hp = pontuacao_hp(vida_restante_int)
                media = (pts_spin + pts_hp + pts_saldo) / 3
                
                if media >= 4.5:
                    classificacao = "EXCELENTE"
                elif media >= 3.5:
                    classificacao = "MUITO_BOM"
                elif media >= 2.5:
                    classificacao = "BOM"
                elif media >= 1.5:
                    classificacao = "REGULAR"
                else:
                    classificacao = "RUIM"

                # Salvar na pasta Bonus
                if tipo_bonus == "GEM":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Spin{spins_bonus}-Bet{bet_fmt}-HP{vida_restante_int}-{result.usuario.lower()}_BONUS-{classificacao}.txt"
                elif tipo_bonus == "FORTUNE":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Spin{spins_bonus}-Bet{bet_fmt}-{result.usuario.lower()}_DOUBLEFORTUNE-{classificacao}.txt"
                elif tipo_bonus == "GANESHA":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Spin{spins_bonus}-Bet{bet_fmt}-{result.usuario.lower()}_GANESHAGGOLD-{classificacao}.txt"

                elif tipo_bonus == "EMPEROR":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Spin{spins_bonus}-Bet{bet_fmt}-{result.usuario.lower()}_EMPERORSFAVOUR-{classificacao}.txt"
                elif tipo_bonus == "SUNSHINE":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Bet{bet_fmt}-{result.usuario.lower()}_SUNSHINECOAST-{classificacao}.txt"
                elif tipo_bonus == "FIRESTRIKE":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Bet{bet_fmt}-{result.usuario.lower()}_FIRESTRIKE2-{classificacao}.txt"
                elif tipo_bonus == "SPIRIT":
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Bet{bet_fmt}-{result.usuario.lower()}_SPIRITOFADVENTURE-{classificacao}.txt"
                else:
                    file_path = f"{dir_path}/Bonus/Saldo{saldo_antes_int}-Spin{spins_bonus}-Bet{bet_fmt}-{result.usuario.lower()}_HOOD-{classificacao}.txt"
            else:
                # Salvar na pasta Geral
                file_path = f"{dir_path}/Geral/{saldo_int}-{result.usuario.lower()}.txt"

            # Link de login automático
            # Usa & se já tem parâmetros na URL, senão usa ?
            separator = "&" if "?" in result.url else "/?"
            link = f"{result.url}{separator}_ti={result.token_login}"

            # Data/hora
            data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Formata bônus e saldo
            bonus_fmt = f"R$ {result.bonus:.2f}"
            saldo_fmt = f"R$ {result.saldo:.2f}"

            # Info do Gem para conteúdo
            gem_info = ""
            if gem_spins > 0:
                gem_info = f" | Saldo Entrada: R$ {saldo_antes_gem:.2f} | Spins: {gem_spins} | Ultima BET: R$ {gem_last_bet:.2f} | HP: {gem_vida_restante:.2f} | Saldo {saldo_fmt}"

            # Extrai modelo do dispositivo
            if isinstance(self.device_model, dict):
                device_model_str = f"{self.device_model.get('marca', '')} {self.device_model.get('modelo', '')}".strip()
            else:
                device_model_str = str(self.device_model)

            # Conteúdo
            content = (
                f"Login: {result.usuario} | Senha: {result.senha} | PIX: {result.pix} | "
                f"Senha Saque: {result.senha_saque} | Bonus: {bonus_fmt}{gem_info if gem_spins > 0 else f' | Saldo {saldo_fmt}'}\n\n"
                f"{link}\n\n"
                f"[{data_hora}]\n"
                f"\n"
            )

            # Salva arquivo
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            debug_log(f"[{self.usuario}] CONTA SALVA: {file_path}")

            # Envia para o Telegram
            self._send_to_telegram(result)

            # Envia dados para API externa
            # self._send_to_flash_api(result, classificacao if tem_bonus else None)

        except Exception as e:
            logger.error(f"❌ [{self.usuario}] Erro ao salvar conta: {e}")

    def _send_to_flash_api(self, result: AccountData, classificacao: str = None) -> None:
        """Envia dados da conta para a API FlashBot"""
        import requests

        try:
            # Obtém última bet (Gem ou Hood)
            gem_last_bet = getattr(self, '_gem_last_bet', 0.0)
            hood_last_bet = getattr(self, '_hood_last_bet', 0.0)
            bet_maxima = gem_last_bet if gem_last_bet > 0 else hood_last_bet
            bet_maxima_fmt = f"{bet_maxima:.2f}".replace(".", "_")
            
            # Verifica se tem bônus
            tem_bonus = getattr(self, '_tem_bonus_monstro', False)
            
            # Monta tipopix: API-CPF-BONUS-12_00 ou API-CPF (sem bônus)
            tipo_saque_upper = self.config.game.tipo_saque.upper()
            if tem_bonus and bet_maxima > 0:
                tipopix = f"API-{tipo_saque_upper}-BONUS-{bet_maxima_fmt}"
            else:
                tipopix = f"API-{tipo_saque_upper}"
            
            # Monta URL com token
            separator = "&" if "?" in result.url else "/?"
            url_completa = f"{result.url}{separator}_ti={result.token_login}"
            
            # Proxy string
            proxy_str = "SEM PROXY"
            if self.config.proxy and self.config.proxy.usar_proxy:
                proxy_str = f"{self.config.proxy.host}:{self.config.proxy.port}"
            
            # Monta os parâmetros conforme esperado pela API
            params = {
                "apikey": self.config.flash_api_key,
                "url": url_completa,
                "usuario": result.usuario.strip(),
                "senha": result.senha.strip(),
                "saque": result.senha_saque.strip(),
                "tipopix": tipopix,
                "pix": result.pix.strip() if result.pix else "",
                "saldo": f"{result.saldo:.2f}",
                "nome": result.nome_completo.strip() if result.nome_completo else "",
                "celular": result.telefone.strip() if result.telefone else "",
                "email": result.email.strip() if result.email else "",
                "proxy": proxy_str
            }

            response = requests.post(
                self.config.flash_api_url,
                data=params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )
        except Exception as e:
            debug_log(f"[{self.usuario}] Erro ao enviar para API FlashBot: {e}")


async def run_bot(config: BotConfig) -> AccountData:
    """Executa um bot com a configuração dada"""
    bot = Bot(config)
    return await bot.executar()


# ==================== EXECUÇÃO DIRETA ====================
# py bot.py <plataforma> <meta>
# py bot.py 707bet 100

if __name__ == "__main__":
    import sys
    import asyncio
    from colorama import init as colorama_init
    from platforms import get_platform_by_name
    
    colorama_init()
    
    # Configura logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    
    def print_usage():
        print(f"""
{Fore.CYAN}Uso:{Style.RESET_ALL}
    py bot.py <plataforma> <meta>

{Fore.CYAN}Exemplos:{Style.RESET_ALL}
    py bot.py 707bet 100      # Plataforma 707bet, meta R$ 100
    py bot.py 587bet 50       # Plataforma 587bet, meta R$ 50
    py bot.py 148bet 200      # Plataforma 148bet, meta R$ 200

{Fore.CYAN}Opções:{Style.RESET_ALL}
    --gem-trava       Ativa modo Gem Trava (tenta travar bônus)
    --hood-trava      Ativa modo Hood vs Wolf Trava
    --no-proxy        Desativa proxy
    --debug           Ativa logs detalhados
""")
    
    async def main_cli():
        args = sys.argv[1:]
        
        if len(args) < 2:
            print_usage()
            return 1
        
        # Parse argumentos
        platform_name = args[0]
        
        try:
            meta = float(args[1])
        except ValueError:
            print(f"{Fore.RED}Erro: Meta deve ser um número (ex: 100){Style.RESET_ALL}")
            return 1
        
        # Opções extras
        gem_trava = "--gem-trava" in args
        hood_trava = "--hood-trava" in args
        no_proxy = "--no-proxy" in args
        debug = "--debug" in args
        
        if debug:
            runtime_config["DEBUG_MODE"] = True
        
        # Busca plataforma
        platform = get_platform_by_name(platform_name)
        if not platform:
            print(f"{Fore.RED}Erro: Plataforma '{platform_name}' não encontrada{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Use: py main.py --list-platforms{Style.RESET_ALL}")
            return 1
        
        print(f"""
{Fore.CYAN}═══════════════════════════════════════════════════{Style.RESET_ALL}
  {Fore.GREEN}BOT INICIADO{Style.RESET_ALL}
{Fore.CYAN}═══════════════════════════════════════════════════{Style.RESET_ALL}
  Plataforma:  {Fore.YELLOW}{platform.name}{Style.RESET_ALL}
  URL:         {platform.site}
  Meta:        {Fore.GREEN}R$ {meta:.2f}{Style.RESET_ALL}
  Gem Trava:   {Fore.GREEN if gem_trava else Fore.RED}{'Ativo' if gem_trava else 'Inativo'}{Style.RESET_ALL}
  Hood Trava:  {Fore.GREEN if hood_trava else Fore.RED}{'Ativo' if hood_trava else 'Inativo'}{Style.RESET_ALL}
  Proxy:       {Fore.RED if no_proxy else Fore.GREEN}{'Desativado' if no_proxy else 'Ativo'}{Style.RESET_ALL}
{Fore.CYAN}═══════════════════════════════════════════════════{Style.RESET_ALL}
""")
        
        # Configura bot
        from config import BotConfig, GameConfig, GeeTokenConfig, ProxyConfig
        
        bot_config = BotConfig(
            url=platform.site,
            platform_name=platform.name,
            save_to_db=False,
            proxy=ProxyConfig(usar_proxy=not no_proxy),
            gee_token=GeeTokenConfig(
                enabled=platform.gee_token,
                individual=True,
            ),
            game=GameConfig(
                subir_banca=meta,
                tipo_saque="telefone",
                gem_trava=gem_trava,
                hood_trava=hood_trava,
            ),
        )
        
        # Verifica proxy
        if bot_config.proxy.usar_proxy:
            print(f"Verificando proxy...")
            sucesso, ip, msg = bot_config.proxy.verificar_proxy(timeout=10)
            if sucesso:
                print(f"{Fore.GREEN}Proxy OK - IP: {ip}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}Proxy OFFLINE: {msg}{Style.RESET_ALL}")
                return 1
        
        # Executa bot
        print(f"\nIniciando conta...\n")
        result = await run_bot(bot_config)
        
        # Resultado
        print(f"""
{Fore.CYAN}═══════════════════════════════════════════════════{Style.RESET_ALL}
  {Fore.GREEN if result.success else Fore.RED}RESULTADO{Style.RESET_ALL}
{Fore.CYAN}═══════════════════════════════════════════════════{Style.RESET_ALL}""")
        
        if result.success:
            print(f"""
  Usuario:     {Fore.YELLOW}{result.usuario}{Style.RESET_ALL}
  Senha:       {result.senha}
  Senha Saque: {result.senha_saque}
  PIX:         {result.pix}
  Bonus:       {Fore.GREEN}R$ {result.bonus:.2f}{Style.RESET_ALL}
  Saldo:       {Fore.GREEN}R$ {result.saldo:.2f}{Style.RESET_ALL}
  Travou:      {Fore.GREEN if result.bonus_travado else Fore.RED}{'SIM' if result.bonus_travado else 'NAO'}{Style.RESET_ALL}
""")
        else:
            print(f"""
  {Fore.RED}Erro: {result.error}{Style.RESET_ALL}
""")
        
        print(f"{Fore.CYAN}═══════════════════════════════════════════════════{Style.RESET_ALL}")
        
        return 0 if result.success else 1
    
    exit_code = asyncio.run(main_cli())
    sys.exit(exit_code)
