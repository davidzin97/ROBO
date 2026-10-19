import os
import sys
import json
import subprocess
import threading
import time
import signal
import atexit
import requests
import re

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, name): return ""
    Fore = DummyColor()
    Style = DummyColor()

# Armazena os processos ativos
processes = []
platform_color_map = {}

# Paleta de cores vibrantes para o terminal do PC
PLATFORM_COLORS = [
    Fore.CYAN,
    Fore.YELLOW,
    Fore.MAGENTA,
    Fore.GREEN,
    Fore.BLUE,
    Fore.LIGHTCYAN_EX,
    Fore.LIGHTYELLOW_EX,
    Fore.LIGHTMAGENTA_EX,
    Fore.LIGHTGREEN_EX,
    Fore.LIGHTBLUE_EX
]

def get_color_for_platform(platform):
    if platform not in platform_color_map:
        idx = len(platform_color_map) % len(PLATFORM_COLORS)
        platform_color_map[platform] = PLATFORM_COLORS[idx]
    return platform_color_map[platform]

def format_and_print_log(platform, line, flask_port):
    # Remove códigos de escape ANSI antes de processar/enviar para o Flask
    clean_line = ansi_escape.sub('', line)
    
    p_color = get_color_for_platform(platform)
    tag = f"[{platform.upper()}]"
    
    # Detecção de cor baseada no tipo de mensagem
    line_lower = clean_line.lower()
    content_color = Fore.WHITE
    
    # Vermelho para Erros/Problemas (Maior Prioridade)
    if any(x in line_lower for x in ["erro", "error", "falhou", "🔴", "cancelado", "falha", "recusada", "invalid", "inválido", "incorrect", "sem saldo", "saldo zerado", "saldo zerou", "zerado", "zerou", "bloqueado", "bloqueou", "banido", "limitado"]):
        content_color = Fore.RED
    # Verde para Sucessos, Bônus e Recolhimento
    elif any(x in line_lower for x in ["sucesso", "success", "concluído", "concluido", "ganhou", "🟢", "recolhido", "ganho", "obtido", "bonus", "bônus", "💰", "recebido", "salvo", "registrado", "criada"]):
        content_color = Fore.GREEN
    # Amarelo para Avisos
    elif any(x in line_lower for x in ["aviso", "warning", "atenção", "atencao", "🟡", "alerta", "redefinindo", "expirou"]):
        content_color = Fore.YELLOW
    # Ciano para Operações normais (Apostas, Giros, Saldos, Conexão)
    elif any(x in line_lower for x in ["giro", "girando", "rodada", "caçando", "cacando", "aposta", "apostando", "saldo", "balance", "login", "conectando"]):
        content_color = Fore.CYAN
        
    # Exibe no console visível do PC com cor
    print(f"{p_color}{tag}{Style.RESET_ALL} {content_color}{clean_line}{Style.RESET_ALL}")
    
    # Envia de volta para o Painel Web do Flask sem códigos de escape
    log_text = f"[{platform.upper()}] {clean_line}"
    try:
        requests.post(f"http://127.0.0.1:{flask_port}/api/log_webhook", json={"log": log_text}, timeout=1)
    except Exception:
        pass

def read_output(proc, platform, flask_port):
    for line in iter(proc.stdout.readline, ''):
        line = line.strip()
        if line:
            format_and_print_log(platform, line, flask_port)
    proc.stdout.close()
    proc.wait()
    finish_msg = f"🔴 PROCESSO FINALIZADO (Código de saída: {proc.returncode})"
    format_and_print_log(platform, finish_msg, flask_port)

def cleanup():
    if not processes:
        return
    print(f"\n{Fore.RED}🛑 Encerrando todas as instâncias filhas de bots...{Style.RESET_ALL}")
    for proc in processes:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    time.sleep(0.5)
    for proc in processes:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
    processes.clear()

def signal_handler(signum, frame):
    cleanup()
    sys.exit(0)

def monitor_parent(parent_pid):
    """Monitora se o processo Flask foi fechado para limpar os bots órfãos."""
    while True:
        time.sleep(2)
        if parent_pid == 1:
            break
        if sys.platform == "win32":
            try:
                import ctypes
                PROCESS_QUERY_INFORMATION = 0x0400
                SYNCHRONIZE = 0x0010
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, parent_pid)
                if not handle:
                    break
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                STILL_ACTIVE = 259
                if exit_code.value != STILL_ACTIVE:
                    break
            except Exception:
                pass
        else:
            try:
                os.kill(parent_pid, 0)
            except OSError:
                break
    print(f"\n{Fore.RED}⚠️ Flask (Painel Web) encerrado. Parando bots...{Style.RESET_ALL}")
    cleanup()
    os._exit(0)

def main():
    if len(sys.argv) < 2:
        print("Erro: Arquivo de configuração não especificado.")
        sys.exit(1)
        
    config_file = sys.argv[1]
    if not os.path.exists(config_file):
        print(f"Erro: Arquivo {config_file} não encontrado.")
        sys.exit(1)
        
    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        
    args = config_data.get("args", [])
    platforms = config_data.get("platforms", {})
    flask_port = config_data.get("flask_port", 5000)
    
    print(f"{Fore.CYAN}===============================================")
    print(f"{Fore.CYAN}🚀 GERENCIADOR DE BOTS INICIADO")
    print(f"{Fore.CYAN}==============================================={Style.RESET_ALL}\n")
    
    # Registra handlers de término
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGHUP, signal_handler)
        
    # Inicia a monitoração do processo pai
    parent_pid = os.getppid()
    if parent_pid > 1:
        t_monitor = threading.Thread(target=monitor_parent, args=(parent_pid,), daemon=True)
        t_monitor.start()

    # Configura variáveis de ambiente
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # Lança os bots de cada plataforma
    for platform, parallel_count in platforms.items():
        print(f"{Fore.GREEN}Lançando a casa: {platform.upper()} com {parallel_count} conta(s) paralela(s)...{Style.RESET_ALL}")
        # Garante que roda a partir de main.py com as contas paralelas especificadas
        python_args = [sys.executable, "main.py"] + args + ["--parallel", str(parallel_count), "--platform", platform]
        
        proc = subprocess.Popen(
            python_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            env=env
        )
        processes.append(proc)
        
        t = threading.Thread(
            target=read_output, 
            args=(proc, platform, flask_port), 
            daemon=True
        )
        t.start()
        # Pequeno delay para não sobrecarregar na inicialização imediata
        time.sleep(0.5)

    # Mantém o script rodando enquanto houver processos ativos
    while True:
        active = [p for p in processes if p.poll() is None]
        if not active:
            print(f"\n{Fore.YELLOW}Todos os processos foram encerrados.{Style.RESET_ALL}")
            break
        time.sleep(1)

if __name__ == "__main__":
    main()
