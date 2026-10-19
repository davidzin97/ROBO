# -*- coding: utf-8 -*-
"""
Jogo Gem Saviour com lógica de trava de bônus
Baseado em gameGemTrava.js

Lógica de trava:
- Detecta monstro com HP >= 90 (monstro grande)
- Detecta baú travado (bauTravado > 0 && bauTravado <= 6)
"""
import asyncio
import base64
import hashlib
import json
import logging
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

TRAVAR_BET = 15

# Constantes de configuração
MONSTRO_HP_MIN = 90  # HP mínimo do monstro para considerar "grande"
BAU_TRAVADO_MAX = 6  # Máximo de baús travados

# APIs do jogo (mesmo do gameGemTrava.js)
API_SESSION = "api.nkjx8564m.com"  # Para session e rule
API_GAME = "api-ali-virginia-a.nkjx8564m.com"  # Para info, update e spin


def headers_jogo() -> Dict[str, str]:
    """Headers padrão para requisições do jogo"""
    return {
        "accept": "*/*",
        "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://m.whwz8187o.com",
        "referer": "https://m.whwz8187o.com/",
        "sec-ch-ua": '"Chromium";v="150", "Not(A:Brand";v="24", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Linux; Android 13; SM-A536B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36",
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


async def game_gem_trava(
    http: BotHttpClient,
    game_url: str,
    banca_minima: float = 5.0,
    bet_maxima_porcentagem: float = 6.0,
    trava_bau_ativo: bool = False,  # Trava por baú desativada por padrão
    apenas_uma_bet: bool = False,  # Se True, para na primeira trava. Se False, continua em outras bets
    usuario: str = "",
    senha: str = "",
) -> Tuple[int, int, float, float]:
    """
    Executa jogo Gem Saviour com lógica de trava de bônus.

    Args:
        http: Cliente HTTP
        game_url: URL do jogo (game_url do login)
        banca_minima: Saldo mínimo para continuar jogando
        bet_maxima_porcentagem: Valor máximo da aposta
        trava_bau_ativo: Se True, ativa trava por baú (default: False - desativado)
        apenas_uma_bet: Se True (padrão), para na primeira trava. Se False, continua para outras bets
        usuario: Nome do usuário para logs
        senha: Senha do usuário para logs

    Returns:
        Tupla (bonus, spin_count, last_bet, vida_restante): 1 se encontrou bônus, quantidade de spins, valor última aposta e HP restante
    """
    vida_restante = 0.0  # Inicializa HP restante

    # Variáveis de tracking inicializadas ANTES do try para preservar estado no except
    bonus = 0
    spin_count = 0
    last_bet = 0.0
    primeira_bet_trava = 0.0  # Bet da primeira detecção do monstro
    primeira_hp_trava = 0.0   # HP da primeira detecção do monstro

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

        # ===== VerifyOperatorPlayerSession =====
        # Usando API_SESSION (api.6pvx87oz6.com) - mesmo do JS
        payload = {
            "btt": btt,
            "vc": 0,
            "pf": 1,
            "l": "pt",
            "gi": id_game,
            "os": ops,
            "otk": ot,
        }

        session_player = await http.game_request(API_SESSION, f"/web-api/auth/session/v2/verifyOperatorPlayerSession?traceId={codigo_pg()}", payload)

        if not isinstance(session_player, dict) or session_player.get("err"):
            logger.error(f" Erro na sessão: {session_player}")
            return (0, 0, 0.0, 0.0)

        session_dt = session_player.get("dt") or {}
        atk = session_dt.get("tk")
        eatk = session_dt.get("eatk")
        geu = session_dt.get("geu") or "gem-saviour/"

        if not atk:
            logger.error(" Token não encontrado na sessão")
            return (0, 0, 0.0, 0.0)

        # ===== GameRule =====
        # Usando API_SESSION (api.6pvx87oz6.com) - mesmo do JS
        payload = {
            "btt": btt,
            "gid": id_game,
            "atk": atk,
            "pf": 1,
        }
        await http.game_request(API_SESSION, f"/web-api/game-proxy/v2/GameRule/Get?traceId={codigo_pg()}", payload)

        # ===== GameInfo =====
        # Usando API_GAME (api-ali-virginia-a.6pvx87oz6.com) - mesmo do JS
        payload = {
            "eatk": eatk,
            "btt": btt,
            "atk": atk,
            "pf": 1,
        }
        info_game = await http.game_request(API_GAME, f"/{geu}v2/GameInfo/Get?traceId={codigo_pg()}", payload)

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
        wk = ls.get("wk") or si.get("wk") or "0_C"
        hr_data = ls.get("hr") or {}
        jogo_liberado = bool(hr_data.get("atk"))
        rodada_ativa = bool(ls.get("wp"))

        # Monstro (usa "or {}" para evitar NoneType)
        m_data = ls.get("m") or {}
        vida_monstro = m_data.get("mhp") or 0
        hp_array = m_data.get("hp") or []
        vida_restante = hp_array[-1] if hp_array else 0
        ss_data = ls.get("ss") or {}
        rodada_ativa_npc = bool(ss_data.get("act"))

        # Baú
        rlc_data = ls.get("rlc") or {}
        trava_bau = rlc_data.get("c") or 0

        # Saldo
        bet_minima = info_dt.get("cs", [0.4])[0] * info_dt.get("ml", [1])[0] * info_dt.get("mxl", 1)
        saldo_atual = ls.get("bl") or 0

        logger.info(f" ══════════════════════════════════════════════════════════")
        logger.info(f" GEM SAVIOUR INICIADO")
        logger.info(f"  Usuario: {usuario} |  Senha: {senha}")
        logger.info(f"  Saldo: R$ {saldo_atual:.2f}")
        logger.info(f" ══════════════════════════════════════════════════════════")

        # ===== Finalizar rodada em andamento =====
        finalize_count = 0
        MAX_FINALIZE = 50  # Limite para finalizar rodada
        if rodada_ativa or (vida_restante and rodada_ativa_npc):
            while rodada_ativa or (vida_restante and rodada_ativa_npc):
                finalize_count += 1
                if finalize_count > MAX_FINALIZE:
                    logger.warning(f" Limite de 50 finalizações atingido |  {usuario}")
                    break
                logger.debug(f" Concluindo rodada anterior - Baú: {'' if trava_bau else ''}")

                payload = {
                    "id": id_play,
                    "cs": cs,
                    "ml": ml,
                    "wk": wk,
                    "btt": btt,
                    "atk": atk,
                    "pf": 1,
                }

                # Usando API_GAME (api-ali-virginia-a.6pvx87oz6.com) - mesmo do JS
                play_game = await http.game_request(API_GAME, f"/{geu}v2/spin?traceId={codigo_pg()}", payload)

                if not isinstance(play_game, dict):
                    break

                play_dt = play_game.get("dt") or {}
                play_si = play_dt.get("si") or {}
                rodada_ativa = bool(play_si.get("wp"))
                m_data = play_si.get("m") or {}
                vida_monstro = m_data.get("mhp") or 0
                hp_array = m_data.get("hp") or []
                vida_restante = hp_array[-1] if hp_array else 0
                ss_data = play_si.get("ss") or {}
                rodada_ativa_npc = bool(ss_data.get("act"))
                id_play = play_si.get("sid") or 0

        # ===== Loop principal do jogo =====
        last_bet_anterior = 0.0
        vida_restante_trava = 0.0  # HP da bet anterior (para quando trocar de bet)
        roll = 0
        error_count = 0
        log_spin = ""

        for set_bet in apostas:
            # Só muda de bet se vida_restante > 0 e <= 30 (faixa de trava)
            # Se HP alto ou sem monstro, fica na bet atual
            if last_bet > 0 and vida_restante > 30:
                logger.debug(f" Mantendo bet R$ {last_bet} | HP: {vida_restante} > 30")
                continue

            # Salva vida_restante da bet anterior antes de trocar
            if last_bet_anterior > 0 and vida_restante > 0:
                vida_restante_trava = vida_restante
                logger.debug(f" HP anterior salvo: {vida_restante_trava} | Bet: R$ {last_bet_anterior}")
            last_bet_anterior = last_bet
            valor_aposta = set_bet["cs"] * set_bet["ml"] * info_dt.get("mxl", 1)
            valor_aposta_bet = round(valor_aposta, 2)
            last_bet = valor_aposta_bet  # Salva última aposta

            # Calcula bet máxima baseada no saldo
            saldo = max(0, float(saldo_atual or 0))
            porcentagem = (
                0.05 if saldo >= 500 else
                0.03 if saldo >= 200 else
                0.025 if saldo >= 100 else
                0.015
            )
            bet_maxima = bet_maxima_porcentagem
            bet_maxima = TRAVAR_BET

            logger.debug(f" BET Calculada: R$ {bet_maxima} ({porcentagem*100:.1f}%)")

            # Verifica limites
            if valor_aposta > bet_maxima:
                continue

            if valor_aposta > saldo_atual:
                continue

            if saldo_atual <= 0:
                logger.warning(f" SEM SALDO |  {usuario} |  Saldo {LIME}R$ {saldo_atual:.2f}{RESET} |  BET R$ {valor_aposta_bet}")
                break

            if saldo_atual < TRAVAR_BET:
                logger.warning(f" SALDO INSUFICIENTE (<R$6) |  {usuario} |  Saldo {LIME}R$ {saldo_atual:.2f}{RESET}")
                # Usa bet/HP da primeira trava se existir
                bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                return (bonus, spin_count, bet_final, hp_final)

            logger.info(f"🎲 Valor da BET: R$ {valor_aposta_bet}")

            await asyncio.sleep(1)

            # ===== Update Game (com retry) =====
            # Usando API_GAME (api-ali-virginia-a.6pvx87oz6.com) - mesmo do JS
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
            while update_error_count < 3:
                update_game = await http.game_request(API_GAME, f"/{geu}v2/GameInfo/Update?traceId={codigo_pg()}", payload)
                if isinstance(update_game, dict) and not update_game.get("err"):
                    break
                update_error_count += 1
                logger.warning(f" Erro update_game ({update_error_count}/3) |  {usuario} |  Saldo {LIME}R$ {saldo_atual:.2f}{RESET}")
                await asyncio.sleep(5)  # Espera 5 segundos antes de tentar novamente
            if not isinstance(update_game, dict) or update_game.get("err"):
                logger.error(f" Erro persistente update_game (3x) |  {usuario} |  BET R$ {valor_aposta_bet} → Próxima aposta")
                break

            update_dt = update_game.get("dt") or {}
            update_ls = update_dt.get("ls") or {}
            update_si = update_ls.get("si") or {}
            saldo_atual = update_si.get("bl") or 0
            rodada_ativa = bool(update_si.get("wp"))
            update_hr = update_si.get("hr") or {}
            jogo_liberado = bool(update_hr.get("atk"))
            update_rlc = update_si.get("rlc") or {}
            bau_travado = update_rlc.get("c") or 0
            tipo_coluna = update_rlc.get("rt") or 0  # 1=Baú, 2=Sacola, 3=Mapa
            update_m = update_si.get("m") or {}
            hp_array = update_m.get("hp") or []
            vida_restante = hp_array[-1] if hp_array else 0
            vida_monstro = update_m.get("mhp") or 0
            update_ss = update_si.get("ss") or {}
            rodada_ativa_npc = bool(update_ss.get("act"))
            id_play = update_si.get("sid") or 0

            # Verifica condições de trava ANTES de jogar
            if not rodada_ativa and jogo_liberado and not rodada_ativa_npc:
                # Trava por monstro com HP baixo
                if vida_restante and 0 < vida_restante <= 50:
                    last_vida_monstro = vida_monstro[-1] if isinstance(vida_monstro, list) else 0
                    count_vida = len(vida_monstro) if isinstance(vida_monstro, list) else 0
                    logger.info(f" MONSTRO ATIVO #{count_vida} |  HP: {vida_restante}/{last_vida_monstro}")
                    continue

                # Trava por baú (somente se trava_bau_ativo=True)
                if trava_bau_ativo and 0 < bau_travado <= BAU_TRAVADO_MAX and tipo_coluna == 1:
                    logger.info(f" BAÚ ATIVO - TRAVA ATIVADA!")
                    continue

            # ===== Loop de spins =====
            tb_retry_count = 0
            cwc_retry_count = 0
            while True:
                payload = {
                    "id": id_play,
                    "cs": set_bet["cs"],
                    "ml": set_bet["ml"],
                    "wk": wk,
                    "btt": btt,
                    "atk": atk,
                    "pf": 1,
                }

                # Usando API_GAME (api-ali-virginia-a.6pvx87oz6.com) - mesmo do JS
                play_game = await http.game_request(API_GAME, f"/{geu}v2/spin?traceId={codigo_pg()}", payload)
                log_spin = play_game

                # Verifica se resposta é válida
                if not isinstance(play_game, dict):
                    error_count += 1
                    if error_count >= 5:
                        logger.error(f" Resposta inválida do spin |  {usuario}")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        hp_final = vida_restante if vida_restante else 0
                        return (bonus, spin_count, bet_final, hp_final)
                    await asyncio.sleep(2)
                    continue

                # Verifica se tb (total bet) é 0 - se for, repetir request
                play_dt_check = play_game.get("dt") or {}
                play_si_check = play_dt_check.get("si") or {}
                tb_value = float(play_si_check.get("tb", 0) or 0)

                if not isinstance(play_game, dict) or play_game.get("err"):
                    if error_count < 5:
                        error_count += 1
                        if isinstance(play_game, dict):
                            error_msg = play_game.get("err", {})
                            error_code = error_msg.get("cd", "unknown") if isinstance(error_msg, dict) else "unknown"
                            logger.debug(f"⚠️ Erro spin ({error_code}) - tentativa {error_count}/5")
                            err_dt = play_game.get("dt") or {}
                            err_si = err_dt.get("si") or {}
                            id_play = err_si.get("sid") or id_play
                        await asyncio.sleep(5)  # Espera 5 segundos antes de tentar novamente
                        continue
                    else:
                        play_text = json.dumps(play_game) if isinstance(play_game, dict) else str(play_game)
                        if "enough" in play_text.lower():
                            bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                            hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                            return (bonus, spin_count, bet_final, hp_final)
                        else:
                            logger.error(f" Erro spin após 5 tentativas |  {usuario}")
                            bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                            hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                            return (bonus, spin_count, bet_final, hp_final)
                else:
                    error_count = 0
                    
                if tb_value == 0:
                    tb_retry_count += 1
                    if tb_retry_count >= 50:
                        logger.warning(f" tb=0 persistente ({tb_retry_count}x) - saindo |  {usuario} - Response: {log_spin} ")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                        return (bonus, spin_count, bet_final, hp_final)
                    logger.debug(f" Finalizando spin ({tb_retry_count}/50)")
                    id_play = play_si_check.get("sid") or id_play
                    wk = play_si_check.get("wk") or wk
                    await asyncio.sleep(1)
                    continue



                # tb != 0, spin válido - resetar contador e continuar
                tb_retry_count = 0

                spin_count += 1
                roll += valor_aposta

                play_dt = play_game.get("dt") or {}
                play_si = play_dt.get("si") or {}
                tb_value = play_si.get("tb") or 0
                id_play = play_si.get("sid") or 0
                saldo_atual = play_si.get("bl") or 0
                saldo_up = play_si.get("blb") or 0

                # Saldo passou de 1000 - sai da conta (sem bonus)
                if saldo_atual >= 1000:
                    logger.info(f" SALDO ALTO R$ {saldo_atual:.2f} |  {usuario}")
                    return (0, spin_count, last_bet, vida_restante)
                bet_atual = play_si.get("tbb") or 0
                rodada_ativa = bool(play_si.get("wp"))
                play_hr = play_si.get("hr") or {}
                jogo_liberado = bool(play_hr.get("atk"))
                play_rlc = play_si.get("rlc") or {}
                bau_travado = play_rlc.get("c") or 0
                tipo_coluna = play_rlc.get("rt") or 0
                play_m = play_si.get("m") or {}
                vida_monstro = play_m.get("mhp") or 0
                hp_array = play_m.get("hp") or []
                vida_restante = hp_array[-1] if hp_array else 0
                play_ss = play_si.get("ss") or {}
                rodada_ativa_npc = bool(play_ss.get("act"))

                if tb_value == 0:
                    continue

                last_vida_monstro = vida_monstro[-1] if isinstance(vida_monstro, list) else 0
                count_vida = len(vida_monstro) if isinstance(vida_monstro, list) else 0

                valor_roll = round(roll, 2)
                ganho = play_si.get("tw", 0)

                # Verifica se jogo bloqueou por saldo

                # ===== LÓGICA DE TRAVA DE BÔNUS =====
                # Detecta monstro grande (HP >= MONSTRO_HP_MIN)
                if vida_restante and last_vida_monstro >= MONSTRO_HP_MIN:
                    vida_restante_fmt = round(vida_restante, 2)
                    # Log: BRUXA se HP máximo >= 97, senão MONSTRO
                    if last_vida_monstro >= 90:
                        bonus = 1
                        primeira_bet_trava = valor_aposta_bet
                        primeira_hp_trava = vida_restante
                        logger.info(f"👤 {usuario} |  Spin #{spin_count} |  OLHAAAAAA BRUXA!  |  HP: {vida_restante_fmt}/{last_vida_monstro} |  Saldo {LIME}R$ {saldo_atual:.2f}{RESET} |  BET R$ {valor_aposta_bet} |  +R$ {ganho:.2f}")
                    else:
                        logger.info(f"👤 {usuario} |  Spin #{spin_count} |  MONSTRO!  HP: {vida_restante_fmt}/{last_vida_monstro} |  Saldo {LIME}R$ {saldo_atual:.2f}{RESET} |  BET R$ {valor_aposta_bet} |  +R$ {ganho:.2f}")

                    #return (bonus, spin_count, last_bet)
                else:
                    logger.info(f"👤 {usuario} |  Spin #{spin_count} |  Saldo {LIME}R$ {saldo_atual:.2f}{RESET} |  BET R$ {valor_aposta_bet} |  +R$ {ganho:.2f}")

                # Verifica condições de parada (igual JS original)
                if jogo_liberado or (trava_bau_ativo and bau_travado) or not rodada_ativa_npc:
                    if not rodada_ativa:
                        # Monstro grande com HP <= 30 - TRAVA
                        if vida_restante and last_vida_monstro >= MONSTRO_HP_MIN:
                            if 0 < vida_restante <= 50:
                                bonus = 1
                                primeira_bet_trava = valor_aposta_bet
                                primeira_hp_trava = vida_restante
                                logger.info(f" ═══════════════════════════════════════════════")
                                logger.info(f"  Usuario: {usuario} |  Senha: {senha}")
                                logger.info(f"  BRUXA!  TRAVA POR HP BAIXO!")
                                logger.info(f"  Saldo {LIME}R$ {saldo_atual:.2f}{RESET} |  BET R$ {valor_aposta_bet}")
                                logger.info(f"  HP: {vida_restante} <= 50  |  Spins: {spin_count}")
                                logger.info(f" ═══════════════════════════════════════════════")
                                if apenas_uma_bet:
                                    # Para na primeira trava
                                    return (bonus, spin_count, valor_aposta_bet, vida_restante)
                                else:
                                    # Continua para próxima bet
                                    break

                        # Baú travado (somente se trava_bau_ativo=True)
                        if trava_bau_ativo and 0 < bau_travado <= BAU_TRAVADO_MAX and tipo_coluna == 1:
                            bonus = 1
                            logger.info(f" ═══════════════════════════════════════════════")
                            logger.info(f"  Usuario: {usuario} |  Senha: {senha}")
                            logger.info(f"  TRAVA POR BAÚ!")
                            logger.info(f"  Baús: {bau_travado}")
                            logger.info(f" ═══════════════════════════════════════════════")
                            if apenas_uma_bet:
                                # Para na primeira trava
                                return (bonus, spin_count, valor_aposta_bet, vida_restante)
                            else:
                                # Continua para próxima bet
                                break

                cwc_value = float(play_si_check.get("cwc", 0) or 0)
                if cwc_value == 0 and tb_value == 0:
                    cwc_retry_count += 1
                    if cwc_retry_count >= 50:
                        logger.warning(f" cwc=0 persistente ({cwc_retry_count}x) - saindo | 👤 {usuario} - Response: {log_spin} ")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                        return (bonus, spin_count, bet_final, hp_final)
                    logger.debug(f" Finalizando spin cwc ({cwc_retry_count}/50)")
                    id_play = play_si_check.get("sid") or id_play
                    wk = play_si_check.get("wk") or wk
                    await asyncio.sleep(1)
                    continue
                else:
                    cwc_retry_count = 0

                # Verifica saldo
                if not rodada_ativa and jogo_liberado:
                    if saldo_atual < valor_aposta:
                        logger.warning(f" Saldo insuficiente para aposta")
                        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                        hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                        return (bonus, spin_count, bet_final, hp_final)

                if saldo_atual < bet_minima:
                    logger.warning(f" Saldo abaixo da bet mínima")
                    bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
                    hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
                    return (bonus, spin_count, bet_final, hp_final)

                await asyncio.sleep(1)

        # Usa bet/HP da primeira trava se existir
        bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
        hp_final = primeira_hp_trava if primeira_hp_trava > 0 else (vida_restante_trava if vida_restante == 0 and vida_restante_trava > 0 else vida_restante)
        return (bonus, spin_count, bet_final, hp_final)

    except Exception as e:
        logger.error(f" Erro no game_gem_trava: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        # Preserva bônus já detectado mesmo se erro ocorrer depois
        if bonus > 0:
            bet_final = primeira_bet_trava if primeira_bet_trava > 0 else last_bet
            hp_final = primeira_hp_trava if primeira_hp_trava > 0 else vida_restante
            logger.info(f" Bonus preservado após erro! bonus={bonus} spin={spin_count} bet={bet_final} hp={hp_final}")
            return (bonus, spin_count, bet_final, hp_final)
        return (0, 0, 0.0, 0.0)


async def jogar_gem_trava(
    http: BotHttpClient,
    data_login: Dict,
    platform_api_url: str,
    headers_cipher: Dict[str, str],
    key_request: str,
    jogo: Dict,
    trava_bau_ativo: bool = False,  # Trava por baú desativada por padrão
) -> Tuple[int, float]:
    """
    Interface de alto nível para jogar Gem Saviour com trava.

    Args:
        http: Cliente HTTP
        data_login: Dados de login do usuário
        platform_api_url: URL da API da plataforma
        headers_cipher: Headers cifrados
        key_request: Chave de request
        jogo: Dados do jogo
        trava_bau_ativo: Se True, ativa trava por baú (default: False - desativado)

    Returns:
        Tupla (bonus, saldo_final)
    """
    from utils import encrypt_request, decrypt_request, is_base64
    import time

    try:
        # Login no jogo
        game_data = {k: v for k, v in jogo.items() if k != "name"}
        game_data["time"] = int(time.time())

        encrypted = encrypt_request(json.dumps(game_data), key_request)

        response = await http.api_request(
            platform_api_url,
            "/hall/api/gameCenter/gameApi/login",
            encrypted,
            headers_cipher,
            use_proxy=False,
        )

        if not is_base64(response):
            logger.error(" Resposta de login não é base64")
            return 0, 0.0

        decrypted = decrypt_request(response, key_request)
        data = json.loads(decrypted)

        if data.get("code") != 1:
            logger.error(f" Erro no login do jogo: {data}")
            return 0, 0.0

        game_url = data.get("data", {}).get("game_url", "")

        if not game_url:
            logger.error(" game_url não encontrado")
            return 0, 0.0

        # Executa jogo com trava
        resultado_jogo = await game_gem_trava(
            http,
            game_url,
            trava_bau_ativo=trava_bau_ativo,
        )
        bonus = resultado_jogo[0] if isinstance(resultado_jogo, tuple) else 0

        # Obtém saldo final
        saldo_final = 0.0  # TODO: Implementar obtenção de saldo final

        return bonus, saldo_final

    except Exception as e:
        logger.error(f" Erro no jogar_gem_trava: {e}")
        return 0, 0.0
