# -*- coding: utf-8 -*-
"""
Verificador de todas as plataformas em massa.
Testa a velocidade de todas as plataformas em platforms.py e salva no cache.
Assim o main.py já inicia com a API mais rápida sem precisar testar de novo.
"""
import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from colorama import Fore, Style, init
from platforms import PLATFORM_RECORDS, PlatformRecord
from bot import (
    _fetch_platform_config_standalone,
    _save_platform_config_to_file,
    BotConfig,
    PlatformConfig
)
from config import runtime_config

# Inicializa colorama
init()

# Configuração de logging (reduzida para não poluir)
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

# Semáforo para limitar concorrência (não sobrecarregar rede/CPU)
CONCURRENCY_LIMIT = 10
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

# Estatísticas
stats = {
    "total": len(PLATFORM_RECORDS),
    "online": 0,
    "offline": 0,
    "erros": 0
}

async def check_single_platform(record: PlatformRecord) -> Tuple[str, Optional[PlatformConfig], str]:
    """Verifica uma única plataforma com semáforo"""
    async with semaphore:
        url = record.site
        if not url.startswith("http"):
            url = f"https://{url}"
        
        # Remove trailing slash para consistência no cache
        url = url.rstrip("/")
        
        # Config padrão para a descoberta
        bot_config = BotConfig(url=url)
        
        try:
            # Força descoberta "fresca" (standalone)
            result = await _fetch_platform_config_standalone(url, bot_config)
            
            if result:
                from urllib.parse import urlparse
                original_host = urlparse(url).netloc
                
                # SALVA NO CACHE DO BOT
                _save_platform_config_to_file(result, original_host)
                
                stats["online"] += 1
                return record.name, result, "OK"
            else:
                stats["offline"] += 1
                return record.name, None, "OFFLINE"
        except Exception as e:
            stats["erros"] += 1
            return record.name, None, f"ERRO: {str(e)[:30]}"

async def run_bulk_check():
    """Executa verificação em massa"""
    start_time = time.time()
    
    print(f"\n{Fore.CYAN}🚀 INICIANDO VERIFICAÇÃO DE {len(PLATFORM_RECORDS)} PLATAFORMAS...{Style.RESET_ALL}\n")
    print(f"{Fore.YELLOW}Aguarde, extraindo SiteCode e testando APIs mais rápidas...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Modo: Paralelo (Limite: {CONCURRENCY_LIMIT}){Style.RESET_ALL}\n")
    
    tasks = [check_single_platform(p) for p in PLATFORM_RECORDS]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Cabeçalho da tabela
    print("\n" + "="*85)
    print(f"{'PLATAFORMA':<20} | {'STATUS':<8} | {'SITECODE':<8} | {'API MAIS RÁPIDA'}")
    print("-" * 85)
    
    # Linhas da tabela
    for name, config, status in sorted(results, key=lambda x: x[0]):
        status_color = Fore.GREEN if status == "OK" else (Fore.RED if status == "OFFLINE" else Fore.YELLOW)
        
        if config:
            sitecode = config.sitecode
            api_url = config.api_url
        else:
            sitecode = "---"
            api_url = status
            
        print(f"{name:<20} | {status_color}{status:<8}{Style.RESET_ALL} | {sitecode:<8} | {api_url}")
    
    print("="*85)
    
    # Resumo final
    print(f"\n{Fore.CYAN}📊 RESUMO FINAL{Style.RESET_ALL}")
    print(f"Total: {stats['total']}")
    print(f"{Fore.GREEN}Online: {stats['online']}{Style.RESET_ALL}")
    print(f"{Fore.RED}Offline: {stats['offline']}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Erros: {stats['erros']}{Style.RESET_ALL}")
    print(f"\nTempo total: {elapsed:.1f}s")
    print(f"\n{Fore.GREEN}✅ Todas as configurações foram salvas na pasta 'cache/'.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}O 'main.py' agora usará esses dados instantaneamente sem re-verificar!{Style.RESET_ALL}\n")

if __name__ == "__main__":
    if sys.platform == "win32":
        # Necessário para evitar erro de loop no Windows com muitas conexões
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    
    # Desativa logging de debug do bot para a saída ficar limpa
    runtime_config["DEBUG_MODE"] = False
    
    try:
        asyncio.run(run_bulk_check())
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Cancelado pelo usuário.{Style.RESET_ALL}")
