# -*- coding: utf-8 -*-
"""
Verificador de Auth (WebPush EngageLab)
=======================================

Lê os arquivos de contas gerados (ex: contas/<plataforma>/bonus 00;00/)
Acessa o link de login da conta e, em seguida, verifica a autenticação
do push notification na API TheEngageLab.
Após verificar, roda a coleta de bônus padrão (tasks).

Uso:
  python verificador_auth.py --platform 1212pg -v
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
from datetime import datetime

from colorama import Fore, Style, init

from config import ProxyConfig, BotConfig, GeeTokenConfig, GameConfig
from bot import Bot, AccountData, debug_log
from utils import generate_key, flash_browsers

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

init(wrap=False)

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")

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
    import re
    from urllib.parse import urlparse, parse_qs
    with open(caminho, "r", encoding="utf-8") as f:
        texto = f.read()

    conta = ContaLink()
    conta.arquivo = caminho

    linha1_match = re.search(
        r"Login:\s*(\S+)\s*\|"
        r"\s*Senha:\s*([^\s\|]*)\s*\|"
        r"\s*PIX:\s*([^\s\|]*)\s*\|"
        r"\s*Senha Saque:\s*([^\s\|]*)\s*\|"
        r"\s*Bonus:\s*R\$\s*([\d\.,]+)\s*\|"
        r"\s*Saldo\s*R\$\s*([\d\.,]+)",
        texto,
        re.IGNORECASE
    )
    if not linha1_match: return None

    conta.login       = linha1_match.group(1)
    conta.senha       = linha1_match.group(2)
    conta.pix         = linha1_match.group(3)
    conta.senha_saque = linha1_match.group(4)
    conta.bonus       = float(linha1_match.group(5).replace(",", "."))
    conta.saldo       = float(linha1_match.group(6).replace(",", "."))

    url_match = re.search(r"(https?://\S+\?_ti=\S+)", texto)
    if not url_match: return None
    conta.url_link = url_match.group(1)
    
    parsed = urlparse(conta.url_link)
    conta.url_site = f"{parsed.scheme}://{parsed.netloc}"

    qs = parse_qs(parsed.query)
    ti_b64 = qs.get("_ti", [""])[0]
    if not ti_b64: return None

    try:
        ti_json = base64.b64decode(ti_b64).decode()
        ti_data = json.loads(ti_json)
        conta.session_key = ti_data.get("session_key", "")
        conta.jwt_token   = ti_data.get("jwt_token", "")
        conta.userkey     = ti_data.get("userkey", "")
    except Exception:
        return None

    return conta

def listar_contas(diretorio: str, diretorio_jogadas: str = None):
    contas = []
    if not os.path.isdir(diretorio): return contas
    
    logins_jogados = set()
    if diretorio_jogadas and os.path.isdir(diretorio_jogadas):
        for nome in os.listdir(diretorio_jogadas):
            if nome.endswith(".txt"):
                login = nome.replace(".txt", "")
                if "-" in login:
                    login = login.split("-")[-1]
                logins_jogados.add(login)

    import shutil
    for nome in sorted(os.listdir(diretorio)):
        if nome.endswith(".txt"):
            caminho = os.path.join(diretorio, nome)
            
            login_atual = nome.replace(".txt", "")
            if "-" in login_atual:
                login_atual = login_atual.split("-")[-1]
                
            if login_atual in logins_jogados:
                try:
                    os.remove(caminho)
                except Exception:
                    pass
                continue

            conta = ler_arquivo_conta(caminho)
            if conta:
                if conta.login in logins_jogados:
                    try:
                        os.remove(caminho)
                    except Exception:
                        pass
                    continue
                contas.append(conta)
    return contas


class BotAuth(Bot):
    """
    Herda de Bot para injetar sessão da conta e chamar métodos nativos.
    """
    def __init__(self, config: BotConfig, conta: ContaLink):
        super().__init__(config)
        self._conta_link = conta
        self.usuario = conta.login
        self.senha = conta.senha
        self.senha_saque = conta.senha_saque
        self.cpf = conta.pix
        self.telefone = conta.pix


    async def _coletar_bonus_custom(self) -> float:
        """Coleta missões e retorna o valor total do bônus coletado."""
        total_bonus = 0.0
        try:
            http = await self._get_http()
            from utils import encrypt_request, decrypt_request, is_base64, flash_headers
            import time
            headers = flash_headers(
                self.login_id, self.platform.host, self.device_id, self.device_model,
                self.platform.url_domain, self.platform.sitecode, self.platform.speed_version,
                self.platform.app_version, self.android_version, mode="cipher",
                token=self.data_login["session_key"], uid=self.data_login["username"]
            )
            headers["auth"] = self.data_login["userkey"]
            headers["newjwt"] = self.data_login["jwt_token"]
            headers["x-device"] = "2-5"

            for action_type in [1, 2]:
                address_data = {"address": self.device_id, "actionType": action_type, "time": int(time.time())}
                encrypted = encrypt_request(json.dumps(address_data), self.key_request)
                resp_addr = await http.api_request(self.platform.api_url, "/hall/activetask/task_save_address", encrypted, headers, use_proxy=False)
                debug_log(f"task_save_address - Response: {resp_addr}")

            headers_chip = headers.copy()
            headers_chip["x-data-mode"] = "chipher"
            resp_pop = await http.api_request(self.platform.api_url, "/hall/api/active/tasks/newcomer_benefit_pop", "", headers_chip, use_proxy=False)
            debug_log(f"newcomer_benefit_pop - Response: {resp_pop}")

            create_task_data = {"template": 1, "bindType": 31, "time": int(time.time())}
            encrypted_create = encrypt_request(json.dumps(create_task_data), self.key_request)
            resp_create = await http.api_request(self.platform.api_url, "/hall/api/active/tasks/createTaskInfo", encrypted_create, headers, use_proxy=False)
            debug_log(f"createTaskInfo - Response: {resp_create}")

            task_data = {"taskId": 1, "template": 1, "time": int(time.time())}
            encrypted = encrypt_request(json.dumps(task_data), self.key_request)
            response = await http.api_request(self.platform.api_url, "/hall/api/active/tasks/task", encrypted, headers, use_proxy=True)
            debug_log(f"task - Response: {response}")

            if not is_base64(response): return 0.0

            decrypted = decrypt_request(response, self.key_request)
            data = json.loads(decrypted)

            if data.get("code") != 1: return 0.0

            rules = data.get("data", {}).get("rules", [])
            for rule in rules:
                receive_log_id = rule.get("receiveLogId", 0)
                if receive_log_id > 0:
                    bonus_data = {"template": 1, "receiveLogIds": str(receive_log_id), "time": int(time.time())}
                    encrypted = encrypt_request(json.dumps(bonus_data), self.key_request)
                    
                    headers_receive = headers.copy()
                    headers_receive["x-data-mode"] = "chipher"
                    headers_receive["x-custom-referer"] = f"{self._conta_link.url_site}/home/task?eventCurrent=1&curTask=101"
                    
                    response_receive = await http.api_request(self.platform.api_url, "/hall/api/active/tasks/receiveOne", encrypted, headers_receive, use_proxy=True)
                    
                    if is_base64(response_receive):
                        try:
                            decrypted_resp = decrypt_request(response_receive, self.key_request)
                            debug_log(f"receiveOne - Response: {decrypted_resp}")
                            bonus_response = json.loads(decrypted_resp)
                            if bonus_response.get("code") == 1:
                                prize = float(bonus_response.get("data", {}).get("prize", 0) or 0)
                                if prize > 0:
                                    total_bonus += prize
                                    debug_log(f"[{self.usuario}] Bônus resgatado: R$ {prize:.2f}")
                            else:
                                if bonus_response.get("errorCode") in [41040, 410410001, 41041]:
                                    self._reivindicada = True
                                msg = bonus_response.get("msg", "")
                                if msg:
                                    self._erro_msg = msg
                        except Exception as e:
                            debug_log(f"receiveOne - decrypt erro: {e}")
                    else:
                        debug_log(f"receiveOne - Response: {response_receive}")
                        try:
                            bonus_response = json.loads(response_receive)
                            if bonus_response.get("code") == 1:
                                prize = float(bonus_response.get("data", {}).get("prize", 0) or 0)
                                if prize > 0:
                                    total_bonus += prize
                                    debug_log(f"[{self.usuario}] Bônus resgatado: R$ {prize:.2f}")
                            else:
                                if bonus_response.get("errorCode") in [41040, 410410001, 41041]:
                                    self._reivindicada = True
                                msg = bonus_response.get("msg", "")
                                if msg:
                                    self._erro_msg = msg
                        except Exception:
                            pass
        except Exception as e:
            debug_log(f"[{self.usuario}] Erro na coleta customizada: {e}")
            
        return total_bonus

    async def executar(self, appkey: str) -> AccountData:
        conta = self._conta_link
        result = AccountData(
            usuario=self.usuario,
            senha=self.senha,
            senha_saque=self.senha_saque,
            pix=self.cpf,
            telefone=self.telefone,
            nome_completo=self.nome_completo,
            url=conta.url_site or self.config.url or "",
            sitecode="",
            saldo=conta.saldo,
            bonus=conta.bonus,
        )

        try:
            debug_log(f"[{self.usuario}] Obtendo config da plataforma...")
            platform = await self._obter_config_plataforma()
            if not platform:
                result.error = "Erro config"
                return result
                
            self.platform = platform
            self.user_agent = flash_browsers(self.device_model, platform.speed_version)
            result.sitecode = platform.sitecode

            uid = conta.login
            if conta.jwt_token:
                try:
                    parts = conta.jwt_token.split('.')
                    if len(parts) >= 2:
                        pad = "=" * (4 - len(parts[1]) % 4)
                        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad).decode())
                        uid = str(payload.get("u", conta.login))
                except Exception as e:
                    debug_log(f"[{self.usuario}] Aviso JWT: {e}")

            self.data_login = {
                "session_key": conta.session_key,
                "jwt_token":   conta.jwt_token,
                "userkey":     conta.userkey,
                "username":    uid,
            }
            self.key_request = generate_key(conta.session_key, uid)

            debug_log(f"[{self.usuario}] Sessão injetada via link. UID: {uid}")

            http = await self._get_http()
            
            debug_log(f"[{self.usuario}] Acessando link da conta...")
            await http.get(conta.url_link, use_proxy=True, timeout=10)

            debug_log(f"[{self.usuario}] Coletando bônus padrão...")
            result.bonus = await self._coletar_bonus_custom()

            if result.bonus > 0:
                from utils import buscar_jogo_pg_aleatorio, buscar_jogo_pg
                nome_busca = self.config.game.nome_jogo
                jogo = None
                if nome_busca == "aleatorio":
                    jogo = buscar_jogo_pg_aleatorio()
                else:
                    jogo = buscar_jogo_pg(nome_busca)
                
                is_firestrike = getattr(self.config.game, "firestrike_trava", False)
                is_fire88 = getattr(self.config.game, "fire88_trava", False)
                is_spirit = getattr(self.config.game, "spirit_trava", False)
                is_voodoo = getattr(self.config.game, "voodoo_trava", False)
                is_muertos = getattr(self.config.game, "muertos_trava", False)
                if is_firestrike and not jogo:
                    jogo = {"name": "Fire Strike 2", "gameid": "3010002", "platfromid": "301"}
                elif is_fire88 and not jogo:
                    jogo = {"name": "Fire 88", "gameid": "3010193", "platfromid": "301"}
                elif is_spirit and not jogo:
                    jogo = {"name": "Spirit of Adventure", "gameid": "3010003", "platfromid": "301"}
                elif is_voodoo and not jogo:
                    jogo = {"name": "Voodoo Magic", "gameid": "3010095", "platfromid": "301"}
                elif is_muertos and not jogo:
                    jogo = {"name": "Muertos Multiplier Megaways", "gameid": "3010272", "platfromid": "301"}
                elif getattr(self.config.game, "diamond_trava", False) and not jogo:
                    jogo = {"name": "Diamond Cluster Luck", "gameid": "3010389", "platfromid": "301"}
                elif getattr(self.config.game, "charm_trava", False) and not jogo:
                    jogo = {"name": "Lucky Charm", "gameid": "3010059", "platfromid": "301"}
                elif getattr(self.config.game, "treasure_house_trava", False) and not jogo:
                    jogo = {"name": "Treasure House", "gameid": "3010173", "platfromid": "301"}

                debug_log(f"[{self.usuario}] Iniciando jogo...")
                bonus_valor, saldo_final, tem_bonus_monstro = await self._jogar(jogo)
                result.saldo = saldo_final
                self._tem_bonus_monstro = tem_bonus_monstro
                result.bonus_travado = tem_bonus_monstro
                result.pix = self.cpf
                result.token_login = base64.b64encode(json.dumps({
                    "session_key": self.data_login["session_key"],
                    "jwt_token": "",
                    "userkey": "",
                }).encode()).decode()
                result.x_device = "2-5"
                
                saldo_zerou_com_bonus = saldo_final < 0.30 and getattr(self.config.game, "bonus", False)
                if saldo_final >= self.config.game.subir_banca or tem_bonus_monstro or saldo_zerou_com_bonus:
                    self._save_meta_account(result)

            result.success = True
            
        except Exception as e:
            result.error = str(e)
            debug_log(f"[{self.usuario}] Erro: {e}")
        finally:
            if self._http:
                await self._http.close()

        return result

class Progress:
    def __init__(self, total):
        self.total = total
        self.done = 0
        self.lock = asyncio.Lock()
        
    async def increment(self):
        async with self.lock:
            self.done += 1

async def progress_reporter(progress: Progress):
    try:
        while True:
            await asyncio.sleep(60)
            async with progress.lock:
                remaining = progress.total - progress.done
                print(f"\n[{_now()}] {Fore.CYAN}--- Faltam {remaining} contas para terminar ---{Style.RESET_ALL}\n", flush=True)
    except asyncio.CancelledError:
        pass

async def run_worker(config: BotConfig, conta: ContaLink, appkey: str, sem: asyncio.Semaphore, progress: Progress):
    async with sem:
        bot = BotAuth(config, conta)
        result = await bot.executar(appkey)
        msg_bonus = f"Bônus: R$ {result.bonus:.2f}"
        if result.bonus > 0:
            if result.saldo >= config.game.subir_banca:
                msg_saldo = f" | Saldo Final: {Fore.CYAN}R$ {result.saldo:.2f}{Style.RESET_ALL}"
            else:
                msg_saldo = f" | Saldo Final: R$ {result.saldo:.2f}"
        else:
            msg_saldo = ""
            
        msg_erro = f" | {Fore.YELLOW}Resp: {getattr(bot, '_erro_msg', '')}{Style.RESET_ALL}" if getattr(bot, '_erro_msg', None) else ""
        
        if result.success:
            print(f"[{_now()}] {Fore.GREEN}SUCESSO{Style.RESET_ALL} | Usuário: {Fore.WHITE}{result.usuario:<15}{Style.RESET_ALL} | {msg_bonus}{msg_saldo}{msg_erro}", flush=True)
        else:
            print(f"[{_now()}] {Fore.RED}FALHA{Style.RESET_ALL}   | Usuário: {Fore.WHITE}{result.usuario:<15}{Style.RESET_ALL} | Erro: {result.error}{msg_erro}", flush=True)
            
        try:
            import shutil
            folder_jogadas = os.path.join("contas", config.platform_name, "contas jogadas")
            os.makedirs(folder_jogadas, exist_ok=True)
            novo_caminho = os.path.join(folder_jogadas, os.path.basename(conta.arquivo))
            try:
                shutil.move(conta.arquivo, novo_caminho)
            except Exception:
                # Se der erro (ex: arquivo ja existe lá), pelo menos apaga do bonus 00;00
                os.remove(conta.arquivo)
        except Exception as e:
            print(f"[{_now()}] {Fore.YELLOW}Aviso: Não foi possível mover/deletar {conta.arquivo} ({e}){Style.RESET_ALL}")
            
        await progress.increment()
        return result


async def main():
    parser = argparse.ArgumentParser(description="Verificador de Auth via Link")
    parser.add_argument("--platform", "-P", required=True, help="Nome da plataforma (pasta em contas/)")
    parser.add_argument("--appkey", default="0a3b1e255a2a7ae4dd1ae797", help="Appkey do EngageLab")
    parser.add_argument("--parallel", "-n", type=int, default=1, help="Testes em paralelo")
    parser.add_argument("--no-proxy", action="store_true", help="Desativa proxy")
    parser.add_argument("-v", "--verbose", action="store_true", help="Modo verbose")
    parser.add_argument("--game", "-g", default="aleatorio", help="Nome do jogo PG (ex: fortune_ox) ou aleatorio")
    parser.add_argument("--target", "-t", type=float, default=10.0, help="Alvo de banca")
    parser.add_argument("--spirit", action="store_true", help="Jogar Spirit of Adventure (Trava)")
    parser.add_argument("--spirit-bet", type=float, default=0.0, help="Aposta do Spirit of Adventure")
    parser.add_argument("--voodoo", action="store_true", help="Jogar Voodoo Magic (Trava)")
    parser.add_argument("--voodoo-bet", type=float, default=0.0, help="Aposta do Voodoo Magic")
    parser.add_argument("--muertos", action="store_true", help="Jogar Muertos Multiplier Megaways (Trava)")
    parser.add_argument("--muertos-bet", type=float, default=0.0, help="Aposta do Muertos Multiplier")
    parser.add_argument("--diamond", action="store_true", help="Jogar Diamond Cluster Luck (Trava)")
    parser.add_argument("--diamond-bet", type=float, default=0.0, help="Aposta do Diamond Cluster Luck")
    parser.add_argument("--charm", action="store_true", help="Jogar Lucky Charm (Trava)")
    parser.add_argument("--charm-bet", type=float, default=0.0, help="Aposta do Lucky Charm")
    parser.add_argument("--firestrike", action="store_true", help="Jogar Fire Strike 2 All-Win")
    parser.add_argument("--fire88", action="store_true", help="Jogar Fire 88 All-Win")
    
    args = parser.parse_args()
    
    from config import runtime_config
    if args.verbose:
        runtime_config["DEBUG_MODE"] = True
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                "[%(asctime)s] %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        logging.getLogger("curl_cffi").setLevel(logging.WARNING)
        logging.getLogger("playwright").setLevel(logging.WARNING)

    diretorio = os.path.join("contas", args.platform, "bonus 00;00")
    diretorio_jogadas = os.path.join("contas", args.platform, "contas jogadas")
    os.makedirs(diretorio_jogadas, exist_ok=True)
    contas = listar_contas(diretorio, diretorio_jogadas)
    
    if not contas:
        print(f"{Fore.RED}Nenhuma conta encontrada em: {diretorio}{Style.RESET_ALL}")
        return

    print(f"\n{Fore.CYAN}=== VERIFICADOR AUTH WEBPUSH ==={Style.RESET_ALL}")
    print(f"  Plataforma : {Fore.WHITE}{args.platform}{Style.RESET_ALL}")
    print(f"  AppKey     : {Fore.WHITE}{args.appkey}{Style.RESET_ALL}")
    print(f"  Contas     : {Fore.WHITE}{len(contas)}{Style.RESET_ALL}")
    print(f"  Paralelo   : {Fore.WHITE}{args.parallel}{Style.RESET_ALL}")
    print(f"  Jogo       : {Fore.WHITE}{args.game}{Style.RESET_ALL}")
    print(f"  Target     : {Fore.WHITE}R$ {args.target:.2f}{Style.RESET_ALL}")
    print()

    # Prepara base da url para config do bot
    url_base = contas[0].url_site

    config = BotConfig(
        url=url_base,
        platform_name=args.platform,
        parallel_count=args.parallel,
        proxy=ProxyConfig(usar_proxy=not args.no_proxy),
        gee_token=GeeTokenConfig(enabled=False),
        save_to_db=False,
        game=GameConfig(
            nome_jogo=args.game, 
            tipo_saque="cpf", 
            subir_banca=args.target,
            spirit_trava=args.spirit,
            spirit_trava_bet=args.spirit_bet,
            voodoo_trava=args.voodoo,
            voodoo_trava_bet=args.voodoo_bet,
            muertos_trava=args.muertos,
            muertos_trava_bet=args.muertos_bet,
            diamond_trava=args.diamond,
            diamond_trava_bet=args.diamond_bet,
            charm_trava=args.charm,
            charm_trava_bet=args.charm_bet,
            firestrike_trava=getattr(args, 'firestrike', False),
            fire88_trava=getattr(args, 'fire88', False),
        )
    )

    progress = Progress(len(contas))
    reporter = asyncio.create_task(progress_reporter(progress))

    sem = asyncio.Semaphore(args.parallel)
    tasks = [run_worker(config, conta, args.appkey, sem, progress) for conta in contas]
    await asyncio.gather(*tasks)
    
    reporter.cancel()
    
    print(f"\n{Fore.CYAN}=== CONCLUÍDO ==={Style.RESET_ALL}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
