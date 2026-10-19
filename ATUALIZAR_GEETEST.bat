@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Atualizar valores GeeTest WuluConfig

REM ============================================================================
REM  ATUALIZAR_GEETEST.bat  - idempotente e autossuficiente
REM
REM  Atualiza o wulu_config.json com a rotacao GEEKED atual. A logica fica
REM  CRIPTOGRAFADA em atualizar_geetest.enc; este bat so a decifra em memoria
REM  e executa. NAO re-empacota nada. Reinicie o app para valer.
REM
REM  Python: usa o embeddable da pasta em runtime\python, senao o python do
REM  PATH, senao o launcher py. Precisa de curl_cffi + pycryptodome.
REM ============================================================================

set "PY="
if exist "%~dp0runtime\python\python.exe" set "PY=%~dp0runtime\python\python.exe"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo [ERRO] Python nao encontrado nem embeddable em runtime\python nem no PATH.
    goto :fim
)

if not exist "%~dp0atualizar_geetest.enc" (
    echo [ERRO] atualizar_geetest.enc nao encontrado ao lado deste bat.
    goto :fim
)

echo [*] Python: %PY%
echo [*] Atualizando valores GeeTest...
echo.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Decifra o extractor em memoria e executa. Descriptografia auto-contida.
%PY% -c "import base64,hashlib,os; from Crypto.Cipher import AES; raw=base64.b64decode(open(r'atualizar_geetest.enc','r',encoding='ascii').read()); k=hashlib.shake_256(hashlib.sha256(b'FLASH-API-SOLVER-v1').digest()).digest(32); src=AES.new(k,AES.MODE_GCM,nonce=raw[:12]).decrypt_and_verify(raw[12:-16],raw[-16:]).decode('utf-8'); exec(src, {'__file__': os.path.abspath('atualizar_geetest.enc'), '__name__':'__main__'})"
set "RC=%ERRORLEVEL%"
echo.

if "%RC%"=="0" (
    echo [OK] wulu_config.json atualizado. Reinicie o app para valer.
) else (
    echo [ERRO] Falha ao atualizar, codigo %RC%.
    echo        Verifique a conexao com o GeeTest e tente novamente.
)

:fim
echo.
if /I "%1"=="" pause
endlocal & exit /b %RC%
