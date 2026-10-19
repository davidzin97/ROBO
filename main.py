# -*- coding: utf-8 -*-
"""
Ponto de entrada principal - Execução paralela com CLI

py main.py --platform 939bet --count 10000 --parallel 200 --no-gee-token --pix-type email --target 1000

py main.py --platform 707bet --count 10 --parallel 5
py main.py -P 707bet -c 100 -n 20
py main.py --url https://exemplo.com --count 5 --verbose
py main.py --list-platforms
  
"""
import argparse
import re
import asyncio
import json
import logging
import os
import sys

# Força UTF-8 no terminal do Windows para evitar UnicodeEncodeError com emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime
from typing import List

from config import BotConfig, GameConfig, GeeTokenConfig, ProxyConfig, SMSConfig, runtime_config
from bot import Bot, AccountData, run_bot, obter_config_plataforma
from colorama import Fore, Style, init

# Inicializa colorama para Windows
init()

# Habilita cores ANSI no Windows
if sys.platform == "win32":
    # Allows more than 64/1024 concurrent sockets on Windows
    pass  # asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # Deprecated in >=3.14, default since 3.8


# Configuração de logging
def setup_logging(verbose: bool = False):
    """Configura logging"""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Formato
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    
    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)
    
    # Reduz verbosidade de bibliotecas externas
    logging.getLogger("curl_cffi").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("PIL.PngImagePlugin").setLevel(logging.WARNING)
    logging.getLogger("PIL.Image").setLevel(logging.WARNING)


def _now() -> str:
    """Retorna timestamp formatado"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _format_brl(value: float) -> str:
    """Formata valor em BRL"""
    return f"R$ {value:.2f}"


def print_account_result(result: AccountData, bot_config: BotConfig):
    """Imprime resultado da conta no formato bonito"""
    bonus = result.bonus
    saldo_final = result.saldo
    success = saldo_final >= bot_config.game.subir_banca

    if bonus > 0:
        if success:
            color = Fore.LIGHTGREEN_EX
            saldo_color = Fore.LIGHTRED_EX
        else:
            color = Fore.LIGHTBLUE_EX
            saldo_color = Fore.LIGHTWHITE_EX
    else:
        color = Fore.LIGHTRED_EX
        saldo_color = Fore.LIGHTWHITE_EX

    # Extrai nome completo, pix e casa da conta
    nome = (result.nome_completo or "N/A").strip()
    pix = (result.pix or result.cpf or result.telefone or result.email or "N/A").strip()
    casa = (result.platform or getattr(bot_config, "platform_name", "") or result.sitecode or "N/A").strip()

    # Padding fixo para alinhar colunas de valores
    usuario_pad = f"{result.usuario:<16}"
    senha_pad = f"{result.senha:<16}"
    bonus_pad = f"{_format_brl(bonus):>5}"
    saldo_pad = f"{_format_brl(saldo_final):>6}"

    # COR ALTERADA AQUI 👇
    cor_titulo = '\033[38;2;255;255;0m'

    # Sufixo final da linha de log
    is_sunshine = getattr(bot_config.game, "sunshine_trava", False)
    if is_sunshine:
        # Sunshine: mostra NÃO ARMOU se não travou, nada se travou
        suffix = " | BÔNUS TRAVADO" if result.bonus_travado else " | NÃO ARMOU"
    elif result.bonus_travado:
        suffix = " | BÔNUS TRAVADO"
    elif success:
        suffix = " | META ATINGIDA"
    elif bonus == 0 and result.error:
        suffix = f" | {result.error}"
    elif bonus == 0:
        suffix = " | IP/SEM SALDO"
    else:
        suffix = ""

    log = (
        f"{cor_titulo}[{_now()}]{Style.RESET_ALL}"
        f" {cor_titulo}Nome: {Fore.LIGHTWHITE_EX}{nome}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Pix: {Fore.LIGHTWHITE_EX}{pix}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Casa: {Fore.LIGHTWHITE_EX}{casa}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Usuário: {Fore.LIGHTWHITE_EX}{usuario_pad}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Senha: {Fore.LIGHTWHITE_EX}{senha_pad}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Saque: {Fore.LIGHTWHITE_EX}{result.senha_saque}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Bônus: {Fore.LIGHTWHITE_EX}{bonus_pad}{Style.RESET_ALL} {color}|"
        f" {cor_titulo}Saldo: {saldo_color}{saldo_pad}{Style.RESET_ALL}"
        f"{color}{suffix}{Style.RESET_ALL}"
    )

    print(log)

async def run_single_bot(
    bot_config: BotConfig,
    semaphore: asyncio.Semaphore,
    index: int,
) -> AccountData:
    """Executa um bot com controle de concorrência"""
    async with semaphore:
        if runtime_config["DEBUG_MODE"]:
            logging.info(f" Iniciando bot #{index + 1}")
        
        result = await run_bot(bot_config)        
        # Sempre imprime resultado final no formato bonito
        if result.success:
            print_account_result(result, bot_config)
        else:
            if runtime_config["DEBUG_MODE"]:
                logging.warning(
                    f" Bot #{index + 1} falhou: {result.error} "
                    f"| Usuário: {result.usuario}"
                )
            #else:                
                #print( f"[{_now()}]  Usuario: {Fore.CYAN}{result.usuario}{Style.RESET_ALL} |  "Erro: {Fore.RED}{result.error}{Style.RESET_ALL}")
        
        return result


async def run_parallel_aguardar_codigo(
    bot_config: BotConfig,
    count: int,
    parallel: int,
) -> None:
    """
    Fluxo --aguardar-codigo em 3 fases:

    FASE 1 — Cria 'count' contas em paralelo (máx 'parallel') + configura saque.
             Aguarda todas terminarem antes de continuar.

    FASE 2 — Pede código no terminal. Resgata o código em todas as contas em
             paralelo. Exibe resumo: quantas tiveram saldo, quantas deram erro e
             qual foi o erro de cada uma.

    FASE 3 — Pergunta quantas contas em paralelo jogar. Joga apenas nas contas
             que obtiveram saldo com o código.
    """
    import time as _time
    from datetime import datetime

    cor_titulo  = "\033[38;2;255;20;147m"
    cor_cyan    = "\033[96m"
    cor_verde   = "\033[92m"
    cor_amarelo = "\033[93m"
    cor_vermelho= "\033[91m"
    cor_branco  = "\033[97m"
    cor_cinza   = "\033[90m"
    cor_azul    = "\033[94m"
    reset       = "\033[0m"

    def _sep(char="═", n=55, cor=cor_azul):
        print(f"{cor}{char * n}{reset}")

    # ──────────────────────────────────────────────────────────
    # FASE 1 — Criar contas + configurar saque
    # ──────────────────────────────────────────────────────────
    _sep()
    print(f"{cor_cyan}  ▶  FASE 1 — Criando {count} contas ({parallel} em paralelo){reset}")
    _sep()

    # Obtém config da plataforma uma vez
    platform_config = await obter_config_plataforma(bot_config.url, bot_config)
    if not platform_config:
        logging.error("Falha ao obter config da plataforma!")
        return

    semaphore_fase1 = asyncio.Semaphore(parallel)
    bots_criados: List["Bot"] = []          # Bots que tiveram conta criada com sucesso
    erros_fase1: int = 0
    lock_lista = asyncio.Lock()

    async def _criar_conta(idx: int):
        nonlocal erros_fase1
        async with semaphore_fase1:
            bot = Bot(bot_config)
            result = await bot.executar_criar_e_saque()
            async with lock_lista:
                if result.success and not result.error:
                    bots_criados.append(bot)
                    cor_titulo_l  = "\033[38;2;148;0;211m"
                    nome = (result.nome_completo or "N/A").strip()
                    pix = (result.pix or result.cpf or result.telefone or result.email or "N/A").strip()
                    casa = (result.platform or getattr(bot_config, "platform_name", "") or result.sitecode or "N/A").strip()
                    log = (
                        f"{cor_titulo_l}[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{reset}"
                        f" {cor_titulo_l}Nome: {Fore.LIGHTWHITE_EX}{nome}{reset} |"
                        f" {cor_titulo_l}Pix: {Fore.LIGHTWHITE_EX}{pix}{reset} |"
                        f" {cor_titulo_l}Casa: {Fore.LIGHTWHITE_EX}{casa}{reset} |"
                        f" {cor_titulo_l}Usuário: {Fore.LIGHTWHITE_EX}{result.usuario:<16}{reset} |"
                        f" {cor_titulo_l}Senha: {Fore.LIGHTWHITE_EX}{result.senha:<16}{reset} |"
                        f" {cor_titulo_l}Saque: {Fore.LIGHTWHITE_EX}{result.senha_saque}{reset}"
                        f" {Fore.LIGHTGREEN_EX}| ✅ CONTA CRIADA{reset}"
                    )
                    print(log)
                else:
                    erros_fase1 += 1
                    logging.warning(f"  [FASE1] Conta #{idx+1} falhou: {result.error}")

    tasks_fase1 = [_criar_conta(i) for i in range(count)]
    await asyncio.gather(*tasks_fase1, return_exceptions=True)

    print()
    _sep("-", 55, cor_cinza)
    print(f"  {cor_verde}Contas criadas com sucesso: {len(bots_criados)}{reset}")
    print(f"  {cor_vermelho}Erros na criação:           {erros_fase1}{reset}")
    _sep("-", 55, cor_cinza)

    if not bots_criados:
        print(f"\n{cor_vermelho}  Nenhuma conta foi criada. Abortando.{reset}\n")
        return

    # ──────────────────────────────────────────────────────────
    # FASE 2 — Aguardar código + resgatar
    # ──────────────────────────────────────────────────────────
    print()
    _sep()
    print(f"{cor_cyan}  ▶  FASE 2 — Aguardando código do Telegram{reset}")
    _sep()
    print(f"  {cor_branco}✅ {len(bots_criados)} conta(s) criadas e prontas.{reset}")
    print()

    code = ""
    while not code.strip():
        try:
            code = input(f"  {cor_amarelo}➤  Digite o código do Telegram e pressione ENTER: {reset}").strip()
        except EOFError:
            break
        if not code:
            print(f"  {cor_vermelho}  Código vazio! Tente novamente.{reset}")

    print()
    print(f"  {cor_verde}Código recebido: {Fore.LIGHTWHITE_EX}{code}{reset}")
    print(f"  {cor_cyan}Resgatando em {len(bots_criados)} conta(s)...{reset}")
    print()

    # Resgate em paralelo usando TODOS os bots com saldo
    # LIMITA A 250 PARA NÃO ESTOURAR O LIMITE DE SOCKETS DO WINDOWS (ValueError: too many file descriptors)
    safe_parallel = min(parallel, 250)
    semaphore_fase2 = asyncio.Semaphore(safe_parallel)
    contas_com_saldo: List["Bot"] = []      # Bots com resgate bem-sucedido
    erros_fase2: dict = {}                  # usuario -> mensagem_erro
    lock_fase2 = asyncio.Lock()

    async def _resgatar_codigo(bot: "Bot"):
        async with semaphore_fase2:
            try:
                ok, msg = await bot._resgatar_codigo_telegram(code)
                async with lock_fase2:
                    if ok:
                        contas_com_saldo.append(bot)
                        print(f"  {Fore.LIGHTGREEN_EX}✅ [{bot.usuario}] Código resgatado com sucesso!{reset}")
                    else:
                        erros_fase2[bot.usuario] = msg
                        print(f"  {Fore.LIGHTRED_EX}❌ [{bot.usuario}] Erro: {msg}{reset}")
            except Exception as e:
                async with lock_fase2:
                    erros_fase2[bot.usuario] = str(e)
                    print(f"  {Fore.LIGHTRED_EX}❌ [{bot.usuario}] Exceção: {e}{reset}")

    tasks_fase2 = [_resgatar_codigo(b) for b in bots_criados]
    await asyncio.gather(*tasks_fase2, return_exceptions=True)

    print()
    _sep("-", 55, cor_cinza)
    print(f"  {cor_verde}Contas com saldo (resgate OK): {len(contas_com_saldo)}{reset}")
    print(f"  {cor_vermelho}Erros no resgate:              {len(erros_fase2)}{reset}")
    if erros_fase2:
        print(f"  {cor_amarelo}Detalhes dos erros:{reset}")
        # Agrupa erros iguais para exibir resumido
        from collections import Counter
        contagem_erros = Counter(erros_fase2.values())
        for msg_err, qtd in contagem_erros.most_common():
            print(f"    {cor_vermelho}• {qtd}x — {msg_err}{reset}")
    _sep("-", 55, cor_cinza)

    if not contas_com_saldo:
        print(f"\n{cor_vermelho}  Nenhuma conta obteve saldo com o código. Encerrando.{reset}\n")
        return

    # ──────────────────────────────────────────────────────────
    # FASE 3 — Perguntar paralelo e jogar
    # ──────────────────────────────────────────────────────────
    print()
    _sep()
    print(f"{cor_cyan}  ▶  FASE 3 — Jogar nas {len(contas_com_saldo)} conta(s) com saldo{reset}")
    _sep()
    print(f"  {cor_branco}Quantas contas em paralelo deseja jogar?{reset}")
    print(f"  {cor_cinza}(máximo sugerido: {min(len(contas_com_saldo), parallel)}){reset}")
    print()

    parallel_jogo = 0
    while parallel_jogo <= 0:
        try:
            raw = input(f"  {cor_amarelo}➤  Paralelo para jogar: {reset}").strip()
            parallel_jogo = int(raw)
            if parallel_jogo <= 0:
                raise ValueError
        except (ValueError, EOFError):
            print(f"  {cor_vermelho}  Valor inválido! Digite um número positivo.{reset}")
            parallel_jogo = 0

    print()
    print(f"  {cor_verde}Iniciando jogo em {len(contas_com_saldo)} conta(s) com paralelo={parallel_jogo}...{reset}")
    print()

    semaphore_fase3 = asyncio.Semaphore(parallel_jogo)
    resultados_fase3: List[AccountData] = []
    lock_fase3 = asyncio.Lock()

    async def _jogar_conta(bot: "Bot", idx: int):
        async with semaphore_fase3:
            result = await bot.executar_jogar_direto()   # ← só joga, código já resgatado na FASE 2
            async with lock_fase3:
                resultados_fase3.append(result)
                # Imprime resultado no formato padrão
                if result.success:
                    print_account_result(result, bot_config)
                else:
                    if runtime_config.get("DEBUG_MODE"):
                        logging.warning(f"  [FASE3] Bot #{idx+1} falhou: {result.error} | {result.usuario}")

    tasks_fase3 = [_jogar_conta(b, i) for i, b in enumerate(contas_com_saldo)]
    await asyncio.gather(*tasks_fase3, return_exceptions=True)

    # ──────────────────────────────────────────────────────────
    # RESUMO FINAL
    # ──────────────────────────────────────────────────────────
    sucesso_jogo   = sum(1 for r in resultados_fase3 if r.success and r.saldo >= bot_config.game.subir_banca)
    bonus_travados = sum(1 for r in resultados_fase3 if r.bonus_travado)
    total_bonus    = sum(r.bonus for r in resultados_fase3 if r.success)
    total_saldo    = sum(r.saldo for r in resultados_fase3 if r.success)

    print()
    _sep()
    print(f"{cor_cyan}  RESUMO FINAL — AGUARDAR CÓDIGO{reset}")
    _sep()
    print(f"  {cor_branco}Contas criadas:        {cor_verde}{len(bots_criados)}{reset}")
    print(f"  {cor_branco}Código resgatado em:   {cor_verde}{len(contas_com_saldo)}{reset}")
    print(f"  {cor_branco}Jogaram:               {cor_amarelo}{len(resultados_fase3)}{reset}")
    print(f"  {cor_branco}Atingiram meta:        {cor_verde}{sucesso_jogo}{reset}")
    print(f"  {cor_branco}Bônus travados:        {cor_amarelo}{bonus_travados}{reset}")
    print()
    print(f"  {cor_branco}Total Bônus:           R$ {total_bonus:.2f}{reset}")
    print(f"  {cor_branco}Total Saldo:           R$ {total_saldo:.2f}{reset}")
    _sep()
    print()


async def run_parallel(
    bot_config: BotConfig,
    count: int,
    parallel: int,
) -> List[AccountData]:
    """
    Executa múltiplos bots em paralelo.
    
    Args:
        bot_config: Configuração base do bot
        count: Número total de contas a criar
        parallel: Número máximo de bots em paralelo
    
    Returns:
        Lista de resultados
    """
    import time
    import math
    from datetime import datetime
    from gee_token import get_gee_token_manager
    from bot import obter_config_plataforma
    
    start_time = time.time()
    start_datetime = datetime.now()
    
    # PASSO 0: Obter config da plataforma (testa APIs e seleciona a mais rápida)
    logging.info(f" ⚙️  Obtendo configuração da plataforma: {bot_config.url}")
    
    platform_config = await obter_config_plataforma(bot_config.url, bot_config)
    
    if not platform_config:
        logging.error(f" ❌ {Fore.RED}FALHA ao obter config da plataforma! Verifique a URL e o proxy.{Style.RESET_ALL}")
        logging.error(f"    URL: {bot_config.url}")
        return []
    
    logging.info(f" ✅ Plataforma OK — SiteCode: {Fore.CYAN}{platform_config.sitecode}{Style.RESET_ALL} | API: {platform_config.api_url}")
    logging.info(f" 🚀 Iniciando {Fore.YELLOW}{count}{Style.RESET_ALL} contas com {Fore.YELLOW}{parallel}{Style.RESET_ALL} em paralelo...")
    
    # PASSO 1: Obter geeTokens (se habilitado e não for individual)
    if bot_config.gee_token.enabled and not bot_config.gee_token.individual:
        tokens_necessarios = math.ceil(count / bot_config.gee_token.max_uses)
        max_browsers = 10  # Máximo de navegadores em paralelo
        
        if runtime_config["DEBUG_MODE"]:
            logging.info(" ==================================================")
            logging.info(f" PASSO 1: Obtendo geeTokens")
            logging.info(f"  {tokens_necessarios} tokens for {count} contas")
            logging.info(f"  Paralelo: max {min(tokens_necessarios, max_browsers)} navegadores")
            logging.info(" ==================================================")
        
        gee_manager = get_gee_token_manager(bot_config.gee_token, bot_config.proxy)
        
        # Semáforo para limitar navegadores em paralelo
        browser_semaphore = asyncio.Semaphore(max_browsers)
        
        async def fetch_single_token(index: int) -> tuple:
            """Busca um token com controle de concorrência"""
            async with browser_semaphore:
                if runtime_config["DEBUG_MODE"]:
                    logging.info(f" Buscando token {index + 1}/{tokens_necessarios}...")
                token = await gee_manager.get_token(bot_config.url, force_new=(index > 0))
                return index, token
        
        # Busca todos os tokens em paralelo
        token_start = time.time()
        tasks = [fetch_single_token(i) for i in range(tokens_necessarios)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        token_elapsed = time.time() - token_start
        
        # Processa resultados
        tokens_obtidos = 0
        for result in results:
            if isinstance(result, Exception):
                if runtime_config["DEBUG_MODE"]:
                    logging.error(f" Erro ao buscar token: {result}")
            else:
                index, token = result
                if token and token != "disabled":
                    tokens_obtidos += 1
                    if runtime_config["DEBUG_MODE"]:
                        logging.info(f" Token {index + 1} pronto: {token[:30]}...")
        
        if runtime_config["DEBUG_MODE"]:
            logging.info(f" Total: {tokens_obtidos} tokens em {token_elapsed:.1f}s (capacidade: {tokens_obtidos * bot_config.gee_token.max_uses} contas)")
    elif bot_config.gee_token.enabled or bot_config.gee_token.individual:
        if runtime_config["DEBUG_MODE"]:
            logging.info(" [!] ==================================================")
            logging.info(" [!] PASSO 1: geeToken INDIVIDUAL")
            logging.info(" [!]  Cada conta busca seu próprio token via API")
            logging.info(" [!] ==================================================")
    else:
        if runtime_config["DEBUG_MODE"]:
            logging.info(" [!] ==================================================")
            logging.info(" [!] PASSO 1: geeToken DESATIVADO")
            logging.info(" [!]  Usando 'disabled'")
            logging.info(" [!] ==================================================")
        
        # PASSO 2: Iniciar contas em paralelo
        #logging.info("=" * 50)
        #logging.info(f"PASSO 2: Iniciando {count} bots com {parallel} em paralelo")
        #logging.info("=" * 50)
    
    # Semáforo para controlar concorrência
    semaphore = asyncio.Semaphore(parallel)
    
    # Cria tasks
    tasks = [
        run_single_bot(bot_config, semaphore, i)
        for i in range(count)
    ]
    
    logging.info(f" ⏳ Executando {count} bots... aguarde os resultados.")
    # Executa todos
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Processa resultados
    success_count = 0
    fail_count = 0
    total_saldo = 0.0
    total_bonus = 0.0
    saldo_meta = 0.0
    bonus_travado = 0
    atingiram_meta = 0
    
    final_results = []
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            if runtime_config["DEBUG_MODE"]:
                logging.error(f" Bot #{i + 1} erro: {result}")
            fail_count += 1
            final_results.append(AccountData(error=str(result)))
        elif isinstance(result, AccountData):
            final_results.append(result)
            if result.success:
                success_count += 1
                total_saldo += result.saldo
                total_bonus += result.bonus
                if result.saldo >= bot_config.game.subir_banca:
                    atingiram_meta += 1
                    saldo_meta += result.saldo
                if result.bonus_travado:
                    bonus_travado += 1
                if result.bonus == 0:
                    fail_count += 1
            else:
                fail_count += 1
    
    # Calcula tempo
    end_time = time.time()
    end_datetime = datetime.now()
    elapsed = end_time - start_time
    contas_por_min = (count / elapsed) * 60 if elapsed > 0 else 0
    
    # Formata tempo de execução em Dias Horas Minutos Segundos
    def format_elapsed(seconds):
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        
        return " ".join(parts)
    
    elapsed_formatted = format_elapsed(elapsed)
    
    # Resumo estilizado
    print()
    print("\033[96m  RESUMO FINAL\033[0m")
    print("\033[94m" + "=" * 50 + "\033[0m")
    print()
    print(f"  \033[97mContas Criadas:\033[0m       \033[93m{success_count}\033[0m")
    print(f"  \033[92mAtingiram Meta:\033[0m       \033[92m{atingiram_meta}\033[0m")
    print(f"  \033[35mBonus Travado:\033[0m        \033[35m{bonus_travado}\033[0m")
    print(f"  \033[91mErros:\033[0m                \033[91m{fail_count}\033[0m")
    print()
    print("\033[94m" + "-" * 50 + "\033[0m")
    print()
    print(f"  \033[93mSoma Total Bonus:\033[0m     \033[97mR$ {total_bonus:.2f}\033[0m")
    print(f"  \033[96mSoma Total Saldos:\033[0m    \033[97mR$ {total_saldo:.2f}\033[0m")
    print(f"  \033[92mSoma Saldos (>=Meta):\033[0m \033[97mR$ {saldo_meta:.2f}\033[0m")
    print()
    print("\033[94m" + "-" * 50 + "\033[0m")
    print()
    print(f"  \033[90mInício:\033[0m    {start_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  \033[90mFinal:\033[0m     {end_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  \033[90mDuração:\033[0m   {elapsed_formatted} ({contas_por_min:.1f} contas/min)")
    print()
    print("\033[94m" + "=" * 50 + "\033[0m")
    print()
    
    return final_results



def parse_args():
    """Parse argumentos da linha de comando"""
    parser = argparse.ArgumentParser(
        description="Bot Python Assíncrono para automação",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py --platform 707bet --count 10 --parallel 5
  python main.py -P 707bet -c 100 -n 20
  python main.py --url https://exemplo.com --count 5 --verbose
  python main.py --list-platforms
        """
    )
    
    # URL da plataforma (opcional se --platform for usado)
    parser.add_argument(
        "--url", "-u",
        help="URL da plataforma (ex: https://d1kwyxjzq9j4uo.cloudfront.net)"
    )
    
    # Plataforma pelo nome (alternativa a --url)
    parser.add_argument(
        "--platform", "-P",
        help="Nome da plataforma (ex: 707bet, 8fclub)"
    )
    
    # Listar plataformas disponíveis
    parser.add_argument(
        "--list-platforms", "-l",
        action="store_true",
        help="Lista todas as plataformas disponíveis e sai"
    )
    
    # Buscar plataformas
    parser.add_argument(
        "--search-platform", "-s",
        help="Busca plataformas por nome parcial"
    )
    
    # Quantidade de contas
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=10,
        help="Número total de contas a criar (padrão: 10)"
    )
    
    # Paralelo
    parser.add_argument(
        "--parallel", "-n",
        type=int,
        default=5,
        help="Número máximo de bots em paralelo (padrão: 5)"
    )
    
    # Bet máxima
    parser.add_argument(
        "--bet-max",
        type=float,
        default=100.0,
        help="Aposta máxima (padrão: 10.0)"
    )
    
    # Subir banca
    parser.add_argument(
        "--target",
        type=float,
        default=1000.0,
        help="Saldo alvo para parar (padrão: 1000.0)"
    )
    
    # Tipo de saque
    parser.add_argument(
        "--pix-type",
        choices=["cpf", "telefone", "email"],
        default="cpf",
        help="Tipo de chave PIX (padrão: cpf)"
    )

    parser.add_argument(
        "--sms",
        type=int,
        choices=[0, 1],
        default=0,
        help="Ativa fluxo de verificação via SMS (0=desativado, 1=ativado)"
    )
    
    # Invite ID (código de convite/afiliado)
    parser.add_argument(
        "--invite-id", "-i",
        help="ID do convite/afiliado (ex: 123456)"
    )
    
    # Proxy
    parser.add_argument(
        "--proxy",
        help="Proxy no formato usuario:senha@host:porta"
    )
    
    # Max uses do geeToken
    parser.add_argument(
        "--gee-max-uses",
        type=int,
        default=100,
        help="Máximo de contas por geeToken (padrão: 100)"
    )
    
    # Desativar geeToken
    parser.add_argument(
        "--no-gee-token",
        action="store_true",
        default=False,
        help="Desativa geeToken (usa 'disabled')"
    )
    
    # geeToken individual (um por conta via API)
    parser.add_argument(
        "--gee-token-individual",
        action="store_true",
        default=False,
        help="Busca geeToken individual para cada conta via API (não usa cache)"
    )
    
    parser.add_argument(
        "--no-save-db",
        action="store_true",
        default=False,
        help="Desativa salvamento de contas no banco SQLite"
    )
    
    # Gem Trava (desabilitado por padrão)
    parser.add_argument(
        "--gem-trava",
        action="store_true",
        default=False,
        help="Ativa o modo Gem Trava (tenta travar bônus no Gem Saviour, saldo 50-1000)"
    )
    
    # Hood vs Wolf Trava (desabilitado por padrão)
    parser.add_argument(
        "--hood-trava",
        action="store_true",
        default=False,
        help="Ativa o modo Hood vs Wolf Trava (tenta travar bônus, saldo 250-1000)"
    )
    
    # Desativar proxy
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        default=False,
        help="Desativa o uso de proxy (padrão: ativada)"
    )

    # Double Fortune Trava (ex: --double "fortune-trava-bet 0.9")
    parser.add_argument(
        "--double",
        help="Ativa o modo Double Fortune Trava (ex: --double \"fortune-trava-bet 0.9\")"
    )

    # Ganesha Gold Trava (ex: --ganesha "ganesha-trava-bet 2.0")
    parser.add_argument(
        "--ganesha",
        help="Ativa o modo Ganesha Gold Trava (ex: --ganesha \"ganesha-trava-bet 2.0\")"
    )

    # Emperor's Favour Trava (ex: --emperor "emperor-trava-bet 12")
    parser.add_argument(
        "--emperor",
        help="Ativa o modo Emperor's Favour Trava (ex: --emperor \"emperor-trava-bet 12\")"
    )

    # Sunshine Coast Trava (ex: --sunshine "sunshine-armar-bet 0.5")
    parser.add_argument(
        "--sunshine",
        help="Ativa o modo Sunshine Coast Trava (ex: --sunshine \"sunshine-armar-bet 0.5\")"
    )

    # Journey to the Wealth Trava (ex: --journey "journey-trava-bet 0.4")
    parser.add_argument(
        "--journey",
        help="Ativa o modo Journey to the Wealth Trava (ex: --journey \"journey-trava-bet 0.4\")"
    )

    # Fire Strike 2 All-Win (Modo subir saldo)
    parser.add_argument(
        "--firestrike",
        action="store_true",
        help="Ativa o modo Fire Strike 2 All-Win para subir saldo"
    )

    # Fire 88 All-Win (Modo subir saldo)
    parser.add_argument(
        "--fire88",
        action="store_true",
        help="Ativa o modo Fire 88 All-Win para subir saldo"
    )

    # Spirit of Adventure Trava (ex: --spirit "spirit-trava-bet 10")
    parser.add_argument(
        "--spirit",
        help="Ativa o modo Spirit of Adventure Trava (ex: --spirit \"spirit-trava-bet 10\")"
    )

    # Voodoo Magic Trava (ex: --voodoo "voodoo-trava-bet 0.40")
    parser.add_argument(
        "--voodoo",
        help="Ativa o modo Voodoo Magic Trava (ex: --voodoo \"voodoo-trava-bet 0.40\")"
    )

    # Muertos Multiplier Megaways Trava (ex: --muertos "muertos-trava-bet 0.40")
    parser.add_argument(
        "--muertos",
        help="Ativa o modo Muertos Multiplier Megaways Trava (ex: --muertos \"muertos-trava-bet 0.40\")"
    )

    # Pure Platinum Trava (ex: --pure-platinum "pure-platinum-trava-bet 2.0")
    parser.add_argument(
        "--pure-platinum",
        help="Ativa o modo Pure Platinum Trava (ex: --pure-platinum \"pure-platinum-trava-bet 2.0\")"
    )

    # Diamond Cluster Luck Trava (ex: --diamond "diamond-trava-bet 0.40")
    parser.add_argument(
        "--diamond",
        help="Ativa o modo Diamond Cluster Luck Trava (ex: --diamond \"diamond-trava-bet 0.40\")"
    )
    
    # Lucky Charm Trava (ex: --charm "charm-trava-bet 0.40")
    parser.add_argument(
        "--charm",
        help="Ativa o modo Lucky Charm Trava (ex: --charm \"charm-trava-bet 0.40\")"
    )

    # Treasure House Trava (ex: --treasure-house "treasure-house-trava-bet 2.0" ou --treasure-house "trava bet de 2")
    parser.add_argument(
        "--treasure-house",
        nargs="?",
        const="2.0",
        help="Ativa o modo Treasure House Trava (ex: --treasure-house \"treasure-house-trava-bet 2.0\")"
    )
    
    # Output
    parser.add_argument(
        "--output", "-o",
        default="resultados.json",
        help="Arquivo de saída JSON (padrão: resultados.json)"
    )

    # Bet Aleatória
    parser.add_argument(
        "--bet-aleatoria",
        action="store_true",
        default=False,
        help="Escolhe bet aleatória acima de 12 nos jogos suportados"
    )
    
    # Verbose
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Modo verbose (debug)"
    )
    
    # Quiet mode - só mostra resultado final
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Modo silencioso - só mostra resultado final de cada conta"
    )
    
    # Loop infinito - joga até zerar saldo (desativado por padrão)
    parser.add_argument(
        "--loop-infinito",
        action="store_true",
        help="Ativa loop infinito (joga até zerar saldo, sem limite de ciclos)"
    )

    # Código do Telegram
    parser.add_argument(
        "--codigo",
        help="Código de resgate do Telegram (ativa o fluxo de resgate ao invés do bônus padrão)"
    )

    # Aguardar código (fluxo 3 fases: criar contas → esperar código → resgatar → jogar)
    parser.add_argument(
        "--aguardar-codigo",
        action="store_true",
        default=False,
        help="Modo 3 fases: cria contas+saque, aguarda código no terminal, resgata e joga"
    )


    # Triple Tigers Recuperação
    parser.add_argument(
        "--10-cetavo",
        dest="recuperar_pp",
        action="store_true",
        default=False,
        help="Ativa a recuperação no Triple Tigers com saldo < 0.30 (aposta de 0.10)"
    )

    
    args = parser.parse_args()
    
    # Listar plataformas
    if args.list_platforms:
        from platforms import list_platforms
        print("\n[LISTA] Plataformas disponiveis:\n")
        platforms = list_platforms()
        # Exibe em colunas
        cols = 5
        for i in range(0, len(platforms), cols):
            row = platforms[i:i+cols]
            print("  " + "  ".join(f"{p:<15}" for p in row))
        print(f"\n  Total: {len(platforms)} plataformas\n")
        import sys
        sys.exit(0)
    
    # Buscar plataformas
    if args.search_platform:
        from platforms import search_platforms
        results = search_platforms(args.search_platform)
        if results:
            print(f"\n[BUSCA] Plataformas encontradas para '{args.search_platform}':\n")
            for p in results:
                print(f"  - {p.name:<15} -> {p.site}")
            print(f"\n  Total: {len(results)} resultado(s)\n")
        else:
            print(f"\n[ERRO] Nenhuma plataforma encontrada para '{args.search_platform}'\n")
        import sys
        sys.exit(0)
    
    # Validação: precisa de --url ou --platform
    if not args.url and not args.platform:
        parser.error("É necessário fornecer --url ou --platform")
    
    # Se usar --platform, resolve para URL
    if args.platform:
        from platforms import get_platform_by_name
        platform = get_platform_by_name(args.platform)
        if not platform:
            from platforms import search_platforms
            sugestoes = search_platforms(args.platform[:3])
            msg = f"Plataforma não encontrada: {args.platform}"
            if sugestoes:
                msg += f"\n  Sugestões: {', '.join(p.name for p in sugestoes[:5])}"
            parser.error(msg)
        
        # Define URL a partir da plataforma
        args.url = platform.site if platform.site.startswith("http") else f"https://{platform.site}"
        args.platform_record = platform
    else:
        args.platform_record = None
    
    # Adiciona invite_id à URL se fornecido
    if args.invite_id:
        # Garante que a URL termina com / antes de adicionar parâmetros
        if "?" in args.url:
            args.url = f"{args.url}&id={args.invite_id}"
        else:
            # Adiciona / se não terminar com /
            if not args.url.endswith("/"):
                args.url = f"{args.url}/"
            args.url = f"{args.url}?id={args.invite_id}"
    
    args.game = "aleatorio"
    
    return args


def build_config(args) -> BotConfig:
    """Constrói configuração a partir dos argumentos"""
    # Proxy config (ativada por padrão, --no-proxy desativa)
    usar_proxy = not args.no_proxy
    proxy_config = ProxyConfig(usar_proxy=usar_proxy)
    
    # Se --proxy com string customizada
    if args.proxy and usar_proxy:
        # Parse proxy string: usuario:senha@host:porta
        try:
            auth, hostport = args.proxy.rsplit("@", 1)
            username, password = auth.split(":", 1)
            host, port = hostport.rsplit(":", 1)
            proxy_config = ProxyConfig(
                host=host,
                port=int(port),
                username=username,
                password=password,
                usar_proxy=True,
            )
        except ValueError:
            logging.warning(f" [!] Proxy inválido: {args.proxy}, usando padrão")
    
    # GeeToken config
    # Prioridade: 1) --no-gee-token (linha de comando), 2) plataforma, 3) padrão (True)
    gee_enabled = True
    if args.no_gee_token:
        gee_enabled = False  # Linha de comando tem prioridade
    elif args.platform_record:
        gee_enabled = args.platform_record.gee_token  # Usa config da plataforma
    
    # Individual: cada conta busca seu próprio token via API
    gee_individual = args.gee_token_individual
    
    gee_config = GeeTokenConfig(
        enabled=gee_enabled,
        individual=gee_individual,
        max_uses=args.gee_max_uses,
    )
    
    # Game config
    game_config = GameConfig(
        nome_jogo=args.game,
        subir_banca=args.target,
        bet_maxima=args.bet_max,
        tipo_saque=args.pix_type,
        loop_infinito=args.loop_infinito,
        gem_trava=args.gem_trava,
        hood_trava=args.hood_trava,
        bet_aleatoria=args.bet_aleatoria,
        triple_tigers_recuperacao=args.recuperar_pp,
    )

    # Double Fortune Trava logic
    if args.double:
        # Extrai bet usando regex (ex: "fortune-trava-bet 0.9")
        match = re.search(r"fortune-trava-bet\s+([\d.]+)", str(args.double), re.IGNORECASE)
        if match:
            game_config.double_fortune_trava = True
            game_config.fortune_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Double Fortune"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Double Fortune Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.fortune_trava_bet:.2f}")

    # Ganesha Gold Trava logic
    if args.ganesha:
        # Extrai bet usando regex (ex: "ganesha-trava-bet 2.0")
        match = re.search(r"ganesha-trava-bet\s+([\d.]+)", str(args.ganesha), re.IGNORECASE)
        if match:
            game_config.ganesha_gold_trava = True
            game_config.ganesha_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Ganesha Gold"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Ganesha Gold Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.ganesha_trava_bet:.2f}")

    # Emperor's Favour Trava logic
    if args.emperor:
        # Extrai bet usando regex (ex: "emperor-trava-bet 12")
        match = re.search(r"emperor-trava-bet\s+([\d.]+)", str(args.emperor), re.IGNORECASE)
        if match:
            game_config.emperor_favour_trava = True
            game_config.emperor_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Emperor's Favour"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Emperor's Favour Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.emperor_trava_bet:.2f}")

    # Sunshine Coast Trava logic
    if args.sunshine:
        # Extrai bet usando regex (ex: "sunshine-armar-bet 0.5")
        match_bet = re.search(r"sunshine-armar-bet\s+([\d.,]+)", str(args.sunshine), re.IGNORECASE)
        match_aleatoria = re.search(r"sunshine-aleatoria\s+([\d.,]+)", str(args.sunshine), re.IGNORECASE)
        
        if match_bet:
            game_config.sunshine_trava = True
            game_config.sunshine_trava_bet = float(match_bet.group(1).replace(",", "."))
            game_config.nome_jogo = "Sunshine Coast"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Sunshine Coast Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.sunshine_trava_bet:.2f}")
        elif match_aleatoria:
            game_config.sunshine_trava = True
            game_config.sunshine_aleatoria = True
            game_config.sunshine_min_bet = float(match_aleatoria.group(1).replace(",", "."))
            game_config.nome_jogo = "Sunshine Coast"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Sunshine Coast Trava (ALEATÓRIA){Style.RESET_ALL} ATIVO | Mínimo R$ {game_config.sunshine_min_bet:.2f}")

    # Journey to the Wealth Trava logic
    if args.journey:
        # Extrai bet usando regex (ex: "journey-trava-bet 0.4")
        match = re.search(r"journey-trava-bet\s+([\d.]+)", str(args.journey), re.IGNORECASE)
        if match:
            game_config.journey_to_the_wealth_trava = True
            game_config.journey_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Journey to the Wealth"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Journey to the Wealth Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.journey_trava_bet:.2f}")

    # Fire Strike 2 All-Win logic
    if args.firestrike:
        game_config.firestrike_trava = True
        game_config.firestrike_trava_bet = 0.0 # 0.0 significa All-Win sem limite
        game_config.nome_jogo = "Fire Strike 2"
        logging.info(f" 🔥 Modo {Fore.YELLOW}Fire Strike 2 All-Win{Style.RESET_ALL} ATIVO (Subir Saldo)")

    # Fire 88 All-Win logic
    if getattr(args, 'fire88', False):
        game_config.fire88_trava = True
        game_config.fire88_trava_bet = 0.0 # 0.0 significa All-Win sem limite
        game_config.nome_jogo = "Fire 88"
        logging.info(f" 🔥 Modo {Fore.YELLOW}Fire 88 All-Win{Style.RESET_ALL} ATIVO (Subir Saldo)")

    # Spirit of Adventure Trava logic
    if args.spirit:
        # Extrai bet usando regex (ex: "spirit-trava-bet 10")
        match = re.search(r"spirit-trava-bet\s+([\d.]+)", str(args.spirit), re.IGNORECASE)
        if match:
            game_config.spirit_trava = True
            game_config.spirit_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Spirit of Adventure"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Spirit of Adventure Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.spirit_trava_bet:.2f}")

    # Voodoo Magic Trava logic
    if args.voodoo:
        # Extrai bet usando regex (ex: "voodoo-trava-bet 0.40")
        match = re.search(r"voodoo-trava-bet\s+([\d.]+)", str(args.voodoo), re.IGNORECASE)
        if match:
            game_config.voodoo_trava = True
            game_config.voodoo_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Voodoo Magic"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Voodoo Magic Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.voodoo_trava_bet:.2f}")

    # Muertos Multiplier Megaways Trava logic
    if args.muertos:
        match = re.search(r"muertos-trava-bet\s+([\d.]+)", str(args.muertos), re.IGNORECASE)
        if match:
            game_config.muertos_trava = True
            game_config.muertos_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Muertos Multiplier Megaways"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Muertos Multiplier Megaways Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.muertos_trava_bet:.2f}")

    # Pure Platinum Trava logic
    if getattr(args, 'pure_platinum', None):
        match = re.search(r"pure-platinum-trava-bet\s+([\d.]+)", str(args.pure_platinum), re.IGNORECASE)
        if match:
            game_config.pure_platinum_trava = True
            game_config.pure_platinum_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Pure Platinum"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Pure Platinum Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.pure_platinum_trava_bet:.2f}")

    # Diamond Cluster Luck Trava logic
    if getattr(args, 'diamond', None):
        match = re.search(r"diamond-trava-bet\s+([\d.]+)", str(args.diamond), re.IGNORECASE)
        if match:
            game_config.diamond_trava = True
            game_config.diamond_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Diamond Cluster Luck"
            logging.info(f" 💎 Modo {Fore.YELLOW}Diamond Cluster Luck Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.diamond_trava_bet:.2f}")

    # Lucky Charm Trava logic
    if getattr(args, 'charm', None):
        match = re.search(r"charm-trava-bet\s+([\d.]+)", str(args.charm), re.IGNORECASE)
        if match:
            game_config.charm_trava = True
            game_config.charm_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Lucky Charm"
            logging.info(f" 🍀 Modo {Fore.YELLOW}Lucky Charm Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.charm_trava_bet:.2f}")

    # Treasure House Trava logic
    if getattr(args, 'treasure_house', None):
        val_str = str(args.treasure_house)
        match = re.search(r"(?:treasure-house-trava-bet|trava\s+bet\s+de|bet\s+de|bet)\s+([\d.,]+)", val_str, re.IGNORECASE) or re.search(r"([\d.,]+)", val_str)
        if match:
            bet_val = float(match.group(1).replace(",", "."))
        else:
            bet_val = 2.0
        game_config.treasure_house_trava = True
        game_config.treasure_house_trava_bet = bet_val
        game_config.nome_jogo = "Treasure House"
        logging.info(f" 🏠 Modo {Fore.YELLOW}Treasure House Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.treasure_house_trava_bet:.2f}")

    sms_config = SMSConfig(
        verificar_sms=(args.sms == 1),
        provedora="sms24h",
        api_sms24h=(os.environ.get("SMS24_KEY") or SMSConfig().api_sms24h),
    )
    
    # Nome da plataforma
    platform_name = args.platform_record.name if args.platform_record else ""
    

    return BotConfig(
        url=args.url,
        platform_name=platform_name,
        parallel_count=args.parallel,
        total_accounts=args.count,
        save_to_db=not args.no_save_db,
        proxy=proxy_config,
        gee_token=gee_config,
        game=game_config,
        sms=sms_config,
        telegram_code=args.codigo or "",
    )







async def main():
    """Função principal"""
    args = parse_args()
    
    # Configura modo debug
    if args.verbose:
        runtime_config["DEBUG_MODE"] = True
    if args.quiet:
        runtime_config["DEBUG_MODE"] = False
    
    # Setup logging
    setup_logging(args.verbose)
    
    if runtime_config["DEBUG_MODE"]:
        logging.info(" ==================================================")
        logging.info(" BOT PYTHON ASSÍNCRONO")
        logging.info(" ==================================================")
        if args.platform_record:
            logging.info(f" Plataforma: {args.platform_record.name}")
        logging.info(f" URL: {args.url}")
        logging.info(f" Contas: {args.count}")
        logging.info(f" Paralelo: {args.parallel}")
        logging.info(f" Jogo: Aleatório")
        logging.info(f" Bet máxima: R$ {args.bet_max:.2f}")
        logging.info(f" Saldo alvo: R$ {args.target:.2f}")
        logging.info(f" geeToken max uses: {args.gee_max_uses}")
        logging.info(" ==================================================")
    
    # Cria diretórios necessários
    os.makedirs("cache", exist_ok=True)
    
    # Constrói configuração
    bot_config = build_config(args)
    
    # ===== VERIFICAÇÃO DE PROXY =====
    if bot_config.proxy.usar_proxy:
        logging.info(" Verificando proxy...")
        
        max_tentativas = 3
        for tentativa in range(1, max_tentativas + 1):
            sucesso, ip, mensagem = bot_config.proxy.verificar_proxy(timeout=15)
            if sucesso:
                logging.info(f" Proxy OK - IP: {Fore.GREEN}{ip}{Style.RESET_ALL} (Tentativa {tentativa})")
                break
            else:
                logging.warning(f" Falha ao verificar proxy (Tentativa {tentativa}/{max_tentativas}): {mensagem}")
                if tentativa < max_tentativas:
                    import time
                    time.sleep(3)
        
        if not sucesso:
            logging.error(f" {Fore.RED}PROXY OFFLINE OU CREDENCIAIS INVALIDAS{Style.RESET_ALL}")
            logging.error(f" {mensagem}")
            logging.error(f" Host: {bot_config.proxy.host}:{bot_config.proxy.port}")
            logging.error(f" Usuario: {bot_config.proxy.username}")
            logging.info(" Verifique as credenciais do proxy em config.py")
            logging.info(" Ou desative o proxy com: usar_proxy = False")
            sys.exit(1)
    else:
        logging.info(f" Proxy {Fore.YELLOW}DESATIVADO{Style.RESET_ALL} - usando IP local")
    
    # Executa
    if args.aguardar_codigo:
        await run_parallel_aguardar_codigo(bot_config, args.count, args.parallel)
        return 0

    results = await run_parallel(bot_config, args.count, args.parallel)
    
    # Contas são salvas em tempo real pelo bot quando atingem a meta
    
    # Retorna código de saída
    success_count = sum(1 for r in results if r.success)
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logging.info(" Interrompido pelo usuário")
        sys.exit(130)
    except Exception as e:
        logging.error(f" Erro fatal: {e}")
        sys.exit(1)
