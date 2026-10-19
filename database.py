# -*- coding: utf-8 -*-
"""
Banco de dados SQLite para armazenar contas criadas
Cada sitecode tem seu próprio banco: cache/{sitecode}.db
"""
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, List

logger = logging.getLogger(__name__)

# Diretório de cache
CACHE_DIR = "cache"

# Cache de bancos já inicializados
_initialized_dbs = set()


def _get_db_path(sitecode: str) -> str:
    """Retorna o caminho do banco de dados para um sitecode"""
    return os.path.join(CACHE_DIR, f"{sitecode}.db")


def _init_db(sitecode: str):
    """Inicializa o banco de dados para um sitecode"""
    if sitecode in _initialized_dbs:
        return
    
    os.makedirs(CACHE_DIR, exist_ok=True)
    db_path = _get_db_path(sitecode)
    
    conn = sqlite3.connect(db_path)
    
    # Tabela todascontas - salva response completo do registro
    conn.execute("""
        CREATE TABLE IF NOT EXISTS todascontas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Identificação
            platform TEXT,
            sitecode TEXT,
            url TEXT,
            
            -- Dados da conta (input)
            usuario TEXT,
            senha TEXT,
            senha_saque TEXT,
            cpf TEXT,
            telefone TEXT,
            email TEXT,
            nome_completo TEXT,
            android_version TEXT,
            device_id TEXT,
            login_id TEXT,
            device_model TEXT,
            app_version TEXT,
            speed_version TEXT,
            
            -- Response do registro (campos principais)
            user_id INTEGER,
            session_key TEXT,
            
            -- Metadados
            inviter_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Índices para consultas rápidas
    conn.execute("CREATE INDEX IF NOT EXISTS idx_todascontas_platform ON todascontas(platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_todascontas_created ON todascontas(created_at)")
    
    conn.commit()
    conn.close()
    
    _initialized_dbs.add(sitecode)
    logger.debug(f"Banco de dados inicializado: {db_path}")


@contextmanager
def get_db(sitecode: str):
    """Context manager para conexão com o banco"""
    _init_db(sitecode)
    db_path = _get_db_path(sitecode)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def salvar_conta(
    sitecode: str,
    platform: str = None,
    url: str = None,
    usuario: str = None,
    senha: str = None,
    senha_saque: str = None,
    cpf: str = None,
    telefone: str = None,
    email: str = None,
    nome_completo: str = None,
    android_version: str = None,
    device_id: str = None,
    login_id: str = None,
    device_model: str = None,
    app_version: str = None,
    speed_version: str = None,
    register_response: Dict = None,
    inviter_id: str = None,
) -> int:
    """
    Salva uma conta no banco de dados.
    
    Returns:
        ID da conta inserida
    """
    # Extrai campos do response de registro
    user_id = None
    session_key = None
    
    if register_response:
        # Campos podem estar em register_response ou em register_response["userInfos"]
        user_infos = register_response.get("userInfos", register_response)
        
        user_id = register_response.get("userId") or user_infos.get("userId")
        session_key = user_infos.get("session_key")
    
    with get_db(sitecode) as conn:
        cursor = conn.execute("""
            INSERT INTO todascontas (
                platform, sitecode, url,
                usuario, senha, senha_saque, cpf, telefone, email, nome_completo,
                android_version, device_id, login_id, device_model, app_version, speed_version,
                user_id, session_key,
                inviter_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            platform, sitecode, url,
            usuario, senha, senha_saque, cpf, telefone, email, nome_completo,
            android_version, device_id, login_id, device_model, app_version, speed_version,
            user_id, session_key,
            inviter_id,
        ))
        
        conn.commit()
        account_id = cursor.lastrowid
        
        logger.debug(f"Conta salva no banco {sitecode}.db: ID={account_id}, usuario={usuario}")
        return account_id


def buscar_contas(
    sitecode: str,
    platform: str = None,
    limit: int = 100,
) -> List[Dict]:
    """Busca contas no banco"""
    conditions = []
    values = []
    
    if platform:
        conditions.append("platform = ?")
        values.append(platform)
    
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    values.append(limit)
    
    with get_db(sitecode) as conn:
        cursor = conn.execute(f"""
            SELECT * FROM todascontas 
            {where}
            ORDER BY created_at DESC
            LIMIT ?
        """, values)
        
        return [dict(row) for row in cursor.fetchall()]


def estatisticas(sitecode: str, platform: str = None) -> Dict:
    """Retorna estatísticas das contas"""
    condition = "WHERE platform = ?" if platform else ""
    values = [platform] if platform else []
    
    with get_db(sitecode) as conn:
        cursor = conn.execute(f"""
            SELECT 
                COUNT(*) as total
            FROM todascontas
            {condition}
        """, values)
        
        row = cursor.fetchone()
        return {
            "total": row["total"] or 0,
        }


GEETOKEN_FAILURE_GATE = "__FAILURE_GATE__"
GEETOKENS_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geetokens.db")


def init_geetokens_db():
    """Inicializa a tabela de tokens do GeeTest"""
    conn = sqlite3.connect(GEETOKENS_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plataforma TEXT NOT NULL,
            token TEXT NOT NULL,
            tamanho INTEGER NOT NULL,
            limite INTEGER NOT NULL,
            usos INTEGER NOT NULL DEFAULT 0,
            data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@contextmanager
def get_geetokens_db():
    """Context manager para o banco geetokens.db"""
    init_geetokens_db()
    conn = sqlite3.connect(GEETOKENS_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
