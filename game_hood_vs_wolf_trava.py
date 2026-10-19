# -*- coding: utf-8 -*-
"""
Jogo Hood vs Wolf com lógica de trava de bônus

Lógica de trava:
- Detecta quando ["dt"]["si"]["bf"]["src"] contém algum valor == 1
- tb (total bet) !== 0
"""
import asyncio
import base64
import hashlib
import json
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from colorama import Fore, Style
from http_client import BotHttpClient
from utils import codigo_pg, SimpleMsgPack, extract_value, extract_options_pg

logger = logging.getLogger(__name__)

# Cores para logs
LIME = Fore.LIGHTGREEN_EX
CYAN = Fore.CYAN
YELLOW = Fore.YELLOW
RED = Fore.RED
MAGENTA = Fore.MAGENTA
RESET = Style.RESET_ALL

# Constantes de configuração
TRAVAR_BET = 15  # Bet máxima para trava

# APIs do jogo PG (serão definidas dinamicamente no loop)
DEFAULT_API_SESSION = "api.6pvx87oz6.com"
DEFAULT_API_GAME = "api-ali-virginia-a.6pvx87oz6.com"

GAME_SLUG = "hood-vs-wolf"

def resultado_jokenpo(jogador, maquina):
    if jogador == maquina:
        return " EMPATE"
    # PEDRA ganha de TESOURA
    # TESOURA ganha de PAPEL
    # PAPEL ganha de PEDRA
    if (jogador == 101 and maquina == 102) or \
       (jogador == 102 and maquina == 103) or \
       (jogador == 103 and maquina == 101):
        return " VITÓRIA"
    else:
        return " DERROTA"

def headers_jogo(host) -> Dict[str, str]:
    """Headers padrão para requisições do jogo"""
    return {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"https://{host}",
        "Priority": "u=1, i",
        "Referer": f"https://{host}/",
        "Sec-CH-UA": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Storage-Access": "active",
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36"
    }



def build_apostas(info_dt: Dict) -> List[Dict]:
    """
    Constrói array de apostas ordenado do maior para o menor valor.

    Args:
        info_dt: Dados do jogo (dt)

    Returns:
        Lista de apostas ordenadas
    """
    cs_list = info_dt.get("cs", [])
    ml_list = info_dt.get("ml", [])
    mxl = info_dt.get("mxl", 1)

    # Reverte as listas (maior para menor)
    cs_reversed = list(reversed(cs_list))
    ml_reversed = list(reversed(ml_list))

    # Usa dict para remover duplicatas pelo valor
    apostas_map = {}

    for cs in cs_reversed:
        for ml in ml_reversed:
            valor_aposta = cs * ml * mxl
            # Usa hash MD5 como chave para evitar duplicatas
            hash_key = hashlib.md5(str(valor_aposta).encode()).hexdigest()
            apostas_map[hash_key] = {
                "valor": valor_aposta,
                "cs": cs,
                "ml": ml,
            }

    return list(apostas_map.values())


def check_bonus_trava(play_si: Dict) -> bool:
    """
    Verifica se o bônus está travado.

    Lógica: ["dt"]["si"]["bf"]["src"] - primeiro valor == 1 ou == 17

    Args:
        play_si: Dados do spin (si)

    Returns:
        True se bônus travado, False caso contrário
    """
    bf = play_si.get("bf") or {}
    src = bf.get("src")

    if not src:
        return False

    # Se src é um dict (ex: {"2": 12, "3": 6}), pega o primeiro valor
    if isinstance(src, dict):
        if src:
            first_value = list(src.values())[0]
            return first_value == 1 or first_value == 17

    # Se src é uma lista, pega o primeiro elemento
    if isinstance(src, list) and len(src) > 0:
        first_value = src[0]
        return first_value == 1 or first_value == 17

    return False


async def game_hood_vs_wolf_trava(
    http: BotHttpClient,
    game_url: str,
    banca_minima: float = 5.0,
    bet_maxima_porcentagem: float = 6.0,
    apenas_uma_bet: bool = False,
    usuario: str = "",
    senha: str = "",
) -> Tuple[int, int, float, float]:
    """
    Executa jogo Hood vs Wolf com lógica de trava de bônus.

    Args:
        http: Cliente HTTP
        game_url: URL do jogo (game_url do login)
        banca_minima: Saldo mínimo para continuar jogando
        bet_maxima_porcentagem: Valor máximo da aposta
        apenas_uma_bet: Se True (padrão), para na primeira trava
        usuario: Nome do usuário para logs
        senha: Senha do usuário para logs

    Returns:
        Tupla (bonus, spin_count, last_bet, bonus_count):
        - bonus: 1 se encontrou bônus, 0 caso contrário
        - spin_count: quantidade de spins
        - last_bet: valor última aposta
        - bonus_count: quantidade de símbolos de bônus
    """
    bonus_count = 0
    spin_count = 0
    last_bet = 0.0
    primeira_bet_trava = 0.0
    saldo_atual = 0.0
    valor_aposta_bet = 0.0

    try:
        # Extrai dados do game_url
        html_code = extract_value(game_url)
        if not html_code:
            logger.error(" Não foi possível extrair dados do game_url")
            return (0, 0, 0.0, 0.0)

        binary_data = base64.b64decode(html_code)
        decoder = SimpleMsgPack(binary_data)
        game_decode = decoder.unpack()
        game_login_data = extract_options_pg(game_decode)

        if not game_login_data.get("host"):
            logger.error(" Host do jogo não encontrado")
            return (0, 0, 0.0, 0.0)

        # Extrai parâmetros
        ot = game_login_data["params"].get("ot")
        ops = game_login_data["params"].get("ops")
        btt = game_login_data["params"].get("btt", 1)
        id_game = game_login_data.get("idGame")
        host_game = str(game_login_data.get("host") or "").split(":")[0].strip()

        # Determina domínios de API dinamicamente
        base_domain = host_game
        if base_domain.startswith("m."):
            base_domain = base_domain[2:]
        elif base_domain.startswith("www."):
            base_domain = base_domain[4:]
        
        api_session = f"api.{base_domain}"
        api_game = f"api.{base_domain}"
        
        # Tenta usar o subdomínio virginia como fallback
        api_game_alt = f"api-ali-virginia-a.{base_domain}"

        # ===== VerifyOperatorPlayerSession =====
        payload = {
            "btt": btt,
            "vc": 0,
            "pf": 1,
            "l": "pt",
            "gi": id_game,
            "os": ops,
            "otk": ot,
        }

        # Tenta a requisição de sessão
        headers = headers_jogo(host_game)
        
        try:
            session_player = await http.game_request(
                api_session,
                f"/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={codigo_pg()}",
                payload,
                headers
            )
        except Exception:
            # Fallback para o domínio padrão
            session_player = await http.game_request(
                DEFAULT_API_SESSION,
                f"/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={codigo_pg()}",
                payload,
                headers
            )

        if not isinstance(session_player, dict) or session_player.get("err"):
            # Tenta o domínio alternativo
            try:
                session_player = await http.game_request(
                    api_game_alt,
                    f"/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={codigo_pg()}",
                    payload,
                    headers
                )
            except Exception:
                pass
            if not isinstance(session_player, dict) or session_player.get("err"):
                logger.debug(f" Erro na sessão (após fallbacks): {session_player}")
                return (0, 0, 0.0, 0.0)
            api_session = api_game_alt

        if not isinstance(session_player, dict) or session_player.get("err"):
            logger.debug(f" Erro na sessão: {session_player}")
            return (0, 0, 0.0, 0.0)

        session_dt = session_player.get("dt") or {}
        atk = session_dt.get("tk")
        eatk = session_dt.get("eatk")
        geu = session_dt.get("geu") or f"{GAME_SLUG}/"

        if not atk:
            logger.error(" Token não encontrado na sessão")
            return (0, 0, 0.0, 0.0)

        # ===== GameRule =====
        payload = {
            "btt": btt,
            "gid": id_game,
            "atk": atk,
            "pf": 1,
        }
        await http.game_request(
            api_session,
            f"/web-api/game-proxy/v2/GameRule/Get?traceId={codigo_pg()}",
            payload,
            headers
        )


        # ===== GameInfo =====
        payload = {
            "eatk": eatk,
            "btt": btt,
            "atk": atk,
            "pf": 1,
        }
        # Tenta obter info usando api_game (derivado)
        info_game = await http.game_request(
            api_game,
            f"/{geu}v2/GameInfo/Get?traceId={codigo_pg()}",
            payload,
            headers
        )
        
        if not isinstance(info_game, dict) or info_game.get("err"):
            # Fallback para virginia
            info_game = await http.game_request(
                api_game_alt, 
                f"/{geu}v2/GameInfo/Get?traceId={codigo_pg()}", 
                payload, 
                headers
            )
            if isinstance(info_game, dict) and not info_game.get("err"):
                api_game = api_game_alt

        if not isinstance(info_game, dict):
            logger.error(" GameInfo inválido")
            return (0, 0, 0.0, 0.0)

        info_dt = info_game.get("dt", {})

        # Build apostas
        apostas = build_apostas(info_dt)

        # Extrai estado inicial do jogo
        info_ls = info_dt.get("ls") or {}
        ls = info_ls.get("si") or {}
        si = info_dt.get("si", {})

        id_play = ls.get("sid") or si.get("sid") or 0
        cs = ls.get("cs")
        ml = ls.get("ml")
        wk = "0_C"

        # Saldo
        bet_minima = info_dt.get("cs", [0.4])[0] * info_dt.get("ml", [1])[0] * info_dt.get("mxl", 1)
        saldo_atual = ls.get("bl") or 0

        logger.info(f" ══════════════════════════════════════════════════════════")
        logger.info(f" HOOD VS WOLF INICIADO")
        logger.info(f"  Usuario: {usuario} |  Senha: {senha}")
        logger.info(f"  Saldo: R$ {saldo_atual:.2f}")
        logger.info(f" ══════════════════════════════════════════════════════════")

        # ===== Loop principal do jogo =====
        bonus = 0
        error_count = 0

        for set_bet in apostas:
            valor_aposta = set_bet["cs"] * set_bet["ml"] * info_dt.get("mxl", 1)
            valor_aposta_bet = round(valor_aposta, 2)
            last_bet = valor_aposta_bet

            # Bet máxima - pula apostas maiores que TRAVAR_BET
            if valor_aposta > TRAVAR_BET:
                continue

            # Pula se saldo insuficiente para essa aposta
            if valor_aposta > saldo_atual:
                continue

            if saldo_atual <= 0:
                logger.warning(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  SEM SALDO")
                break

            # NÃO DELETAR ESTE CODIGO
            #if saldo_atual < 1:
            #    logger.warning(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  SALDO INSUFICIENTE (<R$1)")
            #    bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
            #    return (bonus, spin_count, bet_final, bonus_count)

            if saldo_atual < bet_minima:
                logger.warning(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  SALDO INSUFICIENTE BET MINIMA (<R${bet_minima})")
                bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                return (bonus, spin_count, bet_final, bonus_count)

            logger.info(f" {usuario} |  START |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  Saldo R$ {saldo_atual:.2f} |  Iniciando jogo...")

            await asyncio.sleep(1)

            # ===== Update Game =====
            payload = {
                "cs": set_bet["cs"],
                "ml": set_bet["ml"],
                "btt": btt,
                "wk": wk,
                "atk": atk,
                "pf": 1,
            }

            update_error_count = 0
            update_game = None
            while update_error_count < 2:
                update_game = await http.game_request(api_game, f"/{geu}v2/GameInfo/Update?traceId={codigo_pg()}", payload, headers)
                if isinstance(update_game, dict) and not update_game.get("err"):
                    break
                update_error_count += 1
                logger.warning(f" Erro update_game {set_bet['cs']} {set_bet['ml']}- ({update_error_count}/3) |  {usuario} - Response: {update_game.get('err')}")
                print(update_game)
                await asyncio.sleep(5)

            if not isinstance(update_game, dict) or update_game.get("err"):
                logger.error(f" Erro persistente update_game (3x) |  {usuario}")
                break

            update_dt = update_game.get("dt") or {}
            update_ls = update_dt.get("ls") or {}
            update_si = update_ls.get("si") or {}
            saldo_atual = update_si.get("bl") or 0
            update_hr = update_si.get("hr") or {}
            id_play = update_si.get("sid") or id_play
            # wk é fixo "0_C"

            # ===== Loop de spins - continua até travar ou saldo insuficiente =====
            while True:
                cs = set_bet["cs"]
                ml = set_bet["ml"]
                payload = {
                    "id": id_play,
                    "cs": set_bet["cs"],
                    "ml": set_bet["ml"],
                    "wk": wk,
                    "btt": btt,
                    "atk": atk,
                    "pf": 1,
                }
                play_game = await http.game_request(api_game, f"/{geu}v2/Spin?traceId={codigo_pg()}", payload, headers)

                # Verifica se resposta é válida
                if not isinstance(play_game, dict):
                    error_count += 1
                    if error_count >= 5:
                        logger.error(f"  {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} | Resposta inválida do spin |  {usuario}")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        return (bonus, spin_count, bet_final, bonus_count)
                    await asyncio.sleep(2)
                    continue

                # Verifica erro na resposta
                if play_game.get("err"):
                    error_count += 1
                    if error_count >= 5:
                        if "enough" in play_game.get("err", {}).get("msg", "").lower():
                            logger.warning(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  SALDO INSUFICIENTE PARA ESTA BET (<R${valor_aposta_bet})")
                            break
                        logger.error(f"  {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} | Erro spin após 5 tentativas | Response: {play_game.get('err')}")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        return (bonus, spin_count, bet_final, bonus_count)
                    err_dt = play_game.get("dt") or {}
                    err_si = err_dt.get("si") or {}
                    id_play = err_si.get("sid") or id_play
                    await asyncio.sleep(2)
                    continue

                error_count = 0

                play_dt = play_game.get("dt") or {}
                play_si = play_dt.get("si") or {}
                tb_value = float(play_si.get("tb", 0) or 0)
                
                id_play = play_si.get("sid") or id_play
                saldo_atual = play_si.get("bl") or 0
                ganho = play_si.get("tw", 0)

                if tb_value == 0:
                    logger.debug(f"  {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  Finalizando spin...")
                    await asyncio.sleep(1)
                    continue

                # Spin válido - processa resultado
                spin_count += 1
                # Saldo passou de 1000 - sai
                if saldo_atual >= 2000:
                    logger.info(f"  {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  SALDO ALTO")
                    return (0, spin_count, last_bet, bonus_count)

                # ===== LÓGICA DE TRAVA DE BÔNUS =====
                bf = play_si.get("bf") or {}
                src = bf.get("src")
                primeiro_valor = 0
                ultimo_valor = 0

                if isinstance(src, dict) and src:
                    valores = list(src.values())
                    primeiro_valor = valores[0]
                    ultimo_valor = valores[-1]
                elif isinstance(src, list) and src:
                    primeiro_valor = src[0]
                    ultimo_valor = src[-1]

                # Condição de trava: == 1 ou == 17 (trava direta) ou == 18 (jokenpô)
                def is_trava(v):
                    return v == 1 or v == 17

                def is_jokenpo(v):
                    return v == 18

                # Verifica se tem símbolo de bônus (trava ou jokenpô)
                has_trava = is_trava(primeiro_valor) or is_trava(ultimo_valor)
                has_jokenpo = is_jokenpo(primeiro_valor) or is_jokenpo(ultimo_valor)

                # Pega o valor do bônus
                if has_jokenpo:
                    current_bonus_count = 18
                elif is_trava(primeiro_valor):
                    current_bonus_count = primeiro_valor
                else:
                    current_bonus_count = ultimo_valor

                # JOKENPÔ (== 18) - rodada normal, não trava
                if has_jokenpo:
                    vitorias = 0
                    derrotas = 0
                    rodada = 0
                    max_rodadas = 10  # Limite de segurança
                    jokenpo_map = {101: "Pedra", 102: "Tesoura", 103: "Papel"}

                    while vitorias < 2 and derrotas < 2 and rodada < max_rodadas:
                        rodada += 1
                        jokenpo = random.choice([101, 102, 103])
                        jokenpo_nome = jokenpo_map.get(jokenpo, "Desconhecido")
                        payload = {
                            "gs": jokenpo,
                            "cs": set_bet["cs"],
                            "ml": set_bet["ml"],
                            "pf": 1,
                            "id": id_play,
                            "wk": wk,
                            "btt": btt,
                            "atk": atk,
                        }
                        play_game = await http.game_request(api_game, f"/{geu}v2/Gesture/Select?traceId={codigo_pg()}", payload, headers=headers)

                        if not isinstance(play_game, dict):
                            logger.warning(f" Resposta jokenpô inválida: {play_game}")
                            break

                        play_dt = play_game.get("dt") or {}
                        play_si = play_dt.get("si") or {}
                        bns = play_si.get("bns") or {}

                        id_play = play_si.get("sid") or id_play
                        saldo_atual = play_si.get("bl") or saldo_atual
                        ganho = play_si.get("tw", 0)

                        # Identifica resultado pelo campo ws
                        ws = bns.get("ws")
                        gr = bns.get("gr") or {}
                        oponente_jogada = gr.get("2", 0)
                        oponente_nome = jokenpo_map.get(oponente_jogada, "Desconhecido")

                        if ws == 23:
                            resultado = "EMPATE"
                            # Empate: continua sem contar
                        elif ws == 3:
                            resultado = "VITÓRIA"
                            vitorias += 1
                        elif ws == 2:
                            resultado = "DERROTA"
                            derrotas += 1
                        elif ws is None:
                            # ws None pode significar que não é mais jokenpô
                            logger.warning(f" ws=None, saindo do jokenpô")
                            break
                        else:
                            resultado = f"({ws}) DESCONHECIDO"
                            # Valor desconhecido - trata como empate para não travar
                            logger.warning(f" ws desconhecido: {ws}")

                        logger.info(f" ═══════════════════════════════════════════════")
                        logger.info(f"  {usuario}")
                        logger.info(f"  JOKENPÔ: {jokenpo_nome} vs {oponente_nome}")
                        logger.info(f"  Resultado: {resultado}")
                        logger.info(f"  Placar: {vitorias} x {derrotas} (Rodada {rodada})")
                        logger.info(f"  Bet: R$ {valor_aposta_bet}")
                        logger.info(f"  Saldo: R$ {saldo_atual:.2f}")
                        logger.info(f" ═══════════════════════════════════════════════")

                        await asyncio.sleep(0.5)

                    # Resultado final do melhor de 3
                    if vitorias >= 2:
                        logger.info(f"  {usuario} VENCEU O MELHOR DE 3! ({vitorias}x{derrotas})")
                    elif derrotas >= 2:
                        logger.info(f"  {usuario} PERDEU O MELHOR DE 3! ({vitorias}x{derrotas})")
                    else:
                        logger.warning(f" Jokenpô encerrado sem resultado definido ({vitorias}x{derrotas})")

                    # Jokenpô é rodada normal - continua jogando

                # TRAVA DE BÔNUS (Menina == 1 ou == 17)
                elif has_trava:
                    logger.info(f"❌❌❌❌❌❌❌  {usuario} |  ENTRAR JOKENPÔ ❌❌❌❌❌❌❌") 
                    continue
                    bonus = 1
                    bonus_count = current_bonus_count
                    primeira_bet_trava = valor_aposta_bet
                    logger.info(f" ═══════════════════════════════════════════════")
                    logger.info(f"  {usuario}")
                    logger.info(f"  TRAVA POR BÔNUS! - BET R$ {valor_aposta_bet}")
                    logger.info(f"  Saldo Atual: R$ {saldo_atual:.2f}")
                    logger.info(f"  Menina: {primeiro_valor} / Lobo: {ultimo_valor}")
                    logger.info(f"  Spins: {spin_count}")
                    logger.info(f" ═══════════════════════════════════════════════")
                    if primeiro_valor == 17:
                        bonus_count = 2
                    else:
                        bonus_count = 1                        
                    if apenas_uma_bet:
                        # Para na primeira trava
                        return (bonus, spin_count, valor_aposta_bet, bonus_count)
                    else:
                        # Continua para próxima bet
                        break
                # Spin normal - continua
                else:
                    if saldo_atual < bet_minima:
                        logger.warning(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  SALDO INSUFICIENTE BET MINIMA (<R${bet_minima})")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        return (bonus, spin_count, bet_final, bonus_count)
                    if saldo_atual < valor_aposta:
                        logger.info(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  Saldo R$ {saldo_atual:.2f} < BET R$ {valor_aposta_bet} - Mudando próxima bet...")
                        break  # Sai para próxima aposta
                    else:
                        logger.info(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} | +R$ {ganho:.2f}")

                cwc_value = float(play_si.get("cwc", 0) or 0)
                if cwc_value >= 1:
                    logger.debug(f" {usuario} |  Spin #{spin_count} |  R$ {saldo_atual:.2f} | BET R$ {valor_aposta_bet} |  Finalizando spin...")
                    await asyncio.sleep(1)
                    continue
                    
                # Delay entre spins
                await asyncio.sleep(0.2)

            # Fim do loop de spins para esta aposta - saldo insuficiente, vai para próxima aposta

        # Retorna resultado
        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
        return (bonus, spin_count, bet_final, bonus_count)

    except Exception as e:
        logger.error(f"❌  {usuario} | Erro no game_hood_vs_wolf_trava: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return (0, spin_count, last_bet, bonus_count)
