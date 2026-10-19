# -*- coding: utf-8 -*-
"""
Teste de x-devices para cadastro e coleta de bônus
Verifica quais x-devices funcionam para registro e coleta
"""
import sys
import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

from colorama import Fore, Style, init
from config import BotConfig, GameConfig, GeeTokenConfig, runtime_config
from platforms import get_platform_by_name
from http_client import BotHttpClient
from utils import (
    decrypt,
    decrypt_request,
    encrypt_request,
    flash_browsers,
    flash_headers,
    generate_android_version,
    generate_device_model,
    generate_key,
    generate_wechat_id,
    gerar_celular,
    gerar_cpf,
    gerar_data_nascimento,
    gerar_email,
    gerar_nome_completo,
    gerar_senha,
    gerar_usuario,
    is_base64,
    is_json,
    numero,
    postdata_register,
    uuid4,
)
from bot import obter_config_plataforma
from gee_token import get_gee_token_manager

init()  # Inicializa colorama

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Lista de x-devices para testar
X_DEVICES = [
    "1-1", "1-2", "1-3", "1-4", "1-5",
    "2-1", "2-2", "2-3", "2-4", "2-5",
    "3-1", "3-2", "3-3", "3-4", "3-5",
    "4-1", "4-2", "4-3", "4-4", "4-5",
    "5-1", "5-2", "5-3", "5-4", "5-5",
    "6-1", "6-2", "6-3", "6-4", "6-5"
]


@dataclass
class TestResult:
    """Resultado do teste de um x-device"""
    x_device: str
    registro_ok: bool = False
    coleta_ok: bool = False
    bonus_valor: float = 0.0
    usuario: str = ""
    senha: str = ""
    erro: str = ""
    coleta_erro: str = ""  # Resposta quando coleta falha


class XDeviceTester:
    """Testador de x-devices"""
    
    def __init__(self, config: BotConfig, x_device: str, platform, use_proxy: bool = False):
        self.config = config
        self.x_device = x_device
        self.platform = platform  # Platform já carregado (com cache)
        self.use_proxy = use_proxy
        
        # Dados gerados
        self.usuario = gerar_usuario()
        self.senha = gerar_senha()
        self.senha_saque = "222221"
        self.email = gerar_email(config.game.dominio_email)
        self.cpf = gerar_cpf()
        self.telefone = gerar_celular()
        self.nome_completo = gerar_nome_completo()
        
        # Device info
        self.device_id = uuid4()
        self.login_id = uuid4()
        self.token = uuid4()
        self.device_model = generate_device_model()
        self.android_version = generate_android_version()
        self.tipo_app = 3
        
        # Login data
        self.data_login = None
        self.key_request = None
        self._http = None
        self.user_agent = flash_browsers(self.device_model, self.platform.speed_version)
    
    async def _get_http(self) -> BotHttpClient:
        if self._http is None:
            self._http = BotHttpClient(self.config, self.user_agent)
        return self._http
    
    def _create_headers(self, mode: str = None, token: str = None) -> Dict:
        """Cria headers com x-device específico"""
        headers = flash_headers(
            self.login_id,
            self.platform.host,
            self.device_id,
            self.device_model,
            self.platform.url_domain,
            self.platform.sitecode,
            self.platform.speed_version,
            self.platform.app_version,
            self.tipo_app,
            self.android_version,
            mode=mode,
            token=token,
        )
        # Sobrescreve x-device com o valor de teste
        headers["x-device"] = self.x_device
        return headers
    
    async def _registrar(self) -> bool:
        """Registra conta com x-device específico"""
        http = await self._get_http()
        
        # Busca gee_token individual se habilitado
        gee_token = ""
        if self.config.gee_token.individual:
            manager = get_gee_token_manager(proxy_config=self.config.proxy)
            gee_token = await manager._fetch_token_via_api(self.platform.url_domain)
            if gee_token is None:
                logger.warning(f"❌ [{self.x_device}] Falha ao obter geeToken individual")
                return False
        
        post_data = postdata_register(
            self.platform.url_domain,
            self.device_id,
            self.device_model,
            self.usuario,
            self.senha,
            self.cpf,
            self.telefone,
            self.nome_completo,
            self.platform.sitecode,
            speed_version=self.platform.speed_version,
            token=self.token,
            gee_token=gee_token,
            inviter_id=self.platform.inviter_id if self.platform.inviter_id else None,
        )
        
        headers = self._create_headers()
        
        response = await http.api_request(
            self.platform.api_url,
            "/hall/api/member/register",
            post_data,
            headers,
            use_proxy=self.use_proxy,
        )
        
        # Processa resposta (igual bot.py)
        data = None
        data_register = None
        
        if is_base64(response):
            decrypted = decrypt(response)
            data = json.loads(decrypted)
            if data.get("data"):
                data_register = data["data"]
        else:
            import re
            match = re.search(r'"encryptString":"([^"]+)"', response)
            if match:
                encrypted = match.group(1)
                decrypted = decrypt(encrypted)
                data = json.loads(decrypted)
                if data.get("data"):
                    data_register = data["data"]
            else:
                # Tenta validação de captcha
                data = is_json(response)
        
        # Validação de captcha (geetest) - igual bot.py
        if not data_register and data and len(data.get("msg", "")) == 32:
            from utils import postdata_validate
            
            validate_data = postdata_validate(
                self.device_id,
                data["msg"],
                "/api/member/register"
            )
            
            headers_cipher = self._create_headers(mode="cipher")
            
            validate_response = await http.api_request(
                self.platform.api_url,
                "/hall/api/member/geetest/validate/v4",
                validate_data,
                headers_cipher,
                use_proxy=self.use_proxy,
            )
            
            if is_base64(validate_response):
                decrypted = decrypt(validate_response)
                validate_data = json.loads(decrypted)
                
                if validate_data.get("code") == 1:
                    # Tenta registro novamente
                    response = await http.api_request(
                        self.platform.api_url,
                        "/hall/api/member/register",
                        post_data,
                        headers,
                        use_proxy=self.use_proxy,
                    )
                    
                    import re
                    match = re.search(r'"encryptString":"([^"]+)"', response)
                    if match:
                        encrypted = match.group(1)
                        decrypted = decrypt(encrypted)
                        data = json.loads(decrypted)
                        if data.get("data"):
                            data_register = data["data"]
        
        # Configura data_login igual bot.py
        if data_register:
            self.data_login = data_register.get("userInfos", data_register)
            self.key_request = generate_key(
                self.data_login["session_key"],
                self.data_login["username"]
            )
            return True
        
        logger.warning(f"❌ [{self.x_device}] Registro falhou: {response[:200]}")
        return False
    
    async def _configurar_conta(self) -> tuple:
        """Configura dados da conta (igual bot.py). Retorna (ok, erro)"""
        http = await self._get_http()
        
        headers = self._create_headers(mode="cipher", token=self.data_login["session_key"])
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers:
            del headers["x-data-mode"]
        
        try:
            # Data de nascimento e redes sociais
            modify_data = {
                "birthday": gerar_data_nascimento(),
                "facebook": f"1000{numero(10)}",
                "line": None,
                "email": self.email,
                "mineDisplayOptions": None,
                "nickname": None,
                "realName": None,
                "telegram": numero(10),
                "twitter": None,
                "wechat": generate_wechat_id(),
                "whatsapp": gerar_celular(),
                "zalo": None,
                "registerTime": self.data_login.get("register_time"),
                "time": int(time.time()),
            }
            
            encrypted = encrypt_request(json.dumps(modify_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                "/hall/api/member/user/settings/modifyinfo",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )
            
            # Verifica resposta modifyinfo
            if is_base64(response):
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                if data.get("code") != 1:
                    return False, f"modifyinfo code={data.get('code')}: {decrypted[:200]}"
            else:
                resp_data = is_json(response)
                if resp_data and resp_data.get("code") != 1:
                    return False, f"modifyinfo: {response[:200]}"
            
            # Email simples
            email_data = {
                "email": self.email,
                "secondVerify": {"type": 6, "loginPass": self.senha},
                "time": int(time.time()),
            }
            
            encrypted = encrypt_request(json.dumps(email_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                "/hall/api/member/user/security/bindEmail",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )
            
            # Verifica resposta bindEmail
            if is_base64(response):
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                if data.get("code") != 1:
                    return False, f"bindEmail code={data.get('code')}: {decrypted[:200]}"
            
            # Pergunta secreta
            answer_data = {
                "id": 1,
                "answer": self.usuario,
                "secondVerify": {"type": 6, "loginPass": self.senha},
                "time": int(time.time()),
            }
            
            encrypted = encrypt_request(json.dumps(answer_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                "/hall/api/member/user/passQuint",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )
            
            # Verifica resposta passQuint
            if is_base64(response):
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                if data.get("code") != 1:
                    return False, f"passQuint code={data.get('code')}: {decrypted[:200]}"
            
            return True, ""
        except Exception as e:
            return False, f"Erro: {e}"
    
    async def _configurar_saque(self) -> tuple:
        """Configura método de saque (igual bot.py). Retorna (ok, erro)"""
        http = await self._get_http()
        
        headers = self._create_headers(mode="cipher", token=self.data_login["session_key"])
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers:
            del headers["x-data-mode"]
        
        try:
            # Senha de saque
            withdraw_data = {
                "withdraw_pass": self.senha_saque,
                "secondVerify": {"type": 0, "withdraw_pass": self.senha_saque},
                "time": int(time.time()),
            }
            
            encrypted = encrypt_request(json.dumps(withdraw_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                "/hall/api/member/user/security/modifyWithdrawPass",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )
            
            # Verifica resposta modifyWithdrawPass
            if is_base64(response):
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                if data.get("code") != 1:
                    return False, f"modifyWithdrawPass code={data.get('code')}: {decrypted[:200]}"
            
            # Verifica senha de saque
            verify_data = {
                "addWithdrawAccountType": 5,
                "withdrawalPassword": self.senha_saque,
                "time": int(time.time()),
            }
            
            encrypted = encrypt_request(json.dumps(verify_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                "/hall/api/finance/certify/verifyWithdrawalPasswordV2",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )            
            uuid_saque = None
            if is_base64(response):
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                if data.get("code") == 1:
                    uuid_saque = data.get("data", {}).get("key")
                else:
                    return False, f"verifyWithdrawPass code={data.get('code')}: {decrypted[:200]}"
            else:
                return False, f"verifyWithdrawPass: {response[:200]}"
            
            if not uuid_saque:
                return False, "UUID saque não encontrado"
            
            # Adiciona método de saque (PIX) - usa CPF
            pix_data = {
                "name": self.nome_completo,
                "account": self.cpf,
                "extendInfo": self.cpf,
                "cpf": self.cpf,
                "subType": "CPF",
                "accountType": 7,
                "subTypeExtend": {"bank": "", "branchBank": "", "companyName": ""},
                "time": int(time.time()),
            }
            
            encrypted = encrypt_request(json.dumps(pix_data), self.key_request)
            response = await http.api_request(
                self.platform.api_url,
                f"/hall/api/finance/certify/bindalipayV3?withdrawal_uuid={uuid_saque}",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )
            
            # Verifica resposta bindalipay
            if is_base64(response):
                decrypted = decrypt_request(response, self.key_request)
                data = json.loads(decrypted)
                if data.get("code") != 1:
                    return False, f"bindalipay code={data.get('code')}: {decrypted[:200]}"
            
            return True, ""
        except Exception as e:
            return False, f"Erro: {e}"
    
    async def _coletar_bonus(self) -> tuple:
        """Coleta bônus e retorna (valor, erro)"""
        http = await self._get_http()
        valor_total = 0.0
        erro = ""
        
        headers = self._create_headers(mode="cipher", token=self.data_login["session_key"])
        headers["auth"] = self.data_login["userkey"]
        headers["newjwt"] = self.data_login["jwt_token"]
        if "x-data-mode" in headers:
            del headers["x-data-mode"]
        
        # Save address
        for action_type in [1, 2]:
            address_data = {
                "address": self.device_id,
                "actionType": action_type,
                "time": int(time.time()),
            }
            encrypted = encrypt_request(json.dumps(address_data), self.key_request)
            await http.api_request(
                self.platform.api_url,
                "/hall/activetask/task_save_address",
                encrypted,
                headers,
                use_proxy=self.use_proxy,
            )
        
        # Lista missões
        task_data = {
            "taskId": 1,
            "template": 1,
            "time": int(time.time()),
        }
        encrypted = encrypt_request(json.dumps(task_data), self.key_request)
        response = await http.api_request(
            self.platform.api_url,
            "/hall/api/active/tasks/task",
            encrypted,
            headers,
            use_proxy=self.use_proxy,
        )
        
        if not is_base64(response):
            erro = f"Task list: {response[:300]}"
            logger.warning(f"❌ [{self.x_device}] {erro}")
            return 0.0, erro
        
        decrypted = decrypt_request(response, self.key_request)
        data = json.loads(decrypted)
        
        if data.get("code") != 1:
            erro = f"Task list code={data.get('code')}: {decrypted[:300]}"
            logger.warning(f"❌ [{self.x_device}] {erro}")
            return 0.0, erro
        
        # Coleta bônus
        rules = data.get("data", {}).get("rules", [])
        if not rules:
            erro = f"Nenhuma regra de bonus. Response: {decrypted[:300]}"
            return 0.0, erro
        
        bonus_coletados = 0
        for rule in rules:
            receive_log_id = rule.get("receiveLogId", 0)
            if receive_log_id > 0:
                bonus_data = {
                    "template": 1,
                    "receiveLogIds": str(receive_log_id),
                    "time": int(time.time()),
                }
                encrypted = encrypt_request(json.dumps(bonus_data), self.key_request)
                response = await http.api_request(
                    self.platform.api_url,
                    "/hall/api/active/tasks/receiveOne",
                    encrypted,
                    headers,
                    use_proxy=self.use_proxy,
                )
                
                if is_base64(response):
                    try:
                        bonus_decrypted = decrypt_request(response, self.key_request)
                        bonus_response = json.loads(bonus_decrypted)
                        
                        if bonus_response.get("code") == 1:
                            # Tenta pegar o valor de prize, amount ou reward
                            data_bonus = bonus_response.get("data", {})
                            valor = float(data_bonus.get("prize", 0) or data_bonus.get("amount", 0) or 0)
                            # Se não encontrou, tenta no receiveList
                            if valor == 0:
                                receive_list = data_bonus.get("receiveList", [])
                                if receive_list:
                                    valor = float(receive_list[0].get("reward", 0) or receive_list[0].get("amount", 0) or 0)
                            valor_total += valor
                            bonus_coletados += 1
                        else:
                            erro = f"ReceiveOne code={bonus_response.get('code')}: {bonus_decrypted[:300]}"
                            logger.warning(f"❌ [{self.x_device}] {erro}")
                    except Exception as e:
                        erro = f"ReceiveOne erro: {e}"
                        logger.warning(f"❌ [{self.x_device}] {erro}")
                else:
                    erro = f"ReceiveOne: {response[:300]}"
                    logger.warning(f"❌ [{self.x_device}] {erro}")
        
        # Se não coletou nenhum bônus, mostra as regras
        if valor_total == 0 and not erro:
            rules_info = [{"id": r.get("receiveLogId", 0), "status": r.get("status")} for r in rules[:5]]
            erro = f"Nenhum bonus disponivel. Rules: {rules_info}"
        
        return valor_total, erro
    
    async def testar(self) -> TestResult:
        """Executa teste completo para o x-device"""
        result = TestResult(x_device=self.x_device, usuario=self.usuario, senha=self.senha)
        
        try:
            # 1. Registro
            registro_ok = await self._registrar()
            if registro_ok:
                logger.info(f"   ✅ [{self.x_device}] Registro OK")
            else:
                logger.info(f"   ❌ [{self.x_device}] Registro FALHOU")
                result.erro = "Registro falhou"
                return result
            
            result.registro_ok = True
            
            # 2. Configurar conta
            conta_ok, conta_erro = await self._configurar_conta()
            if conta_ok:
                logger.info(f"   ✅ [{self.x_device}] Configurar conta OK")
            else:
                logger.info(f"   ❌ [{self.x_device}] Configurar conta FALHOU: {conta_erro if conta_erro else 'N/A'}")
            
            # 3. Configurar saque
            saque_ok, saque_erro = await self._configurar_saque()
            if saque_ok:
                logger.info(f"   ✅ [{self.x_device}] Configurar saque OK")
            else:
                logger.info(f"   ❌ [{self.x_device}] Configurar saque FALHOU: {saque_erro if saque_erro else 'N/A'}")
            
            # 4. Coleta bônus
            bonus, coleta_erro = await self._coletar_bonus()
            result.bonus_valor = bonus
            result.coleta_erro = coleta_erro
            
            if bonus > 0:
                result.coleta_ok = True
                logger.info(f"   ✅ [{self.x_device}] Coletar bonus OK: R$ {bonus:.2f}")
            else:
                logger.info(f"   ❌ [{self.x_device}] Coletar bonus FALHOU: {coleta_erro if coleta_erro else 'N/A'}")
            
        except Exception as e:
            import traceback
            logger.error(f"   ❌ [{self.x_device}] ERRO EXCEÇÃO: {e}")
            logger.error(traceback.format_exc())
            result.erro = str(e)
        
        finally:
            if self._http:
                await self._http.close()
        
        return result


async def testar_x_device(config: BotConfig, x_device: str, platform, index: int, total: int, use_proxy: bool = False) -> TestResult:
    """Testa um único x-device"""
    logger.info(f"🔄 [{index}/{total}] Testando x-device: {Fore.CYAN}{x_device}{Style.RESET_ALL}")
    
    tester = XDeviceTester(config, x_device, platform, use_proxy)
    result = await tester.testar()
    
    # Log do resultado
    if result.coleta_ok:
        status = f"{Fore.GREEN}✅ SUCESSO{Style.RESET_ALL}"
        bonus_color = Fore.GREEN if result.bonus_valor >= 1 else Fore.YELLOW
        logger.info(
            f"{status} | x-device: {Fore.CYAN}{x_device}{Style.RESET_ALL} | "
            f"Bônus: {bonus_color}R$ {result.bonus_valor:.2f}{Style.RESET_ALL} | "
            f"User: {result.usuario} | Senha: {result.senha}"
        )
    elif result.registro_ok:
        logger.info(
            f"{Fore.YELLOW}⚠️ SEM BÔNUS{Style.RESET_ALL} | x-device: {Fore.CYAN}{x_device}{Style.RESET_ALL} | "
            f"User: {result.usuario} | Erro: {result.coleta_erro if result.coleta_erro else 'N/A'}"
        )
    else:
        logger.info(
            f"{Fore.RED}❌ FALHOU{Style.RESET_ALL} | x-device: {Fore.CYAN}{x_device}{Style.RESET_ALL} | "
            f"Erro: {result.erro}"
        )
    
    return result


async def main():
    """Função principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Teste de x-devices para cadastro e coleta de bônus")
    parser.add_argument("plataforma", help="Nome da plataforma ou URL completa")
    parser.add_argument(
        "--gee-token-individual",
        action="store_true",
        default=False,
        help="Busca geeToken individual para cada conta via API"
    )
    parser.add_argument(
        "--proxy",
        action="store_true",
        default=False,
        help="Usa proxy nas chamadas hall/api"
    )
    
    args = parser.parse_args()
    
    # Resolve URL da plataforma
    plataforma = args.plataforma.strip()
    gee_individual = args.gee_token_individual
    use_proxy = args.proxy
    
    # Se começar com http, usa direto
    if plataforma.startswith("http"):
        URL = plataforma
    else:
        # Busca na lista de plataformas
        platform_record = get_platform_by_name(plataforma)
        if platform_record:
            URL = platform_record.site
            print(f"📍 Plataforma encontrada: {Fore.CYAN}{platform_record.name}{Style.RESET_ALL}")
        else:
            # Se não encontrar, tenta montar URL
            plataforma = plataforma.replace("www.", "")
            if "." not in plataforma:
                plataforma = f"{plataforma}.com"
            URL = f"https://www.{plataforma}"
            print(f"⚠️ Plataforma '{args.plataforma}' não encontrada na lista, usando: {URL}")
    
    print()
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}  TESTE DE X-DEVICES - Cadastro e Coleta de Bônus{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print()
    
    config = BotConfig(
        url=URL,
        game=GameConfig(
            nome_jogo="Fortune Tiger",
            bet_maxima=20,
            subir_banca=30,
            dominio_email="gmail.com",
        ),
        gee_token=GeeTokenConfig(enabled=gee_individual, individual=gee_individual),
    )
    
    if gee_individual:
        print(f"🔑 {Fore.YELLOW}geeToken individual ATIVADO{Style.RESET_ALL}")
    if use_proxy:
        print(f"🌐 {Fore.YELLOW}Proxy ATIVADO para hall/api{Style.RESET_ALL}")
    
    # Carrega config da plataforma UMA VEZ (usa cache)
    print(f"🔍 Carregando config da plataforma (com cache)...")
    platform = await obter_config_plataforma(URL, config)
    if not platform:
        print(f"{Fore.RED}❌ Erro ao obter config da plataforma{Style.RESET_ALL}")
        return
    
    print(f"✅ Plataforma: {Fore.CYAN}{platform.sitecode}{Style.RESET_ALL} | API: {platform.api_url}")
    print()
    
    # Testa todos os x-devices
    results: List[TestResult] = []
    total = len(X_DEVICES)
    
    print(f"📋 Testando {total} x-devices...")
    print(f"🌐 URL: {URL}")
    print()
    
    for i, x_device in enumerate(X_DEVICES, 1):
        result = await testar_x_device(config, x_device, platform, i, total, use_proxy)
        results.append(result)
    
    # Resumo final
    print()
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}  RESUMO FINAL{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print()
    
    sucesso = [r for r in results if r.coleta_ok]
    registro_ok = [r for r in results if r.registro_ok and not r.coleta_ok]
    falhou = [r for r in results if not r.registro_ok]
    
    print(f"✅ {Fore.GREEN}SUCESSO (registro + coleta):{Style.RESET_ALL} {len(sucesso)}")
    if sucesso:
        for r in sucesso:
            bonus_color = Fore.GREEN if r.bonus_valor >= 1 else Fore.YELLOW
            print(f"   • {Fore.CYAN}{r.x_device}{Style.RESET_ALL} → Bônus: {bonus_color}R$ {r.bonus_valor:.2f}{Style.RESET_ALL} | User: {r.usuario} | Senha: {r.senha}")
    
    print()
    print(f"⚠️ {Fore.YELLOW}PARCIAL (registro OK, sem coleta):{Style.RESET_ALL} {len(registro_ok)}")
    if registro_ok:
        for r in registro_ok:
            print(f"   • {Fore.CYAN}{r.x_device}{Style.RESET_ALL} | User: {r.usuario}")
    
    print()
    print(f"❌ {Fore.RED}FALHOU (registro falhou):{Style.RESET_ALL} {len(falhou)}")
    if falhou:
        for r in falhou:
            print(f"   • {Fore.CYAN}{r.x_device}{Style.RESET_ALL} → {r.erro}")
    
    print()
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    
    # Exporta x-devices que funcionaram
    if sucesso:
        # Separa por valor do bônus
        bonus_alto = [r for r in sucesso if r.bonus_valor >= 1]
        bonus_baixo = [r for r in sucesso if r.bonus_valor > 0 and r.bonus_valor < 1]
        
        print()
        print(f"{Fore.GREEN}📋 X-DEVICES BÔNUS >= R$ 1.00:{Style.RESET_ALL}")
        x_devices_alto = [r.x_device for r in bonus_alto]
        print(f"   {x_devices_alto if x_devices_alto else 'Nenhum'}")
        
        print()
        print(f"{Fore.YELLOW}📋 X-DEVICES BÔNUS > 0 e < R$ 1.00:{Style.RESET_ALL}")
        x_devices_baixo = [r.x_device for r in bonus_baixo]
        print(f"   {x_devices_baixo if x_devices_baixo else 'Nenhum'}")
        
        # Salva relatório em arquivo
        import os
        os.makedirs("testes", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"testes/xdevices_ok_{timestamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("  RELATÓRIO DE TESTE DE X-DEVICES\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"URL: {URL}\n")
            f.write(f"Total testados: {len(results)}\n")
            f.write(f"Sucesso: {len(sucesso)}\n")
            f.write(f"  - Bônus >= R$ 1.00: {len(bonus_alto)}\n")
            f.write(f"  - Bônus > 0 e < R$ 1.00: {len(bonus_baixo)}\n")
            f.write(f"Parcial: {len(registro_ok)}\n")
            f.write(f"Falhou: {len(falhou)}\n\n")
            
            f.write("=" * 70 + "\n")
            f.write("  X-DEVICES BÔNUS >= R$ 1.00\n")
            f.write("=" * 70 + "\n\n")
            
            if bonus_alto:
                f.write("X_DEVICES_BONUS_ALTO = [\n")
                for xd in x_devices_alto:
                    f.write(f'    "{xd}",\n')
                f.write("]\n\n")
                for r in bonus_alto:
                    f.write(f"  {r.x_device}: R$ {r.bonus_valor:.2f} | {r.usuario}:{r.senha}\n")
            else:
                f.write("Nenhum\n")
            
            f.write("\n" + "=" * 70 + "\n")
            f.write("  X-DEVICES BÔNUS > 0 e < R$ 1.00\n")
            f.write("=" * 70 + "\n\n")
            
            if bonus_baixo:
                f.write("X_DEVICES_BONUS_BAIXO = [\n")
                for xd in x_devices_baixo:
                    f.write(f'    "{xd}",\n')
                f.write("]\n\n")
                for r in bonus_baixo:
                    f.write(f"  {r.x_device}: R$ {r.bonus_valor:.2f} | {r.usuario}:{r.senha}\n")
            else:
                f.write("Nenhum\n")
        
        print(f"\n   💾 Relatório salvo em: {Fore.CYAN}{filename}{Style.RESET_ALL}")
        
        # Salva contas separadas por bônus
        if bonus_alto:
            contas_alto_filename = f"testes/contas_bonus_alto_{timestamp}.txt"
            with open(contas_alto_filename, "w", encoding="utf-8") as f:
                for r in bonus_alto:
                    f.write(f"{r.x_device}:{r.usuario}:{r.senha}\n")
            print(f"   💾 Contas bônus >= R$1: {Fore.GREEN}{contas_alto_filename}{Style.RESET_ALL}")
        
        if bonus_baixo:
            contas_baixo_filename = f"testes/contas_bonus_baixo_{timestamp}.txt"
            with open(contas_baixo_filename, "w", encoding="utf-8") as f:
                for r in bonus_baixo:
                    f.write(f"{r.x_device}:{r.usuario}:{r.senha}\n")
            print(f"   💾 Contas bônus < R$1: {Fore.YELLOW}{contas_baixo_filename}{Style.RESET_ALL}")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
