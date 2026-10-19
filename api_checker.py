# -*- coding: utf-8 -*-
"""
Verificador de API independente (código único)
Testa qual API é mais rápida - não depende de bot.py
"""
import asyncio
import base64
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from Crypto.Cipher import AES

# Tenta usar curl_cffi
try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Chave de config
CONFIG_KEY_B64 = "dGhhbmtzLHBpZzRjbG91ZA=="


@dataclass
class PlatformConfig:
    """Configuração da plataforma"""
    url_domain: str = ""
    api_url: str = ""
    host: str = ""
    sitecode: str = ""
    speed_version: str = "1.1.50"
    app_version: str = "7.0.105"
    inviter_id: str = ""
    api_domains: List[str] = field(default_factory=list)


def decrypt_b64_aes128_ecb(ciphertext: str, key_b64: str) -> str:
    """Descriptografa AES-128-ECB em base64"""
    try:
        key = base64.b64decode(key_b64)[:16]
        data = base64.b64decode(ciphertext)
        cipher = AES.new(key, AES.MODE_ECB)
        decrypted = cipher.decrypt(data)
        decrypted = decrypted.rstrip(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10')
        return decrypted.decode('utf-8', errors='ignore')
    except:
        return ""


class HttpClient:
    """Cliente HTTP simples"""
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
    
    async def get(self, url: str) -> Tuple[Optional[str], int]:
        """GET request, retorna (texto, status)"""
        try:
            if HAS_CURL_CFFI:
                async with AsyncSession(impersonate="chrome120") as session:
                    response = await session.get(url, timeout=self.timeout, allow_redirects=True)
                    return response.text, response.status_code
            else:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout), ssl=False) as response:
                        text = await response.text()
                        return text, response.status
        except Exception as e:
            return None, 0


async def test_fastest_domain(
    http: HttpClient,
    domains: list,
    test_path: str = "/",
    label: str = "API",
    rounds: int = 10
) -> Optional[str]:
    """Testa múltiplos domínios e retorna o mais rápido"""
    if not domains:
        return None
    
    if len(domains) == 1:
        return domains[0]
    
    logger.info(f"[CONFIG] === Testando {len(domains)} {label}s ({rounds}x cada) ===")
    
    domain_times: Dict[str, list] = {d: [] for d in domains}
    domain_status: Dict[str, str] = {d: "" for d in domains}
    
    async def test_domain_once(domain: str) -> Tuple[str, float, str]:
        try:
            start = time.time()
            test_url = f"{domain.rstrip('/')}{test_path}"
            text, status = await http.get(test_url)
            elapsed = time.time() - start
            
            if status and status < 500:
                return (domain, elapsed, f"{status}")
            else:
                return (domain, float('inf'), f"HTTP {status}")
        except:
            return (domain, float('inf'), "ERRO")
    
    for round_num in range(1, rounds + 1):
        logger.info(f"[CONFIG] Verificação {round_num}/{rounds}...")
        
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
    
    logger.info(f"[CONFIG] --- Resultados (média de {rounds} testes) ---")
    
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
        logger.info(f"[CONFIG] {marker} MÉDIA:{avg_str} | MIN:{min_str} | MAX:{max_str} | ({status}){fail_info} {domain}")
    
    if fastest:
        logger.info(f"[CONFIG] >> Selecionada: {fastest} (média: {fastest_avg*1000:.0f}ms)")
    else:
        logger.info(f"[CONFIG] !! Nenhuma {label} respondeu!")
    
    return fastest


async def fetch_platform_config(url: str) -> Optional[PlatformConfig]:
    """Extrai configuração da plataforma"""
    http = HttpClient()
    
    try:
        html, status = await http.get(url)
        if not html or status < 200 or status >= 400:
            logger.error(f"Falha ao acessar URL: {status}")
            return None
        
        cfg = None
        version_data = None
        domains = []
        
        # Método 1: preconnect link
        match = re.search(r'<link\s+rel=preconnect\s+href=([^\s>]+)\s+crossorigin="">', html, re.I)
        if match:
            base = match.group(1).rstrip("/")
            logger.info(f"[CONFIG] Base via preconnect: {base}")
            
            cfg_text, _ = await http.get(f"{base}/cocos/config_data.json")
            if cfg_text:
                try:
                    cfg = json.loads(cfg_text)
                except:
                    decrypted = decrypt_b64_aes128_ecb(cfg_text, CONFIG_KEY_B64)
                    if decrypted:
                        cfg = json.loads(decrypted)
            
            if cfg:
                ver_text, _ = await http.get(f"{base}/hall/api/lobby/webapi/forceUpdate/getForceUpdate.json")
                if ver_text:
                    try:
                        version_data = json.loads(ver_text)
                    except:
                        version_data = json.loads(decrypt_b64_aes128_ecb(ver_text, CONFIG_KEY_B64))
        
        # Método 2: fallback
        if not cfg:
            parsed = urlparse(url)
            host = parsed.netloc
            
            logger.info(f"[CONFIG] Tentando fallback: /fapage/sd/{host}.json")
            fallback_url = f"https://{host}/fapage/sd/{host}.json?t={int(time.time())}"
            fb_text, _ = await http.get(fallback_url)
            
            if fb_text:
                plain = decrypt_b64_aes128_ecb(fb_text, CONFIG_KEY_B64)
                if plain:
                    obj = json.loads(plain)
                    rels = obj.get("data", {}).get("targetRelations", [])
                    
                    for rel in rels:
                        rel = rel.rstrip("/")
                        if not rel:
                            continue
                        
                        cfg_text, _ = await http.get(f"{rel}/cocos/config_data.json")
                        if cfg_text:
                            try:
                                cfg = json.loads(cfg_text)
                            except:
                                cfg = json.loads(decrypt_b64_aes128_ecb(cfg_text, CONFIG_KEY_B64))
                            
                            if cfg:
                                oss = cfg.get("oss_url", [""])[0]
                                if oss:
                                    force_url = oss.replace("/cocos/config_data.json", "/hall/api/lobby/webapi/forceUpdate/getForceUpdate.json")
                                    ver_text, _ = await http.get(force_url)
                                    if ver_text:
                                        try:
                                            version_data = json.loads(ver_text)
                                        except:
                                            version_data = json.loads(decrypt_b64_aes128_ecb(ver_text, CONFIG_KEY_B64))
                                break
        
        if not cfg:
            logger.error("Não foi possível extrair config_data.json")
            return None
        # Extrai domínios
        for key in ["non_ma_domain", "lobby_domain"]:
            for d in cfg.get(key, []):
                if d and d not in domains:
                    domains.append(d)
        
        if not domains:
            logger.error("Nenhum domínio encontrado")
            return None
        
        # Escolhe CDN preferido
        url_domain = None
        for d in domains:
            if re.search(r"(azure|cloud)", d):
                url_domain = d
                break
        if not url_domain:
            url_domain = domains[0]
        
        # Testa APIs
        api_domains = cfg.get("api_domain", [])
        if api_domains and len(api_domains) > 1:
            api_url = await test_fastest_domain(http, api_domains, "/", label="API")
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
        
        return PlatformConfig(
            url_domain=url_domain,
            api_url=api_url,
            host=host,
            sitecode=str(cfg.get("siteCode", 0)),
            speed_version=version_data.get("data", {}).get("speedVersion", "1.1.50") if version_data else "1.1.50",
            app_version=version_data.get("data", {}).get("version", "7.0.105") if version_data else "7.0.105",
            inviter_id=inviter_id,
            api_domains=api_domains
        )
        
    except Exception as e:
        logger.error(f"Erro: {e}")
        return None


def print_result(url: str, config: Optional[PlatformConfig]):
    """Imprime resultado"""
    print("\n" + "="*70)
    print("📊 RESULTADO DA VERIFICAÇÃO")
    print("="*70)
    print(f"🌐 URL: {url}")
    print("-"*70)
    
    if config:
        print(f"✅ Status: Online")
        print(f"🔑 SiteCode: {config.sitecode}")
        print(f"🏠 URL Domain: {config.url_domain}")
        print(f"🚀 API URL: {config.api_url}")
        print(f"🌐 Host: {config.host}")
        print(f"📦 Speed Version: {config.speed_version}")
        print(f"📱 App Version: {config.app_version}")
        if config.inviter_id:
            print(f"👤 Inviter ID: {config.inviter_id}")
        if config.api_domains:
            print(f"📡 APIs disponíveis: {len(config.api_domains)}")
    else:
        print("❌ Falha ao obter configuração")
    
    print("="*70)


def save_result(url: str, config: Optional[PlatformConfig], filename: str):
    """Salva resultado em JSON"""
    data = {"url": url}
    if config:
        data["config"] = {
            "sitecode": config.sitecode,
            "url_domain": config.url_domain,
            "api_url": config.api_url,
            "host": config.host,
            "speed_version": config.speed_version,
            "app_version": config.app_version,
            "inviter_id": config.inviter_id,
            "api_domains": config.api_domains
        }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Salvo em: {filename}")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Verificador de API - Testa qual API é mais rápida",
        epilog="Exemplo: python api_checker.py https://example.com"
    )
    
    parser.add_argument("url", type=str, help="URL da plataforma")
    parser.add_argument("-s", "--save", action="store_true", help="Salva resultado em JSON")
    parser.add_argument("-o", "--output", type=str, default="platform_config.json", help="Arquivo de saída")
    
    args = parser.parse_args()
    
    print(f"\n🔍 Verificando: {args.url}\n")
    
    config = await fetch_platform_config(args.url)
    print_result(args.url, config)
    
    if args.save:
        save_result(args.url, config, args.output)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    asyncio.run(main())
