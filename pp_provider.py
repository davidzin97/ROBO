# -*- coding: utf-8 -*-
"""
Motor de jogo para Pragmatic Play (Spirit of Adventure e outros)
Protocolo: form-urlencoded via gameService (doSpin, doCollect, etc.)
Resposta: query-string (key=value&key=value)

Fluxo:
1. Hall API login → retorna playGame.do URL
2. Acessar playGame.do → redirect para html5Game.do?...&mgckey=AUTHTOKEN@...~stylename@...~SESSION@...~SN@...
3. Extrair mgckey completo da URL final
4. Usar mgckey para todas as operações (spin, balance, settings, collect)
"""
import json
import time
import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlparse, parse_qs, urlencode, unquote

logger = logging.getLogger(__name__)


class PPProvider:
    """
    Motor de jogo para Pragmatic Play.
    
    A Pragmatic usa:
    - Autenticação via mgckey (formato: AUTHTOKEN@<token>~stylename@<style>~SESSION@<session>~SN@<sn>)
    - Giros via POST form-urlencoded para /gs2c/gameService
    - Respostas em formato query-string (balance=X&tw=Y&...)
    - Verificação de saldo via GET /gs2c/reloadBalance.do?mgckey=...
    - Detecção de bônus: na=b (tela dos baús) / rs_m (free spins ativos)
    """

    def __init__(self, http_client, mgckey: str = "", symbol: str = "vs10spiritadv"):
        self.http = http_client
        self.mgckey = mgckey
        self.symbol = symbol
        self.last_balance = 0.0
        self.index = 0
        self.counter = 0
        self.game_host = None  # Ex: https://v5lrk1jamp.zoblcavrbj.net
        self.game_referer = None  # URL completa do html5Game.do para usar como referer

    def _parse_response(self, text: str) -> Dict[str, str]:
        """
        Parseia resposta da Pragmatic (formato query-string).
        Ex: tw=1.00&balance=307.69&na=c&...
        """
        if not text or not isinstance(text, str):
            return {}
        
        result = {}
        for key, value in parse_qsl(text, keep_blank_values=True):
            result[key] = value
        
        return result

    def _get_headers(self) -> Dict[str, str]:
        """Headers padrão para requisições ao servidor Pragmatic"""
        headers = {
            "Accept": "*/*",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.game_host or "",
            "Sec-Ch-Ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        }
        if self.game_referer:
            headers["Referer"] = self.game_referer
        return headers

    async def get_user_info(self, game_url: str) -> Optional[Dict]:
        """
        Inicializa a sessão Pragmatic:
        1. Acessa playGame.do (com follow_redirects)
        2. Extrai o mgckey COMPLETO da URL final (html5Game.do)
        3. Extrai o host do servidor de jogo
        4. Busca saldo inicial via reloadBalance
        
        Args:
            game_url: URL do playGame.do retornada pelo Hall API
        """
        try:
            # Extrai host base da URL original
            parsed_original = urlparse(game_url)
            self.game_host = f"{parsed_original.scheme}://{parsed_original.netloc}"
            
            # Acessa a URL do jogo seguindo redirects
            response = await self.http.request(
                game_url,
                method="GET",
                follow_redirects=True,
                use_proxy=False,
                timeout=20,
            )
            
            # Tenta extrair mgckey da URL final (após redirect)
            final_url = str(response.url) if hasattr(response, 'url') else ""
            
            if final_url:
                # Atualiza o host a partir da URL final (pode mudar após redirect)
                parsed_final = urlparse(final_url)
                self.game_host = f"{parsed_final.scheme}://{parsed_final.netloc}"
                self.game_referer = final_url
                
                # Extrai mgckey da URL final
                qs_final = parse_qs(parsed_final.query)
                if 'mgckey' in qs_final:
                    self.mgckey = unquote(qs_final['mgckey'][0])
            
            # Se não conseguiu via redirect, tenta extrair do HTML
            if not self.mgckey:
                text = response.text if hasattr(response, 'text') else str(response)
                mgckey_match = re.search(r'mgckey[=\s:]+([A-Z]+@[a-f0-9]+~[^\s\'"&]+)', text)
                if mgckey_match:
                    self.mgckey = unquote(mgckey_match.group(1))

            if not self.mgckey:
                logger.error("PPProvider: Não foi possível extrair o mgckey!")
                return None

            # Busca saldo inicial via Init
            await self.do_init()
            
            return {"status": "ok", "balance": self.last_balance, "mgckey": self.mgckey[:30] + "..."}
            
        except Exception as e:
            logger.error(f"Erro no get_user_info Pragmatic: {e}")
            return None

    async def do_init(self) -> Optional[Dict]:
        """
        POST doInit -> retorna balance, index e counter iniciais.
        index=1, counter=1 no envio; servidor retorna counter=2.
        """
        if not self.game_host or not self.mgckey:
            return None

        # Init manda index=1 e counter=1
        self.index = 1
        self.counter = 1

        payload = {
            "action": "doInit",
            "symbol": self.symbol,
            "cver": "399071",
            "index": "1",
            "counter": "1",
            "repeat": "0",
            "mgckey": self.mgckey,
        }

        url = f"{self.game_host}/gs2c/ge/v4/gameService"
        headers = self._get_headers()

        try:
            response = await self.http.post_form(
                url,
                payload,
                headers=headers,
                use_proxy=False,
                timeout=15,
            )
            
            text = response.text if hasattr(response, 'text') else str(response)
            logger.debug(f"PPProvider init raw response: {text[:400]}")
            result = self._parse_response(text)
            
            if "balance" in result:
                try:
                    self.last_balance = float(result["balance"])
                except:
                    pass
            elif "balance_cash" in result:
                try:
                    self.last_balance = float(result["balance_cash"])
                except:
                    pass
                    
            if "index" in result:
                try:
                    self.index = int(result["index"])
                except:
                    pass
            if "counter" in result:
                try:
                    self.counter = int(result["counter"])
                except:
                    pass
                    
            return result
        except Exception as e:
            logger.warning(f"Erro no doInit Pragmatic: {e}")
            return None

    async def reload_balance(self) -> float:
        """
        Verifica o saldo atual via /gs2c/reloadBalance.do
        A Pragmatic faz isso a cada ~10 segundos.
        """
        if not self.game_host or not self.mgckey:
            return self.last_balance

        url = f"{self.game_host}/gs2c/reloadBalance.do?mgckey={self.mgckey}"
        
        headers = self._get_headers()
        # reloadBalance é GET, não precisa Content-Type
        headers.pop("Content-Type", None)

        try:
            response = await self.http.request(
                url,
                method="GET",
                headers=headers,
                use_proxy=False,
                timeout=10,
            )
            
            text = response.text if hasattr(response, 'text') else str(response)
            
            # Resposta pode ser JSON ou query-string
            # Tenta JSON primeiro
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    balance = data.get("balance", data.get("balance_cash", None))
                    if balance is not None:
                        self.last_balance = float(balance)
                        return self.last_balance
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Tenta query-string
            result = self._parse_response(text)
            if "balance" in result:
                self.last_balance = float(result["balance"])
            elif "balance_cash" in result:
                self.last_balance = float(result["balance_cash"])
                
            return self.last_balance

        except Exception as e:
            logger.warning(f"Erro no reloadBalance Pragmatic: {e}")
            return self.last_balance

    async def spin(self, c: float = 0.10, l: int = 10) -> Optional[Dict[str, str]]:
        """
        Executa um giro no jogo Pragmatic via /gs2c/gameService (action=doSpin).
        
        Args:
            c: Valor da moeda (coin). Total bet = c * l
            l: Número de linhas
            
        Returns:
            Dict com a resposta parseada (balance, tw, na, g, etc.)
        """
        if not self.game_host or not self.mgckey:
            logger.error("PPProvider: game_host ou mgckey não inicializado. Chame get_user_info primeiro.")
            return None

        self.index += 1
        self.counter += 1

        # Payload no formato form-urlencoded
        payload = {
            "action": "doSpin",
            "symbol": self.symbol,
            "c": f"{c:.2f}",
            "l": str(l),
            "sInfo": "n",
            "index": str(self.index),
            "counter": str(self.counter),
            "repeat": "0",
            "mgckey": self.mgckey,
        }

        url = f"{self.game_host}/gs2c/ge/v4/gameService"
        headers = self._get_headers()

        try:
            response = await self.http.post_form(
                url,
                payload,
                headers=headers,
                use_proxy=False,
                timeout=15,
            )
            
            text = response.text if hasattr(response, 'text') else str(response)
            logger.debug(f"PPProvider spin raw response: {text[:800]}")
            result = self._parse_response(text)
            
            if not result:
                logger.warning(f"PPProvider: Resposta vazia ou inválida no spin: {text[:300]}")
                return None

            # Atualiza saldo
            if "balance" in result:
                try:
                    self.last_balance = float(result["balance"])
                except:
                    pass

            # Atualiza contadores (a Pragmatic devolve o index/counter atualizados)
            if "index" in result:
                try:
                    self.index = int(result["index"])
                except:
                    pass
            if "counter" in result:
                try:
                    self.counter = int(result["counter"])
                except:
                    pass

            return result

        except Exception as e:
            logger.error(f"Erro no spin Pragmatic: {e}")
            return None

    async def do_free_spin(self, c: float = 0.10, l: int = 10) -> Optional[Dict[str, str]]:
        """
        Executa um giro grátis (free spin) no modo bônus.
        Mesmo endpoint, mas a Pragmatic sabe que é free spin pelo estado da sessão.
        """
        return await self.spin(c=c, l=l)

    async def collect(self) -> Optional[Dict[str, str]]:
        """
        Coleta o prêmio (doCollect) na tela dos baús.
        """
        if not self.game_host or not self.mgckey:
            return None

        self.index += 1
        self.counter += 1

        payload = {
            "action": "doCollect",
            "symbol": self.symbol,
            "index": str(self.index),
            "counter": str(self.counter),
            "repeat": "0",
            "mgckey": self.mgckey,
        }

        url = f"{self.game_host}/gs2c/ge/v4/gameService"
        headers = self._get_headers()

        try:
            response = await self.http.post_form(
                url,
                payload,
                headers=headers,
                use_proxy=False,
                timeout=15,
            )

            text = response.text if hasattr(response, 'text') else str(response)
            result = self._parse_response(text)

            if "balance" in result:
                try:
                    self.last_balance = float(result["balance"])
                except:
                    pass
                    
            if "index" in result:
                try:
                    self.index = int(result["index"])
                except:
                    pass
            if "counter" in result:
                try:
                    self.counter = int(result["counter"])
                except:
                    pass

            return result

        except Exception as e:
            logger.error(f"Erro no collect Pragmatic: {e}")
            return None
