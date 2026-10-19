# -*- coding: utf-8 -*-
"""
Ponto de entrada principal - Execução paralela com CLI + Multiprocessamento

py main.py --platform 939bet --count 10000 --parallel 200 --no-gee-token --pix-type email --target 1000

py main.py --platform 707bet --count 10 --parallel 5
py main.py -P 707bet -c 100 -n 20
py main.py --url https://exemplo.com --count 5 --verbose
py main.py --list-platforms
  
"""
import argparse
import asyncio
import ctypes
import json
import logging
import math
import multiprocessing
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any, List, Dict

from config import BotConfig, GameConfig, GeeTokenConfig, ProxyConfig, SMSConfig, runtime_config
from bot import Bot, AccountData, run_bot, obter_config_plataforma
from colorama import Fore, Style, init

# Inicializa colorama para Windows
init()

# Habilita cores ANSI e aumenta limite de conexões no Windows
if sys.platform == "win32":
    os.system("")  # Habilita ANSI escape codes
    # Allows more than 64/1024 concurrent sockets on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Flag global para interrupção (Ctrl+C)
_interrupted = False
_pool = None  # Referência ao pool de processos


# Configuração de logging
def setup_logging(verbose: bool = False):
    """Configura logging para os processos"""
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
    if root.handlers:
        root.handlers = []
    root.setLevel(level)
    root.addHandler(console)
    
    # Reduz verbosidade de bibliotecas externas
    logging.getLogger("curl_cffi").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


def _now() -> str:
    """Retorna timestamp formatado"""
    return datetime.now().strftime("%d/%m %H:%M")


def _format_brl(value: float) -> str:
    """Formata valor em BRL"""
    return f"R$ {value:.2f}"


def print_account_result(result: AccountData, bot_config: BotConfig):
    """Imprime resultado da conta no formato bonito"""
    bonus = result.bonus
    saldo_final = result.saldo
    success = saldo_final >= bot_config.game.subir_banca
    
    # Extrai nome completo, pix e casa da conta
    nome = (result.nome_completo or "N/A").strip()
    pix = (result.pix or result.cpf or result.telefone or result.email or "N/A").strip()
    casa = (result.platform or getattr(bot_config, "platform_name", "") or result.sitecode or "N/A").strip()

    # Padding fixo para alinhar colunas de valores
    usuario_pad = f"{result.usuario:<16}"
    senha_pad = f"{result.senha:<16}"
    bonus_pad = f"{_format_brl(bonus):>5}"
    saldo_pad = f"{_format_brl(saldo_final):>6}"
    
    ORANGE = '\033[38;5;208m'
    color = ORANGE
    
    # Sufixo final da linha de log
    is_sunshine = getattr(bot_config.game, "sunshine_trava", False)
    if is_sunshine:
        suffix = "" if result.bonus_travado else " | NÃO ARMOU"
    elif bonus == 0:
        suffix = " | IP/SEM BONUS"
    else:
        suffix = ""

    log = (
        f"{ORANGE}[{_now()}]{Style.RESET_ALL}"
        f" {ORANGE}Nome: {Fore.LIGHTWHITE_EX}{nome}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Pix: {Fore.LIGHTWHITE_EX}{pix}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Casa: {Fore.LIGHTWHITE_EX}{casa}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Usuário: {Fore.LIGHTWHITE_EX}{usuario_pad}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Senha: {Fore.LIGHTWHITE_EX}{senha_pad}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Saque: {Fore.LIGHTWHITE_EX}{result.senha_saque}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Bônus: {Fore.WHITE}{bonus_pad}{Style.RESET_ALL} {color}|"
        f" {ORANGE}Saldo: {Fore.WHITE}{saldo_pad}{Style.RESET_ALL}"
        f"{color}{suffix}{Style.RESET_ALL}"
    )
    
    print(log)


def update_console_title(stats: Dict, platform_name: str = ""):
    """Atualiza título do console com estatísticas em tempo real"""
    c = stats.get('criadas', 0)
    s = stats.get('sucesso', 0)
    e = stats.get('erros', 0)
    v = int(stats.get('saldo', 0))
    m = stats.get('meta', 0)
    t = stats.get('travado', 0)
    
    plat = f" | {platform_name}" if platform_name else ""
    title = f"FlashAPI{plat} | Criadas:{c} | Meta:{m} | Travado:{t} | Erros:{e} | R${v}"
    
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except:
            pass
    else:
        sys.stdout.write(f"\033]2;{title}\007")
        try:
            sys.stdout.flush()
        except:
            pass


async def run_worker(
    queue: asyncio.Queue,
    bot_config: BotConfig,
    results_list: List[AccountData],
    worker_id: int,
    total_count: int,
    atingiram_meta_ref: List[int],
    shared_stats: Any = None,
    shared_lock: Any = None,
    local_stats: Dict = None
) -> None:
    """Worker que processa contas da fila"""
    global _interrupted
    while True:
        try:
            # Verifica se foi interrompido
            if _interrupted:
                break
                
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            
            # Verifica novamente antes de processar
            if _interrupted:
                queue.task_done()
                break
            
            result = await run_bot(bot_config)
            results_list.append(result)
            
            # Pequeno delay após processar para aliviar o proxy
            await asyncio.sleep(0.1)
            
            # Atualiza Estatísticas
            if shared_stats is not None and shared_lock is not None:
                # Modo multiprocessamento - estatísticas compartilhadas
                with shared_lock:
                    shared_stats['criadas'] += 1
                    if result.success:
                        shared_stats['sucesso'] += 1
                        shared_stats['saldo'] += result.saldo
                        shared_stats['bonus'] += result.bonus
                        if result.saldo >= bot_config.game.subir_banca:
                            shared_stats['meta'] += 1
                            shared_stats['saldo_meta'] += result.saldo
                        if result.bonus_travado:
                            shared_stats['travado'] += 1
                        if result.bonus == 0:
                            shared_stats['erros'] += 1
                    else:
                        shared_stats['erros'] += 1
                    
                    update_console_title(dict(shared_stats), bot_config.platform_name)
            elif local_stats is not None:
                # Modo async simples - estatísticas locais
                local_stats['criadas'] += 1
                if result.success:
                    local_stats['sucesso'] += 1
                    local_stats['saldo'] += result.saldo
                    if result.saldo >= bot_config.game.subir_banca:
                        local_stats['meta'] += 1
                    if result.bonus_travado:
                        local_stats['travado'] += 1
                    if result.bonus == 0:
                        local_stats['erros'] += 1
                else:
                    local_stats['erros'] += 1
                
                update_console_title(local_stats, bot_config.platform_name)

            if result.success:
                if result.saldo >= bot_config.game.subir_banca:
                    atingiram_meta_ref[0] += 1
                
                if not runtime_config.get("QUIET_MODE") or result.saldo >= bot_config.game.subir_banca:
                    print_account_result(result, bot_config)
            else:
                if not runtime_config.get("QUIET_MODE"):
                    print(f"[{_now()}] {Fore.RED}[XX]{Style.RESET_ALL} Usuario: {result.usuario} | Erro: {result.error}")

            queue.task_done()
        except Exception as e:
            logging.error(f"❌ Erro no worker: {e}")
            try:
                queue.task_done()
            except:
                pass


async def run_parallel_async(
    bot_config: BotConfig,
    count: int,
    parallel: int,
    process_id: int,
    shared_stats: Any = None,
    shared_lock: Any = None
) -> List[AccountData]:
    """Loop assíncrono interno de cada processo"""
    # Garante que não temos mais workers que contas
    actual_parallel = min(parallel, count) if count > 0 else 1
    
    queue = asyncio.Queue()
    for i in range(count):
        queue.put_nowait(i)
    for _ in range(actual_parallel):
        queue.put_nowait(None)  # Sinal de parada para cada worker
    
    results_list = []
    atingiram_meta_ref = [0]
    
    # Se não tem shared_stats (modo async simples), cria local_stats
    local_stats = None
    if shared_stats is None:
        local_stats = {
            'criadas': 0,
            'sucesso': 0,
            'erros': 0,
            'saldo': 0.0,
            'meta': 0,
            'travado': 0
        }
    
    workers = [
        asyncio.create_task(run_worker(queue, bot_config, results_list, i, count, atingiram_meta_ref, shared_stats, shared_lock, local_stats))
        for i in range(actual_parallel)
    ]
    
    await asyncio.gather(*workers)
    return results_list


def run_process_wrapper(bot_config: BotConfig, count: int, parallel: int, process_id: int, verbose: bool, quiet_mode: bool, shared_stats: Any = None, shared_lock: Any = None):
    """Entry point para cada processo do multiprocessing"""
    setup_logging(verbose)
    if quiet_mode:
        runtime_config["QUIET_MODE"] = True
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        return asyncio.run(run_parallel_async(bot_config, count, parallel, process_id, shared_stats, shared_lock))
    except Exception as e:
        logging.error(f"Erro no processo {process_id}: {e}")
        return []


def format_elapsed(seconds):
    """Formata tempo de execução em Dias Horas Minutos Segundos"""
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


async def run_parallel(
    bot_config: BotConfig,
    count: int,
    parallel: int,
) -> List[AccountData]:
    """
    Executa múltiplos bots em paralelo usando MULTIPROCESSAMENTO + ASYNC.
    
    Args:
        bot_config: Configuração base do bot
        count: Número total de contas a criar
        parallel: Número máximo de bots em paralelo
    
    Returns:
        Lista de resultados
    """
    from gee_token import get_gee_token_manager
    
    start_time = time.time()
    start_datetime = datetime.now()
    
    # PASSO 0: Obter config da plataforma (testa APIs e seleciona a mais rápida)
    if runtime_config["DEBUG_MODE"]:
        logging.info("⚙️ ══════════════════════════════════════════════════")
        logging.info("⚙️ PASSO 0: Obtendo configuração da plataforma")
        logging.info("⚙️ ══════════════════════════════════════════════════")
    
    platform_config = await obter_config_plataforma(bot_config.url, bot_config)
    
    if not platform_config:
        logging.error("❌ Falha ao obter config da plataforma!")
        return []
    
    bot_config.platform_resolved = platform_config
    
    if runtime_config["DEBUG_MODE"]:
        logging.info(f"📋 SiteCode: {platform_config.sitecode}")
        logging.info(f"🌐 API: {platform_config.api_url}")
        logging.info(f"☁️ CDN: {platform_config.url_domain}")
    
    # PASSO 1: Obter geeTokens (se habilitado e não for individual)
    if bot_config.gee_token.enabled and not bot_config.gee_token.individual:
        tokens_necessarios = min(math.ceil(count / bot_config.gee_token.max_uses), 10)
        max_browsers = 30  # Máximo de navegadores em paralelo
        
        if runtime_config["DEBUG_MODE"]:
            logging.info("🔑 ══════════════════════════════════════════════════")
            logging.info(f"🔑 PASSO 1: Obtendo geeTokens")
            logging.info(f"🔑 📊 {tokens_necessarios} tokens para {count} contas")
            logging.info(f"🔑 🌐 Paralelo: max {min(tokens_necessarios, max_browsers)} navegadores")
            logging.info("🔑 ══════════════════════════════════════════════════")
        
        gee_manager = get_gee_token_manager(bot_config.gee_token, bot_config.proxy)
        
        # Semáforo para limitar navegadores em paralelo
        browser_semaphore = asyncio.Semaphore(max_browsers)
        
        async def fetch_single_token(index: int) -> tuple:
            """Busca um token com controle de concorrência"""
            async with browser_semaphore:
                if runtime_config["DEBUG_MODE"]:
                    logging.info(f"🔍 Buscando token {index + 1}/{tokens_necessarios}...")
                token = await gee_manager.get_token(bot_config.url, force_new=(index > 0))
                return index, token
        
        # Busca todos os tokens em paralelo (Boot Rápido)
        if tokens_necessarios > 1:
            logging.info(f"Iniciando BOOT Rápido (Pré-buscando {tokens_necessarios} tokens)...")
            await asyncio.gather(*[fetch_single_token(i) for i in range(tokens_necessarios)], return_exceptions=True)
            
    elif bot_config.gee_token.enabled and bot_config.gee_token.individual:
        if runtime_config["DEBUG_MODE"]:
            logging.info("🔑 ══════════════════════════════════════════════════")
            logging.info("🔑 PASSO 1: geeToken INDIVIDUAL")
            logging.info("🔑 📝 Cada conta busca seu próprio token via API")
            logging.info("🔑 ══════════════════════════════════════════════════")
    else:
        if runtime_config["DEBUG_MODE"]:
            logging.info("🔑 ══════════════════════════════════════════════════")
            logging.info("🔑 PASSO 1: geeToken DESATIVADO")
            logging.info("🔑 ⚠️ Usando 'disabled'")
            logging.info("🔑 ══════════════════════════════════════════════════")

    # PASSO 2: Decidir entre ASYNC SIMPLES ou MULTIPROCESSAMENTO
    # Para poucas contas (< 50), usar apenas async (boot instantâneo)
    # Para muitas contas (>= 50), usar multiprocessamento (mais rápido no total)
    
    USE_MULTIPROCESS_THRESHOLD = 50  # Mínimo de contas para usar multiprocessamento
    
    all_results = []
    num_processes = 1  # Default
    
    if count >= USE_MULTIPROCESS_THRESHOLD:
        # === MODO MULTIPROCESSAMENTO (muitas contas) ===
        num_processes = min(multiprocessing.cpu_count(), 14)
        accounts_per_process = count // num_processes
        parallel_per_process = max(1, parallel // num_processes)
        
        logging.info(f" TURBO MODE: {num_processes} processos | {accounts_per_process} contas/proc | {parallel_per_process} paralelos/proc")
        
        # Manager para compartilhar estatísticas entre processos
        manager = multiprocessing.Manager()
        shared_stats = manager.dict({
            'criadas': 0,
            'sucesso': 0,
            'erros': 0,
            'saldo': 0.0,
            'bonus': 0.0,
            'saldo_meta': 0.0,
            'meta': 0,
            'travado': 0
        })
        shared_lock = manager.Lock()
        
        try:
            global _pool
            _pool = multiprocessing.Pool(processes=num_processes)
            
            process_args = []
            quiet = runtime_config.get("QUIET_MODE", False)
            debug = runtime_config.get("DEBUG_MODE", False)
            
            for i in range(num_processes):
                c = accounts_per_process + (count % num_processes if i == num_processes-1 else 0)
                process_args.append((
                    bot_config, 
                    c, 
                    parallel_per_process, 
                    i, 
                    debug,
                    quiet, 
                    shared_stats, 
                    shared_lock
                ))
            
            try:
                encoded_results = _pool.starmap(run_process_wrapper, process_args)
                
                for res_list in encoded_results:
                    if res_list:
                        all_results.extend(res_list)
            except KeyboardInterrupt:
                print(f"\n\n{Fore.YELLOW}⚠️ Ctrl+C detectado! Finalizando processos...{Style.RESET_ALL}\n")
                _pool.terminate()
                _pool.join()
            finally:
                _pool.close()
                _pool.join()
                _pool = None
                
        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}⚠️ Interrompido pelo usuário!{Style.RESET_ALL}\n")
        except Exception as e:
            logging.error(f"Erro no pool de processos: {e}")
        
        # Usa shared_stats para resumo (mais confiável no multiprocessamento)
        if shared_stats:
            success_count = shared_stats.get('sucesso', 0)
            fail_count = shared_stats.get('erros', 0)
            total_saldo = shared_stats.get('saldo', 0.0)
            atingiram_meta = shared_stats.get('meta', 0)
            bonus_travado = shared_stats.get('travado', 0)
            
            # Calcula tempo
            end_time = time.time()
            end_datetime = datetime.now()
            elapsed = end_time - start_time
            contas_por_min = (count / elapsed) * 60 if elapsed > 0 else 0
            elapsed_formatted = format_elapsed(elapsed)
            
            # Resumo TURBO
            interrupted_msg = " (INTERROMPIDO)" if _interrupted else ""
            print()
            print(f"\033[96m  RESUMO FINAL - MODO TURBO ({num_processes} NÚCLEOS){interrupted_msg}\033[0m")
            print("\033[94m" + "=" * 55 + "\033[0m")
            print()
            print(f"  \033[97mContas Criadas:\033[0m       \033[93m{shared_stats.get('criadas', 0)}\033[0m")
            print(f"  \033[92mAtingiram Meta:\033[0m       \033[92m{atingiram_meta}\033[0m")
            print(f"  \033[35mBonus Travado:\033[0m        \033[35m{bonus_travado}\033[0m")
            print(f"  \033[91mErros:\033[0m                \033[91m{fail_count}\033[0m")
            print()
            print("\033[94m" + "-" * 55 + "\033[0m")
            print()
            total_bonus = shared_stats.get('bonus', 0.0)
            saldo_meta = shared_stats.get('saldo_meta', 0.0)
            print(f"  \033[93mSoma Total Bonus:\033[0m     \033[97mR$ {total_bonus:.2f}\033[0m")
            print(f"  \033[96mSoma Total Saldos:\033[0m    \033[97mR$ {total_saldo:.2f}\033[0m")
            print(f"  \033[92mSoma Saldos (>=Meta):\033[0m \033[97mR$ {saldo_meta:.2f}\033[0m")
            print()
            print("\033[94m" + "-" * 55 + "\033[0m")
            print()
            print(f"  \033[90mInício:\033[0m    {start_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"  \033[90mFinal:\033[0m     {end_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"  \033[90mDuração:\033[0m   {elapsed_formatted} ({contas_por_min:.1f} contas/min)")
            print()
            print("\033[94m" + "=" * 55 + "\033[0m")
            print()
            
            return all_results
    else:
        # === MODO ASYNC SIMPLES (poucas contas - boot instantâneo) ===
        logging.info(f" FAST MODE: {count} contas with {parallel} parallel (async simples)")
        
        # Usa semáforo + gather (padrão simples e funcional)
        semaphore = asyncio.Semaphore(parallel)
        local_stats = {
            'criadas': 0,
            'sucesso': 0,
            'erros': 0,
            'saldo': 0.0,
            'bonus': 0.0,
            'saldo_meta': 0.0,
            'meta': 0,
            'travado': 0
        }
        
        async def run_single(index: int) -> AccountData:
            global _interrupted
            async with semaphore:
                # Verifica se foi interrompido
                if _interrupted:
                    return AccountData(error="Interrompido")
                
                result = await run_bot(bot_config)
                
                # Atualiza estatísticas
                local_stats['criadas'] += 1
                if result.success:
                    local_stats['sucesso'] += 1
                    local_stats['saldo'] += result.saldo
                    local_stats['bonus'] += result.bonus
                    if result.saldo >= bot_config.game.subir_banca:
                        local_stats['meta'] += 1
                        local_stats['saldo_meta'] += result.saldo
                    if result.bonus_travado:
                        local_stats['travado'] += 1
                    if result.bonus == 0:
                        local_stats['erros'] += 1
                else:
                    local_stats['erros'] += 1
                
                update_console_title(local_stats, bot_config.platform_name)
                
                # Imprime resultado
                if result.success:
                    print_account_result(result, bot_config)
                else:
                    if not runtime_config.get("QUIET_MODE"):
                        print(f"[{_now()}] {Fore.RED}[XX]{Style.RESET_ALL} Usuario: {result.usuario} | Erro: {result.error}")
                
                return result
        
        tasks = [run_single(i) for i in range(count)]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for r in results:
                if isinstance(r, AccountData):
                    all_results.append(r)
                elif isinstance(r, Exception):
                    if not isinstance(r, asyncio.CancelledError):
                        logging.error(f"❌ Erro: {r}")
        except asyncio.CancelledError:
            print(f"\n\n{Fore.YELLOW}⚠️ Tarefas canceladas!{Style.RESET_ALL}\n")
        
        # Usa local_stats para resumo (modo async simples)
        if local_stats and local_stats.get('criadas', 0) > 0:
            success_count = local_stats.get('sucesso', 0)
            fail_count = local_stats.get('erros', 0)
            total_saldo = local_stats.get('saldo', 0.0)
            total_bonus = local_stats.get('bonus', 0.0)
            saldo_meta = local_stats.get('saldo_meta', 0.0)
            atingiram_meta = local_stats.get('meta', 0)
            bonus_travado = local_stats.get('travado', 0)
            
            # Calcula tempo
            end_time = time.time()
            end_datetime = datetime.now()
            elapsed = end_time - start_time
            contas_por_min = (local_stats['criadas'] / elapsed) * 60 if elapsed > 0 else 0
            elapsed_formatted = format_elapsed(elapsed)
            
            # Resumo MODO RÁPIDO
            interrupted_msg = " (INTERROMPIDO)" if _interrupted else ""
            print()
            print(f"\033[96m  RESUMO FINAL - MODO RÁPIDO{interrupted_msg}\033[0m")
            print("\033[94m" + "=" * 55 + "\033[0m")
            print()
            print(f"  \033[97mContas Criadas:\033[0m       \033[93m{local_stats.get('criadas', 0)}\033[0m")
            print(f"  \033[92mAtingiram Meta:\033[0m       \033[92m{atingiram_meta}\033[0m")
            print(f"  \033[35mBonus Travado:\033[0m        \033[35m{bonus_travado}\033[0m")
            print(f"  \033[91mErros:\033[0m                \033[91m{fail_count}\033[0m")
            print()
            print("\033[94m" + "-" * 55 + "\033[0m")
            print()
            print(f"  \033[93mSoma Total Bonus:\033[0m     \033[97mR$ {total_bonus:.2f}\033[0m")
            print(f"  \033[96mSoma Total Saldos:\033[0m    \033[97mR$ {total_saldo:.2f}\033[0m")
            print(f"  \033[92mSoma Saldos (>=Meta):\033[0m \033[97mR$ {saldo_meta:.2f}\033[0m")
            print()
            print("\033[94m" + "-" * 55 + "\033[0m")
            print()
            print(f"  \033[90mInício:\033[0m    {start_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"  \033[90mFinal:\033[0m     {end_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"  \033[90mDuração:\033[0m   {elapsed_formatted} ({contas_por_min:.1f} contas/min)")
            print()
            print("\033[94m" + "=" * 55 + "\033[0m")
            print()
            
            return all_results

    # Processa resultados finais (fallback)
    success_count = 0
    fail_count = 0
    total_saldo = 0.0
    total_bonus = 0.0
    saldo_meta = 0.0
    bonus_travado = 0
    atingiram_meta = 0
    
    for result in all_results:
        if isinstance(result, AccountData):
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
    elapsed_formatted = format_elapsed(elapsed)
    
    # Resumo estilizado
    print()
    print(f"\033[96m  RESUMO FINAL - {num_processes} NÚCLEOS UTILIZADOS\033[0m")
    print("\033[94m" + "=" * 55 + "\033[0m")
    print()
    print(f"  \033[97mContas Criadas:\033[0m       \033[93m{success_count}\033[0m")
    print(f"  \033[92mAtingiram Meta:\033[0m       \033[92m{atingiram_meta}\033[0m")
    print(f"  \033[35mBonus Travado:\033[0m        \033[35m{bonus_travado}\033[0m")
    print(f"  \033[91mErros:\033[0m                \033[91m{fail_count}\033[0m")
    print()
    print("\033[94m" + "-" * 55 + "\033[0m")
    print()
    print(f"  \033[93mSoma Total Bonus:\033[0m     \033[97mR$ {total_bonus:.2f}\033[0m")
    print(f"  \033[96mSoma Total Saldos:\033[0m    \033[97mR$ {total_saldo:.2f}\033[0m")
    print(f"  \033[92mSoma Saldos (>=Meta):\033[0m \033[97mR$ {saldo_meta:.2f}\033[0m")
    print()
    print("\033[94m" + "-" * 55 + "\033[0m")
    print()
    print(f"  \033[90mInício:\033[0m    {start_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  \033[90mFinal:\033[0m     {end_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  \033[90mDuração:\033[0m   {elapsed_formatted} ({contas_por_min:.1f} contas/min)")
    print()
    print("\033[94m" + "=" * 55 + "\033[0m")
    print()
    
    return all_results



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

    # Midas Fortune Trava (ex: --midas "midas-trava-bet 14.40")
    parser.add_argument(
        "--midas",
        help="Ativa o modo Midas Fortune Trava (ex: --midas \"midas-trava-bet 14.40\")"
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
    
    # Desativar proxy
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        default=False,
        help="Desativa o uso de proxy (padrão: ativada)"
    )
    
    # Output
    parser.add_argument(
        "--output", "-o",
        default="resultados.json",
        help="Arquivo de saída JSON (padrão: resultados.json)"
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
    
    args.game = "aleatorio"
    
    return args


def build_config(args) -> BotConfig:
    """Constrói configuração a partir dos argumentos"""
    # Proxy config (ativada por padrão, --no-proxy desativa)
    usar_proxy = not args.no_proxy
    proxy_config = ProxyConfig(usar_proxy=usar_proxy)
    
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
            )
        except ValueError:
            logging.warning(f"⚠️ Proxy inválido: {args.proxy}, usando padrão")
    
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
    )

    import re
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

    # Midas Fortune Trava logic
    if args.midas:
        # Extrai bet usando regex (ex: "midas-trava-bet 14.40")
        match = re.search(r"midas-trava-bet\s+([\d.]+)", str(args.midas), re.IGNORECASE)
        if match:
            game_config.midas_fortune_trava = True
            game_config.midas_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Midas Fortune"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Midas Fortune Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.midas_trava_bet:.2f}")

    # Sunshine Coast Trava logic
    if args.sunshine:
        # Extrai bet usando regex (ex: "sunshine-armar-bet 0.5")
        match = re.search(r"sunshine-armar-bet\s+([\d.]+)", str(args.sunshine), re.IGNORECASE)
        if match:
            game_config.sunshine_trava = True
            game_config.sunshine_trava_bet = float(match.group(1).replace(",", "."))
            game_config.nome_jogo = str(args.sunshine)
            logging.info(f" 🎯 Modo {Fore.YELLOW}Sunshine Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.sunshine_trava_bet:.2f}")

    # Journey to the Wealth Trava logic
    if args.journey:
        # Extrai bet usando regex (ex: "journey-trava-bet 0.4")
        match = re.search(r"journey-trava-bet\s+([\d.]+)", str(args.journey), re.IGNORECASE)
        if match:
            game_config.journey_to_the_wealth_trava = True
            game_config.journey_trava_bet = float(match.group(1))
            game_config.nome_jogo = "Journey to the Wealth"
            logging.info(f" 🎯 Modo {Fore.YELLOW}Journey to the Wealth Trava{Style.RESET_ALL} ATIVO | Alvo R$ {game_config.journey_trava_bet:.2f}")

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
        turbo_mode=True,  # Ativa modo de alta performance
    )


async def main():
    """Função principal"""
    args = parse_args()
    
    # Configura modo debug
    if args.quiet:
        runtime_config["DEBUG_MODE"] = False
    
    # Setup logging
    setup_logging(args.verbose)
    
    if runtime_config["DEBUG_MODE"]:
        logging.info(" ==================================================")
        logging.info(" BOT PYTHON ASSINCRONO")
        logging.info(" ==================================================")
        if args.platform_record:
            logging.info(f" Plataforma: {args.platform_record.name}")
        logging.info(f" URL: {args.url}")
        logging.info(f" Contas: {args.count}")
        logging.info(f" Paralelo: {args.parallel}")
        logging.info(f" Jogo: Aleatório")
        logging.info(f" Bet maxima: R$ {args.bet_max:.2f}")
        logging.info(f" Saldo alvo: R$ {args.target:.2f}")
        logging.info(f" geeToken max uses: {args.gee_max_uses}")
        logging.info(" ==================================================")
    
    # Cria diretórios necessários
    os.makedirs("cache", exist_ok=True)
    
    # Constrói configuração
    bot_config = build_config(args)
    
    # Executa
    results = await run_parallel(bot_config, args.count, args.parallel)
    
    # Contas são salvas em tempo real pelo bot quando atingem a meta
    
    # Retorna código de saída
    success_count = sum(1 for r in results if r.success)
    return 0 if success_count > 0 else 1


def signal_handler(signum, frame):
    """Handler para Ctrl+C"""
    global _interrupted, _pool
    
    if _interrupted:
        # Segundo Ctrl+C - força saída imediata
        print(f"\n{Fore.RED}⚠️ Forçando saída...{Style.RESET_ALL}")
        if _pool:
            _pool.terminate()
        sys.exit(130)
    
    _interrupted = True
    print(f"\n\n{Fore.YELLOW}⚠️ Ctrl+C detectado! Finalizando graciosamente...{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}   (Pressione Ctrl+C novamente para forçar saída){Style.RESET_ALL}\n")
    
    # Termina o pool de processos se existir
    if _pool:
        _pool.terminate()


if __name__ == "__main__":
    # Configura handler de sinal para Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        # Handler já tratou
        sys.exit(130)
    except Exception as e:
        logging.error(f"❌ Erro fatal: {e}")
        sys.exit(1)
