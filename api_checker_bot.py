# -*- coding: utf-8 -*-
"""
Verificador de API independente
Usa as mesmas funções do bot para extrair config e testar APIs

Principal função: testar qual API é mais rápida
"""
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Configura logging para ver os testes de velocidade
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Importa as funções do bot
from bot import (
    obter_config_plataforma,
    _fetch_platform_config_standalone,
    _test_fastest_domain_standalone,
    PlatformConfig
)
from config import BotConfig


@dataclass
class CheckResult:
    """Resultado da verificação"""
    url: str
    config: Optional[PlatformConfig] = None
    error: str = ""
    checked_at: str = ""


async def check_platform(url: str, fresh: bool = False) -> CheckResult:
    """
    Verifica uma plataforma usando as funções do bot.
    
    Args:
        url: URL da plataforma
        fresh: Se True, ignora cache e força teste de velocidade
        
    Returns:
        CheckResult com configuração extraída
    """
    result = CheckResult(
        url=url,
        checked_at=datetime.now().isoformat()
    )
    
    # Cria config mínima (usa defaults)
    config = BotConfig(url=url)
    
    try:
        print(f"\n🔍 Verificando: {url}")
        if fresh:
            print("🔄 Modo FRESH: ignorando cache, testando APIs...\n")
        print()
        
        if fresh:
            # Usa função standalone (sem cache) - mostra teste de velocidade
            platform_config = await _fetch_platform_config_standalone(url, config)
        else:
            # Usa função com cache
            platform_config = await obter_config_plataforma(url, config)
        
        if platform_config:
            result.config = platform_config
        else:
            result.error = "Não foi possível obter configuração"
            
    except Exception as e:
        result.error = str(e)
    
    return result


def print_result(result: CheckResult):
    """Imprime resultado da verificação"""
    print("\n" + "="*70)
    print("📊 RESULTADO DA VERIFICAÇÃO")
    print("="*70)
    print(f"📅 Verificado em: {result.checked_at}")
    print(f"🌐 URL: {result.url}")
    print("-"*70)
    
    if result.error:
        print(f"❌ ERRO: {result.error}")
    elif result.config:
        cfg = result.config
        print(f"✅ Status: Online")
        print(f"🔑 SiteCode: {cfg.sitecode}")
        print(f"🏠 URL Domain: {cfg.url_domain}")
        print(f"🚀 API MAIS RÁPIDA: {cfg.api_url}")
        print(f"🌐 Host: {cfg.host}")
        print(f"📦 Speed Version: {cfg.speed_version}")
        print(f"📱 App Version: {cfg.app_version}")
        if cfg.inviter_id:
            print(f"� Inviter ID: {cfg.inviter_id}")
    else:
        print("❌ Configuração não disponível")
    
    print("="*70)


def save_result(result: CheckResult, filename: str = "platform_config.json"):
    """Salva resultado em JSON"""
    data = {
        "url": result.url,
        "checked_at": result.checked_at,
        "error": result.error,
    }
    
    if result.config:
        cfg = result.config
        data["config"] = {
            "sitecode": cfg.sitecode,
            "url_domain": cfg.url_domain,
            "api_url": cfg.api_url,
            "host": cfg.host,
            "speed_version": cfg.speed_version,
            "app_version": cfg.app_version,
            "inviter_id": cfg.inviter_id
        }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Salvo em: {filename}")


async def main():
    """Função principal"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Verificador de API - Usa as mesmas funções do bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python api_checker.py https://took.333betapp.cc
  python api_checker.py https://example.com --save
        """
    )
    
    parser.add_argument("url", type=str, help="URL da plataforma")
    parser.add_argument("-c", "--cached", action="store_true",
                       help="Usa cache (padrão: ignora cache e testa velocidade das APIs)")
    parser.add_argument("-s", "--save", action="store_true", 
                       help="Salva resultado em JSON")
    parser.add_argument("-o", "--output", type=str, default="platform_config.json",
                       help="Arquivo de saída")
    
    args = parser.parse_args()
    
    result = await check_platform(args.url, fresh=not args.cached)
    print_result(result)
    
    if args.save:
        save_result(result, args.output)
    
    return result


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    
    asyncio.run(main())
