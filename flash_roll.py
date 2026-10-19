#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Executa lista de jogos PG aleatórios
"""

import os
import sys
import json
import time
import random
import hashlib
import base64
import struct
import secrets
import uuid
import requests
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import logging
import re

logger = logging.getLogger(__name__)


# ============================================
# CLASSES
# ============================================

class SimpleMsgPack:
    """Decodificador MessagePack simplificado"""
    
    def __init__(self, data: bytes):
        self.buffer = data
        self.pos = 0
        self.length = len(data)
    
    def unpack(self):
        if self.pos >= self.length:
            return None
        
        byte = self.buffer[self.pos]
        self.pos += 1
        
        # nil
        if byte == 0xc0:
            return None
        # false
        if byte == 0xc2:
            return False
        # true
        if byte == 0xc3:
            return True
        # Positive fixint (0x00 - 0x7f)
        if byte <= 0x7f:
            return byte
        # Fixmap (0x80 - 0x8f)
        if 0x80 <= byte <= 0x8f:
            n = byte - 0x80
            result = {}
            for _ in range(n):
                key = self.unpack()
                val = self.unpack()
                result[key] = val
            return result
        # Fixarray (0x90 - 0x9f)
        if 0x90 <= byte <= 0x9f:
            n = byte - 0x90
            return [self.unpack() for _ in range(n)]
        # Fixstr (0xa0 - 0xbf)
        if 0xa0 <= byte <= 0xbf:
            n = byte - 0xa0
            return self.read_bytes(n)
        # str 8
        if byte == 0xd9:
            n = self.buffer[self.pos]
            self.pos += 1
            return self.read_bytes(n)
        # str 16
        if byte == 0xda:
            n = self.read_uint(2)
            return self.read_bytes(n)
        # str 32
        if byte == 0xdb:
            n = self.read_uint(4)
            return self.read_bytes(n)
        # bin 8
        if byte == 0xc4:
            n = self.buffer[self.pos]
            self.pos += 1
            return self.read_bin(n)
        # bin 16
        if byte == 0xc5:
            n = self.read_uint(2)
            return self.read_bin(n)
        # bin 32
        if byte == 0xc6:
            n = self.read_uint(4)
            return self.read_bin(n)
        # float 32
        if byte == 0xca:
            return self.read_float32()
        # float 64
        if byte == 0xcb:
            return self.read_float64()
        # uint 8
        if byte == 0xcc:
            return self.read_uint(1)
        # uint 16
        if byte == 0xcd:
            return self.read_uint(2)
        # uint 32
        if byte == 0xce:
            return self.read_uint(4)
        # uint 64
        if byte == 0xcf:
            return self.read_uint(8)
        # int 8
        if byte == 0xd0:
            return self.read_int(1)
        # int 16
        if byte == 0xd1:
            return self.read_int(2)
        # int 32
        if byte == 0xd2:
            return self.read_int(4)
        # int 64
        if byte == 0xd3:
            return self.read_int(8)
        # array 16
        if byte == 0xdc:
            n = self.read_uint(2)
            return [self.unpack() for _ in range(n)]
        # array 32
        if byte == 0xdd:
            n = self.read_uint(4)
            return [self.unpack() for _ in range(n)]
        # map 16
        if byte == 0xde:
            n = self.read_uint(2)
            result = {}
            for _ in range(n):
                key = self.unpack()
                val = self.unpack()
                result[key] = val
            return result
        # map 32
        if byte == 0xdf:
            n = self.read_uint(4)
            result = {}
            for _ in range(n):
                key = self.unpack()
                val = self.unpack()
                result[key] = val
            return result
        # Negative fixint (0xe0 - 0xff)
        if 0xe0 <= byte <= 0xff:
            return byte - 256
        
        return f"Unknown Type: {hex(byte)}"
    
    def read_bytes(self, n: int) -> str:
        data = self.buffer[self.pos:self.pos + n]
        self.pos += n
        try:
            return data.decode('utf-8')
        except:
            return data.hex()
    
    def read_bin(self, n: int) -> bytes:
        data = self.buffer[self.pos:self.pos + n]
        self.pos += n
        return data
    
    def read_uint(self, num_bytes: int) -> int:
        value = 0
        for _ in range(num_bytes):
            value = value * 256 + self.buffer[self.pos]
            self.pos += 1
        return value
    
    def read_int(self, num_bytes: int) -> int:
        value = 0
        first = True
        for _ in range(num_bytes):
            b = self.buffer[self.pos]
            self.pos += 1
            if first:
                value += (b & 127)
                if b & 128:
                    value -= 128
                first = False
            else:
                value *= 256
                value += b
        return value
    
    def read_float32(self) -> float:
        data = self.buffer[self.pos:self.pos + 4]
        self.pos += 4
        return struct.unpack('>f', data)[0]
    
    def read_float64(self) -> float:
        data = self.buffer[self.pos:self.pos + 8]
        self.pos += 8
        return struct.unpack('>d', data)[0]


class Browser:
    """Classe para fazer requisições HTTP"""
    
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        self.cookie_file = None
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 5
        self.referer = None
        self.session = requests.Session()
        self.session.verify = False
        
        # Desabilitar warnings de SSL
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def open(self, url: str, data: dict = None) -> str:
        """
        Faz requisição HTTP com retry automático
        
        Args:
            url: URL para requisição
            data: Dicionário com opções:
                - headers: Lista de headers
                - post: Dados para POST
                - header: Se True, retorna headers também
                - http: Se True, retorna info completa
                - follow: Se True, segue redirects
                - proxy: Proxy para usar
        """
        if data is None:
            data = {}
        
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Accept-Encoding': 'gzip, deflate, br',
            'User-Agent': self.user_agent
        }
        
        # Adicionar headers customizados
        if data.get('headers'):
            if isinstance(data['headers'], list):
                for h in data['headers']:
                    if ':' in h:
                        key, val = h.split(':', 1)
                        headers[key.strip()] = val.strip()
            elif isinstance(data['headers'], dict):
                headers.update(data['headers'])
        
        # Referer
        if data.get('referer') or self.referer:
            headers['Referer'] = data.get('referer') or self.referer
        
        # Proxy
        proxies = None
        if data.get('proxy'):
            proxies = {
                'http': data['proxy'],
                'https': data['proxy']
            }
        
        # Loop de retry
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if data.get('post'):
                    post_data = data['post']
                    # Se os dados são uma string URL-encoded, definir Content-Type apropriado
                    if isinstance(post_data, str) and '=' in post_data and 'Content-Type' not in headers:
                        headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    
                    response = self.session.post(
                        url,
                        data=post_data,
                        headers=headers,
                        timeout=self.timeout,
                        allow_redirects=data.get('follow', False),
                        proxies=proxies
                    )
                else:
                    response = self.session.get(
                        url,
                        headers=headers,
                        timeout=self.timeout,
                        allow_redirects=data.get('follow', False),
                        proxies=proxies
                    )
                
                result = response.text.strip()
                
                if data.get('http'):
                    return {
                        'info': {
                            'http_code': response.status_code,
                            'url': response.url,
                            'content_type': response.headers.get('Content-Type', '')
                        },
                        'response': result
                    }
                
                return result
                
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    print(f"Erro na requisição (tentativa {attempt}/{self.max_retries}): {e}")
                    print(f"Aguardando {self.retry_delay}s para tentar novamente...")
                    time.sleep(self.retry_delay)
                else:
                    print(f"Erro na requisição (tentativa {attempt}/{self.max_retries}): {e}")
        
                print(f"Falha após {self.max_retries} tentativas")
        return ""


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


# Chave de criptografia para config
CONFIG_KEY_B64 = "REVGQVVMVF9LRVlfQjY0"  # DEFAULT_KEY_B64


def decrypt_b64_aes128_ecb(ciphertext: str, key_b64: str) -> str:
    """Descriptografa texto em base64 com AES-128-ECB"""
    from Crypto.Cipher import AES
    import base64
    
    key = base64.b64decode(key_b64)
    cipher = AES.new(key, AES.MODE_ECB)
    
    # Decodifica o ciphertext de base64
    encrypted_data = base64.b64decode(ciphertext)
    
    # Descriptografa
    decrypted = cipher.decrypt(encrypted_data)
    
    # Remove padding PKCS7
    padding_len = decrypted[-1]
    decrypted = decrypted[:-padding_len]
    
    return decrypted.decode('utf-8')


class AsyncHttpClient:
    """Cliente HTTP assíncrono simples para compatibilidade"""
    
    def __init__(self, proxy: str = None):
        self.proxy = proxy
        self.session = None
    
    async def get(self, url: str, use_proxy: bool = False, timeout: int = 30, max_retries: int = 3):
        """Faz requisição GET assíncrona"""
        # pyrefly: ignore [missing-import]
        import aiohttp
        
        proxies = self.proxy if use_proxy and self.proxy else None
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, proxy=proxies, timeout=aiohttp.ClientTimeout(total=timeout), ssl=False) as response:
                        text = await response.text()
                        return type('Response', (), {'status_code': response.status, 'text': text})()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(1)
    
    async def close(self):
        """Fecha a sessão"""
        pass


async def _test_fastest_domain_standalone(
    http: 'AsyncHttpClient',
    domains: list,
    test_path: str = "/",
    label: str = "API",
    rounds: int = 10
) -> Optional[str]:
    """Testa múltiplos domínios em paralelo e retorna o mais rápido (standalone)"""
    if not domains:
        return None

    if len(domains) == 1:
        return domains[0]

    logging.info(f"[CONFIG] === Testando {len(domains)} {label}s ({rounds}x cada) ===")

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
        logging.info(f"[CONFIG] Round {round_num}/{rounds}...")

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

    logging.info(f"[CONFIG] --- Resultados (média de {rounds} testes) ---")

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
        logging.info(f"[CONFIG] {marker} AVG:{avg_str} | MIN:{min_str} | MAX:{max_str} | ({status}){fail_info} {domain}")

    if fastest:
        logging.info(f"[CONFIG] >> Selecionada: {fastest} (média: {fastest_avg*1000:.0f}ms)")
    else:
        logging.info(f"[CONFIG] !! Nenhuma {label} respondeu!")

    return fastest


async def _fetch_platform_config_standalone(url: str, proxy: str = None) -> Optional[PlatformConfig]:
    """Busca config da plataforma sem cache (standalone)"""

    http = AsyncHttpClient(proxy)

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
            logging.info(f"[CONFIG] InviterId: {inviter_id}")

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
        logger.error(f"[CONFIG] Erro ao obter config: {e}")
        return None
    finally:
        try:
            await http.close()
        except:
            pass


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def is_json(string: str):
    """Verifica se string é JSON válido e retorna o objeto decodificado"""
    try:
        return json.loads(string)
    except (json.JSONDecodeError, TypeError):
        return False


def generate_key(token: str, username: str) -> str:
    """Gera chave de criptografia"""
    return hashlib.md5((token + username).encode()).hexdigest()[:16]


def generate_random_key() -> str:
    """Gera chave aleatória com prefixo GEE3-01-"""
    prefix = 'GEE3-01-'
    random_hex = secrets.token_hex(32)
    return prefix + random_hex


def codigo_pg() -> str:
    """Gera código PG aleatório (6 letras + dia do mês)"""
    letras = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    resultado = ''.join(random.choice(letras) for _ in range(6))
    return resultado + str(datetime.now().day)


def set_headers(data: dict) -> list:
    """Converte dicionário de headers para lista"""
    return [f"{key}: {value}" for key, value in data.items()]


def flash_headers(host: str, device_id: str, device_model: dict, 
                  url: str, sitecode: str, speed_version: str, 
                  android_version: str, mode: str = 'chipher', 
                  session_key: str = None, account: dict = None) -> dict:
    """Gera headers para requisições flash"""
    
    if account is None:
        account = {}
    
    formatters = {
        "Apple": lambda d: d["nome"],
        "Samsung": lambda d: f"{d['marca']} {d['modelo']}",
        "Motorola": lambda d: d["nome"],
    }
    
    marca = device_model.get("marca", "Samsung")
    formatter = formatters.get(marca, lambda d: f"{d['marca']} {d['modelo']}")
    dispositivo = formatter(device_model)
    
    sistema = 'iOS' if marca == 'Apple' else 'Android'
    modelo = device_model.get("modelo", "SM-G991B")
    
    # User-Agent dinâmico
    if marca == 'Apple':
        user_agent = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    else:
        user_agent = f'Mozilla/5.0 (Linux; Android {android_version}; {modelo}) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/131.0.6778.205 Mobile Safari/537.36'
    
    # Timestamp e nonce
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    
    # Sign = md5(timestamp + nonce + session_key)
    sign_str = f"{timestamp}{nonce}{session_key or ''}"
    sign = hashlib.md5(sign_str.encode()).hexdigest()
    
    # physicaldevicemodel com marca minúscula
    physical_model = f"{marca.lower()} {modelo}"
    
    return {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'pt',
        'appsystem': 'iOS 17' if marca == 'Apple' else f'Android {android_version}',
        'appversion': speed_version,
        'browserfingerid': '',
        'browsertype': 'Android Browser v4.0',
        'clienttimezone': '-3',
        'content-type': 'text/plain',
        'currency': 'BRL',
        'device': device_id,
        'devicebrand': marca,
        'devicemodel': dispositivo,
        'devicetype': '3',
        'domain': host,
        'language': 'pt',
        'nonce': nonce,
        'operatingsystem': sistema,
        'origin': url,
        'physicaldevicemodel': physical_model,
        'platformtype': '5',
        'referer': url,
        'sitecode': str(sitecode),
        'timestamp': timestamp,
        'token': session_key or '',
        'sign': sign,
        'auth': account.get('userkey', ''),
        'newjwt': account.get('jwt_token', ''),
        'user-agent': user_agent,
        'x-custom-referer': url,
        'x-data-mode': mode,
        'x-device': '2-3',
        'x-request-id': str(uuid.uuid4()),
        'x-version': '6.1.130'
    }


def buscar_jogo_pg_por_nome(nome_busca: str) -> list:
    """Busca jogo PG por nome (case insensitive)"""
    
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(script_dir, "jogospg.json")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'data' not in data or 'g1' not in data['data']:
            return []
        
        lista = data['data']['g1']
        
        # Busca case insensitive
        nome_busca_lower = nome_busca.lower().strip()
        encontrados = [
            jogo for jogo in lista 
            if nome_busca_lower in jogo.get('g1', '').lower()
        ]
        
        if not encontrados:
            print(f"Nenhum jogo encontrado com '{nome_busca}'")
            return []
        
        timestamp = int(time.time())
        resultado = []
        
        for jogo in encontrados:
            if not all(k in jogo for k in ['g1', 'g0', 'g10']):
                continue
            resultado.append({
                "name": jogo['g1'],
                "gameid": jogo['g0'],
                "platfromid": jogo['g10'],
                "os_type": 2,
                "exitUrl": "",
                "time": timestamp
            })
        
        print(f"Encontrados {len(resultado)} jogo(s) com '{nome_busca}':")
        for r in resultado:
            print(f"  - {r['name']} (ID: {r['gameid']})")
        
        return resultado
        
    except FileNotFoundError:
        print("Arquivo jogospg.json não encontrado")
        return []
    except json.JSONDecodeError:
        print("Erro ao decodificar jogospg.json")
        return []


def buscar_jogo_pg_aleatorio(quantidade: int) -> list:
    """Busca jogos PG aleatórios do arquivo JSON"""
    
    # Palavras bloqueadas no nome do jogo
    palavras_bloqueadas = ['Gem S']
    
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(script_dir, "jogospg.json")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'data' not in data or 'g1' not in data['data']:
            return []
        
        lista = data['data']['g1']
        
        # Filtrar jogos com palavras bloqueadas
        lista = [jogo for jogo in lista if not any(
            palavra.lower() in jogo.get('g1', '').lower() 
            for palavra in palavras_bloqueadas
        )]
        
        total = len(lista)
        
        if total == 0:
            return [{"erro": "Lista de jogos vazia"}]
        
        quantidade = min(quantidade, total)
        random.shuffle(lista)
        selecionados = lista[:quantidade]
        
        timestamp = int(time.time())
        resultado = []
        
        for jogo in selecionados:
            if not all(k in jogo for k in ['g1', 'g0', 'g10']):
                continue
            
            resultado.append({
                "name": jogo["g1"],
                "os_type": 2,
                "gameid": jogo["g0"],
                "platfromid": jogo["g10"],
                "exitUrl": "",
                "time": timestamp
            })
        
        return resultado
        
    except FileNotFoundError:
        print("Arquivo jogospg.json não encontrado")
        return []
    except json.JSONDecodeError:
        print("Erro ao decodificar jogospg.json")
        return []


def extract_value(string: str) -> Optional[str]:
    """Extrai valor do payload codificado ou retorna a string se for uma URL direta"""
    if not string:
        return None
        
    # Se já parece uma URL direta, retorna ela mesma para processamento posterior
    if string.startswith("http"):
        return string
        
    # Tenta padrões conhecidos de JS obfuscado
    start_patterns = [')}})("', '})("', ')("', '("']
    end_pattern = '")}();'
    
    for start_pattern in start_patterns:
        start_index = string.find(start_pattern)
        end_index = string.find(end_pattern)
        
        if start_index != -1 and end_index != -1:
            start = start_index + len(start_pattern)
            return string[start:end_index]
            
    # Se não encontrou padrão de JS mas a string é bem longa e parece base64, retorna ela
    if len(string) > 100 and not string.startswith("http"):
        return string
        
    return None


def decode_payload(base64_payload: str):
    """Decodifica payload base64 MessagePack"""
    binary_data = base64.b64decode(base64_payload)
    decoder = SimpleMsgPack(binary_data)
    return decoder.unpack()


def extract_options_pg(data) -> dict:
    """Extrai opções do jogo PG dos dados decodificados"""
    
    def find_url(arr):
        if not isinstance(arr, (list, dict)):
            return None
        
        items = arr.values() if isinstance(arr, dict) else arr
        
        for v in items:
            if isinstance(v, (list, dict)):
                result = find_url(v)
                if result is not None:
                    return result
            elif isinstance(v, str) and 'ot=' in v:
                return v
        
        return None
    
    if isinstance(data, str) and ('ot=' in data or 'ops=' in data):
        url = data
    else:
        url = find_url(data)
    
    if url is None:
        return {
            'url': None,
            'host': None,
            'idGame': None,
            'params': {}
        }
    
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path
    segments = [s for s in path.strip('/').split('/') if s]
    id_game = segments[0] if segments else None
    
    # Extrair parâmetros da query (?...)
    params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
    
    # Extrair parâmetros do fragmento (#...) e mesclar
    if parsed.fragment:
        fragment_params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.fragment).items()}
        params.update(fragment_params)
        
    # Mapeamento de nomes alternativos para 'ot' se ele não existir
    if not params.get("ot"):
        for alt in ["token", "tk", "otk", "accessToken"]:
            if params.get(alt):
                params["ot"] = params[alt]
                break
    
    return {
        'url': url,
        'host': host,
        'idGame': id_game,
        'params': params
    }


def limpar_nome_arquivo(nome: str) -> str:
    """Remove caracteres especiais do nome para usar em arquivo"""
    import re
    # Substituir espaços por underscore e remover caracteres especiais
    nome_limpo = re.sub(r'[^\w\-]', '_', nome)
    # Remover underscores múltiplos
    nome_limpo = re.sub(r'_+', '_', nome_limpo)
    # Remover underscores no início e fim
    nome_limpo = nome_limpo.strip('_')
    # Limitar tamanho
    return nome_limpo[:30]


# ============================================
# MENU
# ============================================

def limpar_tela():
    """Limpa a tela do terminal"""
    os.system('cls' if os.name == 'nt' else 'clear')


def mostrar_menu():
    """Exibe menu e retorna configurações escolhidas"""
    
    config = {
        "jogos_min": 5,
        "jogos_max": 15,
        "spin_min": 5,
        "spin_max": 15,
        "zerar_saldo": False,
        "salvar_logs": False,
        "jogo_especifico": None,  # Nome do jogo para busca específica
        "aposta_fixa": 0.0,        # Valor de aposta fixa
        "trava_ativa": False,      # Se True, para ao detectar bônus
        "flash_tour": False        # Modo Flash Tour: 4-7 giros na bet minima, maximo de jogos
    }
    
    opcoes_jogos = {
        '1': (5, 10),
        '2': (5, 15),
        '3': (10, 20),
        '4': (15, 30),
        '5': (30, 50)
    }
    
    opcoes_spins = {
        '1': (5, 10),
        '2': (5, 15),
        '3': (10, 30),
        '4': (30, 80),
        '5': (100, 200)
    }
    
    while True:
        limpar_tela()
        print("\n" + "="*50)
        print("       RODA LISTA PG - CONFIGURACAO")
        print("="*50)
        
        # Mostrar modo de seleção de jogos
        if config['jogo_especifico']:
            jogo_status = f"BUSCA: '{config['jogo_especifico']}'"
        else:
            jogo_status = f"{config['jogos_min']}-{config['jogos_max']} jogos aleatorios"
        
        print(f"\n  Jogos: {jogo_status}")
        print(f"  Spins: {config['spin_min']}-{config['spin_max']} por jogo")
        zerar_status = "ATIVADO" if config['zerar_saldo'] else "DESATIVADO"
        logs_status = "ATIVADO" if config['salvar_logs'] else "DESATIVADO"
        flash_tour_status = "ATIVADO" if config['flash_tour'] else "DESATIVADO"
        print(f"  Zerar saldo: {zerar_status}")
        print(f"  Salvar logs: {logs_status}")
        aposta_status = f"R$ {config['aposta_fixa']:.2f}" if config['aposta_fixa'] > 0 else "ALEATORIA (MINIMA)"
        trava_status = "ATIVADO" if config['trava_ativa'] else "DESATIVADO"
        print(f"  Aposta fixa: {aposta_status}")
        print(f"  Modo Trava: {trava_status}")
        print(f"  Flash Tour: {flash_tour_status}")
        print("\n  [1] Quantidade de jogos (aleatorio)")
        print("  [2] Quantidade de spins por jogo")
        print(f"  [3] Zerar saldo no ultimo jogo [{zerar_status}]")
        print(f"  [4] Salvar logs [{logs_status}]")
        print("  [5] Buscar jogo por nome")
        print(f"  [7] Definir aposta fixa [{aposta_status}]")
        print(f"  [8] Modo Trava (parar no bonus) [{trava_status}]")
        print("  [9] ATALHO: Double Fortune (Trava 12)")
        print("  [10] ATALHO: Ganesha Gold")
        print("  [11] ATALHO: Hood vs Wolf Trava")
        print("  [12] ATALHO: Emperor's Favour")
        print("  [13] ATALHO: Midas Fortune (Trava Scatter)")
        print("  [14] ATALHO: Genie's 3 Wishes (Trava Scatter)")
        print("  [15] ATALHO: Legend of Perseus (Trava Scatter)")
        print("  [16] ATALHO: Honey Trap of Diao Chan (Trava Scatter)")
        print("  [17] ATALHO: Medusa II (2 Vermelhos + 5 Vidas)")
        print(f"  [18] FLASH TOUR (4-7 giros bet minima, maximo jogos) [{flash_tour_status}]")
        print("  [6] INICIAR")
        print("  [0] Sair")
        print("\n" + "="*50)
        
        escolha = input("\n  Escolha uma opcao: ").strip()
        
        if escolha == '0':
            print("\n  Saindo...")
            return None
        
        if escolha == '3':
            config['zerar_saldo'] = not config['zerar_saldo']
            continue
        
        if escolha == '4':
            config['salvar_logs'] = not config['salvar_logs']
            continue
        
        if escolha == '5':
            # Buscar jogo por nome
            limpar_tela()
            print("\n" + "="*50)
            print("       BUSCAR JOGO POR NOME")
            print("="*50)
            print("\n  Digite parte do nome do jogo (case insensitive)")
            print("  Exemplo: 'Gem' encontra 'Gem Saviour', 'Gem Bonanza', etc.")
            print("\n  [0] Voltar (usar jogos aleatorios)")
            print("\n" + "="*50)
            
            nome = input("\n  Nome do jogo: ").strip()
            
            if nome == '0' or nome == '':
                config['jogo_especifico'] = None
            else:
                # Verificar se encontra jogos
                jogos_encontrados = buscar_jogo_pg_por_nome(nome)
                if jogos_encontrados:
                    config['jogo_especifico'] = nome
                    config['jogos_min'] = len(jogos_encontrados)
                    config['jogos_max'] = len(jogos_encontrados)
                    input("\n  Pressione ENTER para continuar...")
                else:
                    config['jogo_especifico'] = None
                    input("\n  Pressione ENTER para continuar...")
            continue
        
        if escolha == '7':
            # Definir aposta fixa
            limpar_tela()
            print("\n" + "="*50)
            print("       DEFINIR APOSTA FIXA")
            print("="*50)
            print(f"\n  Valor atual: R$ {config['aposta_fixa']:.2f}")
            print("\n  Digite o valor da aposta (ex: 12.00 ou 0.40)")
            print("  Digite 0 para usar a aposta minima dos jogos")
            print("\n" + "="*50)
            
            try:
                val_aposta = float(input("\n  Valor R$: ").strip().replace(',', '.'))
                config['aposta_fixa'] = max(0.0, val_aposta)
            except ValueError:
                print("  Valor invalido!")
                time.sleep(1)
            continue
            
        if escolha == '8':
            config['trava_ativa'] = not config['trava_ativa']
            continue
            
        if escolha == '9':
            # Atalho Double Fortune Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: DOUBLE FORTUNE")
            print("="*50)
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 12.00): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 12.00
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Double Fortune"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 5000
            print(f"\n  Configurado: Double Fortune | Bet {bet_val:.2f} | Modo Trava ATIVO")
            time.sleep(2)
            continue
            
        if escolha == '10':
            # Atalho Ganesha Gold
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: GANESHA GOLD")
            print("="*50)
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 0.80): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 0.80
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Ganesha Gold"
            config['aposta_fixa'] = bet_val
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            print(f"\n  Configurado: Ganesha Gold | Bet {bet_val:.2f}")
            time.sleep(1)
            continue
            
        if escolha == '11':
            # Atalho Hood vs Wolf Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: HOOD VS WOLF TRAVA")
            print("="*50)
            
            try:
                bet_val = float(input("\n  Qual valor de aposta inicial? (Ex: 1.20): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 1.20
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Hood vs Wolf"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['modo_hood_wolf_trava'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 10000
            print(f"\n  Configurado: Hood vs Wolf | Bet Inicial {bet_val:.2f} | Modo Trava Hood Wolf")
            time.sleep(2)
            continue
        
        if escolha == '12':
            # Atalho Emperor's Favour
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: EMPEROR'S FAVOUR")
            print("="*50)
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 12.00): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 12.00
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Emperor's Favour"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 5000
            print(f"\n  Configurado: Emperor's Favour | Bet {bet_val:.2f} | Modo Trava ATIVO")
            time.sleep(2)
            continue
        
        if escolha == '13':
            # Atalho Midas Fortune Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: MIDAS FORTUNE")
            print("="*50)
            print("  Para ao detectar 3 scatters (bonus)")
            print("  Aposta mais proxima sera usada se a exata nao existir")
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 12.00): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 12.00
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Midas Fortune"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['modo_scatter_trava'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 5000
            print(f"\n  Configurado: Midas Fortune | Bet {bet_val:.2f} | Modo Trava Scatter ATIVO")
            time.sleep(2)
            continue
        
        if escolha == '14':
            # Atalho Genie's 3 Wishes Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: GENIE'S 3 WISHES")
            print("="*50)
            print("  Para ao detectar 3 scatters (bonus)")
            print("  Aposta mais proxima sera usada se a exata nao existir")
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 12.00): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 12.00
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Genie's 3 Wishes"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['modo_scatter_trava'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 5000
            print(f"\n  Configurado: Genie's 3 Wishes | Bet {bet_val:.2f} | Modo Trava Scatter ATIVO")
            time.sleep(2)
            continue
        
        if escolha == '15':
            # Atalho Legend of Perseus Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: LEGEND OF PERSEUS")
            print("="*50)
            print("  Para ao detectar 3 scatters (bonus)")
            print("  Aposta mais proxima sera usada se a exata nao existir")
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 12.00): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 12.00
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Legend of Perseus"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['modo_scatter_trava'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 5000
            print(f"\n  Configurado: Legend of Perseus | Bet {bet_val:.2f} | Modo Trava Scatter ATIVO")
            time.sleep(2)
            continue
        
        if escolha == '16':
            # Atalho Honey Trap of Diao Chan Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: HONEY TRAP OF DIAO CHAN")
            print("="*50)
            print("  Para ao detectar 3 scatters (bonus)")
            print("  Aposta mais proxima sera usada se a exata nao existir")
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 12.00): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 12.00
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Honey Trap of Diao Chan"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['modo_scatter_trava'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 5000
            print(f"\n  Configurado: Honey Trap of Diao Chan | Bet {bet_val:.2f} | Modo Trava Scatter ATIVO")
            time.sleep(2)
            continue
        
        if escolha == '17':
            # Atalho Medusa II Trava
            limpar_tela()
            print("\n" + "="*50)
            print("       ATALHO: MEDUSA II")
            print("="*50)
            print("  Para ao detectar 2+ pedras vermelhas (ssc>=2)")
            print("  E acumular 5+ vidas azuis (msb>=5)")
            
            try:
                bet_val = float(input("\n  Qual valor de aposta deseja usar? (Ex: 0.01): ").strip().replace(',', '.'))
            except ValueError:
                bet_val = 0.01
                print(f"  Valor invalido! Usando padrao: R$ {bet_val:.2f}")
                time.sleep(1)
                
            config['jogo_especifico'] = "Medusa II"
            config['aposta_fixa'] = bet_val
            config['trava_ativa'] = True
            config['modo_medusa_trava'] = True
            config['jogos_min'] = 1
            config['jogos_max'] = 1
            config['spin_min'] = 1000
            config['spin_max'] = 10000
            print(f"\n  Configurado: Medusa II | Bet {bet_val:.2f} | Modo Trava ATIVO (2 Vermelhos + 5 Vidas)")
            time.sleep(2)
            continue
        
        if escolha == '18':
            # Modo Flash Tour: giros na bet minima, maximo de jogos
            limpar_tela()
            print("\n" + "="*50)
            print("       MODO FLASH TOUR")
            print("="*50)
            print("  Entra em um monte de jogos diferentes")
            print("  Faz poucos giros na aposta MINIMA (rapido)")
            print("  Muda de jogo automaticamente")
            print("  Objetivo: cobrir o maximo de jogos possivel")
            print("\n--- QUANTIDADE DE JOGOS ---")
            print("  [1] 30-50 jogos (rapido)")
            print("  [2] 50-100 jogos (medio)")
            print("  [3] 100-200 jogos (longo)")
            print("  [4] Personalizado")
            print("  [0] Cancelar")
            print("\n" + "="*50)
            
            sub = input("\n  Escolha quantidade de jogos: ").strip()
            
            qtd_map = {
                '1': (30, 50),
                '2': (50, 100),
                '3': (100, 200)
            }
            
            if sub == '0':
                continue
            elif sub in qtd_map:
                jmin, jmax = qtd_map[sub]
            elif sub == '4':
                try:
                    jmin = int(input("  Minimo de jogos: ").strip())
                    jmax = int(input("  Maximo de jogos: ").strip())
                    if jmin > jmax or jmin < 1:
                        print("  Valores invalidos!")
                        time.sleep(1)
                        continue
                except ValueError:
                    print("  Valores invalidos!")
                    time.sleep(1)
                    continue
            else:
                print("  Opcao invalida!")
                time.sleep(1)
                continue
            
            # Perguntar quantidade de giros por jogo
            print("\n--- GIROS POR JOGO ---")
            print("  [1] 1-3 giros (ultra rapido)")
            print("  [2] 4-7 giros (padrao)")
            print("  [3] 5-10 giros")
            print("  [4] 10-15 giros")
            print("  [5] Personalizado")
            print("\n" + "="*50)
            
            sub_spin = input("\n  Escolha giros por jogo: ").strip()
            
            spin_map = {
                '1': (1, 3),
                '2': (4, 7),
                '3': (5, 10),
                '4': (10, 15)
            }
            
            if sub_spin in spin_map:
                smin, smax = spin_map[sub_spin]
            elif sub_spin == '5':
                try:
                    smin = int(input("  Giros minimo por jogo: ").strip())
                    smax = int(input("  Giros maximo por jogo: ").strip())
                    if smin < 1 or smax < smin:
                        print("  Valores invalidos! Usando 4-7.")
                        smin, smax = 4, 7
                except ValueError:
                    print("  Valores invalidos! Usando 4-7.")
                    smin, smax = 4, 7
            else:
                # Padrao 4-7
                smin, smax = 4, 7
            
            # Ativar Flash Tour
            config['flash_tour'] = True
            config['jogos_min'] = jmin
            config['jogos_max'] = jmax
            config['spin_min'] = smin
            config['spin_max'] = smax
            config['aposta_fixa'] = 0.0  # Sempre bet minima
            config['trava_ativa'] = False
            config['jogo_especifico'] = None
            print(f"\n  Flash Tour ATIVADO: {jmin}-{jmax} jogos, {smin}-{smax} giros cada, bet minima, SEM espera entre spins")
            time.sleep(2)
            continue
        
        
        if escolha == '6':
            return config
        
        if escolha == '1':
            limpar_tela()
            print("\n" + "="*50)
            print("       QUANTIDADE DE JOGOS (ALEATORIO)")
            print("="*50)
            print("\n  [1] 5-10 jogos")
            print("  [2] 5-15 jogos (padrao)")
            print("  [3] 10-20 jogos")
            print("  [4] 15-30 jogos")
            print("  [5] 30-50 jogos")
            print("  [6] Personalizado")
            print("  [0] Voltar")
            print("\n" + "="*50)
            
            while True:
                sub = input("\n  Escolha: ").strip()
                
                if sub == '0':
                    break
                
                if sub in opcoes_jogos:
                    config["jogos_min"], config["jogos_max"] = opcoes_jogos[sub]
                    break
                
                if sub == '6':
                    while True:
                        try:
                            jogos_min = int(input("  Jogos minimo (1-500): ").strip())
                            jogos_max = int(input("  Jogos maximo (1-500): ").strip())
                            if 1 <= jogos_min <= 500 and 1 <= jogos_max <= 500 and jogos_min <= jogos_max:
                                config["jogos_min"] = jogos_min
                                config["jogos_max"] = jogos_max
                                break
                            print("  Valores invalidos. Min deve ser <= Max, ambos entre 1 e 500")
                        except ValueError:
                            print("  Digite numeros validos")
                    break
                
                print("  Opcao invalida!")
            continue
        
        if escolha == '2':
            limpar_tela()
            print("\n" + "="*50)
            print("       QUANTIDADE DE SPINS POR JOGO")
            print("="*50)
            print("\n  [1] 5-10 spins")
            print("  [2] 5-15 spins (padrao)")
            print("  [3] 10-30 spins")
            print("  [4] 30-80 spins")
            print("  [5] 100-200 spins")
            print("  [6] Personalizado")
            print("  [0] Voltar")
            print("\n" + "="*50)
            
            while True:
                sub = input("\n  Escolha: ").strip()
                
                if sub == '0':
                    break
                
                if sub in opcoes_spins:
                    config["spin_min"], config["spin_max"] = opcoes_spins[sub]
                    break
                
                if sub == '6':
                    while True:
                        try:
                            spin_min = int(input("  Spin minimo (1-10000): ").strip())
                            spin_max = int(input("  Spin maximo (1-10000): ").strip())
                            if 1 <= spin_min <= 10000 and 1 <= spin_max <= 10000 and spin_min <= spin_max:
                                config["spin_min"] = spin_min
                                config["spin_max"] = spin_max
                                break
                            print("  Valores invalidos. Min deve ser <= Max, ambos entre 1 e 10000")
                        except ValueError:
                            print("  Digite numeros validos")
                    break
                
                print("  Opcao invalida!")
            continue
        
        print("  Opcao invalida!")
        time.sleep(1)
    
    return config

def uuid4() -> str:
    """Gera UUID v4"""
    data = secrets.token_bytes(16)
    data = bytearray(data)
    data[6] = (data[6] & 0x0f) | 0x40
    data[8] = (data[8] & 0x3f) | 0x80
    hex_str = data.hex()
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"
    
# PROGRAMA PRINCIPAL
# ============================================

def executar(config):
    """Executa o processo com a configuração fornecida"""
    
    jogos_min = config["jogos_min"]
    jogos_max = config["jogos_max"]
    max_jogos = random.randint(jogos_min, jogos_max)  # Quantidade aleatória de jogos
    spin_min = config["spin_min"]
    spin_max = config["spin_max"]
    zerar_saldo = config["zerar_saldo"]
    salvar_logs = config["salvar_logs"]
    aposta_fixa = config.get("aposta_fixa", 0.0)
    trava_ativa = config.get("trava_ativa", False)
    flash_tour = config.get("flash_tour", False)
    modo_hood_wolf_trava = config.get("modo_hood_wolf_trava", False)
    modo_scatter_trava = config.get("modo_scatter_trava", False)  # Trava apenas por scatter (sc>=3), ignora tb==0
    modo_medusa_trava = config.get("modo_medusa_trava", False)   # Trava Medusa II: 2+ vermelhos (ssc>=2) E 5+ vidas (msb>=5)
    modo_dragon_trava = config.get("modo_dragon_trava", False)
    bets_armadas = []
    
    zerar_status = "SIM" if zerar_saldo else "NAO"
    logs_status = "SIM" if salvar_logs else "NAO"
    aposta_status = f"R$ {aposta_fixa:.2f}" if aposta_fixa > 0 else "ALEATORIA"
    trava_status = "SIM" if trava_ativa else "NAO"
    flash_status = "SIM" if flash_tour else "NAO"
    print(f"\n  Configuracao final: {max_jogos} jogos, {spin_min}-{spin_max} spins, Zerar saldo: {zerar_status}, Logs: {logs_status}")
    print(f"  Aposta fixa: {aposta_status}, Modo Trava: {trava_status}, Flash Tour: {flash_status}\n")
    
    if flash_tour:
        print(f"  [FLASH TOUR] Modo ativo: {max_jogos} jogos, {spin_min}-{spin_max} giros na BET MINIMA por jogo")
        print(f"  [FLASH TOUR] Jogando o maximo de jogos possiveis!\n")
    
    # ════════════════════════════════════════
    # CONFIGURAÇÕES DA CONTA (edite aqui)
    # ════════════════════════════════════════
    host            = "zf.jogar580.com"
    url             = "https://d2s5w54tmkgk2g.cloudfront.net"
    usuario         = "785627769"
    device_id       = "7fd21259-d1e2-458f-8bcf-b0f385763fba"
    login_id        = "873b4a69c85cd77ef6331783550342514444810"
    device_model    = {'marca': 'Samsung', 'modelo': 'SM-A546E', 'nome': 'Samsung SM-A546E'}
    data_login      = {
        "userkey":     "",
        "session_key": "10b04896e21c2e045ee71786323594836170709",
        "jwt_token":   ""
    }
    url_domain      = url
    api_url         = f"https://{host}"
    sitecode        = "681"
    speed_version   = "1.1.20"
    app_version     = "7.2.29"
    android_version = "13"
    user_agent      = "Mozilla/5.0 (Linux; Android 13; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6278.25 Mobile Safari/537.36"


    # DEBUG MODE (True para ativar prints de debug)
    DEBUG = False

    # Gerar chave de requisição
    key_request = generate_key(data_login["session_key"], usuario)
    
    # Inicializar navegador
    http = Browser()
    http.user_agent = user_agent
    
    # Criar diretório de cookies se não existir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookies_dir = os.path.join(script_dir, "cookies")
    os.makedirs(cookies_dir, exist_ok=True)
    
    # Contador global de spins para nomes de arquivos
    spin_counter = 0
    session_dir = None
    log_file = None
    session_log = None
    
    # Criar diretório de logs (só se salvar_logs estiver ativado)
    if salvar_logs:
        logs_dir = os.path.join(script_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Criar pasta para esta sessão
        session_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        session_dir = os.path.join(logs_dir, f"session_{session_timestamp}")
        os.makedirs(session_dir, exist_ok=True)
        
        # Arquivo de log principal da sessão
        log_file = os.path.join(session_dir, "session.json")
        
        # Estrutura do log
        session_log = {
            "session_id": session_timestamp,
            "inicio": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "fim": None,
            "config": {
                "jogos_config": f"{jogos_min}-{jogos_max}",
                "jogos_selecionados": max_jogos,
                "spin_min": spin_min,
                "spin_max": spin_max,
                "usuario": usuario
            },
            "estatisticas": {},
            "jogos": []
        }
    
    # SELECIONAR JOGOS
    jogo_especifico = config.get("jogo_especifico")
    if jogo_especifico:
        # Buscar jogo específico por nome
        lista_jogos = buscar_jogo_pg_por_nome(jogo_especifico)
    else:
        # Buscar jogos aleatórios
        lista_jogos = buscar_jogo_pg_aleatorio(max_jogos)
    
    # Mostrar jogos selecionados
    print(f"\n[JOGOS] Selecionados {len(lista_jogos)} jogos")
    if zerar_saldo:
        print(f"[ZERAR SALDO] Spins ilimitados no ULTIMO jogo da lista")
    
    # ESTATÍSTICAS
    tempo_inicio = time.time()
    saldo_inicial = None
    saldo_final = 0.0
    total_spins = 0
    total_ganhos = 0.0
    jogos_executados = 0
    estatisticas_jogos = []  # Lista para rastrear lucro/perda por jogo
    
    print(f"Quantidade de jogos: {len(lista_jogos)} - Start: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    roll = 0.0
    count_jogo = 1
    
    for jogo_pg in lista_jogos:
        print(f"\n{count_jogo}/{len(lista_jogos)} - {jogo_pg['name']}")
        
        # Estatísticas do jogo atual
        saldo_inicio_jogo = None
        saldo_fim_jogo = 0.0
        spins_jogo = 0
        ganhos_jogo = 0.0
        apostado_jogo = 0.0
        
        # Log do jogo atual (só se salvar_logs ativado)
        jogo_log = None
        if salvar_logs:
            jogo_log = {
                "numero": count_jogo,
                "nome": jogo_pg['name'],
                "gameid": jogo_pg.get('gameid'),
                "inicio": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "spins": []
            }
        
        # ETAPA 8 - JOGAR
        # GAME LOGOUT - VER SALDO
        data_logout = json.dumps({
            "os_type": 2,
            "callContext": json.dumps({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "scene": "clean up game; page: game; ifrme: null",
                "stack": json.dumps([
                    "af.apiGameLogout (/assets/theme-0/commonChunk.BQMdnWn5.js)",
                    "nt (/assets/theme-0/index.DTIWZ5aX.js)",
                    "W (/assets/theme-0/index.DTIWZ5aX.js)",
                    "d.logoutAndUpdatePrize (/assets/theme-0/game-opener.impl.CYvNMLtd.js)",
                    "Proxy.<anonymous> (/assets/theme-0/commonChunk.BQMdnWn5.js)"
                ])
            }),
            "time": int(time.time())
        })
        
        headers = flash_headers(
            host, device_id, device_model, url_domain,
            sitecode, speed_version, android_version, 
            "plain", data_login["session_key"], data_login
        )
        
        response = http.open(
            f"{api_url}/hall/api/gameCenter/gameApi/logout",
            {
                "headers": set_headers(headers),
                "header": 0,
                "http": 0,
                "post": data_logout,
                "proxy": ""
            }
        )
        
        data_game_info = is_json(response)
        if data_game_info:
            if data_game_info.get("code") == 1:
                saldo_atual = float(data_game_info.get("data", {}).get("totalGold", 0) or 0)
                
                # Capturar saldo inicial no primeiro jogo
                if saldo_inicial is None:
                    saldo_inicial = saldo_atual
                
                # Capturar saldo inicial deste jogo
                if saldo_inicio_jogo is None:
                    saldo_inicio_jogo = saldo_atual
                
                print(f"Saldo R$: {saldo_atual:.2f}")
            else:
                print(json.dumps({"success": False, "msg": "Erro user info!", "response": response}))
                sys.exit(1)
        else:
            print(json.dumps({"success": False, "msg": "Erro user info!", "response": response}))
            sys.exit(1)
        
        # GAME LOGIN
        post_game_login = jogo_pg.copy()
        post_game_login.pop("name", None)
        post_game_login_str = json.dumps(post_game_login)
        
        headers = flash_headers(
            host, device_id, device_model, url_domain,
            sitecode, speed_version, android_version,
            "plain", data_login["session_key"], data_login
        )
                
        response = http.open(
            f"{api_url}/hall/api/gameCenter/gameApi/login",
            {
                "headers": set_headers(headers),
                "header": 0,
                "http": 0,
                "post": post_game_login_str,
                "proxy": ""
            }
        )
        
        data_game_login = is_json(response)
        if data_game_login:
            if data_game_login.get("code") == 1:
                html_code = extract_value(data_game_login['data']['game_url'])
                
                if not html_code:
                    print(f"Erro: html_code não extraído")
                    continue
                
                # Se html_code começa com http, já é a URL direta
                if html_code.startswith("http"):
                    data_game_login_info = extract_options_pg(html_code)
                    # No caso de URL direta, a API URL é o próprio domínio da URL do jogo
                    parsed_url = urlparse(html_code)
                    api_url_game = f"{parsed_url.scheme}://{parsed_url.netloc}"
                else:
                    try:
                        decoded = decode_payload(html_code)
                        api_url_game = decoded["f"][0]["ad"][0]["v"]
                        if DEBUG:
                            print(f"API URL: {api_url_game}")
                        
                        binary_data = base64.b64decode(html_code)
                        decoder = SimpleMsgPack(binary_data)
                        data_game_decode = decoder.unpack()
                        
                        data_game_login_info = extract_options_pg(data_game_decode)
                    except Exception as e:
                        if DEBUG:
                            print(f"Erro processando payload: {e}")
                            
                        # Tentar extrair opções se o html_code for base64 puro mas não MessagePack
                        data_game_login_info = extract_options_pg(html_code)
                        # Fallback de API URL se falhou o decode do MessagePack
                        if data_game_login_info.get("url"):
                            parsed_url = urlparse(data_game_login_info["url"])
                            api_url_game = f"{parsed_url.scheme}://{parsed_url.netloc}"
                        else:
                            api_url_game = ""

                if not data_game_login_info.get("url"):
                    print(f"Erro: Não foi possível obter parâmetros do jogo")
                    continue
                    
                id_game = data_game_login_info["idGame"]
                
                # Debug: mostrar parâmetros extraídos
                if DEBUG:
                    print(f"DEBUG URL: {data_game_login_info['url']}", flush=True)
                    print(f"DEBUG params: {data_game_login_info['params']}", flush=True)
                    print(f"DEBUG idGame: {id_game}", flush=True)
                
                # Verificar se os parâmetros necessários existem
                params = data_game_login_info.get("params", {})
                ot_value = params.get("ot", "")
                btt_value = params.get("btt", "1")
                ops_value = params.get("ops", "")
                
                if DEBUG:
                    print(f"ot={ot_value}, btt={btt_value}, ops={ops_value}", flush=True)
                
                if not ot_value or ot_value == "":
                    print(f"Erro: Parâmetro 'ot' vazio ou não encontrado")
                    print(f"URL detectada: {html_code[:100]}...") # Mostrar começo da URL para diagnóstico
                    if DEBUG:
                        print(f"Parâmetros: {params}")
                    continue
                
            else:
                print(json.dumps({"success": False, "msg": "Erro user info!", "response": response}))
                sys.exit(1)
        else:
            print(json.dumps({"success": False, "msg": "Erro game login!", "response": response}))
            sys.exit(1)
        
        game_api = api_url_game
        
        # GAME PLAYER SESSION
        post_game_session = {
            "btt": btt_value,
            "vc": 0,
            "pf": 1,
            "l": "pt",
            "gi": id_game,
            "os": ops_value,
            "otk": ot_value
        }
        
        if DEBUG:
            ot_str = str(ot_value) if ot_value else 'EMPTY'
            print(f">>> OT_VALUE type={type(ot_value)} len={len(ot_str)} value=[{ot_str[:50]}]", flush=True)
            print(f">>> POST DATA: {json.dumps(post_game_session)}", flush=True)
            print(f">>> GAME API: {game_api}", flush=True)
        
        response_game = http.open(
            f"https://{game_api}/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={codigo_pg()}",
            {
                "header": 0,
                "http": 0,
                "post": urlencode(post_game_session),
                "proxy": ""
            }
        )
        
        try:
            session_player = json.loads(response_game)
        except json.JSONDecodeError:
            print(f"Erro ao decodificar resposta da sessão: {response_game}")
            continue
        
        # Verificar se a resposta contém os dados necessários
        if not session_player.get("dt") or not session_player["dt"].get("tk"):
            print(f"Erro: Resposta da sessão inválida - {json.dumps(session_player)}")
            continue
        
        # GAME RULE
        post_game_rule = {
            'btt': btt_value,
            'gid': id_game,
            'atk': session_player["dt"]["tk"],
            'pf': 1
        }
        
        rule_game = http.open(
            f"https://{game_api}/{session_player['dt']['bau']}v2/GameRule/Get?traceId={codigo_pg()}",
            {
                "header": 0,
                "http": 0,
                "post": urlencode(post_game_rule),
                "proxy": ""
            }
        )
        
        try:
            rule_game = json.loads(rule_game)
        except json.JSONDecodeError:
            print(f"Erro ao decodificar Game Rule: {rule_game}")
            continue
        
        # GAME INFO
        post_game_info = {
            'eatk': session_player["dt"]["eatk"],
            'btt': btt_value,
            'atk': session_player["dt"]["tk"],
            'pf': 1
        }
        
        game_api = api_url_game.replace('api.', f"{session_player['dt']['sdn']}.")
        
        info_game = http.open(
            f"https://{game_api}/{session_player['dt']['geu']}v2/GameInfo/Get?traceId={codigo_pg()}",
            {
                "header": 0,
                "http": 0,
                "post": urlencode(post_game_info),
                "proxy": ""
            }
        )
        
        try:
            info_game = json.loads(info_game)
        except json.JSONDecodeError:
            print(f"Erro ao decodificar Game Info: {info_game}")
            continue
        
        # Verificar se info_game tem os dados necessários
        if not info_game.get("dt"):
            print(f"Erro: Game Info inválido - {json.dumps(info_game)}")
            continue
        
        # Calcular saldo
        saldo_atual = float(
            info_game.get("dt", {}).get("ls", {}).get("si", {}).get("bl") or
            info_game.get("dt", {}).get("si", {}).get("bl") or
            0
        )
        
        # Verificar se existem os dados necessários para apostas
        dt = info_game.get("dt", {})
        if not dt.get("cs") or not dt.get("ml") or not dt.get("mxl"):
            print(f"Erro: Dados de aposta não encontrados no Game Info")
            continue
        
        if not dt.get("ls") or not dt["ls"].get("si"):
            print(f"Erro: Dados de sessão não encontrados no Game Info")
            continue
        
        # Calcular apostas
        apostas = {}
        cs_list = list(reversed(dt["cs"]))
        ml_list = list(reversed(dt["ml"]))
        
        for cs in cs_list:
            for ml in ml_list:
                valor_aposta = cs * ml * dt["mxl"]
                apostas[hashlib.md5(str(valor_aposta).encode()).hexdigest()] = {
                    'valor': valor_aposta,
                    'cs': cs,
                    'ml': ml
                }
        
        apostas = sorted(list(apostas.values()), key=lambda x: x['valor'])
        current_bet_index = 0
        
        id_play = dt.get("ls", {}).get("si", {}).get("sid", 0)
        
        # Selecionar aposta base
        cs_selecionado = dt["cs"][0]
        ml_selecionado = dt["ml"][0]
        valor_aposta_atual = cs_selecionado * ml_selecionado * dt["mxl"]
        
        if aposta_fixa > 0:
            print(f"Buscando aposta fixa R$ {aposta_fixa:.2f}...")
            # Busca a combinação mais próxima do valor desejado
            diff_minima = float('inf')
            for aposta in apostas:
                diff = abs(aposta['valor'] - aposta_fixa)
                if diff < diff_minima:
                    diff_minima = diff
                    cs_selecionado = aposta['cs']
                    ml_selecionado = aposta['ml']
                    valor_aposta_atual = aposta['valor']
            
            # Encontrar índice da aposta selecionada
            for i, aposta in enumerate(apostas):
                if aposta['cs'] == cs_selecionado and aposta['ml'] == ml_selecionado:
                    current_bet_index = i
                    break
                    
            print(f"Aposta selecionada: R$ {valor_aposta_atual:.2f} (cs: {cs_selecionado}, ml: {ml_selecionado})")
        
        bet_minima = valor_aposta_atual
        
        spin = 1
        # Verificar se é o último jogo da lista
        is_ultimo_jogo = (count_jogo >= len(lista_jogos))
        
        # FLASH TOUR: forçar bet mínima e giros configurados
        if flash_tour:
            cs_selecionado = dt["cs"][0]
            ml_selecionado = dt["ml"][0]
            valor_aposta_atual = cs_selecionado * ml_selecionado * dt["mxl"]
            bet_minima = valor_aposta_atual
            max_spin_count = random.randint(spin_min, spin_max)
            print(f"  [FLASH TOUR] Bet minima R$ {bet_minima:.2f} | {max_spin_count} giros rapidos")
        # Se zerar_saldo ativo E é o último jogo: spins ilimitados
        elif zerar_saldo and is_ultimo_jogo:
            max_spin_count = float('inf')  # Infinito
            print(f"[ZERAR SALDO] Ultimo jogo - Spins ilimitados ate saldo zerar...")
        else:
            max_spin_count = random.randint(spin_min, spin_max)
        
        error_count = 0
        tb_retry_count = 0
        valor_aposta = bet_minima
        skip_to_next_game = False
        is_wolf_game = "hood-vs-wolf" in str(jogo_pg.get('name', '')).lower() or modo_hood_wolf_trava
        is_medusa_game = "medusa" in str(jogo_pg.get('name', '')).lower() or modo_medusa_trava
        is_dragon_game = "dragon kingdom" in str(jogo_pg.get('name', '')).lower() or modo_dragon_trava
        
        # Realizar GameInfo/Update para Hood vs Wolf, Medusa II e Dragon Kingdom para evitar erro 1201
        if is_wolf_game or is_medusa_game or is_dragon_game:
            payload_update = {
                "cs": cs_selecionado,
                "ml": ml_selecionado,
                "btt": 1,
                "wk": "0_C",
                "atk": session_player["dt"]["tk"],
                "pf": 1,
            }
            try:
                update_resp = http.open(
                    f"https://{game_api}/{session_player['dt']['geu']}v2/GameInfo/Update?traceId={codigo_pg()}",
                    {
                        "header": 0,
                        "http": 0,
                        "post": urlencode(payload_update),
                        "proxy": ""
                    }
                )
                update_data = json.loads(update_resp)
                if update_data.get("dt") and update_data["dt"].get("si"):
                    id_play = update_data["dt"]["si"].get("sid", id_play)
            except:
                pass

        while spin <= max_spin_count:
            post_game_play = {
                "id": id_play,
                "cs": cs_selecionado,
                "ml": ml_selecionado,
                "wk": "0_C" if (is_wolf_game or is_medusa_game or is_dragon_game) else dt['ls']['si'].get('wk', '0:0:1:0:0:0'),
                "btt": 1,
                "atk": session_player["dt"]["tk"],
                "pf": 1
            }
            
            # Loop para repetir request até tb != 0
            tb_retry_count = 0
            while True:
                play_game_response = http.open(
                    f"https://{game_api}/{session_player['dt']['geu']}v2/Spin?traceId={codigo_pg()}",
                    {
                        "header": 0,
                        "http": 0,
                        "post": urlencode(post_game_play),
                        "proxy": ""
                    }
                )
                
                # Tentar decodificar resposta
                try:
                    play_game = json.loads(play_game_response)
                except json.JSONDecodeError:
                    # Log de erro (só se salvar_logs ativado)
                    if salvar_logs:
                        spin_counter += 1
                        spin_log = {
                            "spin_global": spin_counter,
                            "spin_numero": spin,
                            "jogo_nome": jogo_pg['name'],
                            "jogo_numero": count_jogo - 1,
                            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "erro": "Resposta inválida do spin",
                            "response_raw": play_game_response[:500] if play_game_response else None
                        }
                        
                        nome_jogo_limpo = limpar_nome_arquivo(jogo_pg['name'])
                        spin_filename = f"{spin_counter:04d}_{nome_jogo_limpo}_{spin}.json"
                        spin_file = os.path.join(session_dir, spin_filename)
                        with open(spin_file, 'w', encoding='utf-8') as f:
                            json.dump(spin_log, f, ensure_ascii=False, indent=2)
                        
                        jogo_log["spins"].append({"spin_global": spin_counter, "file": spin_filename, "erro": spin_log["erro"]})
                    
                    print(f"Erro: Resposta inválida do spin - indo para próximo jogo")
                    skip_to_next_game = True
                    break
                
                # Verificar se há erro na resposta
                if play_game.get("err"):
                    error_msg = play_game.get("err", {})
                    error_code = error_msg.get("cd", "unknown") if isinstance(error_msg, dict) else "unknown"
                    error_text = error_msg.get("msg", "Unknown error") if isinstance(error_msg, dict) else str(error_msg)
                    
                    error_count += 1
                    print(f"Erro no spin ({error_code}): {error_text}")
                    
                    # Se erro persistente (mais de 2 tentativas), ir para próximo jogo
                    if error_count >= 2:
                        print(f"Muitos erros consecutivos - indo para próximo jogo")
                        skip_to_next_game = True
                        break
                    
                    # Tentar atualizar id_play e continuar
                    id_play = play_game.get("dt", {}).get("si", {}).get("sid", 0)
                    post_game_play["id"] = id_play
                    time.sleep(0.5)
                    continue
                
                # VERIFICAÇÃO DE TRAVA (BÔNUS)
                play_si = play_game.get("dt", {}).get("si", {})
                
                # Extrair vida (Hood vs Wolf)
                vida_menina = 0
                vida_lobo = 0
                life_text = ""
                
                if is_wolf_game:
                    bf = play_si.get("bf") or {}
                    src = bf.get("src")
                    if isinstance(src, dict) and src:
                        valores = list(src.values())
                        if len(valores) >= 1:
                            vida_menina = valores[0]
                            vida_lobo = valores[-1]
                    elif isinstance(src, list) and src:
                        if len(src) >= 1:
                            vida_menina = src[0]
                            vida_lobo = src[-1]
                    life_text = f" | Menina: {vida_menina} Lobo: {vida_lobo}"
                    
                    # Se pegar o bônus (18), joga o Jokenpô automaticamente
                    if vida_menina == 18 or vida_lobo == 18:
                        print(f"\n{'='*50}")
                        print(f"!!! ENTRANDO NO BÔNUS (JOKENPÔ) !!!{life_text}")
                        print(f"{'='*50}")
                        
                        vitorias = 0
                        derrotas = 0
                        rodada = 0
                        jokenpo_map = {101: "Pedra", 102: "Tesoura", 103: "Papel"}
                        
                        while vitorias < 2 and derrotas < 2 and rodada < 10:
                            rodada += 1
                            jokenpo = random.choice([101, 102, 103])
                            jokenpo_nome = jokenpo_map.get(jokenpo, "Desconhecido")
                            
                            payload_jokenpo = {
                                "gs": jokenpo,
                                "cs": cs_selecionado,
                                "ml": ml_selecionado,
                                "pf": 1,
                                "id": id_play,
                                "wk": post_game_play["wk"],
                                "btt": 1,
                                "atk": session_player["dt"]["tk"]
                            }
                            
                            jokenpo_resp = http.open(
                                f"https://{game_api}/{session_player['dt']['geu']}v2/Gesture/Select?traceId={codigo_pg()}",
                                {
                                    "header": 0,
                                    "http": 0,
                                    "post": urlencode(payload_jokenpo),
                                    "proxy": ""
                                }
                            )
                            
                            try:
                                jokenpo_data = json.loads(jokenpo_resp)
                            except:
                                print("Erro ao processar resposta do Jokenpô")
                                break
                                
                            jk_si = jokenpo_data.get("dt", {}).get("si", {})
                            bns = jk_si.get("bns") or {}
                            
                            id_play = jk_si.get("sid", id_play)
                            post_game_play["id"] = id_play
                            
                            ws = bns.get("ws")
                            gr = bns.get("gr") or {}
                            op_jogada = gr.get("2", 0)
                            op_nome = jokenpo_map.get(op_jogada, "Desconhecido")
                            
                            if ws == 23:
                                res = "EMPATE"
                            elif ws == 3:
                                res = "VITÓRIA"
                                vitorias += 1
                            elif ws == 2:
                                res = "DERROTA"
                                derrotas += 1
                            elif ws is None:
                                break
                            else:
                                res = f"({ws}) DESCONHECIDO"
                                
                            print(f"  Rodada {rodada}: {jokenpo_nome} vs {op_nome} -> {res} | Placar: {vitorias}x{derrotas}")
                            time.sleep(1)
                            
                        print(f"{'='*50}\n")
                        # Atualizar dados do jogo com a última resposta do jokenpô para que o loop tb==0 detecte os free spins
                        play_game = jokenpo_data
                        play_si = play_game.get("dt", {}).get("si", {})

                if trava_ativa:
                    # Detectar bônus:
                    # - modo_medusa_trava: 2+ pedras vermelhas (ssc>=2) E 5+ vidas azuis (msb>=5)
                    # - modo_scatter_trava (Midas Fortune, Genie's, Perseus, Diao Chan):
                    #   SOMENTE por flag 'bf' ou 3+ scatters reais (tb==0 é re-spin normal nesses jogos)
                    # - demais jogos (Double Fortune, Emperor's Favour, etc):
                    #   flag 'bf', 3+ scatters OU tb==0 (free spin)
                    
                    # ── Lógica Dragon Kingdom: accv >= 10 → escalar bet ──
                    if modo_dragon_trava and is_dragon_game:
                        # Extrair accv do campo 'accv' na resposta (primeiro número antes de ';')
                        play_dt = play_game.get("dt", {})
                        play_si_inner = play_dt.get("si", {})
                        # Para jogos PP via PG wrapper, accv pode estar em si diretamente ou em raw
                        # Tentamos campo 'accv' do si; fallback para campo padrão
                        raw_accv = str(play_si_inner.get("accv", play_si_inner.get("av", "0")))
                        try:
                            dragon_accv = int(raw_accv.split(";")[0].strip())
                        except (ValueError, IndexError):
                            dragon_accv = 0

                        dragon_info = f" | accv: {dragon_accv}/10"

                        if dragon_accv >= 10:
                            print(f"\n{'='*50}")
                            print(f"!!! DRAGON KINGDOM | BET ARMADA R$ {valor_aposta_atual:.2f} !!! accv={dragon_accv}")
                            print(f"{'='*50}")

                            if valor_aposta_atual not in bets_armadas:
                                bets_armadas.append(valor_aposta_atual)

                            # Escalar para a próxima bet
                            current_bet_index += 1
                            if current_bet_index < len(apostas):
                                proxima = apostas[current_bet_index]
                                cs_selecionado = proxima['cs']
                                ml_selecionado = proxima['ml']
                                valor_aposta_atual = proxima['valor']
                                valor_aposta = valor_aposta_atual
                                print(f"Mudando para próxima bet: R$ {valor_aposta_atual:.2f}")

                                post_game_play["cs"] = cs_selecionado
                                post_game_play["ml"] = ml_selecionado

                                # Sincronizar estado para nova bet
                                try:
                                    payload_update = {
                                        "cs": cs_selecionado,
                                        "ml": ml_selecionado,
                                        "btt": 1,
                                        "wk": "0_C",
                                        "atk": session_player["dt"]["tk"],
                                        "pf": 1,
                                    }
                                    update_resp = http.open(
                                        f"https://{game_api}/{session_player['dt']['geu']}v2/GameInfo/Update?traceId={codigo_pg()}",
                                        {
                                            "header": 0,
                                            "http": 0,
                                            "post": urlencode(payload_update),
                                            "proxy": ""
                                        }
                                    )
                                    update_data = json.loads(update_resp)
                                    if update_data.get("dt") and update_data["dt"].get("si"):
                                        id_play = update_data["dt"]["si"].get("sid", id_play)
                                        post_game_play["id"] = id_play
                                except:
                                    pass
                            else:
                                print("[Dragon] Bet máxima atingida. Travando.")
                                skip_to_next_game = True
                                break
                        else:
                            spin_display_drg = "∞" if (zerar_saldo and is_ultimo_jogo) else str(int(max_spin_count))
                            print(f"  [Dragon] Spin {spin}/{spin_display_drg}{dragon_info} | Bet R$ {valor_aposta_atual:.2f} | Saldo R$ {play_si.get('bl', 0):.2f}")

                    # Lógica específica Medusa II Trava (igual ao Hood vs Wolf)
                    if modo_medusa_trava and is_medusa_game:
                        ssc_count = play_si.get("ssc", 0) or 0   # pedras vermelhas no spin
                        msb_count = play_si.get("msb", 0) or 0   # vidas azuis acumuladas
                        
                        medusa_info = f" | Vermelhos: {ssc_count} | Vidas: {msb_count}"
                        
                        # Condição de trava: 2+ vermelhos E 5+ vidas
                        if ssc_count >= 2 and msb_count >= 5:
                            print(f"\n{'='*50}")
                            print(f"!!! ARMOU BET R$ {valor_aposta_atual:.2f} !!! | Vermelhos: {ssc_count} | Vidas: {msb_count}")
                            print(f"{'='*50}\n")
                            
                            if valor_aposta_atual not in bets_armadas:
                                bets_armadas.append(valor_aposta_atual)
                            
                            # Mudar para próxima bet (igual Hood vs Wolf)
                            current_bet_index += 1
                            if current_bet_index < len(apostas):
                                proxima = apostas[current_bet_index]
                                cs_selecionado = proxima['cs']
                                ml_selecionado = proxima['ml']
                                valor_aposta_atual = proxima['valor']
                                valor_aposta = valor_aposta_atual
                                print(f"Mudando para próxima bet: R$ {valor_aposta_atual:.2f}")
                                
                                # Atualizar post_game_play para o próximo giro
                                post_game_play["cs"] = cs_selecionado
                                post_game_play["ml"] = ml_selecionado
                                
                                # Sincronizar novo estado para a nova bet (evitar erro 1201)
                                try:
                                    payload_update = {
                                        "cs": cs_selecionado,
                                        "ml": ml_selecionado,
                                        "btt": 1,
                                        "wk": "0_C",
                                        "atk": session_player["dt"]["tk"],
                                        "pf": 1,
                                    }
                                    update_resp = http.open(
                                        f"https://{game_api}/{session_player['dt']['geu']}v2/GameInfo/Update?traceId={codigo_pg()}",
                                        {
                                            "header": 0,
                                            "http": 0,
                                            "post": urlencode(payload_update),
                                            "proxy": ""
                                        }
                                    )
                                    update_data = json.loads(update_resp)
                                    if update_data.get("dt") and update_data["dt"].get("si"):
                                        id_play = update_data["dt"]["si"].get("sid", id_play)
                                        post_game_play["id"] = id_play
                                except:
                                    pass
                                
                                # Continua no mesmo jogo com a nova bet
                            else:
                                print("Não há mais bets superiores. Finalizando jogo.")
                                skip_to_next_game = True
                                break
                        else:
                            # Mostrar estado atual para monitoramento
                            spin_display_med = "∞" if (zerar_saldo and is_ultimo_jogo) else str(int(max_spin_count))
                            print(f"  [Medusa] Spin {spin}/{spin_display_med}{medusa_info} | Bet R$ {valor_aposta_atual:.2f} | Saldo R$ {play_si.get('bl', 0):.2f}")
                    
                    if modo_scatter_trava:
                        has_bonus = bool(play_si.get("bf")) or (play_si.get("sc", 0) >= 3)
                    else:
                        has_bonus = play_si.get("bf") or (play_si.get("sc", 0) >= 3) or (float(play_si.get("tb", -1)) == 0)
                    
                    # Lógica específica Hood vs Wolf Trava
                    if modo_hood_wolf_trava and is_wolf_game:
                        has_trava_wolf = vida_menina in [1, 17] or vida_lobo in [1, 17]
                        if has_trava_wolf:
                            print(f"\n{'='*50}")
                            print(f"!!! ARMOU BET R$ {valor_aposta_atual:.2f} !!!{life_text}")
                            print(f"{'='*50}\n")
                            
                            if valor_aposta_atual not in bets_armadas:
                                bets_armadas.append(valor_aposta_atual)
                            
                            # Mudar para próxima bet
                            current_bet_index += 1
                            if current_bet_index < len(apostas):
                                proxima = apostas[current_bet_index]
                                cs_selecionado = proxima['cs']
                                ml_selecionado = proxima['ml']
                                valor_aposta_atual = proxima['valor']
                                valor_aposta = valor_aposta_atual
                                print(f"Mudando para próxima bet: R$ {valor_aposta_atual:.2f}")
                                
                                # Atualizar post_game_play para o próximo giro
                                post_game_play["cs"] = cs_selecionado
                                post_game_play["ml"] = ml_selecionado
                                
                                # Sincronizar novo estado para a nova bet (evitar erro 1201)
                                try:
                                    payload_update = {
                                        "cs": cs_selecionado,
                                        "ml": ml_selecionado,
                                        "btt": 1,
                                        "wk": "0_C",
                                        "atk": session_player["dt"]["tk"],
                                        "pf": 1,
                                    }
                                    update_resp = http.open(
                                        f"https://{game_api}/{session_player['dt']['geu']}v2/GameInfo/Update?traceId={codigo_pg()}",
                                        {
                                            "header": 0,
                                            "http": 0,
                                            "post": urlencode(payload_update),
                                            "proxy": ""
                                        }
                                    )
                                    update_data = json.loads(update_resp)
                                    if update_data.get("dt") and update_data["dt"].get("si"):
                                        id_play = update_data["dt"]["si"].get("sid", id_play)
                                        post_game_play["id"] = id_play # Atualiza ID para o próximo giro
                                except:
                                    pass
                                
                                # Continua no mesmo jogo, mas sai do check de bonus para processar o spin atual
                            else:
                                print("Não há mais bets superiores. Finalizando jogo.")
                                skip_to_next_game = True
                                break
                    
                    elif has_bonus and not is_wolf_game:
                        sc_total = play_si.get("sc", 0)
                        sc_info = f" | Scatters: {sc_total}" if sc_total > 0 else ""
                        tb_info = " (Free Spin)" if float(play_si.get("tb", -1)) == 0 else ""
                        
                        print(f"\n{'='*50}")
                        print(f"!!! BÔNUS DETECTADO{tb_info} - JOGO TRAVADO !!!")
                        print(f"Jogo: {jogo_pg['name']} | Spin: {spin}{sc_info}{life_text}")
                        print(f"Aposta: R$ {valor_aposta_atual:.2f}")
                        print(f"Saldo: R$ {play_si.get('bl', 0):.2f}")
                        print(f"{'='*50}\n")
                        
                        # Para os spins deste jogo
                        skip_to_next_game = True
                        break
                
                # Verificar se tb (total bet) é 0 - se for, repetir request até aparecer valor
                tb_value = float(play_game.get("dt", {}).get("si", {}).get("tb", 0) or 0)
                if tb_value == 0:
                    tb_retry_count += 1
                    
                    # Mostrar dados do spin com tb=0
                    tb0_saldo = float(play_game.get("dt", {}).get("si", {}).get("bl", 0) or 0)
                    tb0_ganho = float(play_game.get("dt", {}).get("si", {}).get("tw", 0) or 0)
                    spin_display = "∞" if (zerar_saldo and is_ultimo_jogo) else str(int(max_spin_count))
                    
                    # Se é o último spin, mostrar que está aguardando tb!=0
                    if spin >= max_spin_count and max_spin_count != float('inf'):
                        print(f"  └─ [ULTIMO SPIN {spin}/{spin_display}] Re-Spin ({tb_retry_count}): Saldo R$ {tb0_saldo:.2f} - Ganho R$: {tb0_ganho:.2f}")
                    else:
                        print(f"  └─ Re-Spin ({tb_retry_count}): {spin}/{spin_display} - Saldo R$ {tb0_saldo:.2f} - Ganho R$: {tb0_ganho:.2f}")
                    
                    id_play = play_game.get("dt", {}).get("si", {}).get("sid", 0)
                    post_game_play["id"] = id_play
                    post_game_play["wk"] = play_game.get("dt", {}).get("si", {}).get("wk", post_game_play["wk"])
                    time.sleep(1)
                    continue
                
                # tb != 0, spin válido - sair do loop
                break
            
            # Se houve erro ou tb persistente, sair do loop de spins
            if skip_to_next_game:
                break
            
            # Reset contador de erros se spin bem sucedido
            error_count = 0
            
            roll += valor_aposta
            
            id_play = play_game.get("dt", {}).get("si", {}).get("sid", 0)
            saldo_atual = float(play_game.get("dt", {}).get("si", {}).get("bl", 0) or 0)
            ganho = float(play_game.get("dt", {}).get("si", {}).get("tw", 0) or 0)
            
            # Atualizar estatísticas globais
            total_spins += 1
            total_ganhos += ganho
            saldo_final = saldo_atual
            
            # Atualizar estatísticas do jogo atual
            spins_jogo += 1
            ganhos_jogo += ganho
            apostado_jogo += valor_aposta
            saldo_fim_jogo = saldo_atual
            
            # Salvar spin em arquivo separado (só se salvar_logs ativado)
            if salvar_logs:
                spin_counter += 1
                spin_log = {
                    "spin_global": spin_counter,
                    "spin_numero": spin,
                    "jogo_nome": jogo_pg['name'],
                    "jogo_numero": count_jogo - 1,
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "request": post_game_play,
                    "response": play_game,
                    "tb_retries": tb_retry_count,
                    "saldo": saldo_atual,
                    "aposta": valor_aposta,
                    "ganho": ganho,
                    "roll_acumulado": roll
                }
                
                nome_jogo_limpo = limpar_nome_arquivo(jogo_pg['name'])
                spin_filename = f"{spin_counter:04d}_{nome_jogo_limpo}_{spin}.json"
                spin_file = os.path.join(session_dir, spin_filename)
                with open(spin_file, 'w', encoding='utf-8') as f:
                    json.dump(spin_log, f, ensure_ascii=False, indent=2)
                
                jogo_log["spins"].append({
                    "spin_global": spin_counter,
                    "file": spin_filename,
                    "saldo": saldo_atual,
                    "aposta": valor_aposta,
                    "ganho": ganho
                })
            
            sc_count = play_game.get("dt", {}).get("si", {}).get("sc", 0)
            sc_text = f" - SC: {sc_count}" if sc_count > 0 else ""
            
            spin_display = "∞" if (zerar_saldo and is_ultimo_jogo) else str(int(max_spin_count))
            # Usar life_text se disponível (definido acima no loop de spin)
            print(f"Spin: {spin}/{spin_display} - Saldo R$ {saldo_atual:.2f} - BET R$ {valor_aposta:.2f} - Ganho R$: {ganho:.2f} - ROLL R$ {roll:.2f}{sc_text}{life_text}")
            
            # Aguardar entre spins: no Flash Tour sem espera (giro rapido), normal 1 segundo
            if not flash_tour:
                time.sleep(1)
            
            if saldo_atual < 0.30:
                print(f"\n[SALDO ZEROU] R$ {saldo_atual:.2f} < R$ 0.30 - Parando execucao...")
                break
            
            if saldo_atual < bet_minima:
                print(f"\n[SALDO BAIXO] R$ {saldo_atual:.2f} < R$ {bet_minima:.2f} (aposta minima) - Proximo jogo...")
                break
            
            if "enough" in play_game_response.lower():
                break
            
            spin += 1
        
        # Contabilizar jogo executado
        jogos_executados += 1
        
        # Calcular lucro/perda do jogo e adicionar às estatísticas
        if saldo_inicio_jogo is not None:
            lucro_jogo = saldo_fim_jogo - saldo_inicio_jogo
            estatisticas_jogos.append({
                "nome": jogo_pg['name'],
                "saldo_inicio": saldo_inicio_jogo,
                "saldo_fim": saldo_fim_jogo,
                "lucro": lucro_jogo,
                "spins": spins_jogo,
                "apostado": apostado_jogo,
                "ganhos": ganhos_jogo
            })
        
        # Finalizar log do jogo (só se salvar_logs ativado)
        if salvar_logs:
            jogo_log["fim"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            jogo_log["total_spins"] = len(jogo_log["spins"])
            jogo_log["saldo_final"] = saldo_atual if 'saldo_atual' in dir() else 0
            session_log["jogos"].append(jogo_log)
            
            # Salvar log parcial a cada jogo (para não perder dados em caso de erro)
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(session_log, f, ensure_ascii=False, indent=2)
        
        # Aguardar antes de trocar de jogo (só se NÃO for modo zerar_saldo nem flash_tour)
        if not zerar_saldo and not flash_tour and saldo_atual >= bet_minima:
            tempo_espera = random.randint(10, 60)
            print(f"Aguardando {tempo_espera}s para proximo jogo...")
            time.sleep(tempo_espera)
        elif flash_tour:
            # Flash Tour: espera mínima entre jogos (1-3 segundos)
            time.sleep(random.uniform(1.0, 3.0))
        
        # Incrementar contador de jogos
        count_jogo += 1
        
        # Se houve erro, ir para próximo jogo
        if skip_to_next_game:
            continue
        
        # Verificar se precisa sair do loop externo (saldo < R$ 0.30)
        if saldo_atual < 0.30 or "enough" in play_game_response.lower():
            break
    
    # CALCULAR ESTATÍSTICAS FINAIS
    tempo_fim = time.time()
    tempo_total = tempo_fim - tempo_inicio
    
    horas = int(tempo_total // 3600)
    minutos = int((tempo_total % 3600) // 60)
    segundos = int(tempo_total % 60)
    
    # Se não conseguiu capturar saldo inicial, usar 0
    if saldo_inicial is None:
        saldo_inicial = 0
    
    lucro_perda = saldo_final - saldo_inicial
    percentual = ((saldo_final / saldo_inicial) - 1) * 100 if saldo_inicial > 0 else 0
    
    # EXIBIR RESUMO FINAL
    print(f"\n{'='*60}")
    print(f"{'ESTATÍSTICAS FINAIS':^60}")
    print(f"{'='*60}")
    print(f"  Horário Início:    {datetime.fromtimestamp(tempo_inicio).strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  Horário Fim:       {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  Tempo de Execução: {horas:02d}h {minutos:02d}m {segundos:02d}s")
    print(f"{'='*60}")
    print(f"  Jogos Executados:  {jogos_executados}/{len(lista_jogos)}")
    print(f"  Total de Spins:    {total_spins}")
    print(f"  Total Apostado:    R$ {roll:.2f}")
    print(f"  Total Ganhos:      R$ {total_ganhos:.2f}")
    print(f"{'='*60}")
    print(f"  Saldo Inicial:     R$ {saldo_inicial:.2f}")
    print(f"  Saldo Final:       R$ {saldo_final:.2f}")
    print(f"  {'Lucro' if lucro_perda >= 0 else 'Perda'}:             R$ {abs(lucro_perda):.2f} ({'+' if lucro_perda >= 0 else '-'}{abs(percentual):.2f}%)")
    
    if modo_dragon_trava and bets_armadas:
        print(f"{'='*60}")
        print(f"{'BETS ARMADAS (DRAGON KINGDOM)':^60}")
        print(f"{'='*60}")
        for bet in sorted(bets_armadas):
            print(f"  - R$ {bet:.2f}")

    if modo_hood_wolf_trava and bets_armadas:
        print(f"{'='*60}")
        print(f"{'BETS ARMADAS (HOOD VS WOLF)':^60}")
        print(f"{'='*60}")
        for bet in sorted(bets_armadas):
            print(f"  - R$ {bet:.2f}")
    
    if modo_medusa_trava and bets_armadas:
        print(f"{'='*60}")
        print(f"{'BETS ARMADAS (MEDUSA II)':^60}")
        print(f"{'='*60}")
        for bet in sorted(bets_armadas):
            print(f"  - R$ {bet:.2f}")
            
    print(f"{'='*60}")
    
    # ESTATÍSTICAS POR JOGO (mais lucrou / mais perdeu)
    if estatisticas_jogos:
        # Ordenar por lucro (maior para menor)
        jogos_ordenados = sorted(estatisticas_jogos, key=lambda x: x['lucro'], reverse=True)
        
        # Jogo que mais lucrou
        jogo_mais_lucrou = jogos_ordenados[0]
        # Jogo que mais perdeu
        jogo_mais_perdeu = jogos_ordenados[-1]
        
        print(f"{'RANKING DE JOGOS':^60}")
        print(f"{'='*60}")
        
        if jogo_mais_lucrou['lucro'] > 0:
            print(f"  MAIS LUCROU: {jogo_mais_lucrou['nome'][:30]}")
            print(f"    Lucro: R$ {jogo_mais_lucrou['lucro']:.2f} ({jogo_mais_lucrou['spins']} spins)")
        else:
            print(f"  MAIS LUCROU: Nenhum jogo teve lucro")
        
        if jogo_mais_perdeu['lucro'] < 0:
            print(f"  MAIS PERDEU: {jogo_mais_perdeu['nome'][:30]}")
            print(f"    Perda: R$ {abs(jogo_mais_perdeu['lucro']):.2f} ({jogo_mais_perdeu['spins']} spins)")
        else:
            print(f"  MAIS PERDEU: Nenhum jogo teve perda")
        
        print(f"{'='*60}")
        
        # Top 10 jogos (se houver mais de 2)
        if len(jogos_ordenados) > 2:
            print(f"{'TOP 10 JOGOS (por lucro)':^60}")
            print(f"{'='*60}")
            for i, jogo in enumerate(jogos_ordenados[:10], 1):
                sinal = "+" if jogo['lucro'] >= 0 else ""
                print(f"  {i}. {jogo['nome'][:35]:<35} {sinal}R$ {jogo['lucro']:.2f}")
            print(f"{'='*60}")
    
    # SALVAR LOG FINAL (só se salvar_logs ativado)
    if salvar_logs:
        session_log["fim"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        session_log["estatisticas"] = {
            "tempo_execucao": f"{horas:02d}h {minutos:02d}m {segundos:02d}s",
            "tempo_segundos": tempo_total,
            "jogos_executados": jogos_executados,
            "jogos_total": len(lista_jogos),
            "total_spins": total_spins,
            "total_apostado": roll,
            "total_ganhos": total_ganhos,
            "saldo_inicial": saldo_inicial,
            "saldo_final": saldo_final,
            "lucro_perda": lucro_perda,
            "percentual": percentual
        }
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(session_log, f, ensure_ascii=False, indent=2)
        
        print(f"  Log salvo em:      {session_dir}/")
        print(f"  Total de arquivos: {spin_counter} spins")
    
    print(f"{'='*60}\n")


def main():
    """Função principal com loop para reexecutar"""
    
    # MENU - Escolher configurações
    config = mostrar_menu()
    if config is None:
        return
    
    while True:
        # Executar com a configuração atual
        executar(config)
        
        # Perguntar se deseja executar novamente
        print("\n" + "="*60)
        resposta = input("  Executar novamente com mesma configuracao? (S/N): ").strip().upper()
        
        if resposta != 'S':
            print("\n  Encerrando...\n")
            break
        
        print("\n  Reiniciando execucao...\n")


if __name__ == "__main__":
    main()
