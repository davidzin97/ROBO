# -*- coding: utf-8 -*-
"""
Coletor de Bônus (Sem jogar)

Executa:
1. Obter configurações da plataforma
2. Registro (com proxy)
3. Configurar conta e fazer as tasks de bônus
4. Salvar arquivo detalhado em contas/<plataforma>/bonus 00;00/

Uso:
  python coletor_bonus.py --platform 707bet --count 10 --parallel 5
"""

import argparse
import asyncio
import sys
import time
import os
import json
import base64
from datetime import datetime
from colorama import Fore, Style, init

from config import BotConfig, ProxyConfig, GeeTokenConfig
from bot import Bot, AccountData
from bot import obter_config_plataforma, debug_log
from gee_token import get_gee_token, mark_gee_token_used, release_gee_token
from utils import generate_key, flash_browsers, is_base64, encrypt_request, decrypt_request, flash_headers

init()

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")

class BonusBot(Bot):
    async def _obter_saldo_info(self) -> float:
        """Obtém o saldo final do usuário após as tarefas."""
        try:
            http = await self._get_http()
            headers = flash_headers(
                self.login_id, self.platform.host, self.device_id, self.device_model,
                self.platform.url_domain, self.platform.sitecode, self.platform.speed_version,
                self.platform.app_version, self.android_version, mode="cipher",
                token=self.data_login["session_key"], uid=self.data_login["username"]
            )
            headers["auth"] = self.data_login["userkey"]
            headers["newjwt"] = self.data_login["jwt_token"]
            
            payload = {"time": int(time.time())}
            encrypted = encrypt_request(json.dumps(payload), self.key_request)
            
            response = await http.api_request(
                self.platform.api_url,
                "/hall/api/member/user/info",
                encrypted,
                headers,
                use_proxy=False,
            )
            if is_base64(response):
                dec = json.loads(decrypt_request(response, self.key_request))
                data = dec.get("data", {})
                for k in ["gold", "balance", "money", "coin"]:
                    if k in data:
                        return float(data[k])
        except Exception as e:
            debug_log(f"[{self.usuario}] Erro ao obter saldo: {e}")
        return 0.0

    async def _coletar_bonus_custom(self) -> float:
        """Coleta missões e retorna o valor total do bônus coletado."""
        total_bonus = 0.0
        try:
            http = await self._get_http()
            headers = flash_headers(
                self.login_id, self.platform.host, self.device_id, self.device_model,
                self.platform.url_domain, self.platform.sitecode, self.platform.speed_version,
                self.platform.app_version, self.android_version, mode="cipher",
                token=self.data_login["session_key"], uid=self.data_login["username"]
            )
            headers["auth"] = self.data_login["userkey"]
            headers["newjwt"] = self.data_login["jwt_token"]

            # Save address
            for action_type in [1, 2]:
                address_data = {"address": self.device_id, "actionType": action_type, "time": int(time.time())}
                encrypted = encrypt_request(json.dumps(address_data), self.key_request)
                await http.api_request(self.platform.api_url, "/hall/activetask/task_save_address", encrypted, headers, use_proxy=False)

            # Newcomer benefit pop
            headers_chip = headers.copy()
            headers_chip["x-data-mode"] = "chipher"
            await http.api_request(self.platform.api_url, "/hall/api/active/tasks/newcomer_benefit_pop", "", headers_chip, use_proxy=False)

            # Create Task Info
            create_task_data = {"template": 1, "bindType": 31, "time": int(time.time())}
            encrypted_create = encrypt_request(json.dumps(create_task_data), self.key_request)
            await http.api_request(self.platform.api_url, "/hall/api/active/tasks/createTaskInfo", encrypted_create, headers, use_proxy=False)

            # Lista missões
            task_data = {"taskId": 1, "template": 1, "time": int(time.time())}
            encrypted = encrypt_request(json.dumps(task_data), self.key_request)
            response = await http.api_request(self.platform.api_url, "/hall/api/active/tasks/task", encrypted, headers, use_proxy=True)

            if not is_base64(response):
                return 0.0

            decrypted = decrypt_request(response, self.key_request)
            data = json.loads(decrypted)

            if data.get("code") != 1:
                return 0.0

            # Coleta bônus desativada conforme solicitado
            # O sistema vai considerar o total_bonus 0.0 e puxar o saldo real
            pass
        except Exception as e:
            debug_log(f"[{self.usuario}] Erro na coleta customizada: {e}")
            
        return total_bonus

    async def executar(self) -> AccountData:
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
            debug_log(f"[{self.usuario}] Obtendo config da plataforma...")
            platform = await self._obter_config_plataforma()
            if not platform:
                result.error = "Erro ao obter config da plataforma"
                return result

            self.platform = platform
            self.user_agent = flash_browsers(self.device_model, platform.speed_version)
            result.sitecode = platform.sitecode

            gee_token = "disabled"
            if self.config.gee_token.enabled:
                if not self.config.gee_token.individual:
                    gee_token = await get_gee_token(platform.url_domain)

            debug_log(f"[{self.usuario}] Registrando conta...")
            data_register = await self._registrar(gee_token)
            
            if not data_register:
                if gee_token != "disabled":
                    release_gee_token(platform.url_domain, gee_token)
                result.error = "Erro no registro"
                return result

            if gee_token != "disabled":
                mark_gee_token_used(platform.url_domain, gee_token)

            self.data_login = data_register.get("userInfos", data_register)
            self.key_request = generate_key(self.data_login["session_key"], self.data_login["username"])

            debug_log(f"[{self.usuario}] Configurando conta...")
            await self._configurar_conta()

            debug_log(f"[{self.usuario}] Configurando saque...")
            await self._configurar_saque()

            debug_log(f"[{self.usuario}] Coletando bônus padrão...")
            total_bonus = await self._coletar_bonus_custom()
            result.bonus = total_bonus
            
            debug_log(f"[{self.usuario}] Obtendo saldo final...")
            result.saldo = await self._obter_saldo_info()

            # Gerar token login (_ti)
            ti_obj = {
                "session_key": self.data_login.get("session_key", ""),
                "jwt_token": "",
                "userkey": ""
            }
            result.token_login = base64.b64encode(json.dumps(ti_obj).encode()).decode()

            result.success = True
            
        except Exception as e:
            result.error = str(e)
            debug_log(f"[{self.usuario}] Erro: {e}")
        finally:
            if self._http:
                await self._http.close()

        return result

def salvar_em_arquivo(result: AccountData, platform_name: str, base_url: str):
    """Salva os dados da conta em um arquivo .txt organizado em contas/<plataforma>/bonus 00;00/"""
    if not result.success:
        return
        
    base_dir = os.path.join("contas", platform_name or "Outros", "bonus 00;00")
    os.makedirs(base_dir, exist_ok=True)
    
    try:
        prefixo = len(os.listdir(base_dir)) + 1
    except:
        prefixo = 1
        
    filename = f"{prefixo}-{result.usuario}.txt"
    filepath = os.path.join(base_dir, filename)
    
    # Monta URL com _ti
    url_limpa = base_url.split('?')[0].rstrip('/')
    login_link = f"{url_limpa}/?_ti={result.token_login}"
    
    # Formato solicitado:
    # Login: meluwqcmfwmbwx | Senha: kH5J#w33B6wXc5 | PIX: 47043129176 | Senha Saque: 440089 | Bonus: R$ 0.36 | Saldo R$ 22.18
    # 
    # https://...
    #
    # [data_hora]
    pix = result.cpf if result.cpf else result.telefone
    
    content = (
        f"Login: {result.usuario} | Senha: {result.senha} | PIX: {pix} | "
        f"Senha Saque: {result.senha_saque} | Bonus: R$ {result.bonus:.2f} | Saldo R$ {result.saldo:.2f}\n\n"
        f"{login_link}\n\n"
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n"
    )
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"{Fore.RED}Erro ao salvar arquivo: {e}{Style.RESET_ALL}")

async def run_worker(config: BotConfig, semaphore: asyncio.Semaphore, index: int):
    async with semaphore:
        bot = BonusBot(config)
        result = await bot.executar()
        
        if result.success:
            print(f"[{_now()}] {Fore.GREEN}SUCESSO{Style.RESET_ALL} | Usuário: {Fore.WHITE}{result.usuario:<15}{Style.RESET_ALL} | Bônus: R$ {result.bonus:.2f} | Saldo: R$ {result.saldo:.2f}")
            salvar_em_arquivo(result, config.platform_name, config.url)
        else:
            print(f"[{_now()}] {Fore.RED}FALHA{Style.RESET_ALL}   | Usuário: {Fore.WHITE}{result.usuario:<15}{Style.RESET_ALL} | Erro: {result.error}")
            
        return result

async def main():
    parser = argparse.ArgumentParser(description="Coletor de Bônus (Sem Jogar)")
    parser.add_argument("--url", help="URL da plataforma")
    parser.add_argument("--platform", "-P", help="Nome da plataforma")
    parser.add_argument("--count", "-c", type=int, default=1, help="Quantidade de contas")
    parser.add_argument("--parallel", "-n", type=int, default=1, help="Bots em paralelo")
    parser.add_argument("--no-proxy", action="store_true", help="Desativa proxy")
    parser.add_argument("--gee-token-individual", action="store_true", help="Usa geeToken individual")
    parser.add_argument("--no-save-db", action="store_true", help="Não salva no banco")
    parser.add_argument("-v", "--verbose", action="store_true", help="Modo verbose")
    
    args = parser.parse_args()
    
    platform_name = ""
    if args.platform:
        from platforms import get_platform_by_name
        p = get_platform_by_name(args.platform)
        if p:
            args.url = p.site if p.site.startswith("http") else f"https://{p.site}"
            platform_name = p.name
            
    if not args.url:
        print(f"{Fore.RED}Erro: Forneça --url ou --platform{Style.RESET_ALL}")
        return

    from config import runtime_config
    if args.verbose:
        runtime_config["DEBUG_MODE"] = True
        from main import setup_logging
        setup_logging(verbose=True)

    config = BotConfig(
        url=args.url,
        platform_name=platform_name,
        parallel_count=args.parallel,
        proxy=ProxyConfig(usar_proxy=not args.no_proxy),
        gee_token=GeeTokenConfig(enabled=True, individual=args.gee_token_individual),
        save_to_db=not args.no_save_db
    )

    print(f"{Fore.CYAN}=== INICIANDO COLETA DE BÔNUS ({args.count} contas) ==={Style.RESET_ALL}")
    
    semaphore = asyncio.Semaphore(args.parallel)
    tasks = [run_worker(config, semaphore, i) for i in range(args.count)]
    results = await asyncio.gather(*tasks)
    
    sucesso = sum(1 for r in results if r.success)
    print(f"\n{Fore.CYAN}=== CONCLUÍDO ==={Style.RESET_ALL}")
    print(f"Sucesso: {Fore.GREEN}{sucesso}/{args.count}{Style.RESET_ALL}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
