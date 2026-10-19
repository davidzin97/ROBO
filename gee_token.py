# -*- coding: utf-8 -*-
"""
Sistema de cache do geeToken com Playwright e API direta
Baseado em geeToken.js

- Cache em SQLite com transações atômicas (concorrência segura)
- API direta do GeeTest (método rápido, sem navegador)
- Playwright assíncrono como fallback para buscar novos tokens
- Lock por host para evitar requisições duplicadas
- Persistência em banco de dados para reutilizar entre execuções
"""
import asyncio
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from typing import Dict, Optional
from contextlib import contextmanager

import httpx
from curl_cffi.requests import AsyncSession
from playwright.async_api import async_playwright, BrowserContext, Page

from config import GeeTokenConfig, ProxyConfig, runtime_config
from http_client import (
    BROWSER_PROFILES_ANDROID,
    _select_browser_profile,
    _get_extra_fp,
)

logger = logging.getLogger(__name__)

# Proxy padrão para geeToken (sempre usa proxy)
GEE_PROXY_CONFIG = ProxyConfig(usar_proxy=True)


def _configure_httpx_logging():
    """Configura logging do httpx baseado no DEBUG_MODE"""
    level = logging.DEBUG if runtime_config.get("DEBUG_MODE") else logging.WARNING
    logging.getLogger("httpx").setLevel(level)
    logging.getLogger("httpcore").setLevel(level)


# Configura na importação
_configure_httpx_logging()

# Arquivo do banco de dados SQLite
GEE_TOKEN_DB_PATH = "cache/gee_tokens.db"

# Payload para gerar gee_token via API direta (método rápido)
#GEE_PAYLOAD = '"R0VFAAYxMjg2MTQ5MWIyZGNmMTVkYWNmYWZlNmQ2ZGVkOWUzYWRiNDAzZjM3YTBlOTVjOTJkYjMwZGM4YTFhMDMzMWY2NGUwYTQ3YzM2YjNiNTQwMGY3ZWQ5ZDg2ZjIxMTJlNTVkMzExNjJmNTVjZGQ1MjhmMGQ1OWNiMzY1NjQ0OWU5OGViNzY5NTk4NGRmYmYxYTc0NDcyNDUyMzBjZDkwMzAxNzY5ZmYyZDFjNmI5ZmY3NWJhZjcyMzliMmY0ZGU3Mzc0ZDhlNGRkNWRkNzc3NjRkZjA0YzMzYzA4ZDhkMGQ0ZjhiNDcwOWM0NDYwOTQxZGE5ZTdhN2Y2ZjgzMTI3NmRhNmZlNzFkNjI1OTRiNTZiYzlhNWJlZDA1YTZmNDJhY2Q3NTlhZDUyNmE4NzdiNjMxZDlhNWQ3ZDVkZGRiYjJmODRlYzVmZThlMWI0NDhiY2M0OTczNjdlZWQzODlmMDQxMTA1MGVkMTNlNjdkNmIyNDkwNzA5OTg0ZWZmOGViZTVhMzYwMjlhM2IyMzNiMzQwZTMzMzAwYWZiZTNhMGIyN2JlMjI2ZTZlYjQ0Y2VkZDJlNDI3MGMzZWQyNjUyNzNkODM2MTUxMGU2NDczMmIxODI1ZjFkMmJlNzY4NGI2Mzg5NTVmNmFjNGFhY2IzOTU2OThkMzEyMzlhODgyMzIwYzA1MTE2YThjZDRkMjBkYzVkMWFiZmU5NzhhNmJjMjM0YjFlMDAxNDFlNDNjZTdkNTI2NjZmYTExMzMzYTBiN2M4OWM0NWQzMGVhYzAyMGEyYWU4ZTdiZGU3NTYyMjE2YjFhNDEwYTE0Y2VmMGZlOGZiMTZkODE3YjAyY2EyY2E3YTk1NTJjZWM3Y2FmMzc2ZThjNWY5NTM5OGUyNzg1Nzk3YjZjOGRjNDBmMjg2M2U3ZjUwZWQwNDBhYzI1NTJjYmY1OTFkOTI3ZjM3NGE4OWI4NTRmZWM2ZmZkMDhlOGM1NjQ4MzFiYjFjNDY0MmUxZjFlZjYyZmRmZTZhNGRlODZhZjYxYzQ2Y2ZkNWJmMjNkODRmN2FhMDIyMWM5YTcwYjc5YTU1NTNkMDYyYzI0Yzg0MDQwY2VkZjY1YmQxN2EwMzBhZDAxOWZkMTQ2ZjIwOTJmYWMyZWY5ODFhNDE2YzE1ODI1ZjQ3NmJhMDZkOTU5YTIyNGVkZjIxOGVkMmVhMDM1OGFiMTZiYzRkZjEzZTBjYmVhM2Y2NjIwNWIwMzg0OTE4MWI5OTg5ZjBlM2I4ZDI3MGQ4NDI3YmI0NmYxNmZkMTdjNWU3MWRjN2IxODA0ZmNiNmUyZmUzZTVkYzAxZDMzN2ZjYjkyMWQ0ZmVjZmYxZjU3Zjc1MWZiMzczZjRlODQ5OGVmNzYzNmU2YTA2YjUxNzA0ODhjMWYwYjA3ZjNjOGVkNDQ3OWI0Y2NkY2U2ZWMyMTBhMGYwZDEwZDc4NjU1N2RhNDU1MDVjMDAzNTIyZDdhMzQyZGVmNTQyZjBmZWY4NWUyMDkzNTBiNmNlOGZkZDYwYjMwM2NiZGRiNGQyYWZkNjMwOTk5YjZmMjBlZDdjOTU0MzcxMjRmZjcxNDkzZjEwMGQ1NWU4M2M0ZGU0ZjVjN2JiNGVkNTEyZmY2MDM4Y2VkNWJmNWM3M2Q5ZmYzMDc0YTg0YTU0ZGI4MDRlMGM4YzE1OTdlZWM4YjUzNGZjYzQyNDgwOWM0MjRhYTk0NjVhOGRmZTE0ZjVlNTFjMDg3N2E1MTk1ZGQ4OTQyMWFhYWQ3ZGFhYjUzMTc0ZGZhZjBhOTg1ZDIyNzdmMzQwNmRjMTMzMzY4NDI5MTRjODg1ZmIxMmZlNzI2YmM2N2Q1Y2M5NjNiNTkzMDEzYjdhMzE4MjEyYjRiY2Y5YTA0MzkyMTZhYjQ0MjE1MmY1MTAzODcyNDljN2EwYjdjNGUxMmJkNTdhMWIwMzY0NWUxODM0ZTg4YWUyNjRlNDZlZThhOWQxZDI0NzQ3OWU2NGY3ZTAzYmM0ZDM2YjZjODE3YTY5NGUwMmRlZTc1MzYyMTk3ZWRhNTNlYzA5M2IyYmM4MDAyYTNjNzQ5OGFjZGI3ZWI4ZWI5ODYzYWFiYjZjYmU1MTRiYmU4YzExYWI3YzI0NzgzOTU1ODhhZGM4Mjk3MGRlY2FhMTJkMTUxYmE1YjQ5ZWU1NjY2ZWM3NGU4NzhlNDc3NzgwZTJlMmM5ZTVhNjI1OTNhMDYwMzU2NWM2NDllMTUzNTU3ZjFmYzc5YTM0NDA3NTMwNTQ4ZWE3ODk3OTcxZDUwY2QyZDQ2NzM3OTgxYTBjOWFjZWM1ZWZjYzc4YjVkM2Y1NWM0MzUyNTgxYzE3YjMyMTMwYzgxYWJhMzljY2EzZTk5ZjgxZjY4ZmVjNTI4NTM0ZDQ5MjQzMmY4ZTY2YjM0YjA0MDdlOWZlMTFiNmI4NjkyMmNkYmY3NWI4ZWMwYTgyODhiZDcyOGZkNGI3N2E1NGE1MWI5MGY4ODUwZjQwZmM0ODI5ZDljNDQwNmZiZGQ0NDNiYTQzN2VlZDE0Mjc5MzMwNWNmNmVjNzZiN2U2MGJkYmI2MDJkMWEyOWEzMGJiNzdiMmM1OGMwZjlmODIwODkwYmQ0ZjY4MTEyMTlmNzk1MGQwZGM0ODQ1NDczNzc5NmI1YTk3NzQ2OTM4N2VjY2I3OGU5YmRhYjM5ODE5MTI4YjM2OWUzNmFhMjU0YTk0OTRhZjJjNzdjZDBhY2E3ODZkODY0OTM1MmFkYzRmZTJlOWNjMDBjMDBkMzMyOGQyN2U0YTg1Yzk4NGM4Mjg2YmU5ZTA5MzEwY2YyOWEzNjY4ZDIzYTcyZmU1MTZiMmEwNmI2YTQ4Y2U4NWQ0OWU4NjM3MGZhYjMxYjU0N2VlZjhhNmI0ZDQwNDVmYjU4ZDZhNGNkNDg1ZGVhNDE5OWRhMDkxMDg2MzliYzUzMWQxMTc2NjIyZmNmZGVhODFiNWZkYmIxOWNmZDA4NDdhNDU5NzA1ZTY5MWNhODI2NDg5Mzc3MjUxNTA5YmRiYjBhYmZlMTc2MDI5Nzc5ZTkzOWQxNDcwM2RjM2UxNjcxY2RkM2M3NTc0NzczY2VmMDFiMGMwNzcxN2JiODIxZDc0OTdmZjU1MDhjMzlhM2MxOTQ4ODA4YTExNzgyMTdmZTNhYzk5N2JiNjczMjYzZWM0OTU2OTg2ZGM2MDQ3OTAzNTUzY2EzMjVmZWY0ODYyYmUyYjcwNjI1MTIyMTM5YmFkZTc5YTI5NzRkMDMwYw=="'
#GEE_PAYLOAD = '"R0VFAAY5NjY4ZDY1OTg0ZThkZDA2ZjVlZDQ0YzZmZDU4MzBkOTE2YjlhYWM1ZjY1NjczNGFhYjBhYjU1MTA3MWE2NzAwZjIwMzUyMTVhMDRkMDNiNzQ5NmI0MTMxNzQwOTVhOGVmMTIxNzQ0NjQxOWIzMTZlNGZmNzI5M2EyN2JmMTk2MmE0NjFlNzQ2ODNiOTZhMmFkZTY4ZTFkM2FjYjZjYjM5N2Y3ZDY3NGY5NzlkODc3YzQ3NmYzYTk1ZjU3OTJhMjA2MTBkNjRlNDM2ZGRhNjVmMmVhMWNjOWY3MDUyN2QxY2RlOGZlN2Y5OTI5NGI4YzdmYjRjYWQ2NjIzYjEwYjE2ZmE0ODQ3ZTM2M2E3MDAzNWI2ZTEzZWM4ODQwMTQ4MDEwZjVlYzliNjkzYjllMTY0NzliZWUwZmY0YTRiNmE3YzMxMjA0ZDdhNDliMjRjYTRiMjBjNDE2OTJlY2Y2YjhmZTUxNmY1YTM1NDI5YzQ3MjA5YzM0NTQ2NjZhMTI4OTE1ZWU2MjJlMjQ3YWI1NzRkNWY3YWVjZTUyZTc3MTk0OTc4Y2JiMGU4YmJiYTA4NGU3NmNiZmE1ZTQ0NWIxZDVjMjI4YzNlYzI4MGU3MWE5NmYzZWE5NjdmODgyNjAxNmE2NGY0OWU3MWExZWVkYTliMTRiYjliN2M3OWM1ZDBmYzczNmU1M2MxNDBhNjBkYmUyYzFiZjEwYjllYzA2NmI3MGFlMDU3NWQ0NmQyODVhNWVlYzAyZTUyYTRmNjJiM2YzNzg3NWYzZDViYTU2MDI1MDdmMGFlZjI3MTEwM2Y1OTM4MDA1NzUxZDliNzI5NWY5NGU3MWM2Zjk5ZDFlMzMwNjA2OWI3YTYyN2I1ODA0NzhhYjgyMDg0Y2MzMDVjYTdlNzc0YTIxZDgyODgwYmRlMTY3ZDE3NGUwMDYxZTVkNWM4ZTA5NWM1OTUwNTYxYzgyMDRkMzcwZTA3MjVlZDY5YzUwM2Y5OGNlZDdhNTdhZGU5Mzc0ODRjNDc0ZGZiZDJkN2UyOGRmNmZmNDNmYjRjYjUwYzg5YTZlZWJlNDgxMThkMTY4MjY3ZjU3MmRmYzgyYTY5Mzk2MDVjNTU2ZDE1Y2UwY2M5NzgyYmY4ZjlmNzNjYWVhOGVkMmJkNGY5YjEyNjI5NDhkMWJlNjUzYzcwZTM2NjYyMTc0NWU3MTY2YzgyMDk4ZjM3MGI0NGFiMzU1ZWYyNWNjYjZmYzNmMzA1NDNlOTA2MWFkODA5NjAyNDMwOTc3YzQ3YjNhNzkyMjI3NDdiMDQyNTQxNDliYmU5ZTA2NTg0NTQ2MmM1MGE5YWU3MThmYjZjODZmZjM2NWYxNmY1N2E2NzYwMjUwMjZhYTA0NDQzMzIxZWQzMjgyZTc5NGVhYjAzOGE0NDU3YzQ2NWUyMjRjNzdhM2RmNzAzNjI1YWRkYTQxNTcxZDRmYjg3OGVlMTgwNmFiZGE5OTBjY2U0MjRkNTFiMmU0NzI2Y2Q5MGRhMzdmNzBiZTg5NTUzN2VlNTE4MzlkM2VjODk3ZGIyZjUyOTZmYmZlY2ZkZGM0ZjMwYTc5NDYxZTFjNjg4MjFjNzA1YzM1OWZmOTUxODlhZDdhYzg1NzgzZTAxNmYxZWU0ZmRmYWFlMWYxZjMxODRiNDU5NmYwZDBjZmNhZWIxNDlmN2FkNjEzN2ZjOTZiOWRlNjhlMmFhYzhkY2YwNTkxMTMxOTBhMjA0MDYyNDc5MmVjYmE0MWY5ODFmODcxYWZiZGY4NjNiOGNlNzk0YTlkOWQ1ZjA4YTUwYWFhNTUzNjk5MjU1OTE1NzA5MmY1NTI5MGVlMGNkMmJiN2Y1MjEwNjc2NjBlZDEzMTViOGJkNjVkZjFhMDkzNDI4Njk4NzI1NzJlMjNlYTFmZTZjYjFjOTBhZTBlMWIxOWJmZWQzZDBmZDUzZmU3OWNlYjE4YjAyM2QyNGM5ZmQ5N2M0YzhkMWRjYzkyMGNkMTYxMTMzNjRhODliZTk3MDMxYWMwMGIyYTU3OGZmZDZmZGY5OWRmMWJjODFlMDdiMWQ4YTZhNTllMjgyNzcyMzZlMDViMjM3ZDUzNTZkNDk5NmFiMDA2OTI4MDFlODcyNzgxZTY5ZGEwNjQzODViMmQ3ZTk4YmRmYTAwZjEzOTg0N2M4Y2RiZmEyYTQ0NTZmZDBiYmVmOGY3ZjY3ZDFhYWYyYjE1YTRjMTBmZGYwZDVjNDI2YTI3MTJiOWFkYTdjZDM0NzlhYjY2ZDkyM2IyNzk0NmU3YzgyOTc5NGZkOWRmODBmY2I4ZWQ2NGFkZGVkN2ZhODdjMDQ2N2UxYTgwODE1MTE2OWY0NzgzYjIxMzRlZDhlNGJhZjhlY2QyM2UwN2U3N2IwNDAzOTYyOGY0NTNjZGI5NTU4ZWE1MWYzNjBhOWE5YWY4YjRhOTUyNzRkMGY2YWYwNjc4ODIzYzczYzQxYzg3YTk2NTVhMmUxNzJmNTQxNWViYTBjNDJjNTIyNzE1OWQwMmIxOWYyMDg1MWRkZWFiNTJmNDU0ZDdiM2Q2NDIzZWY0ODNhMjAzNTU1NWFkODgyMTA3NTlkNTg0NWE1Njc3Nzk2OTliYjMzODc3ZjRhYTkxNTJhZWU1MGM3Yzg1MTZjNjNlZTc0ZjViMDZlZTljYWEwMzkyYmIzNzc0Y2IwOTQwYjU3ODU5MjU4MmQzNzgyMTgxNzJiYjlkY2Y2MDIzOGMwYzdkYzBmMjBhOTlmZDQ5YTU1MjAwOTdiMTk1ZDhkZTI2OWIxMWJlNjQwNGJhNjZlM2JjZjUzNzMyOGQ5MjAzMzU3ZGI1N2QzNTViZjU3ZmQ0OTVhMmNjMDMyYmUxNTU0NmUzYTU2MDZlYmJhOWUzZTRhYzhkNTM4ZjU3NWE5OGQ5NmZhZmRhYjdlN2M2ZGNlZjFiNWZlNWZlYzM2MWQ5YWNmZDZlNDVmMTQ1MjVkNWMwMGIzMDE3N2UzMzIyNTU0OGQxYmQwOTJkOGFhOWM4M2QyMThkZWVlMGI0N2U2ZTM0MmJjNDkyNTM5YTEwOGZlZGYzNzkzMmQxZWYzYTYzYTk1YjliZGIyNjA4YjRjMDQ5ZWE1MmM2N2ExMzdiZWRlODMyNzc1OTExMGI0OWFkY2Y3ZjEzYmI2MTdjZDMwNjQxMWY2NjM5MGRlNjU1OWZmZGYwODVjZDQ0OWE2M2FhZTlkMTEwNGY4NWUzNmUyYjEyZDhhYjI3YzliYjk3MzBiMzM5NGI2ZjYwNmY0N2RkZjA0OWUxNWZiNGU3OWZkNzg5ODhhZjk5NDk2NjE3NDhmZGY0OTZjYmVhYTEyODA0ZThkYWUzMDI1NDIxYmFlNTc3YWRmZDJhZWI3ZjZkYTE4NGVkNGUxNWExMDY4M2VmMTc1ZDI1NjliYjY3NWVhODIzZmVkZjQ5ZTQ1NzAzZjQ0ZTNiYmI5ZGQ5OTUxMTUyM2Q5NjZmMmU4OGNkYjgwNzYwNWY0MzZkZjFkYWVjMjZlNDFkODhlZmQyYWY5YzdmY2U3NThiZTVlMWE4NzA2ZmEwNDAxMjVkYmU2YjQxMzRmN2U1NjQxOTQ4M2Y2YjhiNWVkZTM3NDE1NmI5MDY0ZjliZWE4Yjg4ODkzNzFlYTZjZDY5N2IxYWM3OQ=="'
#GEE_PAYLOAD = '"R0VFAAZjMmFkOTAyZTQxYjdkYTgxNzI3OTljMmQzMmQ0MjJlYmFlZTRhOWU0MTMyYzNkNTJlYjk5N2I3NjUyMzQ0ZTFmYjU2YjY4NzM1YjExOGVhNzQyNTI5YWM3ZGQzMjYxZDdlMDdhYTkxOTE1ZjI4MWYxYWM2OGE4ZjdkMDM2MTMxNWM0YzcyMzBkZjk0ZjEwOGM2YmYzMzdkZGU0YTgyNGZiNjkxMWFjMTVhNmFiNjEwZGE2MTJlY2JmNGZjNDBiZDYwNmZlNzNlZjQzYmQzNTRiZDc2ZGU3ZWVkNWM2NGNhMDVkYzFmYTM0YmVhMmNmMGJiMDNjMGE2ZWQ5YWQ0NjJiY2Q3YmFmZWVmMTQ5Y2ZiMTYyYzQ2ODg4YzhlOThkOGVjYmUzM2NkZTJkZmQ1YmYwZDZkNmE5OGQ3OWJmYzQwZWQ4NjYzMWM0ZDllYTQ3YjdiZGMxOTkxMmQ2YmM1MWJjNGZlNWQwNTZhNTI1YTY2MDA4YTA1OTJhMzlhZjYzY2U0NzQyZjljOTdlMTNiMjRiNGRkMGRlNTNhMGFjYTE0NDUzNzY5NDhjYzkwZmJlZWQ3YjViYjZjODEzMmY4YzJhNWMxZThiZGNlYTNkOGNmNDVlODU5MTNmYWYxNGVjNGY4NTBlNTY2MzFhODMyZDZkZTNlZTY1MDYzOWY2MDI1MDM2MDcxYTM5OWQzMmNkOTA2M2FmYmRkMWYxOWMyMDFkNWMwODUwYWY3MGM4OGI4MjUxZjIwOTk2OWI4NzkxNmMzY2M1YjZhNTAwZmNmNGZjZGY1M2M2NmFkNjcyZDJiNGQ5MGUzM2Y0Y2YxYWNiYmQ1MzZjN2VjNDI0NGQ2NTEzOTIxMjE0NGRkNGQ1ZjE0YzI0YWQxMzA1MTJiM2JkMzI3MjExYjhhNGJlZTVjZmVkZTMzYmZjZDRhY2M5ZmNhOWU5M2U2ZTEzZjcxMzFhMGU2NmZkMDRiMTY5NGI1OGMxYmZiYzcxMDBjY2I5ZDhhM2FjNGZmMGFlZjIyYjVlY2EwY2FlNmViZjAzNmJiZTk0ZGJlZmIxM2M2NGUzZjcxNDgyMTI0M2Q1N2UxZDlkYjMxY2YwYTIwNGQ3NDM1MjRmOWQ0MzNjOTI5ZWQwZjQyYTU4NGJjOGUxYzNlNjM4NjBmZjBkNmU5YTY4ZTkwMDc4NGVhMTYwMmEzYTk4Mzg4YWQ3MTg3YmIzN2UzYWNhMWU4Y2QxYmY2YWE4ZTZjZDJkMzUyNjA3YzZkZWNjYTk3MTc4YTM0NjU1NzJmMTIxY2Q3ZmVkNTg2YjRjN2U2Yzc5NDRkNDAwNjNlYTVmOTJmZjFjODVjMTlkN2E5MDY5ZDdkMDYyNWM3NTI3Yjg3ZmZlNDRiYTUwNDA3ODE3YWE4MmI1NDk2OWIyMzYzMzE2NmIwYWJkMDkyZTZkZDk1M2ExNGEwYmI0ZGRkZTgwNjU3M2VkZWQxYmFjODRiYzU5NzZkMzhiZDIxM2MwZWNkM2Y0ZDRlZWNjOTU2NGY3YjM2MmRhNjAzZDkzMjkzYzUwMWUxMGY3OTYzMWU1MjEwMWFiYzk2ZDlmYjA2ZDk3N2RiODMxYjMwOTQ4YzlmZjU4YTIxMzkwMDllNzk2NzIwOGUzZGUzMDNjYWYwZjE0ODViYjUxYTY3M2Y1YzFjNWRlMjhiOTk4ZDQ5NGUwMGZjZWE2OTJmOTZiNjQ3OTRjNmQ4M2VkNmEzMmI3MmZjZjliZjFjY2VkYTlmMTNiYzgxYzViZWYwMTkwNWM1NDg0ZTEyZDY4MjNhZGJhOTJiMGZhMTgzNmQ5MjdmZmNiMjc4MjkzZDQzNGQ4MmE4OWEzNWRlYjdlYjgyNTY3ZTgzNGE1ODhmMDAxNTE3OTE3ZjQwYjhmYTE3YWI4MmUxNDg5YWUxZDZjMmZjZTMyOTg4MmQwZWY0ZTg1OGE3ODFhZjAzOWM4NjkxYjNmZWQxNDgwODhkOTY5NjIyNzYyZTA3NTZkYjkyYTExYTJhY2E5ZDlkNzc2Mjk1NmFkNTMzZjgxMDVjNzMzMDQwZTZhYTc0N2YxMTA2MTQxZGM2MjdmM2JlNjI4ZTVkMzAzNTBlYTgyMDQyYjRiNDgxMzU1NDUxNGQzN2Y2OWE3MDBmYjM5MTQ2YWI3MzdlMmFiM2E5MjEzZTRiZmJmODMxYjhhNjUyMjM3Y2E5NGVhZjdmM2ZlZTc1ZmIzM2MwYTgwZDg1N2U0M2E0MWIzMjE0YTNhOTBmYWM3NzNhODA1ZGU5NDM0ZTdhZjZiOTAzMmE3ZGNjN2E0NDQ3MTMwZDRiZWM1MTQ5NTEzZWRhZDFkNjU1YzRkZjRkZDg4MDVhMGZmZDA2MTNiMjQ2M2E0ODBhZTYyZDBhNjY3NGViZmMzZmZlNjQwM2VhYzUzNTRiNWI1MGU3M2Y1YzI1YzdhOWE1NTExMjE0ZTQ2ZGJhZDc5YTBmNTJkNGRjYmEzNDRjYzc1MzYzN2JlY2UzYjc0MzI0NTk1Y2RhNjU3NDUzZDdiMjcyMzA5MzQyZjljZDZiZmUyOGY3NmEwMmE5NGZjMjY5NThkMzU4MWYzOWZmZWYyZjZiYmVjMDc5NmI4OTA0NTc4YzM2ODg2NTI1ODg4M2EyNjA1M2UyM2RkMzRjZjliYTZiYjhmN2EwMDY4ZmMyMDJiNjAxMjI0NmIzNDMzMDdkZGU3MTVhMGE4MTM5NzJjNmFhNDY2MmVmODBmOGU0OWE1ZTJjMzY3YTI3YWJiNGEyY2RjYzlmODY5ZDY1OTcyZDBmZmQ2NTUyZjU4YzFhZjM4ZjI1ZWFmNmM2OTViMmY4ZmNiYjkwMjhlOTFlMThjZjY5NDlhNDkxZDljYjllMGRhODk1ODIzMTQ5NGVkMWUzYjRlMWZmMTg3ZGFhNzFlMGQyMTcxY2YxODA4ODg5NjBjNzk3ZTM4N2NhZWMzMmNkYTIzZTljMjQ2OGUyZTdmODgxZTA1YzdiYmFjMTdiNDYxZTAwZDFjYWFiOWQ0MzczMGRkMWY3OGIwNzE3ODBmOWJhMGMxZGJiNTIyYTA5Y2E4MWUwZDY4MmJmN2Q3ZTVmMWFiMWExZjA2ZTdjODVlMTU4MWEzYjQzMTIwMjNlY2UzYjRjNjg0MTJkN2E4OGEzZGQ3YTI4ZjRmNmQ1ZjczMGI2ZDIyNTgzNDJhMTM5MzI5NWM3YmI4YzEyZmMxM2U2NWYwNTY3MjIwNTY2NTljM2VjMWIxZjZhMjNiMDRmMzZmZWQ1ZmI2ZjQ0Y2U1Y2M5MDY2OWJiNTJhYjUxY2FmYmNlY2JkZWU1YWJi"';

# AppID padrão do GeeTest
GEE_APPID = "9ia4hndgblg9xihxcwgdjt9ztg8sjwaf"

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from pathlib import Path
import threading


# Configuração do PostgreSQL
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "postgres",
    "user": "postgres",
    "password": "flashbot"
}


class ClientDB:
    """
    Cliente PostgreSQL com pool de conexões (Singleton).
    Suporta até 20 conexões simultâneas para evitar erro de "muitos clientes".
    """
    
    _instance = None
    _lock = threading.Lock()
    _pool = None
    
    def __new__(cls, pg_config: dict | None = None):
        """Singleton: retorna sempre a mesma instância"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, pg_config: dict | None = None):
        if self._initialized:
            return
        
        self.pg_config = pg_config or PG_CONFIG
        self._init_pool()
        self._initialized = True

    def _init_pool(self) -> None:
        """Inicializa o pool de conexões para uso extremo (1000+ bots)"""
        try:
            if ClientDB._pool is None:
                ClientDB._pool = pool.ThreadedConnectionPool(
                    minconn=20,     # Mínimo de conexões prontas
                    maxconn=200,    # Máximo de conexões simultâneas
                    host=self.pg_config["host"],
                    port=self.pg_config["port"],
                    database=self.pg_config["database"],
                    user=self.pg_config["user"],
                    password=self.pg_config["password"],
                    connect_timeout=30
                )
                debug_log("[ClientDB] Pool PostgreSQL criado - Modo extremo 1000+ bots")
        except psycopg2.Error as e:
            raise Exception(f"Erro ao criar pool PostgreSQL: {e}")

    def _get_conn(self):
        """Obtém uma conexão do pool"""
        if ClientDB._pool is None:
            self._init_pool()
        return ClientDB._pool.getconn()
    
    def _put_conn(self, conn):
        """Devolve a conexão ao pool"""
        if ClientDB._pool and conn:
            ClientDB._pool.putconn(conn)

    def get_post_data_menos_usado(self) -> dict | None:
        conn = None
        try:
            conn = self._get_conn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            sql = """
                SELECT id, post_data, utilizado
                FROM client_reports
                ORDER BY utilizado ASC, id ASC
                LIMIT 1
            """
            cursor.execute(sql)
            row = cursor.fetchone()
            cursor.close()

            if row:
                return {
                    "id": row["id"],
                    "post_data": row["post_data"],
                    "utilizado": row["utilizado"]
                }
            return None

        except psycopg2.Error as e:
            raise Exception(f"Erro ao buscar registro: {e}")
        finally:
            self._put_conn(conn)

    def incrementar_uso(self, conn, record_id: int) -> bool:
        """Incrementa uso usando conexão existente (para transação)"""
        try:
            cursor = conn.cursor()
            sql = """
                UPDATE client_reports
                SET utilizado = utilizado + 1
                WHERE id = %s
            """
            cursor.execute(sql, (record_id,))
            cursor.close()
            return True

        except psycopg2.Error as e:
            raise Exception(f"Erro ao atualizar registro: {e}")

    def get_post_data_e_incrementar(self) -> str | None:
        """Obtém post_data e incrementa uso em transação atômica"""
        conn = None
        try:
            conn = self._get_conn()
            conn.autocommit = False
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # SELECT com FOR UPDATE para lock
            sql = """
                SELECT id, post_data, utilizado
                FROM client_reports
                ORDER BY utilizado ASC, id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """
            cursor.execute(sql)
            row = cursor.fetchone()
            
            if not row:
                conn.rollback()
                cursor.close()
                return None
            
            # Incrementa uso
            cursor.execute(
                "UPDATE client_reports SET utilizado = utilizado + 1 WHERE id = %s",
                (row["id"],)
            )
            
            conn.commit()
            cursor.close()
            return row["post_data"]

        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            self._put_conn(conn)

    def get_estatisticas(self) -> dict:
        conn = None
        try:
            conn = self._get_conn()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            sql = """
                SELECT
                    COUNT(*) AS total,
                    MIN(utilizado) AS min_uso,
                    MAX(utilizado) AS max_uso,
                    AVG(utilizado) AS media_uso
                FROM client_reports
            """
            cursor.execute(sql)
            row = cursor.fetchone()
            cursor.close()

            return dict(row) if row else {}

        except psycopg2.Error as e:
            raise Exception(f"Erro ao buscar estatísticas: {e}")
        finally:
            self._put_conn(conn)

    @classmethod
    def close_pool(cls) -> None:
        """Fecha todas as conexões do pool"""
        if cls._pool:
            cls._pool.closeall()
            cls._pool = None
            cls._instance = None
            logger.info("[ClientDB] Pool de conexões fechado")
    
    @classmethod
    def get_pool_status(cls) -> dict:
        """Retorna status do pool de conexões"""
        if cls._pool:
            return {
                "minconn": cls._pool.minconn,
                "maxconn": cls._pool.maxconn,
                "closed": cls._pool.closed
            }
        return {"status": "pool não inicializado"}



def debug_log(message: str):
    """Log somente se DEBUG_MODE estiver ativo"""
    if runtime_config["DEBUG_MODE"]:
        logger.info(message)


def _init_db():
    """Inicializa o banco de dados SQLite"""
    os.makedirs(os.path.dirname(GEE_TOKEN_DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(GEE_TOKEN_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            token TEXT NOT NULL,
            uses INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 100,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(host, token)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_host ON tokens(host)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON tokens(expires_at)")
    conn.commit()
    conn.close()


@contextmanager
def _get_db():
    """Context manager para conexão com o banco"""
    conn = sqlite3.connect(GEE_TOKEN_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _db_reserve_token(host: str, max_uses: int) -> Optional[str]:
    """
    Reserva um token disponível (operação atômica).
    Incrementa uses e retorna o token, ou None se não houver disponível.
    """
    now = time.time()
    
    with _get_db() as conn:
        # Transação atômica: SELECT + UPDATE
        cursor = conn.execute("""
            UPDATE tokens 
            SET uses = uses + 1
            WHERE id = (
                SELECT id FROM tokens 
                WHERE host = ? 
                  AND uses < max_uses 
                  AND expires_at > ?
                  AND token != 'disabled'
                ORDER BY uses ASC, created_at ASC
                LIMIT 1
            )
            RETURNING token, uses, max_uses
        """, (host, now))
        
        row = cursor.fetchone()
        conn.commit()
        
        if row:
            token, uses, max_uses = row
            debug_log(f"[GeeToken] Token reservado: {uses}/{max_uses} usos")
            return token
        
        return None


def _db_release_token(host: str, token: str) -> None:
    """Libera reserva do token (decrementa uses)"""
    with _get_db() as conn:
        conn.execute("""
            UPDATE tokens 
            SET uses = MAX(0, uses - 1)
            WHERE host = ? AND token = ?
        """, (host, token))
        conn.commit()
        debug_log(f"[GeeToken] Token liberado")


def _db_add_token(host: str, token: str, max_uses: int, ttl_seconds: int) -> None:
    """Adiciona novo token ao banco"""
    now = time.time()
    expires_at = now + ttl_seconds
    
    with _get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO tokens (host, token, uses, max_uses, expires_at, created_at)
            VALUES (?, ?, 1, ?, ?, ?)
        """, (host, token, max_uses, expires_at, now))
        conn.commit()
        debug_log(f"[GeeToken] Token adicionado ao banco")


def _db_get_stats(host: str) -> dict:
    """Retorna estatísticas dos tokens para um host"""
    now = time.time()
    
    with _get_db() as conn:
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN uses < max_uses AND expires_at > ? THEN 1 ELSE 0 END) as available,
                SUM(uses) as total_uses
            FROM tokens 
            WHERE host = ?
        """, (now, host))
        
        row = cursor.fetchone()
        return {
            "total": row["total"] or 0,
            "available": row["available"] or 0,
            "total_uses": row["total_uses"] or 0,
        }


def _db_cleanup_expired() -> int:
    """Remove tokens expirados"""
    now = time.time()
    
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM tokens WHERE expires_at <= ?", (now,))
        deleted = cursor.rowcount
        conn.commit()
        
        if deleted > 0:
            debug_log(f"[GeeToken] {deleted} tokens expirados removidos")
        
        return deleted


# Inicializa o banco na importação
_init_db()


class GeeTokenManager:
    """
    Gerenciador de tokens geeToken com SQLite.
    
    - Um token pode ser usado para até max_uses contas (padrão: 100)
    - Suporta múltiplos tokens por host para alta escalabilidade
    - Transações atômicas garantem concorrência segura
    - Se a busca falhar, retorna "disabled"
    """
    
    def __init__(self, config: Optional[GeeTokenConfig] = None, proxy_config: Optional[ProxyConfig] = None):
        self.config = config or GeeTokenConfig()
        self.proxy_config = proxy_config
        
        # Locks por host para evitar buscas duplicadas de novos tokens
        self._locks: Dict[str, asyncio.Lock] = {}
        
        # Browser compartilhado
        self._browser: Optional[BrowserContext] = None
        self._browser_lock = asyncio.Lock()
        
        # Limpa tokens expirados na inicialização
        _db_cleanup_expired()
    
    def mark_token_used(self, url_or_host: str, token: str) -> None:
        """
        Confirma uso do token (já foi reservado no banco).
        Apenas log, pois o uso já está contabilizado.
        
        Args:
            url_or_host: URL ou host do token
            token: O token que foi usado
        """
        if token == "disabled":
            return
        
        host = self._normalize_host(url_or_host)
        if not host:
            return
        
        stats = _db_get_stats(host)
        debug_log(f"[GeeToken] Token confirmado (total: {stats['total_uses']} usos)")
    
    def release_token(self, url_or_host: str, token: str) -> None:
        """
        Libera reserva do token (quando registro falha).
        Decrementa contador no banco para permitir reutilização.
        
        Args:
            url_or_host: URL ou host do token
            token: O token que falhou
        """
        if token == "disabled":
            return
        
        host = self._normalize_host(url_or_host)
        if not host:
            return
        
        _db_release_token(host, token)
    
    def _get_lock(self, host: str) -> asyncio.Lock:
        """Obtém ou cria lock para um host"""
        if host not in self._locks:
            self._locks[host] = asyncio.Lock()
        return self._locks[host]
    
    def _normalize_host(self, url_or_host: str) -> Optional[str]:
        """Normaliza URL ou host para apenas o host"""
        if not url_or_host:
            return None
        
        raw = url_or_host.strip()
        if not raw:
            return None
        
        # Se não tem scheme, é provavelmente só o host
        if "://" not in raw:
            return raw.split("/")[0].split("?")[0].strip() or None
        
        # URL completa
        try:
            from urllib.parse import urlparse
            parsed = urlparse(raw)
            return parsed.netloc or None
        except Exception:
            return None
    
    async def get_token(
        self, 
        url_or_host: str, 
        force_new: bool = False,
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        Obtém geeToken para um host.
        
        Args:
            url_or_host: URL ou host para obter token
            force_new: Se True, força busca de novo token (para pré-gerar múltiplos)
            custom_headers: Headers customizados (opcional) - usa valores de flash_headers
            user_agent: User-Agent customizado (opcional)
        
        Returns:
            Token string ou "disabled"
        """
        host = self._normalize_host(url_or_host)
        if not host:
            logger.warning(f"Host inválido: {url_or_host}")
            return "disabled"
        
        # Se force_new, busca em paralelo sem lock
        if force_new:
            return await self._fetch_and_add_token(host, custom_headers, user_agent)
        
        # Tenta reservar token existente no banco (operação atômica)
        token = _db_reserve_token(host, self.config.max_uses)
        if token:
            return token
        
        # Nenhum token disponível, busca novo (com lock para evitar buscas duplicadas)
        lock = self._get_lock(host)
        
        async with lock:
            # Double-check: outro processo pode ter adicionado token
            token = _db_reserve_token(host, self.config.max_uses)
            if token:
                return token
            
            # Busca novo token via Playwright
            debug_log(f"[GeeToken] Buscando novo token para {host}...")
            token = await self._fetch_token(host, custom_headers, user_agent)
            
            if token and token != "disabled":
                # Adiciona ao banco com 1 uso já reservado
                _db_add_token(host, token, self.config.max_uses, self.config.valid_ttl_seconds)
                return token
            else:
                logger.warning(f"Token não encontrado para {host}, usando 'disabled'")
                return "disabled"
    
    async def _fetch_and_add_token(
        self, 
        host: str,
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """Busca novo token e adiciona ao banco (para buscas paralelas)"""
        token = await self._fetch_token(host, custom_headers, user_agent)
        
        if token and token != "disabled":
            # Adiciona ao banco (sem reservar uso, pois é pré-fetch)
            _db_add_token(host, token, self.config.max_uses, self.config.valid_ttl_seconds)
            
            # Decrementa o uso que foi adicionado automaticamente
            _db_release_token(host, token)
            
            stats = _db_get_stats(host)
            debug_log(f"[GeeToken] Token adicionado (total: {stats['total']} tokens)")
            
            return token
        else:
            logger.warning(f"Falha ao obter novo token para {host}")
            return "disabled"
    
    def _get_extensions(self) -> list:
        """Lista todas as extensões na pasta 'extensoes'"""
        extensions_dir = os.path.join(os.path.dirname(__file__), "extensoes")
        extensions = []
        
        if os.path.exists(extensions_dir):
            for item in os.listdir(extensions_dir):
                ext_path = os.path.join(extensions_dir, item)
                # Verifica se é uma pasta com manifest.json (extensão válida)
                if os.path.isdir(ext_path) and os.path.exists(os.path.join(ext_path, "manifest.json")):
                    extensions.append(ext_path)
        
        return extensions

    async def _fetch_token_via_api(
        self, 
        host: str, 
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ) -> Optional[str]:
        """
        Busca token via API direta do GeeTest (método rápido, sem navegador).
        Usa curl_cffi para imitar TLS fingerprint com randomização de browser.
        
        Args:
            host: Host da plataforma
            custom_headers: Headers customizados (opcional) - usa valores de flash_headers
            user_agent: User-Agent customizado (opcional)
        """
        url = "https://riskct.geetest.com/g2/api/v1/client_report"
        
        # Seleciona perfil de browser randomizado (Android)
        impersonate_name, browser_user_agent = _select_browser_profile(BROWSER_PROFILES_ANDROID)
        extra_fp = _get_extra_fp(impersonate_name)
        
        # Headers base para GeeTest API
        headers = custom_headers.copy() if custom_headers else {}
        headers['appid'] = GEE_APPID
        
        # User-Agent: usa o passado, ou o do browser selecionado
        final_user_agent = user_agent or browser_user_agent
        headers['user-agent'] = final_user_agent
        
        # Gera sec-ch-ua dinâmico baseado no browser selecionado
        if "chrome" in impersonate_name.lower():
            # Extrai versão do impersonate (chrome131 -> 131)
            version = "".join(filter(str.isdigit, impersonate_name.split("_")[0]))
            if "android" in impersonate_name.lower():
                headers['sec-ch-ua'] = f'"Android WebView";v="{version}", "Chromium";v="{version}", "Not A(Brand";v="24"'
                headers['sec-ch-ua-mobile'] = '?1'
                headers['sec-ch-ua-platform'] = '"Android"'
            else:
                headers['sec-ch-ua'] = f'"Chromium";v="{version}", "Google Chrome";v="{version}", "Not A(Brand";v="24"'
                headers['sec-ch-ua-mobile'] = '?0'
                headers['sec-ch-ua-platform'] = '"Windows"'
        elif "safari" in impersonate_name.lower():
            if "ios" in impersonate_name.lower():
                headers['sec-ch-ua-mobile'] = '?1'
                headers['sec-ch-ua-platform'] = '"iOS"'
            else:
                headers['sec-ch-ua-mobile'] = '?0'
                headers['sec-ch-ua-platform'] = '"macOS"'
        
        # Headers adicionais para GeeTest
        headers['origin'] = f'https://{host}'
        headers['referer'] = f'https://{host}/'
        headers['accept'] = '*/*'
        headers['accept-language'] = 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
        headers['api-version'] = '1'
        headers['client-type'] = '3'
        headers['content-type'] = 'application/x-www-form-urlencoded'
        headers['sec-fetch-dest'] = 'empty'
        headers['sec-fetch-mode'] = 'cors'
        headers['sec-fetch-site'] = 'cross-site'
        
        try:
            # Sempre usa proxy para geeToken
            proxy_url = f"http://{GEE_PROXY_CONFIG.username}:{GEE_PROXY_CONFIG.password}@{GEE_PROXY_CONFIG.host}:{GEE_PROXY_CONFIG.port}"
            debug_log(f"[GeeToken] Usando proxy na API: {GEE_PROXY_CONFIG.host}:{GEE_PROXY_CONFIG.port}")
            debug_log(f"[GeeToken] Browser: {impersonate_name}")            
            async with AsyncSession(
                impersonate=impersonate_name,
                proxy=proxy_url,
                timeout=30,
                extra_fp=extra_fp
            ) as client:
                client_db = ClientDB()
                GEE_PAYLOAD = client_db.get_post_data_e_incrementar()                
                response = await client.post(url, data=GEE_PAYLOAD, headers=headers)
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        data = None
                    if data:
                        gee_token = data.get("data", {}).get("gee_token")
                        if gee_token:
                            return gee_token
                    debug_log(f"[GeeToken] Resposta 200 sem token para {host}")
                else:
                    debug_log(f"[GeeToken] Status {response.status_code} na API para {host}")
                    try:
                        debug_log(f"[GeeToken] Corpo: {response.text[:200]}")
                    except Exception:
                        pass
                return None
        except Exception as e:
            logging.getLogger(__name__).warning(f"[GeeToken] Erro na API para {host}: {e}")
            return None
    
    async def _fetch_token(
        self,
        host: str,
        custom_headers: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ) -> Optional[str]:
        """
        Tenta obter o token via API direta (até 3 tentativas) e,
        em caso de falha, faz fallback para Playwright.
        """
        for attempt in range(1, 4):
            token = await self._fetch_token_via_api(host, custom_headers, user_agent)
            if token:
                return token
            debug_log(f"[GeeToken] API direta tentativa {attempt}/3 falhou para {host}, aguardando 2s...")
            await asyncio.sleep(2)
        debug_log(f"[GeeToken] API direta falhou 3x para {host}, usando Playwright (fallback)")
        return await self._fetch_token_via_playwright(host)
    
    async def _fetch_token_via_playwright(self, host: str) -> Optional[str]:
        context = None
        try:
            async with async_playwright() as p:
                # Obtém extensões
                extensions = self._get_extensions()
                
                # Args base do navegador
                browser_args = [
                    "--disable-dev-shm-usage",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-client-side-phishing-detection",
                    "--disable-component-update",
                    "--disable-default-apps",
                    "--disable-domain-reliability",
                    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
                    "--disable-hang-monitor",
                    "--disable-ipc-flooding-protection",
                    "--disable-popup-blocking",
                    "--disable-prompt-on-repost",
                    "--disable-renderer-backgrounding",
                    "--disable-sync",
                    "--force-color-profile=srgb",
                    "--metrics-recording-only",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--no-sandbox",
                    "--mute-audio",
                    "--disable-gpu",
                ]
                
                # Adiciona extensões se existirem
                if extensions:
                    ext_paths = ",".join(extensions)
                    browser_args.append(f"--load-extension={ext_paths}")
                    browser_args.append(f"--disable-extensions-except={ext_paths}")
                    #debug_log(f"Carregando {len(extensions)} extensão(ões): {[os.path.basename(e) for e in extensions]}")
                else:
                    browser_args.append("--disable-extensions")
                
                # Usa persistent context para suportar extensões
                user_data_dir = tempfile.mkdtemp()
                
                # Sempre usa proxy para geeToken
                proxy_settings = {
                    "server": f"http://{GEE_PROXY_CONFIG.host}:{GEE_PROXY_CONFIG.port}",
                    "username": GEE_PROXY_CONFIG.username,
                    "password": GEE_PROXY_CONFIG.password,
                }
                debug_log(f"[GeeToken] Usando proxy no Playwright: {GEE_PROXY_CONFIG.host}:{GEE_PROXY_CONFIG.port}")
                
                context = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    args=browser_args,
                    proxy=proxy_settings,
                )
                
                page = context.pages[0] if context.pages else await context.new_page()
                
                token = await self._extract_token_from_page(page, host)
                
                await context.close()
                
                # Limpa diretório temporário
                try:
                    shutil.rmtree(user_data_dir, ignore_errors=True)
                except:
                    pass
                
                return token
                
        except Exception as e:
            logger.error(f"Erro ao buscar token para {host}: {e}")
            if context:
                try:
                    await context.close()
                except:
                    pass
            return None
    
    async def _extract_token_from_page(self, page: Page, host: str) -> Optional[str]:
        """Extrai geeToken da página de registro"""
        token_result = None
        token_event = asyncio.Event()
        
        async def handle_response(response):
            nonlocal token_result
            try:
                if "client_report" in response.url:
                    try:
                        data = await response.json()
                    except:
                        return
                    
                    gee_token = data.get("data", {}).get("gee_token")
                    if gee_token:
                        token_result = gee_token
                        token_event.set()
            except Exception:
                pass
        
        page.on("response", handle_response)
        
        try:
            # Navega para página de registro
            await page.goto(f"https://{host}/home/mine", wait_until="networkidle", timeout=60000)
            
            # Aguarda botão "Registro"
            logger.debug(f"Aguardando botão Registro para {host}")
            try:
                await page.wait_for_selector('span:text("Registro")', timeout=15000)
                await page.click('span:text("Registro")')
                logger.debug(f"Botão Registro clicado para {host}")
            except Exception as e:
                logger.warning(f"Botão Registro não encontrado para {host}: {e}")
                return None
            
            # Aguarda input aparecer
            try:
                await page.wait_for_selector('input', timeout=15000)
                logger.debug(f"Input encontrado para {host}")
            except Exception as e:
                logger.warning(f"Input não encontrado para {host}: {e}")
                return None
            
            # Executa script de preenchimento
            await self._fill_form(page)
            
            # Tenta clicar no botão de submit
            await self._click_submit(page)
            
            # Aguarda resposta com token (max 15 segundos)
            try:
                await asyncio.wait_for(token_event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout aguardando token para {host}")
            
            return token_result
            
        except Exception as e:
            logger.error(f"Erro ao extrair token para {host}: {e}")
            return None
    
    async def _fill_form(self, page: Page):
        """Preenche formulário de registro"""
        # Script simplificado para preencher campos
        await page.evaluate("""async () => {
            console.log('>>> EVALUATE INICIADO <<<');

          const SENHA_FIXA = ""; // FlaBX2014@

          const MODO_SOMENTE_CADASTRO = 1;

          const AGUARDAR_CARREGAMENTO_PAGINA = 0;

          const NOME_USUARIO_SIMPLES = 1;
          const TAMANHO_MAXIMO_USUARIO = 14;
          const TAMANHO_MAXIMO_SENHA = 12;
          const MULTIPLICADOR_PIX = 1;
          const VALOR_QR_PIX_MINIMO = 30;
          const VALOR_QR_PIX_MAXIMO = 60;
          const TAMANHO_MAXIMO_CAPTCHA_NUMERICO = 4;
          const PREENCHER_SOMENTE_CAMPO_VISIVEL = 1;

          const CAMPOS_OPCIONAIS = 1; // 1 = Preenche // 0 = Não preencher

          const NAO_PREENCHER_CAMPOS = ['convite'];

          const API_KEY = 'FlashBOT31673289E327c4189209221c8022AfEa58E3FB1EDf3419f47146DEEBB3B1FD9f';

          const iVBORw0KGgoAAA = ['conta', 'usuario', 'insira o caractere', 'nome de acesso'];
          const KAAAAD3CAMAA = ['senha', 'insira o bit', 'digite novamente', 'inserir pin'];
          const FJxwOIyvGKR6v = ['celular', 'telefone', 'telemovel', 'tele'];
          const xrndwHZYBvHNRD = ['verdadeiro', 'completo', 'real', 'apelido'];
          const BSEWUwYWUjtQ = ['nascimento', 'data'];
          const yLLFw7hKiGWD = ['mail'];
          const EsDo3S6GPs0FHjHB = ['numero do imposto', 'cpf', 'document'];
          const CfBFRsPUQ4Ux = ['optional', 'opcional'];
          const CgT1TT7tPTP = ['codigo'];

          function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
          function isNumeric(num) { return !isNaN(num) && !isNaN(parseFloat(num)); }
          function normalizeText(text) { return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim(); }
          function simularDigitacao(e, v) {
            e.focus()
            if (e && e.tagName && e.tagName.toLowerCase() != 'input') {
              return false;
            }
            if (e && e.getAttribute && e.getAttribute('data-type')) {
              return false;
            }
            document.execCommand('delete', false, null);
            e.value = '';
            if (!document.execCommand('insertText', false, v)) {
              e.value = v;
            }
            e.dispatchEvent(new Event('input', { bubbles: true }));
            e.dispatchEvent(new Event('change', { bubbles: true }));
            e.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', code: 'Tab', keyCode: 9, which: 9, bubbles: true }));
          }
          function setValue(selector, value) {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => {
              if (el) {
                el.focus();
                document.execCommand('selectAll');
                if (!document.execCommand('insertText', false, value)) {
                  el.value = value;
                }
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return el;
              }
            });
          }
          function gerarCPF() { function r(r, n) { return Math.floor(Math.random() * (n - r + 1)) + r; } function n(r) { let n = 0; for (let t = 0; t < r.length; t++)n += r[t] * (r.length + 1 - t); let e = n % 11; return e < 2 ? 0 : 11 - e; } let t = []; for (let n = 0; n < 9; n++)t.push(r(0, 9)); return t.push(n(t)), t.push(n(t)), t.join(''); }
          function gerarDataNascimento(minAge = 19, maxAge = 70, format = "DD/MM/YYYY") { const currentDate = new Date(), minYear = currentDate.getFullYear() - maxAge, maxYear = currentDate.getFullYear() - minAge, randomYear = Math.floor(Math.random() * (maxYear - minYear + 1)) + minYear, randomMonth = Math.floor(Math.random() * 12), randomDay = Math.floor(Math.random() * 28) + 1, randomDate = new Date(randomYear, randomMonth, randomDay); return function (date, format) { const day = String(date.getDate()).padStart(2, '0'), month = String(date.getMonth() + 1).padStart(2, '0'), year = date.getFullYear(); return format.replace('DD', day).replace('MM', month).replace('YYYY', year) }(randomDate, format) }
          function captchaNum(l) { let d = '', p = '0123456789'; for (let i = 0; i < l; i++)d += p[Math.floor(Math.random() * p.length)]; return d; }
          function generatePassword(fn, m, s = true) { const [f, l] = fn.split(' '); const u = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', a = 'abcdefghijklmnopqrstuvwxyz', d = '0123456789', sp = '@#$%&*'; let c = u + a + d; if (s) c += sp; let p = u[Math.floor(Math.random() * u.length)] + a[Math.floor(Math.random() * a.length)] + d[Math.floor(Math.random() * d.length)]; if (s) p += sp[Math.floor(Math.random() * sp.length)]; p += f + l; let r = m - p.length; if (r < 0) { p = p.substring(0, m); r = 0; } for (let i = 0; i < r; i++) { p += c[Math.floor(Math.random() * c.length)]; } return p.split('').sort(() => 0.5 - Math.random()).join(''); }
          function findElement(document, texts, visible) {
            return Array.from(document.querySelectorAll('button, div, span, uni-view')).reverse().find(e => {
              if ((e.textContent.length >= 5 && e.textContent.length <= 16) && texts.some(t => normalizeText(e.textContent).includes(normalizeText(t)))) {
                if (visible) {
                  const isVisible = !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
                  const isClickable = e instanceof HTMLButtonElement || e instanceof HTMLAnchorElement || e.hasAttribute('onclick') || window.getComputedStyle(e).cursor === 'pointer';
                  return isVisible && isClickable ? e : false;
                } else {
                  return e;
                }
              }
              return false;
            });
          }
          function getParentText(element, maxLevels = 10) {
            let currentElement = element;
            for (let i = 0; i < maxLevels && currentElement; i++) {
              let parentElement = currentElement.parentElement || currentElement.offsetParent;
              if (parentElement) {
                let parentText = parentElement.textContent.trim();
                if (parentText) {
                  return parentText;
                }
                currentElement = parentElement;
              } else {
                break;
              }
            }
            return '';
          }

          var unicheck = document.querySelectorAll('.uni-checkbox-input');
          var checkboxElements = Array.from(unicheck);
          if (unicheck.length === 0) {
            document.querySelectorAll('iframe').forEach(iframe => {
              try {
                let iframeDocument = iframe.contentDocument || iframe.contentWindow.document;
                checkboxElements.push(...iframeDocument.querySelectorAll('.uni-checkbox-input'));
              } catch (e) {
                console.error('Could not access iframe content:', e);
              }
            });
          }
          checkboxElements.forEach((element, index) => {
            if (!element.className.includes('checked')) {
              element.click();
            }
          });

          //mineiro777
          var vancheck = document.querySelectorAll('[role="checkbox"]');
          var checkboxElements = Array.from(vancheck);
          if (vancheck.length === 0) {
            document.querySelectorAll('iframe').forEach(iframe => {
              try {
                let iframeDocument = iframe.contentDocument || iframe.contentWindow.document;
                checkboxElements.push(...iframeDocument.querySelectorAll('[role="checkbox"]'));
              } catch (e) {
                console.error('Could not access iframe content:', e);
              }
            });
          }
          checkboxElements.forEach((element, index) => {
            if (element.getAttribute('aria-checked') == 'false') {
              element.click();
            }
          });

          if (document.querySelector('input[type="password"], input[type="checkbox"]')) {

            const usuario = 'usuario';
            const celular = '21998217164';
            const email = 'emailmaster123@uorak.com';
            const documento = gerarCPF();
            const nascimento = gerarDataNascimento();
            const usarSenhaAleatoria = true;
            const usarCaracteresEspeciais = true;
            const senha = usarSenhaAleatoria ? generatePassword('JOAO SILVA', (isNumeric(TAMANHO_MAXIMO_SENHA) ? TAMANHO_MAXIMO_SENHA : 12), (usarCaracteresEspeciais ? true : false)) : (SENHA_FIXA ? SENHA_FIXA : 'ObK5Wn5J7l1@v');
            const nomeCompleto = 'JOAO SILVA';
            sessionStorage.setItem('usuario', usuario);
            sessionStorage.setItem('senha', senha);
            var loginCount = 0;
            var passCount = 0;
            var foneCount = 0;
            var mailCount = 0;
            var nomeCount = 0;
            let inputElements = [];
            function getInputElementsWithoutDataType(document) {
              return document.querySelectorAll('input:not([data-type])');
            }
            inputElements.push(...getInputElementsWithoutDataType(document));
            document.querySelectorAll('iframe').forEach(iframe => {
              try {
                let iframeDocument = iframe.contentDocument || iframe.contentWindow.document;
                inputElements.push(...getInputElementsWithoutDataType(iframeDocument));
              } catch (e) {
                console.error('Could not access iframe content:', e);
              }
            });
            inputElements.forEach((element, index) => {
              var offsetParentText = false;
              offsetParentText = getParentText(element);
              let placeholderText = element.getAttribute('placeholder') || '';
              let textParent = normalizeText(offsetParentText).trim();
              if (textParent.length > 64) textParent = '';
              let placeholder = normalizeText(placeholderText).trim();
              if (PREENCHER_SOMENTE_CAMPO_VISIVEL) {
                if (element.offsetWidth == 0 && element.offsetHeight == 0) {
                  return;
                }
              }

              if (element.type == "checkbox") {
                if (!element.checked) {
                  element.click();
                }
                element.checked = true;
                return false;
              }

              if (element.className == "ant-select-search__field") {
                loginCount++;
                simularDigitacao(element, usuario);
                return false;
              }

              if (element.className == "username_input") {
                loginCount++;
                simularDigitacao(element, usuario);
                return false;
              }

              console.log("index: " + index)
              console.log("placeholderText: " + placeholderText)
              console.log("textParent: " + textParent)
              console.log("placeholder: " + placeholder)
              console.log(element.className)
              console.log(element.type)
              console.log("")
              console.log("")

              if (placeholder.length > 0 || textParent.length > 0 || element.className == "ant-select-search__field") {
                if (placeholder.length && placeholder.includes('refer')) {
                  return false;
                } else {
                  if (textParent.length && textParent.includes('refer')) {
                    return false;
                  }
                }
                if (!CAMPOS_OPCIONAIS) {
                  if (placeholder.length && CfBFRsPUQ4Ux.some(valid => placeholder.includes(valid))) {
                    return false;
                  } else {
                    if (textParent.length && CfBFRsPUQ4Ux.some(valid => textParent.includes(valid))) {
                      return false;
                    }
                  }
                }
                if (placeholder.length && NAO_PREENCHER_CAMPOS.some(valid => placeholder.includes(valid))) {
                  return false;
                } else {
                  if (textParent.length && NAO_PREENCHER_CAMPOS.some(valid => textParent.includes(valid))) {
                    return false;
                  }
                }

                if (loginCount < 2) {
                  if (placeholder.length && iVBORw0KGgoAAA.some(valid => placeholder.includes(valid))) {
                    loginCount++;
                    simularDigitacao(element, usuario);
                    return false;
                  } else {
                    if (textParent.length && iVBORw0KGgoAAA.some(valid => textParent.includes(valid))) {
                      loginCount++;
                      simularDigitacao(element, usuario);
                      return false;
                    }
                  }
                }

                if (placeholder.length && KAAAAD3CAMAA.some(valid => placeholder.includes(valid)) || placeholder.includes("senha")) {
                  passCount++;
                  simularDigitacao(element, senha);
                  return false;
                }
                if (passCount < 2) {
                  if (textParent.length && KAAAAD3CAMAA.some(valid => textParent.includes(valid)) || textParent.includes("senha")) {
                    passCount++;
                    simularDigitacao(element, senha);
                    return false;
                  }
                }

                if (nomeCount == 0) {
                  if (placeholder.length && xrndwHZYBvHNRD.some(valid => placeholder.includes(valid))) {
                    nomeCount++;
                    simularDigitacao(element, nomeCompleto);
                    return false;
                  } else {
                    if (textParent.length && xrndwHZYBvHNRD.some(valid => textParent.includes(valid))) {
                      nomeCount++;
                      simularDigitacao(element, nomeCompleto);
                      return false;
                    }
                  }
                }

                if (mailCount < 2) {
                  if (placeholder.length && yLLFw7hKiGWD.some(valid => placeholder.includes(valid))) {
                    mailCount++;
                    simularDigitacao(element, email);
                    return false;
                  } else {
                    if (textParent.length && yLLFw7hKiGWD.some(valid => textParent.includes(valid))) {
                      mailCount++;
                      simularDigitacao(element, email);
                      return false;
                    }
                  }
                }

                if (foneCount < 2) {
                  if (placeholder.length && FJxwOIyvGKR6v.some(valid => placeholder.includes(valid))) {
                    foneCount++;
                    simularDigitacao(element, celular);
                    return false;
                  } else {
                    if (textParent.length && FJxwOIyvGKR6v.some(valid => textParent.includes(valid))) {
                      foneCount++;
                      simularDigitacao(element, celular);
                      return false;
                    }
                  }
                }

                if (placeholder.length && BSEWUwYWUjtQ.some(valid => placeholder.includes(valid))) {
                  simularDigitacao(element, nascimento);
                  return false;
                } else {
                  if (textParent.length && BSEWUwYWUjtQ.some(valid => textParent.includes(valid))) {
                    simularDigitacao(element, nascimento);
                    return false;
                  }
                }

                if (placeholder.length && EsDo3S6GPs0FHjHB.some(valid => placeholder.includes(valid))) {
                  simularDigitacao(element, documento);
                  return false;
                } else {
                  if (textParent.length && EsDo3S6GPs0FHjHB.some(valid => textParent.includes(valid))) {
                    simularDigitacao(element, documento);
                    return false;
                  }
                }
                if (placeholder.length && CgT1TT7tPTP.some(valid => placeholder.includes(valid))) {
                  simularDigitacao(element, captchaNum(TAMANHO_MAXIMO_CAPTCHA_NUMERICO));
                  return false;
                } else {
                  if (textParent.length && CgT1TT7tPTP.some(valid => textParent.includes(valid))) {
                    simularDigitacao(element, captchaNum(TAMANHO_MAXIMO_CAPTCHA_NUMERICO));
                    return false;
                  }
                }
              } else {
                if (index == "0" && placeholder.length == 0) {
                  let currentElement = element;
                  while (currentElement) {
                    if (iVBORw0KGgoAAA.some(valid => normalizeText(currentElement.textContent).includes(valid))) {
                      simularDigitacao(element, usuario);
                      break;
                    }
                    currentElement = currentElement.parentElement;
                  }
                } else if ((index == 0 || index == 1) && element.value === '') {
                  simularDigitacao(element, celular);
                  return false;
                }
              }

              if (element.type == "password") {
                passCount++;
                simularDigitacao(element, senha);
                return false;
              }

            });

          }
          console.log('>>> EVALUATE FINALIZADO <<<');
          return 'OK';
        }""")
        
        await asyncio.sleep(1)
    
    async def _click_submit(self, page: Page):
        """Tenta clicar no botão de submit"""
        # Tenta página principal
        try:
            await page.wait_for_selector('#insideRegisterSubmitClick', timeout=5000, state='visible')
            await page.click('#insideRegisterSubmitClick', force=True)
            logger.debug("Botão submit clicado na página principal")
            await asyncio.sleep(3)
            return
        except:
            pass
        
        # Tenta iframes
        for frame in page.frames:
            try:
                btn = await frame.query_selector('#insideRegisterSubmitClick')
                if btn:
                    await btn.click(force=True)
                    logger.debug("Botão submit clicado no iframe")
                    await asyncio.sleep(3)
                    return
            except:
                pass
        
        # Tenta via JavaScript
        await page.evaluate("""
            () => {
                let btn = document.querySelector('#insideRegisterSubmitClick');
                if (btn) btn.click();
                
                document.querySelectorAll('iframe').forEach(iframe => {
                    try {
                        let iframeBtn = iframe.contentDocument?.querySelector('#insideRegisterSubmitClick');
                        if (iframeBtn) iframeBtn.click();
                    } catch (e) {}
                });
            }
        """)
        await asyncio.sleep(3)
    
    def invalidate(self, url_or_host: str) -> bool:
        """Invalida token em cache para um host"""
        host = self._normalize_host(url_or_host)
        if host and host in self._cache:
            del self._cache[host]
            debug_log(f"Token invalidado para {host}")
            return True
        return False
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do cache"""
        now = time.time()
        stats = {
            "total_hosts": len(self._cache),
            "hosts": {},
        }
        
        for host, cached in self._cache.items():
            stats["hosts"][host] = {
                "token_preview": cached.token[:20] + "..." if len(cached.token) > 20 else cached.token,
                "uses": cached.uses,
                "max_uses": self.config.max_uses,
                "expires_in_seconds": max(0, int(cached.expires_at - now)),
                "is_valid": cached.token != "disabled",
            }
        
        return stats


# Instância global (singleton)
_gee_token_manager: Optional[GeeTokenManager] = None


def get_gee_token_manager(
    config: Optional[GeeTokenConfig] = None,
    proxy_config: Optional[ProxyConfig] = None
) -> GeeTokenManager:
    """Obtém instância global do GeeTokenManager"""
    global _gee_token_manager
    if _gee_token_manager is None:
        _gee_token_manager = GeeTokenManager(config, proxy_config)
    elif proxy_config:
        # Atualiza proxy_config se fornecido (para garantir que use proxy mesmo se manager já existia)
        _gee_token_manager.proxy_config = proxy_config
    return _gee_token_manager


async def get_gee_token(
    url_or_host: str,
    config: Optional[GeeTokenConfig] = None,
    proxy_config: Optional[ProxyConfig] = None,
    force_new: bool = False
) -> str:
    """Função de conveniência para obter geeToken"""
    manager = get_gee_token_manager(config, proxy_config)
    
    # Atualiza proxy_config se fornecido (para garantir que use proxy mesmo se manager já existia)
    if proxy_config:
        manager.proxy_config = proxy_config
    
    return await manager.get_token(url_or_host, force_new=force_new)


def mark_gee_token_used(url_or_host: str, token: str) -> None:
    """
    Confirma uso do token e salva no arquivo.
    Chamar após conta criada com sucesso.
    
    Args:
        url_or_host: URL ou host do token
        token: O token que foi usado
    """
    global _gee_token_manager
    if _gee_token_manager:
        _gee_token_manager.mark_token_used(url_or_host, token)


def release_gee_token(url_or_host: str, token: str) -> None:
    """
    Libera reserva do token (quando registro falha).
    Decrementa contador para permitir reutilização.
    
    Args:
        url_or_host: URL ou host do token
        token: O token que falhou
    """
    global _gee_token_manager
    if _gee_token_manager:
        _gee_token_manager.release_token(url_or_host, token)


async def get_gee_token_individual(
    url_or_host: str,
    proxy_config: Optional[ProxyConfig] = None
) -> str:
    """
    Obtém geeToken individual via API direta (sem cache).
    Cada chamada faz uma requisição nova à API do GeeTest.
    Reutiliza o GeeTokenManager existente.
    
    Args:
        url_or_host: URL ou host para obter token
        proxy_config: Configuração de proxy (opcional)
    
    Returns:
        Token string ou "disabled"
    """
    manager = get_gee_token_manager(proxy_config=proxy_config)
    
    # Atualiza proxy_config se fornecido (para garantir que use proxy mesmo se manager já existia)
    if proxy_config:
        manager.proxy_config = proxy_config
    
    host = manager._normalize_host(url_or_host)
    
    if not host:
        logger.warning(f"[GeeToken] Host inválido: {url_or_host}")
        return "disabled"
    
    # Usa _fetch_token que já funciona (3 tentativas via API + fallback Playwright)
    token = await manager._fetch_token(host)
    
    if token:
        logger.info(f"[GeeToken] Token individual obtido para {host}: {token[:30]}...")
        return token
    
    logger.warning(f"[GeeToken] Não foi possível obter token individual para {host}")
    return "disabled"
