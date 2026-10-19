# -*- coding: utf-8 -*-
"""
CapSolver GeeTest v4 solver - substitui o solver local.
Usa a API do CapSolver para resolver o captcha.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

CAPSOLVER_API_KEY = "CAP-F98B82F66054A98099294FC6861FBB0C1827C3A11B97F1C305A73A5C4DA4C6FC"
CAPSOLVER_CREATE_TASK_URL = "https://api.capsolver.com/createTask"
CAPSOLVER_GET_RESULT_URL = "https://api.capsolver.com/getTaskResult"


class CapSolverGeeTest:
    """Resolve GeeTest v4 usando CapSolver API."""

    def __init__(self, api_key: str = CAPSOLVER_API_KEY):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def solve(
        self,
        website_url: str,
        captcha_id: str,
        *,
        risk_type: str = "slide",
        geetest_api_server_subdomain: Optional[str] = None,
        max_retries: int = 60,
        retry_interval: float = 2.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve GeeTest v4 via CapSolver.

        Retorna dict com:
            - captcha_id
            - lot_number
            - pass_token
            - gen_time
            - captcha_output
        Ou None se falhar.
        """
        task_id = await self._create_task(
            website_url=website_url,
            captcha_id=captcha_id,
            risk_type=risk_type,
            geetest_api_server_subdomain=geetest_api_server_subdomain,
        )
        if not task_id:
            logger.error("[CapSolver] Falha ao criar task")
            return None

        logger.info(f"[CapSolver] Task criada: {task_id}")

        for attempt in range(max_retries):
            await asyncio.sleep(retry_interval)
            result = await self._get_task_result(task_id)
            if result is None:
                continue
            if result.get("status") == "ready":
                solution = result.get("solution", {})
                logger.info("[CapSolver] Captcha resolvido com sucesso")
                return solution
            if result.get("status") == "failed":
                logger.error(f"[CapSolver] Task falhou: {result}")
                return None

        logger.error(f"[CapSolver] Timeout apos {max_retries} tentativas")
        return None

    async def _create_task(
        self,
        website_url: str,
        captcha_id: str,
        risk_type: str,
        geetest_api_server_subdomain: Optional[str],
    ) -> Optional[str]:
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "GeeTestTaskProxyless",
                "websiteURL": website_url,
                "captchaId": captcha_id,
                "riskType": risk_type,
            },
        }
        if geetest_api_server_subdomain:
            payload["task"]["geetestApiServerSubdomain"] = geetest_api_server_subdomain

        try:
            resp = await self.client.post(CAPSOLVER_CREATE_TASK_URL, json=payload)
            data = resp.json()
        except Exception as exc:
            logger.error(f"[CapSolver] Erro ao criar task: {exc}")
            return None

        if data.get("errorId") != 0:
            logger.error(f"[CapSolver] Erro na API: {data}")
            return None

        return data.get("taskId")

    async def _get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        payload = {
            "clientKey": self.api_key,
            "taskId": task_id,
        }
        try:
            resp = await self.client.post(CAPSOLVER_GET_RESULT_URL, json=payload)
            return resp.json()
        except Exception as exc:
            logger.debug(f"[CapSolver] Erro ao obter resultado: {exc}")
            return None


async def solve_geetest_v4_capsolver(
    website_url: str,
    captcha_id: str,
    *,
    risk_type: str = "slide",
    geetest_api_server_subdomain: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Atalho para resolver GeeTest v4 com CapSolver.

    Retorna dict com captcha_id, lot_number, pass_token, gen_time, captcha_output.
    """
    solver = CapSolverGeeTest()
    try:
        return await solver.solve(
            website_url=website_url,
            captcha_id=captcha_id,
            risk_type=risk_type,
            geetest_api_server_subdomain=geetest_api_server_subdomain,
        )
    finally:
        await solver.close()
