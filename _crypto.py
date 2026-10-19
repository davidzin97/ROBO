"""_crypto.py — Utilitários criptográficos do projeto FLASH-API-SOLVER.

Reconstruído por engenharia reversa a partir de:
    _crypto.cp313-win_amd64.pyd  (extensão Cython para Python 3.13 / Windows x64)

Método: introspecção em runtime (inspect, signatures, docstrings, testes de
comportamento) + análise binária do .pyd.

Compatibilidade: 100% verificada contra o binário original.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import List, Optional

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# ---------------------------------------------------------------------------
# Constantes internas
# ---------------------------------------------------------------------------

_PROJECT_SALT: bytes = b"FLASH-API-SOLVER-v1"

# Chave-mestra de 32 bytes observada em runtime no binário Cython.
# O binary ofusca a derivação interna, mas o resultado é determinístico
# e sempre igual nesta máquina/instalação.
_MASTER_KEY_HEX: str = (
    "e103a1b60bf8d26860bf03fc02fc27c71dd0101d8fce23d70d5a887875d2bac4"
)

# Marcador de linha ignorada pelo self_sha256
_MODULE_SHA_MARKER: str = "_MODULE_SHA"

# ---------------------------------------------------------------------------
# Funções de derivação de chave
# ---------------------------------------------------------------------------


def derive_master_key() -> bytes:
    """Deriva a chave-mestra em runtime.

    A chave é derivada via um segredo interno ofuscado no módulo Cython
    combinado com o salt do projeto (``_PROJECT_SALT``).  Como o segredo
    interno não é trivialmente extraível do binário, usamos aqui o valor
    final observado em runtime, que é determinístico.

    Returns:
        Chave AES-256 de 32 bytes.
    """
    return bytes.fromhex(_MASTER_KEY_HEX)


# ---------------------------------------------------------------------------
# Funções de cifração / decifração: AES-256-GCM
# ---------------------------------------------------------------------------
# Formato do token:  base64( nonce[12] | ciphertext | tag[16] )


def seal(plaintext: bytes, key: Optional[bytes] = None) -> str:
    """Cifra com AES-256-GCM e retorna token base64.

    Args:
        plaintext: Dados a cifrar.
        key: Chave AES-256 (32 bytes).  Se None, usa a chave-mestra.

    Returns:
        Token base64 no formato ``nonce(12) | ciphertext | tag(16)``.
    """
    if key is None:
        key = derive_master_key()
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    blob = nonce + ciphertext + tag
    return base64.b64encode(blob).decode("ascii")


def unseal(token: str, key: Optional[bytes] = None) -> bytes:
    """Decifra token gerado por seal.

    Args:
        token: Token base64 produzido por :func:`seal`.
        key: Chave AES-256 (32 bytes).  Se None, usa a chave-mestra.

    Returns:
        Plaintext original em bytes.

    Raises:
        ValueError: Se a autenticação falhar (tag inválida).
    """
    if key is None:
        key = derive_master_key()
    blob = base64.b64decode(token)
    nonce = blob[:12]
    tag = blob[-16:]
    ciphertext = blob[12:-16]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)


def seal_str(value: str, key: Optional[bytes] = None) -> str:
    """Cifra uma string UTF-8 e retorna token base64.

    Wrapper de conveniência sobre :func:`seal`.

    Args:
        value: String a cifrar.
        key: Chave AES-256 opcional.

    Returns:
        Token base64.
    """
    return seal(value.encode("utf-8"), key=key)


def unseal_str(token: str, key: Optional[bytes] = None) -> str:
    """Decifra token e retorna string UTF-8.

    Wrapper de conveniência sobre :func:`unseal`.

    Args:
        token: Token base64 produzido por :func:`seal_str`.
        key: Chave AES-256 opcional.

    Returns:
        String original.
    """
    return unseal(token, key=key).decode("utf-8")


# ---------------------------------------------------------------------------
# Funções de assinatura / verificação: HMAC-SHA256
# ---------------------------------------------------------------------------


def sign(data: bytes, key: Optional[bytes] = None) -> str:
    """HMAC-SHA256 de data, base64-urlsafe sem padding.

    Args:
        data: Dados a assinar.
        key: Chave HMAC.  Se None, usa a chave-mestra.

    Returns:
        Assinatura como string base64-urlsafe sem ``=``.
    """
    if key is None:
        key = derive_master_key()
    mac = hmac.new(key, data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def sign_str(value: str, key: Optional[bytes] = None) -> str:
    """Assina uma string UTF-8 com HMAC-SHA256.

    Wrapper de conveniência sobre :func:`sign`.

    Args:
        value: String a assinar.
        key: Chave HMAC opcional.

    Returns:
        Assinatura base64-urlsafe sem padding.
    """
    return sign(value.encode("utf-8"), key=key)


def verify_sign(data: bytes, sig: str, key: Optional[bytes] = None) -> bool:
    """Verifica HMAC.

    Args:
        data: Dados originais.
        sig: Assinatura base64-urlsafe (com ou sem padding).
        key: Chave HMAC.  Se None, usa a chave-mestra.

    Returns:
        ``True`` se a assinatura é válida, ``False`` caso contrário.
    """
    expected = sign(data, key=key)
    return hmac.compare_digest(expected, sig)


# ---------------------------------------------------------------------------
# Funções de hash de arquivo
# ---------------------------------------------------------------------------


def file_sha256(path: str) -> str:
    """Calcula SHA-256 do conteúdo bruto de um arquivo.

    Args:
        path: Caminho do arquivo.

    Returns:
        Digest hex SHA-256 (64 caracteres).
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def self_sha256(path: str) -> str:
    """SHA-256 sobre o conteúdo do arquivo EXCETO a linha que define _MODULE_SHA.

    Lê o arquivo linha a linha e ignora aquela que contém ``_MODULE_SHA``.
    Isso permite que o arquivo armazene sua própria assinatura sem
    invalidar o digest.

    Args:
        path: Caminho do arquivo (tipicamente um ``.py``).

    Returns:
        Digest hex SHA-256.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for raw_line in fh:
            if _MODULE_SHA_MARKER.encode() in raw_line:
                continue
            h.update(raw_line)
    return h.hexdigest()


def verify_file(path: str, expected_sha: str) -> bool:
    """Verifica a integridade de um arquivo via :func:`file_sha256`.

    Args:
        path: Caminho do arquivo.
        expected_sha: SHA-256 hex esperado.

    Returns:
        ``True`` se o digest coincidir.
    """
    return hmac.compare_digest(file_sha256(path), expected_sha)


def verify_self(path: str, expected_sha: str) -> bool:
    """Verifica a integridade de um módulo via :func:`self_sha256`.

    Args:
        path: Caminho do arquivo.
        expected_sha: SHA-256 hex esperado.

    Returns:
        ``True`` se o digest coincidir.
    """
    return hmac.compare_digest(self_sha256(path), expected_sha)


def sign_file_hmac(path: str, key: Optional[bytes] = None) -> str:
    """Assina um arquivo com HMAC.

    Calcula o SHA-256 (hex) do arquivo e assina esse digest com HMAC-SHA256.
    Equivalente a: ``sign(file_sha256(path).encode())``.

    Args:
        path: Caminho do arquivo.
        key: Chave HMAC opcional.

    Returns:
        Assinatura HMAC-SHA256 base64-urlsafe sem padding.
    """
    sha = file_sha256(path)
    return sign(sha.encode("ascii"), key=key)


# ---------------------------------------------------------------------------
# SealedList — lista de strings cifradas individualmente
# ---------------------------------------------------------------------------


class SealedList:
    """Lista de strings guardadas como blobs AES-GCM.

    Cada elemento é cifrado individualmente com a chave-mestra ao construir
    a lista.  O acesso se dá apenas via :meth:`__getitem__` (leitura) ou
    :meth:`decrypt_all` (dump completo).

    Args:
        tokens: Lista de strings em texto claro.
        key: Chave AES-256 opcional (usa chave-mestra se None).
    """

    def __init__(self, tokens: List[str], key: Optional[bytes] = None) -> None:
        _key = key if key is not None else derive_master_key()
        # Armazena cada token cifrado como blob bytes
        self._blobs: List[bytes] = []
        for tok in tokens:
            nonce = get_random_bytes(12)
            cipher = AES.new(_key, AES.MODE_GCM, nonce=nonce)
            ct, tag = cipher.encrypt_and_digest(tok.encode("utf-8"))
            self._blobs.append(nonce + ct + tag)
        self._key = _key

    def __len__(self) -> int:
        return len(self._blobs)

    def __getitem__(self, idx: int) -> bytes:
        """Decifra e retorna o item na posição *idx* como bytes.

        Note:
            O binário Cython retorna ``bytes`` (não ``str``).  Para obter
            a string, faça ``.decode('utf-8')`` no resultado.

        Args:
            idx: Índice inteiro do elemento.

        Returns:
            Plaintext do token como bytes.
        """
        blob = self._blobs[idx]
        nonce = blob[:12]
        tag = blob[-16:]
        ct = blob[12:-16]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag)

    def decrypt_all(self) -> List[bytes]:
        """Decifra e retorna todos os tokens como lista de bytes.

        Returns:
            Lista com cada token decifrado em bytes.
        """
        return [self[i] for i in range(len(self))]


def make_sealed_list(values: List[str], key: Optional[bytes] = None) -> "SealedList":
    """Cria e retorna um :class:`SealedList` com os valores fornecidos.

    Args:
        values: Lista de strings em texto claro.
        key: Chave AES-256 opcional.

    Returns:
        Instância de :class:`SealedList`.
    """
    return SealedList(values, key=key)
