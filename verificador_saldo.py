# -*- coding: utf-8 -*-
"""
Verificador de Saldo de Contas
=============================

Lê as contas existentes na pasta contas/
Acessa o link de login de cada uma, verifica o status da autenticação (anormal ou normal)
e, caso normal, obtém o saldo atualizado pela API de gold da plataforma.
Por fim, atualiza o saldo no próprio arquivo .txt da conta,
exibe no terminal, registra em arquivo de log e envia notificações para o Telegram em tempo real.

Uso:
  python verificador_saldo.py --platform 2abet -n 5 -c 20 -v
"""

import os
import sys
import re
import json
import base64
import asyncio
import logging
import time
import argparse
from datetime import datetime

from colorama import Fore, Style, init

from config import ProxyConfig, BotConfig, GeeTokenConfig, GameConfig, runtime_config
from bot import Bot, AccountData, debug_log
from utils import generate_key, flash_browsers, is_base64, encrypt_request, decrypt_request, flash_headers

# Habilita cores ANSI no Windows e ProactorEventLoop
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = logging.getLogger("verificador_saldo")

def setup_logging(verbose: bool = False):
    """Configura logging para console e arquivo log"""
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    
    # File handler para verificador_saldo.log
    file_handler = logging.FileHandler("verificador_saldo.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    # Remove handlers antigos para evitar duplicidade
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.addHandler(console)
    root.addHandler(file_handler)
    
    # Reduz verbosidade de bibliotecas externas
    logging.getLogger("curl_cffi").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

def strip_colors(text: str) -> str:
    """Remove códigos de cores ANSI do texto para o arquivo de log"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def log_message(text_colored: str, level: str = "info"):
    """Imprime com cor no terminal e grava limpo no arquivo de log"""
    print(text_colored, flush=True)
    clean_text = strip_colors(text_colored)
    if level == "info":
        logger.info(clean_text)
    elif level == "warning":
        logger.warning(clean_text)
    elif level == "error":
        logger.error(clean_text)

class ContaLink:
    def __init__(self):
        self.login: str = ""
        self.senha: str = ""
        self.pix: str = ""
        self.senha_saque: str = ""
        self.bonus: float = 0.0
        self.saldo: float = 0.0
        self.url_site: str = ""
        self.url_link: str = ""
        self.session_key: str = ""
        self.jwt_token: str = ""
        self.userkey: str = ""
        self.arquivo: str = ""

def ler_arquivo_conta(caminho: str) -> ContaLink:
    from urllib.parse import urlparse, parse_qs
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            texto = f.read()
    except Exception as e:
        log_message(f"{Fore.RED}Erro ao ler arquivo {caminho}: {e}{Style.RESET_ALL}", level="error")
        return None

    conta = ContaLink()
    conta.arquivo = caminho

    # Extrai individualmente os campos com regex de forma flexível
    def extract_field(pattern, default=""):
        m = re.search(pattern, texto, re.IGNORECASE)
        return m.group(1).strip() if m else default

    login = extract_field(r"Login:\s*([^\s\|]+)")
    senha = extract_field(r"Senha:\s*([^\s\|]+)")
    pix = extract_field(r"PIX:\s*([^\s\|]+)")
    senha_saque = extract_field(r"Senha\s+Saque:\s*([^\s\|]+)")
    
    bonus_str = extract_field(r"Bonus:\s*(?:R\$\s*)?([\d\.,]+)")
    saldo_str = extract_field(r"Saldo\s*(?:R\$\s*)?([\d\.,]+)")

    # Se falhar, tenta o padrão estrito de linha única
    if not login or not senha:
        linha1_match = re.search(
            r"Login:\s*(\S+)\s*\|"
            r"\s*Senha:\s*([^\s\|]*)\s*\|"
            r"\s*PIX:\s*([^\s\|]*)\s*\|"
            r"\s*Senha\s+Saque:\s*([^\s\|]*)\s*\|"
            r"\s*Bonus:\s*R\$\s*([\d\.,]+)\s*\|"
            r"\s*Saldo\s*R\$\s*([\d\.,]+)",
            texto,
            re.IGNORECASE
        )
        if not linha1_match:
            return None
        login = linha1_match.group(1)
        senha = linha1_match.group(2)
        pix = linha1_match.group(3)
        senha_saque = linha1_match.group(4)
        bonus_str = linha1_match.group(5)
        saldo_str = linha1_match.group(6)

    conta.login = login
    conta.senha = senha
    conta.pix = pix
    conta.senha_saque = senha_saque

    try:
        conta.bonus = float(bonus_str.replace(",", ".")) if bonus_str else 0.0
    except:
        conta.bonus = 0.0

    try:
        conta.saldo = float(saldo_str.replace(",", ".")) if saldo_str else 0.0
    except:
        conta.saldo = 0.0

    url_match = re.search(r"(https?://\S+\?_ti=\S+)", texto)
    if not url_match: 
        return None
    conta.url_link = url_match.group(1)
    
    parsed = urlparse(conta.url_link)
    conta.url_site = f"{parsed.scheme}://{parsed.netloc}"

    qs = parse_qs(parsed.query)
    ti_b64 = qs.get("_ti", [""])[0]
    if not ti_b64: 
        return None

    try:
        ti_json = base64.b64decode(ti_b64).decode()
        ti_data = json.loads(ti_json)
        conta.session_key = ti_data.get("session_key", "")
        conta.jwt_token   = ti_data.get("jwt_token", "")
        conta.userkey     = ti_data.get("userkey", "")
    except Exception:
        return None

    return conta

def atualizar_arquivo_conta(caminho: str, novo_saldo: float):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        updated = False
        for i, line in enumerate(lines):
            if "login:" in line.lower() and "saldo" in line.lower():
                pattern = r"(Saldo\s*(?:R\$\s*)?)([\d\.,]+)"
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    prefix = match.group(1)
                    new_line = re.sub(pattern, f"{prefix}{novo_saldo:.2f}", line, flags=re.IGNORECASE)
                    lines[i] = new_line
                    updated = True
                    break
        
        if updated:
            with open(caminho, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return True
    except Exception as e:
        log_message(f"{Fore.RED}Erro ao atualizar arquivo {caminho}: {e}{Style.RESET_ALL}", level="error")
    return False

def mover_para_contas_com_saldo(caminho_file: str, novo_saldo: float, plataforma: str, usuario: str):
    try:
        # 1. Primeiro atualiza o saldo no próprio arquivo original
        atualizar_arquivo_conta(caminho_file, novo_saldo)
        
        # 2. Define o diretório de destino
        dest_dir = os.path.join("C:\\Users\\Liedson\\Desktop\\API", "contascomsaldo", plataforma)
        os.makedirs(dest_dir, exist_ok=True)
        
        # 3. Cria o novo nome do arquivo: int(saldo)-usuario.txt
        novo_nome = f"{int(novo_saldo)}-{usuario}.txt"
        caminho_destino = os.path.join(dest_dir, novo_nome)
        
        # 4. Copia o arquivo para o destino
        import shutil
        shutil.copy2(caminho_file, caminho_destino)
        
        # 5. Remove o arquivo original
        if os.path.exists(caminho_file):
            os.remove(caminho_file)
            
        debug_log(f"Conta salva em {caminho_destino} e original removida.")
        return True
    except Exception as e:
        log_message(f"{Fore.RED}Erro ao mover para contascomsaldo: {e}{Style.RESET_ALL}", level="error")
    return False

def find_account_files(contas_dir: str, platform: str = None) -> list:
    files = []
    target_dir = os.path.join(contas_dir, platform) if platform else contas_dir
    if not os.path.exists(target_dir):
        return files
        
    for root, dirs, filenames in os.walk(target_dir):
        # Ignora pastas de contas já jogadas ou backups
        if "contas jogadas" in root.lower() or "jogadas" in root.lower():
            continue
        for f in filenames:
            if f.endswith(".txt"):
                files.append(os.path.join(root, f))
    return files

def obter_plataforma_do_caminho(caminho: str) -> str:
    parts = os.path.normpath(caminho).split(os.sep)
    try:
        idx = parts.index("contas")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    return "Desconhecida"

class BalanceCheckerBot(Bot):
    def __init__(self, config: BotConfig, conta: ContaLink):
        super().__init__(config)
        self._conta_link = conta
        self.usuario = conta.login
        self.senha = conta.senha
        self.cpf = conta.pix
        self.telefone = conta.pix

    async def executar(self) -> dict:
        conta = self._conta_link
        result = {
            "usuario": self.usuario,
            "senha": self.senha,
            "pix": self.cpf,
            "senha_saque": conta.senha_saque,
            "bonus": conta.bonus,
            "saldo_anterior": conta.saldo,
            "saldo_atual": 0.0,
            "url_link": conta.url_link,
            "status": "erro",
            "msg": ""
        }

        try:
            # 1. Obter config da plataforma
            debug_log(f"[{self.usuario}] Obtendo config da plataforma...")
            platform = await self._obter_config_plataforma()
            if not platform:
                result["status"] = "erro"
                result["msg"] = "Erro ao obter config da plataforma"
                return result
                
            self.platform = platform
            self.user_agent = flash_browsers(self.device_model, platform.speed_version)

            uid = conta.login
            if conta.jwt_token:
                try:
                    parts = conta.jwt_token.split('.')
                    if len(parts) >= 2:
                        pad = "=" * (4 - len(parts[1]) % 4)
                        payload_jwt = json.loads(base64.urlsafe_b64decode(parts[1] + pad).decode())
                        uid = str(payload_jwt.get("u", conta.login))
                except Exception as e:
                    debug_log(f"[{self.usuario}] Aviso JWT: {e}")

            self.data_login = {
                "session_key": conta.session_key,
                "jwt_token":   conta.jwt_token,
                "userkey":     conta.userkey,
                "username":    uid,
            }
            self.key_request = generate_key(conta.session_key, uid)

            http = await self._get_http()
            
            # Acessar link de login
            debug_log(f"[{self.usuario}] Acessando link da conta...")
            await http.get(conta.url_link, use_proxy=True, timeout=10)

            # 2. Obter headers no modo "plain" e fazer a requisição de logout diretamente
            headers_logout = flash_headers(
                self.login_id, self.platform.host, self.device_id, self.device_model,
                self.platform.url_domain, self.platform.sitecode, self.platform.speed_version,
                self.platform.app_version, self.android_version, mode="plain",
                token=self.data_login["session_key"], uid=self.data_login["username"]
            )
            headers_logout["auth"] = self.data_login["userkey"]
            headers_logout["newjwt"] = self.data_login["jwt_token"]
            headers_logout["x-custom-referer"] = conta.url_link

            logout_payload = json.dumps({
                "os_type": 3,
                "callContext": json.dumps({
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "scene": "login no lastgameinfo",
                    "stack": "[]",
                }),
                "time": int(time.time()),
            })

            debug_log(f"[{self.usuario}] Obtendo saldo via gameApi/logout (plain)...")
            response_logout = await http.api_request(
                self.platform.api_url,
                "/hall/api/gameCenter/gameApi/logout",
                logout_payload,
                headers_logout,
                use_proxy=True,
            )

            data = None
            if is_base64(response_logout):
                try:
                    decrypted_logout = decrypt_request(response_logout, self.key_request)
                    debug_log(f"logout - Decrypted: {decrypted_logout}")
                    data = json.loads(decrypted_logout)
                except Exception as e:
                    debug_log(f"logout - decrypt erro: {e}")
            
            if data is None:
                debug_log(f"logout - Response: {response_logout}")
                try:
                    data = json.loads(response_logout)
                except Exception:
                    result["status"] = "erro"
                    result["msg"] = "Resposta logout inválida"
                    return result

            # Verifica se o dispositivo está desconectado / anormal
            err_code = data.get("err_code")
            msg_resp = data.get("msg", "")
            if err_code == 410099 or "dispositivo atual foi desconectado" in msg_resp.lower():
                result["status"] = "anormal"
                result["msg"] = msg_resp or "O dispositivo atual foi desconectado"
                return result

            if data.get("code") == 1:
                inner_data = data.get("data", {})
                saldo_final = float(inner_data.get("totalGold", inner_data.get("game_gold", 0.0)))
                result["status"] = "sucesso"
                result["saldo_atual"] = saldo_final
            else:
                result["status"] = "erro"
                result["msg"] = msg_resp or "Erro ao obter saldo"

        except Exception as e:
            result["status"] = "erro"
            result["msg"] = str(e)
        finally:
            if self._http:
                await self._http.close()

        return result

def send_telegram_notification(res: dict, platform_name: str, is_anormal: bool = False):
    import requests
    
    token = "8992049578:AAGHlLT6Rbgr6qWtTpjX1pYCkm2Z23r4vMU"
    chat_ids = ["-1003994079774"]
    
    try:
        if is_anormal:
            tipo = "⚠️ CONTA ANORMAL / DESCONECTADA"
            msg = (
                f"<b>{tipo}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Plataforma:</b> {platform_name}\n"
                f"👤 <b>Usuário:</b> <code>{res['usuario']}</code>\n"
                f"🔑 <b>Senha:</b> <code>{res['senha']}</code>\n"
                f"🔓 <b>Saque:</b> <code>{res['senha_saque']}</code>\n"
                f"❌ <b>Status:</b> Conta Anormal / Dispositivo Desconectado\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
            )
        else:
            tipo = "💰 SALDO VERIFICADO"
            msg = (
                f"<b>{tipo}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏦 <b>Plataforma:</b> {platform_name}\n"
                f"👤 <b>Usuário:</b> <code>{res['usuario']}</code>\n"
                f"🔑 <b>Senha:</b> <code>{res['senha']}</code>\n"
                f"🔓 <b>Saque:</b> <code>{res['senha_saque']}</code>\n"
                f"💵 <b>Saldo Anterior:</b> R$ {res['saldo_anterior']:.2f}\n"
                f"💰 <b>Saldo Atual:</b> R$ {res['saldo_atual']:.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
            )
            
        if "url_link" in res and res["url_link"]:
            link = res["url_link"]
            msg += f"🔗 <a href='{link}'>Clique aqui para entrar na conta</a>\n"
            
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
        pass

def parse_args():
    parser = argparse.ArgumentParser(description="Verificador de Saldo de Contas")
    parser.add_argument("--platform", "-P", help="Nome de uma plataforma específica (nome da pasta em contas/)")
    parser.add_argument("--parallel", "-n", type=int, default=5, help="Quantidade de verificações em paralelo (padrão: 5)")
    parser.add_argument("--count", "-c", type=int, default=0, help="Quantidade máxima de contas a verificar (0 = verificar todas)")
    parser.add_argument("--no-proxy", action="store_true", help="Desativa o uso de proxy")
    parser.add_argument("-v", "--verbose", action="store_true", help="Modo verbose (mostra logs detalhados de rede/debug)")
    return parser.parse_args()

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")

async def main():
    args = parse_args()
    
    init(wrap=False)
    
    # Configura e inicializa o sistema de logs (console e arquivo)
    setup_logging(args.verbose)
    
    if args.verbose:
        runtime_config["DEBUG_MODE"] = True
    else:
        runtime_config["DEBUG_MODE"] = False

    proxy_cfg = ProxyConfig()
    if args.no_proxy:
        proxy_cfg.usar_proxy = False
        
    contas_dir = os.path.join("C:\\Users\\Liedson\\Desktop\\API", "contas")
    
    files = find_account_files(contas_dir, args.platform)
    if not files:
        log_message(f"{Fore.RED}Nenhum arquivo de conta (.txt) encontrado em {contas_dir}{Style.RESET_ALL}", level="warning")
        return

    # Limita a quantidade de contas se solicitado
    if args.count > 0:
        files = files[:args.count]

    log_message(f"\n{Fore.CYAN}=== AUTOMATED BALANCE CHECKER ==={Style.RESET_ALL}")
    log_message(f"  Diretório : {Fore.WHITE}{contas_dir}{Style.RESET_ALL}")
    log_message(f"  Filtro    : {Fore.WHITE}{args.platform or 'Sem filtro (todas)'}{Style.RESET_ALL}")
    log_message(f"  Paralelo  : {Fore.WHITE}{args.parallel}{Style.RESET_ALL}")
    log_message(f"  Quantidade: {Fore.WHITE}{f'{args.count} contas' if args.count > 0 else 'Todas as contas'}{Style.RESET_ALL}")
    log_message(f"  Proxy     : {Fore.WHITE}{'ATIVADO' if proxy_cfg.usar_proxy else 'DESATIVADO'}{Style.RESET_ALL}")
    log_message(f"  Contas    : {Fore.WHITE}{len(files)}{Style.RESET_ALL}")
    log_message("")

    if proxy_cfg.usar_proxy:
        log_message("Verificando proxy...")
        sucesso, ip, msg = proxy_cfg.verificar_proxy(timeout=10)
        if sucesso:
            log_message(f"Proxy funcionando! IP: {Fore.GREEN}{ip}{Style.RESET_ALL}")
        else:
            log_message(f"{Fore.RED}Proxy com problema: {msg}{Style.RESET_ALL}", level="warning")
            log_message("Prosseguindo...")
        log_message("")

    sem = asyncio.Semaphore(args.parallel)
    
    stats = {
        "processed": 0,
        "success": 0,
        "anormal": 0,
        "error": 0
    }
    
    stats_lock = asyncio.Lock()
    
    async def worker(caminho_file):
        async with sem:
            conta = ler_arquivo_conta(caminho_file)
            if not conta:
                async with stats_lock:
                    stats["processed"] += 1
                    stats["error"] += 1
                log_message(f"[{_now()}] {Fore.RED}ERRO{Style.RESET_ALL}    | Arquivo inválido ou corrompido: {os.path.basename(caminho_file)}", level="error")
                return
                
            plataforma = obter_plataforma_do_caminho(caminho_file)
            
            config = BotConfig(
                url=conta.url_site,
                platform_name=plataforma,
                parallel_count=args.parallel,
                proxy=proxy_cfg,
                gee_token=GeeTokenConfig(enabled=False),
                save_to_db=False,
                game=GameConfig(nome_jogo="aleatorio")
            )
            
            bot = BalanceCheckerBot(config, conta)
            res = await bot.executar()
            
            status = res["status"]
            
            async with stats_lock:
                stats["processed"] += 1
                if status == "sucesso":
                    stats["success"] += 1
                elif status == "anormal":
                    stats["anormal"] += 1
                else:
                    stats["error"] += 1
                    
            if status == "sucesso":
                log_message(
                    f"[{_now()}] {Fore.GREEN}SUCESSO{Style.RESET_ALL} | "
                    f"Login: {Fore.WHITE}{res['usuario']:<15}{Style.RESET_ALL} | "
                    f"Senha: {Fore.WHITE}{res['senha']:<10}{Style.RESET_ALL} | "
                    f"PIX: {Fore.WHITE}{res['pix']:<11}{Style.RESET_ALL} | "
                    f"Saque: {Fore.WHITE}{res['senha_saque']:<6}{Style.RESET_ALL} | "
                    f"Saldo Novo: {Fore.CYAN}R$ {res['saldo_atual']:.2f}{Style.RESET_ALL} "
                    f"(Ant: R$ {res['saldo_anterior']:.2f})"
                )
                
                mover_para_contas_com_saldo(caminho_file, res["saldo_atual"], plataforma, res["usuario"])
                
            elif status == "anormal":
                log_message(
                    f"[{_now()}] {Fore.YELLOW}ANORMAL{Style.RESET_ALL} | "
                    f"Login: {Fore.WHITE}{res['usuario']:<15}{Style.RESET_ALL} | "
                    f"Senha: {Fore.WHITE}{res['senha']:<10}{Style.RESET_ALL} | "
                    f"PIX: {Fore.WHITE}{res['pix']:<11}{Style.RESET_ALL} | "
                    f"Saque: {Fore.WHITE}{res['senha_saque']:<6}{Style.RESET_ALL} | "
                    f"{Fore.YELLOW}Conta Anormal / Dispositivo Desconectado{Style.RESET_ALL}",
                    level="warning"
                )
                
            else:
                log_message(
                    f"[{_now()}] {Fore.RED}ERRO{Style.RESET_ALL}    | "
                    f"Login: {Fore.WHITE}{res['usuario']:<15}{Style.RESET_ALL} | "
                    f"Senha: {Fore.WHITE}{res['senha']:<10}{Style.RESET_ALL} | "
                    f"PIX: {Fore.WHITE}{res['pix']:<11}{Style.RESET_ALL} | "
                    f"Saque: {Fore.WHITE}{res['senha_saque']:<6}{Style.RESET_ALL} | "
                    f"Erro: {res['msg']}",
                    level="error"
                )

    tasks = [worker(f) for f in files]
    await asyncio.gather(*tasks)
    
    log_message(f"\n{Fore.CYAN}=== VERIFICAÇÃO CONCLUÍDA ==={Style.RESET_ALL}")
    log_message(f"  Total Processadas : {Fore.WHITE}{stats['processed']}{Style.RESET_ALL}")
    log_message(f"  Sucessos          : {Fore.GREEN}{stats['success']}{Style.RESET_ALL}")
    log_message(f"  Contas Anormais   : {Fore.YELLOW}{stats['anormal']}{Style.RESET_ALL}")
    log_message(f"  Falhas/Erros      : {Fore.RED}{stats['error']}{Style.RESET_ALL}")
    log_message("")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
