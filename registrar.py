# -*- coding: utf-8 -*-
"""
Script de Registro Simplificado - Apenas Cadastro de Contas
Baseado em bot.py e main.py

Uso:
  python registrar.py --platform 707bet --count 10 --parallel 5
  python registrar.py --url https://exemplo.com --count 5 --no-proxy
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
import base64
from collections import Counter
import re
from datetime import datetime
from dataclasses import dataclass, field

# Configuração de Depuração (pode ser sobrescrito por --verbose)
DEBUG_WHEEL = False  # Ativado automaticamente com --verbose/-v
from typing import Any, Dict, List, Optional, Tuple
import random
import string

def random_hex(length: int) -> str:
    """Gera uma string hexadecimal aleatória"""
    return ''.join(random.choices(string.hexdigits.lower(), k=length))

from colorama import Fore, Style, init
from config import BotConfig, ProxyConfig, GeeTokenConfig, SMSConfig, GameConfig, runtime_config, CONFIG_KEY_B64
from database import salvar_conta
from gee_token import get_gee_token, mark_gee_token_used, release_gee_token, get_gee_token_manager
from http_client import BotHttpClient
from utils import (
    decrypt,
    encrypt_request,
    decrypt_request,
    flash_browsers,
    flash_headers,
    generate_android_version,
    generate_device_model,
    gerar_celular,
    gerar_cpf,
    gerar_email,
    gerar_nome_completo,
    gerar_senha_segura,
    gerar_usuario_por_nome,
    is_base64,
    is_json,
    numero,
    postdata_register,
    postdata_validate,
    uuid4,
    generate_key,
)
from bot import PlatformConfig, obter_config_plataforma

# Inicializa colorama
init()

@dataclass
class AccountData:
    usuario: str = ""
    senha: str = ""
    senha_saque: str = ""
    email: str = ""
    cpf: str = ""
    telefone: str = ""
    nome_completo: str = ""
    sitecode: str = ""
    success: bool = False
    error: str = ""
    x_device: str = ""
    valor_roleta: str = ""
    login_link: str = ""

class RegistrarBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.nome_completo = gerar_nome_completo()        
        self.usuario = gerar_usuario_por_nome(self.nome_completo)
        self.senha = gerar_senha_segura()
        self.senha_saque = "222221"
        self.email = gerar_email(config.game.dominio_email)
        self.cpf = gerar_cpf()
        self.telefone = gerar_celular()
        
        self.device_id = str(uuid4())
        self.login_id = str(uuid4())
        self.token = str(uuid4())
        self.browser_finger_id = random_hex(64) # Fingerprint mais longa e randômica
        self.device_model = generate_device_model()
        self.android_version = generate_android_version()

        self.platform: Optional[PlatformConfig] = None
        self._http: Optional[BotHttpClient] = None
        self.user_agent = ""
        self.x_device = ""
        
        # Dados de login para bônus/roleta
        self.data_login: Optional[Dict] = None
        self.key_request: Optional[str] = None

    async def _get_http(self) -> BotHttpClient:
        if self._http is None:
            self._http = BotHttpClient(self.config, self.user_agent)
        return self._http

    async def registrar(self) -> AccountData:
        result = AccountData(
            usuario=self.usuario,
            senha=self.senha,
            senha_saque=self.senha_saque,
            email=self.email,
            cpf=self.cpf,
            telefone=self.telefone,
            nome_completo=self.nome_completo,
        )

        try:
            # 1. Config da plataforma
            platform = await obter_config_plataforma(self.config.url, self.config)
            if not platform:
                result.error = "Erro ao obter config da plataforma"
                return result

            self.platform = platform
            self.user_agent = flash_browsers(self.device_model, platform.speed_version)
            result.sitecode = platform.sitecode

            # 2. Obter geeToken
            gee_token = "disabled"
            if self.config.gee_token.enabled:
                if not self.config.gee_token.individual:
                    gee_token = await get_gee_token(platform.url_domain)
            
            # 3. Registro
            data_register = await self._executar_registro(gee_token)
            if not data_register:
                if gee_token != "disabled":
                    release_gee_token(platform.url_domain, gee_token)
                result.error = "Erro no registro (provável bloqueio de IP ou CAPTCHA)"
                return result

            if gee_token != "disabled":
                mark_gee_token_used(platform.url_domain, gee_token)

            result.success = True
            result.x_device = self.x_device

            # 3.1 Extrair dados de login para roleta
            if self._extrair_dados_login(data_register):
                # 3.2 Girar Roleta
                result.valor_roleta = await self.girar_roleta()
                
                # 3.3 Gerar Link de Login Direto (_ti)
                ti_obj = {
                    "session_key": self.data_login.get("session_key", ""),
                    "jwt_token": "",
                    "userkey": ""
                }
                ti_json = json.dumps(ti_obj)
                ti_b64 = base64.b64encode(ti_json.encode()).decode()
                base_url = self.config.url.split('?')[0].rstrip('/')
                result.login_link = f"{base_url}/?_ti={ti_b64}"

            # 4. Salvar no banco
            if self.config.save_to_db:
                device_model_str = self.device_model.get("nome", "") if isinstance(self.device_model, dict) else self.device_model
                salvar_conta(
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

        except Exception as e:
            result.error = str(e)
        finally:
            if self._http:
                await self._http.close()

        return result

    def _extrair_dados_login(self, data_register: Dict) -> bool:
        """Extrai tokens de login para usar em chamadas de bônus"""
        try:
            # Pega de userInfos ou do root
            info = data_register.get("userInfos", data_register)
            
            session_key = info.get("session_key") or data_register.get("session_key")
            jwt_token = data_register.get("jwt_token") or info.get("jwt_token")
            userkey = data_register.get("userkey") or info.get("userkey")
            username = info.get("username") or self.usuario
            
            self.data_login = {
                "session_key": session_key,
                "jwt_token": jwt_token,
                "userkey": userkey,
                "username": username
            }
            
            if not all([session_key, jwt_token, userkey]):
                return False
                
            self.key_request = generate_key(session_key, username)
            return True
        except Exception:
            return False

    async def girar_roleta(self) -> str:
        """Executa a sequência de giro da roleta (Active ID 742)"""
        http = await self._get_http()
        valor_final = "Processando..."
        
        def debug_api(name: str, resp: str) -> Optional[Dict]:
            """Helper para logar e decodificar respostas de API"""
            if DEBUG_WHEEL:
                print(f"{Fore.MAGENTA}[DEBUG {self.usuario}] {name}:{Style.RESET_ALL}")
            data = None
            if is_base64(resp):
                try:
                    dec = decrypt_request(resp, self.key_request)
                    data = json.loads(dec)
                    if DEBUG_WHEEL:
                        # Força escape de Unicode para evitar charmap error no Windows
                        clean_json = json.dumps(data, ensure_ascii=True)
                        print(f"  {Fore.CYAN}JSON Decrypt: {clean_json}{Style.RESET_ALL}")
                except Exception as e:
                    if DEBUG_WHEEL:
                        print(f"  {Fore.RED}Erro Decrypt: {str(e)} | Base64: {resp[:50]}...{Style.RESET_ALL}")
            else:
                try:
                    data = json.loads(resp)
                    if DEBUG_WHEEL:
                        clean_json = json.dumps(data, ensure_ascii=True)
                        print(f"  {Fore.CYAN}JSON: {clean_json}{Style.RESET_ALL}")
                except Exception:
                    if DEBUG_WHEEL:
                        # Se não for JSON nem Base64, exibe texto com escape
                        amostra = resp[:500].encode('ascii', 'backslashreplace').decode('ascii')
                        print(f"  {Fore.YELLOW}RAW: {amostra}{Style.RESET_ALL}")
            return data

        try:
            headers = flash_headers(
                self.login_id, self.platform.host, self.device_id, self.device_model, 
                self.platform.url_domain, self.platform.sitecode, self.platform.speed_version, 
                self.platform.app_version, self.android_version, mode="cipher",
                token=self.data_login["session_key"], browser_finger_id=self.browser_finger_id,
                uid=self.data_login["username"]
            )
            headers["auth"] = self.data_login["userkey"]
            headers["newjwt"] = self.data_login["jwt_token"]
            
            # Step 1: Informar conclusão de tarefas
            r1 = await http.api_request(self.platform.api_url, "/hall/api/active/activeTaskCompleteList", "{}", headers, use_proxy=True)
            debug_api("activeTaskCompleteList", r1)
            
            # Step 2: Giro da roleta (Chop One Knife)
            spin_payload = {"activeId": 1531, "time": int(time.time())}
            encrypted_spin = encrypt_request(json.dumps(spin_payload), self.key_request)
            
            spin_resp = await http.api_request(
                self.platform.api_url, 
                "/hall/api/active/chop_one_knife_turn", 
                encrypted_spin, 
                headers, 
                use_proxy=True
            )
            
            data = debug_api("chop_one_knife_turn", spin_resp)
            if data:
                if data.get("code") == 1:
                    # Captura o valor correto (em algumas plataformas é 'prize', em outras 'first_award_value')
                    p_data = data.get("data", {})
                    prize = p_data.get("prize") or p_data.get("first_award_value", "0")
                    valor_final = f"R$ {prize}"
                elif data.get("errorCode") == 41040:
                    valor_final = f"{Fore.RED}BLOQUEIO DISPOSITIVO (41040){Style.RESET_ALL}"
                else:
                    valor_final = f"Erro API: {data.get('msg', 'Desconhecido')}"
            else:
                if not is_base64(spin_resp) and not spin_resp.startswith("{"):
                    valor_final = "Resposta Inválida (HTM/TXT)"
                else:
                    valor_final = "Falha Decodificação"
            
            # Step 3 & 4: Sincronização final
            headers["x-data-mode"] = "chipher"
            r4 = await http.api_request(self.platform.api_url, "/hall/api/active/getRedDotV2", "{}", headers, use_proxy=True)
            debug_api("getRedDotV2", r4)
            
            return valor_final
        except Exception as e:
            return f"Erro: {str(e)}"

    async def _executar_registro(self, gee_token: str) -> Optional[Dict]:
        http = await self._get_http()
        
        # Headers para geetoken individual (se fosse o caso, mas aqui mantemos o fluxo simples do bot.py)
        if self.config.gee_token.individual:
            headers_cipher = flash_headers(self.login_id, self.platform.host, self.device_id, self.device_model, self.platform.url_domain, self.platform.sitecode, self.platform.speed_version, self.platform.app_version, self.android_version, mode="cipher", browser_finger_id=self.browser_finger_id)
            manager = get_gee_token_manager(proxy_config=self.config.proxy)
            gee_token = await manager._fetch_token_via_api(self.platform.url_domain, custom_headers=headers_cipher, user_agent=self.user_agent)
            if gee_token is None: return None

        post_data = postdata_register(self.platform.url_domain, self.device_id, self.device_model, self.usuario, self.senha, self.cpf, self.telefone, self.nome_completo, self.platform.sitecode, speed_version=self.platform.speed_version, token=self.token, gee_token=gee_token, inviter_id=self.platform.inviter_id, browser_finger_id=self.browser_finger_id)
        headers = flash_headers(self.login_id, self.platform.host, self.device_id, self.device_model, self.platform.url_domain, self.platform.sitecode, self.platform.speed_version, self.platform.app_version, self.android_version, browser_finger_id=self.browser_finger_id)
        self.x_device = headers.get("x-device", "N/A")

        response = await http.api_request(self.platform.api_url, "/hall/api/member/register", post_data, headers, use_proxy=self.config.proxy.usar_proxy)
        
        # Decodificação básica
        data = None
        if is_base64(response):
            decrypted = decrypt(response)
            data = json.loads(decrypted).get("data")
        else:
            match = re.search(r'"encryptString":"([^"]+)"', response)
            if match:
                data = json.loads(decrypt(match.group(1))).get("data")
        
        if data: return data

        # Tratamento de CAPTCHA se necessário (v4 validate)
        parsed = is_json(response)
        if parsed and len(parsed.get("msg", "")) == 32:
            validate_data = postdata_validate(self.device_id, parsed["msg"], "/api/member/register")
            headers_cipher = flash_headers(self.login_id, self.platform.host, self.device_id, self.device_model, self.platform.url_domain, self.platform.sitecode, self.platform.speed_version, self.platform.app_version, self.android_version, mode="cipher", browser_finger_id=self.browser_finger_id)
            validate_response = await http.api_request(self.platform.api_url, "/hall/api/member/geetest/validate/v4", validate_data, headers_cipher, use_proxy=self.config.proxy.usar_proxy)
            
            if is_base64(validate_response):
                val_data = json.loads(decrypt(validate_response))
                if val_data.get("code") == 1:
                    headers["content-length"] = str(len(post_data))
                    final_resp = await http.api_request(self.platform.api_url, "/hall/api/member/register", post_data, headers, use_proxy=self.config.proxy.usar_proxy)
                    if is_base64(final_resp):
                        return json.loads(decrypt(final_resp)).get("data")
        
        return None

def print_result(result: AccountData):
    time_str = datetime.now().strftime("%H:%M:%S")
    if result.success:
        roleta_txt = f" | {Fore.YELLOW}Roleta: {result.valor_roleta}{Style.RESET_ALL}" if result.valor_roleta else ""
        print(f"{Fore.CYAN}[{time_str}] {Fore.GREEN}REGISTRO OK{Style.RESET_ALL} | "
              f"Usuário: {Fore.WHITE}{result.usuario:<15}{Style.RESET_ALL} | "
              f"Senha: {Fore.WHITE}{result.senha:<12}{Style.RESET_ALL}{roleta_txt}")
    else:
        print(f"{Fore.CYAN}[{time_str}] {Fore.RED}FALHA{Style.RESET_ALL} | "
              f"Usuário: {Fore.WHITE}{result.usuario:<15}{Style.RESET_ALL} | "
              f"Erro: {Fore.LIGHTBLACK_EX}{result.error}{Style.RESET_ALL}")

def salvar_em_arquivo(result: AccountData, platform_name: str, base_url: str):
    """Salva os dados da conta em um arquivo .txt organizado por valor"""
    if not result.success:
        return
    
    # Limpa o valor para a pasta (Ex: "R$ 7.77" -> "7.77")
    valor_pasta = "Geral"
    if result.valor_roleta:
        if "R$" in result.valor_roleta:
            valor_pasta = result.valor_roleta.replace("R$", "").strip()
        elif "BLOQUEIO" in result.valor_roleta:
            valor_pasta = "Bloqueio"
        else:
            valor_pasta = result.valor_roleta.strip()

    # Sanitiza o nome da pasta
    valor_pasta = "".join(c for c in valor_pasta if c.isalnum() or c in ".-_").strip()
    if not valor_pasta: valor_pasta = "Geral"

    base_dir = os.path.join("contas", platform_name or "Outros", valor_pasta)
    os.makedirs(base_dir, exist_ok=True)
    
    # Determina o índice (número de arquivos já existentes + 1)
    try:
        prefixo = len(os.listdir(base_dir)) + 1
    except:
        prefixo = 1
    
    filename = f"{prefixo}-{result.usuario}.txt"
    filepath = os.path.join(base_dir, filename)
    
    content = f"Login: {result.login_link or base_url}\n"
    content += f"Usuário: {result.usuario}\n"
    content += f"Senha: {result.senha}\n"
    content += f"Roleta: {result.valor_roleta}\n"
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"{Fore.RED}Erro ao salvar arquivo: {e}{Style.RESET_ALL}")

async def run_worker(config: BotConfig, semaphore: asyncio.Semaphore):
    async with semaphore:
        bot = RegistrarBot(config)
        result = await bot.registrar()
        print_result(result)
        
        # Salva o arquivo após o registro
        salvar_em_arquivo(result, config.platform_name, config.url)
        
        return result

async def main():
    parser = argparse.ArgumentParser(description="Registro de Contas Simplificado")
    parser.add_argument("--url", help="URL da plataforma")
    parser.add_argument("--platform", "-P", help="Nome da plataforma")
    parser.add_argument("--count", "-c", type=int, default=1, help="Quantidade de contas")
    parser.add_argument("--parallel", "-n", type=int, default=1, help="Bots em paralelo")
    parser.add_argument("--no-proxy", action="store_true", help="Desativa proxy")
    parser.add_argument("--no-save-db", action="store_true", help="Não salvar no banco")
    parser.add_argument("--invite-id", "-i", help="ID de convite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verboso (exibe respostas brutas das APIs)")
    
    args = parser.parse_args()

    # Ativa modo verbose globalmente
    if args.verbose:
        import registrar as _self_module
        _self_module.DEBUG_WHEEL = True
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        print(f"{Fore.MAGENTA}[VERBOSE] Modo verboso ativado — respostas de API serão exibidas.{Style.RESET_ALL}")
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolver plataforma
    url = args.url
    platform_name = ""
    if args.platform:
        from platforms import get_platform_by_name
        p = get_platform_by_name(args.platform)
        if p:
            url = p.site if p.site.startswith("http") else f"https://{p.site}"
            platform_name = p.name
    
    if not url:
        print(f"{Fore.RED}Erro: Defina --url ou --platform{Style.RESET_ALL}")
        return

    if args.invite_id:
        url = f"{url.rstrip('/')}/?id={args.invite_id}" if '?' not in url else f"{url}&id={args.invite_id}"

    # Configuração
    config = BotConfig(
        url=url,
        platform_name=platform_name,
        parallel_count=args.parallel,
        save_to_db=not args.no_save_db,
        proxy=ProxyConfig(usar_proxy=not args.no_proxy)
    )

    print(f"\n{Fore.CYAN}=== INICIANDO REGISTRO DE {args.count} CONTAS ==={Style.RESET_ALL}")
    print(f"Plataforma: {Fore.WHITE}{url}{Style.RESET_ALL}")
    print(f"Proxy: {Fore.YELLOW}{'Sim' if config.proxy.usar_proxy else 'Não'}{Style.RESET_ALL}")
    print(f"Paralelo: {Fore.WHITE}{args.parallel}{Style.RESET_ALL}\n")

    semaphore = asyncio.Semaphore(args.parallel)
    start_total = time.time()
    
    tasks = [run_worker(config, semaphore) for _ in range(args.count)]
    results = await asyncio.gather(*tasks)
    
    end_total = time.time()
    duration = end_total - start_total
    
    success = sum(1 for r in results if r.success)
    rate = success / duration if duration > 0 else 0
    
    # Resumo de Prêmios
    prizes = Counter()
    for r in results:
        if r.success:
            val = r.valor_roleta if r.valor_roleta else "Sem Bônus"
            prizes[val] += 1

    print(f"\n{Fore.CYAN}=== FINALIZADO ==={Style.RESET_ALL}")
    print(f"Contas criadas: {Fore.GREEN}{success}/{args.count}{Style.RESET_ALL}")
    
    m, s = divmod(int(duration), 60)
    print(f"Tempo Total: {Fore.WHITE}{m}m {s}s ({duration:.2f}s){Style.RESET_ALL}")
    print(f"Velocidade: {Fore.WHITE}{rate:.2f} contas/seg{Style.RESET_ALL}")
    
    if success > 0:
        print(f"\n{Fore.YELLOW}Resumo de Prêmios:{Style.RESET_ALL}")
        # Ordena prêmios (Bloqueios por último, valores maiores primeiro)
        sorted_prizes = sorted(prizes.items(), key=lambda x: (
            "BLOQUEIO" in x[0], 
            -float(re.search(r'[\d\.]+', x[0]).group()) if re.search(r'[\d\.]+', x[0]) else 0
        ))
        for val, count in sorted_prizes:
            color = Fore.RED if "BLOQUEIO" in val else Fore.GREEN
            print(f"  - {val}: {color}{count}{Style.RESET_ALL} contas")
    print("")

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrompido.")
