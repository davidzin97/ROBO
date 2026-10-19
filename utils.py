# -*- coding: utf-8 -*-
"""
Funções utilitárias - Geração de dados e criptografia
Baseado em funcoes.php
"""
import base64
import hashlib
import json
import os
import random
import re
import secrets
import string
import struct
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from Crypto.Cipher import AES

from config import (
    DEFAULT_IV,
    DEFAULT_KEY,
    DDDS_BRASIL,
    FAIXAS_IP_BR,
    FIRST_NAMES_FEMALE,
    FIRST_NAMES_MALE,
    LAST_NAMES_BR,
    MIDDLE_NAMES_BR,
)


# ==================== GERAÇÃO DE DADOS ====================

def gerar_usuario_one() -> str:
    """Gera nome de usuário aleatório (14 caracteres)"""
    numeros = str(secrets.randbelow(10**13)).zfill(13)
    letra = chr(random.randint(97, 122))  # a-z
    return letra + numeros  # 1 letra + 13 números = 14 caracteres

def gerar_usuario(length: int = 16) -> str:
    """Gera um username aleatório."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))
    
def gerar_usuario_por_nome(nome_completo: str, minimo: int = 12, maximo: int = 16) -> str:    
    primeiro_nome = (unicodedata.normalize("NFKD", nome_completo.split()[0].lower()).encode("ascii", "ignore") .decode("ascii"))
    if len(primeiro_nome) >= maximo:
        return primeiro_nome[:maximo]
    
    tamanho_final = random.randint(max(minimo, len(primeiro_nome)), maximo)
    chars = string.ascii_lowercase
    restante = ''.join(
        random.choice(chars)
        for _ in range(tamanho_final - len(primeiro_nome))
    )
    return primeiro_nome + restante

    
def gerar_senha() -> str:
    """Gera senha aleatória com requisitos de segurança"""
    #tamanho = random.randint(8, 14)
    tamanho = 12
    
    # Requisitos obrigatórios
    maiuscula = chr(random.randint(65, 90))   # A-Z
    minuscula = chr(random.randint(97, 122))  # a-z
    numero = chr(random.randint(48, 57))      # 0-9
    especial = random.choice(['#', '@'])
    
    # Caracteres restantes
    restantes = tamanho - 4
    todos = (
        list("abcdefghijklmnopqrstuvwxyz") +
        list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") +
        list("0123456789") +
        ['#', '@']
    )
    
    senha = [maiuscula, minuscula, numero, especial]
    for _ in range(restantes):
        senha.append(random.choice(todos))
    
    random.shuffle(senha)
    return ''.join(senha)

def gerar_senha_segura(minimo: int = 6, maximo: int = 16) -> str:
    tamanho = random.randint(minimo, maximo)
    maiuscula = chr(random.randint(65, 90))   # A-Z
    minuscula = chr(random.randint(97, 122))  # a-z
    numero = chr(random.randint(48, 57))      # 0-9
    especial = random.choice(['#', '@'])
    senha = [maiuscula, minuscula, numero, especial]
    todos = (
        list("abcdefghijklmnopqrstuvwxyz") +
        list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") +
        list("0123456789") +
        ['#', '@']
    )
    restantes = tamanho - len(senha)
    for _ in range(restantes):
        senha.append(random.choice(todos))
    random.shuffle(senha)
    return ''.join(senha)


def gerar_cpf(formatado: bool = False) -> str:
    """Gera CPF válido"""
    n = [random.randint(0, 9) for _ in range(9)]
    
    # Primeiro dígito verificador
    soma = sum(n[i] * (10 - i) for i in range(9))
    d1 = 11 - (soma % 11)
    d1 = 0 if d1 >= 10 else d1
    
    # Segundo dígito verificador
    soma = sum(n[i] * (11 - i) for i in range(9)) + d1 * 2
    d2 = 11 - (soma % 11)
    d2 = 0 if d2 >= 10 else d2
    
    cpf = ''.join(map(str, n)) + str(d1) + str(d2)
    
    if formatado:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


def gerar_celular() -> str:
    """Gera número de celular brasileiro válido (11 dígitos, sem +55)"""
    ddd = random.choice(DDDS_BRASIL)
    # Exemplo: 11 + 9 + 8 dígitos aleatórios = 11912433256
    numero_8_digitos = "".join(random.choices(string.digits, k=8))
    return f"{ddd}9{numero_8_digitos}"


def gerar_nome_completo() -> str:
    """Gera nome completo brasileiro"""
    is_male = random.choice([True, False])
    first_names = FIRST_NAMES_MALE if is_male else FIRST_NAMES_FEMALE
    
    first_name = random.choice(first_names)
    middle_name = random.choice(MIDDLE_NAMES_BR)
    last_name = random.choice(LAST_NAMES_BR)
    
    nome = f"{first_name} {middle_name} {last_name}"
    # Remove acentos
    nome = unicodedata.normalize('NFD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.upper()


def gerar_email(dominio: str = "@uorak.com") -> str:
    """Gera email aleatório"""
    palavras_path = "palavras.txt"
    try:
        with open(palavras_path, 'r', encoding='utf-8') as f:
            linhas = [l.strip() for l in f if l.strip()]
        if linhas:
            random.shuffle(linhas)
            palavra = linhas[0].lower()
            palavra = re.sub(r'[^a-z0-9]', '', palavra)
            if palavra:
                digitos = ''.join(str(random.randint(0, 9)) for _ in range(random.randint(1, 4)))
                return f"{palavra}{digitos}{dominio}"
    except FileNotFoundError:
        pass
    
    # Fallback
    palavra = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(8))
    digitos = str(random.randint(100, 999))
    return f"{palavra}{digitos}{dominio}"


def gerar_data_nascimento(min_age: int = 19, max_age: int = 70) -> str:
    """Gera data de nascimento para maior de idade"""
    hoje = datetime.now()
    idade = random.randint(min_age, max_age)
    ano = hoje.year - idade
    mes = random.randint(1, 12)
    dia = random.randint(1, 28)
    return f"{ano}-{mes:02d}-{dia:02d}"


def gerar_ip_brasileiro() -> str:
    """Gera IP brasileiro aleatório"""
    cidr = random.choice(FAIXAS_IP_BR)
    rede, prefixo = cidr.split('/')
    prefixo = int(prefixo)
    
    # Converte rede para inteiro
    octetos = [int(x) for x in rede.split('.')]
    rede_int = (octetos[0] << 24) + (octetos[1] << 16) + (octetos[2] << 8) + octetos[3]
    
    # Calcula range de hosts
    hosts = (1 << (32 - prefixo)) - 2
    ip_int = rede_int + random.randint(1, max(1, hosts))
    
    # Converte de volta para string
    return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"


def numero(tamanho: int = 12) -> str:
    """Gera número aleatório com tamanho específico"""
    return ''.join(str(random.randint(0, 9)) for _ in range(tamanho))


def uuid4() -> str:
    """Gera UUID v4"""
    data = secrets.token_bytes(16)
    data = bytearray(data)
    data[6] = (data[6] & 0x0f) | 0x40
    data[8] = (data[8] & 0x3f) | 0x80
    hex_str = data.hex()
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"


def generate_wechat_id(min_length: int = 6, max_length: int = 20) -> str:
    """Gera WeChat ID válido"""
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    rest_chars = letters + digits + "_-"
    
    length = random.randint(min_length, max_length)
    wechat_id = random.choice(letters)
    for _ in range(length - 1):
        wechat_id += random.choice(rest_chars)
    
    return wechat_id


def generate_device_model() -> Dict[str, str]:
    num = random.randint(100, 999)
    letter = random.choice(["A", "M", "F", "G"])
    prefix = random.choice(["A", "M"])
    modelo = f"SM-{prefix}{num}{letter}"
    devicesModel = [
        {"marca": "Samsung", "modelo": modelo, "nome": f"Samsung {modelo}"},
        {"marca":"Apple","modelo":"A2172","nome":"iPhone 12"},
        {"marca":"Apple","modelo":"A2176","nome":"iPhone 12 mini"},
        {"marca":"Apple","modelo":"A2275","nome":"iPhone SE (2020)"},
        {"marca":"Apple","modelo":"A2275","nome":"iPhone SE (2nd gen)"},
        {"marca":"Apple","modelo":"A2341","nome":"iPhone 12 Pro"},
        {"marca":"Apple","modelo":"A2342","nome":"iPhone 12 Pro Max"},
        {"marca":"Apple","modelo":"A2481","nome":"iPhone 13 mini"},
        {"marca":"Apple","modelo":"A2482","nome":"iPhone 13"},
        {"marca":"Apple","modelo":"A2483","nome":"iPhone 13 Pro"},
        {"marca":"Apple","modelo":"A2484","nome":"iPhone 13 Pro Max"},
        {"marca":"Apple","modelo":"A2595","nome":"iPhone SE (2022)"},
        {"marca":"Apple","modelo":"A2595","nome":"iPhone SE (3rd gen)"},
        {"marca":"Apple","modelo":"A2632","nome":"iPhone 14 Plus"},
        {"marca":"Apple","modelo":"A2649","nome":"iPhone 14"},
        {"marca":"Apple","modelo":"A2650","nome":"iPhone 14 Pro"},
        {"marca":"Apple","modelo":"A2651","nome":"iPhone 14 Pro Max"},
        {"marca":"Apple","modelo":"A2783","nome":"iPhone SE (2024)"},
        {"marca":"Apple","modelo":"A3090","nome":"iPhone 15"},
        {"marca":"Apple","modelo":"A3094","nome":"iPhone 15 Plus"},
        {"marca":"Apple","modelo":"A3102","nome":"iPhone 15 Pro"},
        {"marca":"Apple","modelo":"A3106","nome":"iPhone 15 Pro Max"},
        {"marca":"Apple","modelo":"A3287","nome":"iPhone 16"},
        {"marca":"Apple","modelo":"A3291","nome":"iPhone 16 Plus"},
        {"marca":"Apple","modelo":"A3295","nome":"iPhone 16 Pro"},
        {"marca":"Apple","modelo":"A3299","nome":"iPhone 16 Pro Max"},
        {"marca":"Apple","modelo":"A3442","nome":"iPhone 16e"},
        {"marca":"Apple","modelo":"A3500","nome":"iPhone 17"},
        {"marca":"Apple","modelo":"A3510","nome":"iPhone 17 Pro"},
        {"marca":"Apple","modelo":"A3520","nome":"iPhone 17 Pro Max"},
        {"marca":"Apple","modelo":"A3530","nome":"iPhone Air"},
        {"marca":"Asus","modelo":"AI2201","nome":"ROG Phone 6"},
        {"marca":"Asus","modelo":"AI2201P","nome":"ROG Phone 6 Pro"},
        {"marca":"Asus","modelo":"AI2202","nome":"Zenfone 9"},
        {"marca":"Asus","modelo":"AI2203","nome":"ROG Phone 6D"},
        {"marca":"Asus","modelo":"AI2203U","nome":"ROG Phone 6D Ultimate"},
        {"marca":"Asus","modelo":"AI2205","nome":"ROG Phone 7"},
        {"marca":"Asus","modelo":"AI2205U","nome":"ROG Phone 7 Ultimate"},
        {"marca":"Asus","modelo":"AI2302","nome":"Zenfone 10"},
        {"marca":"Asus","modelo":"AI2401","nome":"ROG Phone 8"},
        {"marca":"Asus","modelo":"AI2401P","nome":"ROG Phone 8 Pro"},
        {"marca":"Asus","modelo":"AI2401Z","nome":"Zenfone 11 Ultra"},
        {"marca":"Asus","modelo":"AI2401Z","nome":"Zenfone 11"},
        {"marca":"Asus","modelo":"AI2402Z","nome":"Zenfone 11 Ultra"},
        {"marca":"Asus","modelo":"AI2501","nome":"ROG Phone 9"},
        {"marca":"Asus","modelo":"AI2501F","nome":"ROG Phone 9 FE"},
        {"marca":"Asus","modelo":"AI2501P","nome":"ROG Phone 9 Pro"},
        {"marca":"Asus","modelo":"AI2501Z","nome":"Zenfone 12 Ultra"},
        {"marca":"Asus","modelo":"AI2501Z","nome":"Zenfone 12"},
        {"marca":"Asus","modelo":"AI2502Z","nome":"Zenfone 12 Ultra"},
        {"marca":"Asus","modelo":"I003D","nome":"ROG Phone 3 Strix"},
        {"marca":"Asus","modelo":"I003DD","nome":"ROG Phone 3"},
        {"marca":"Asus","modelo":"I003DD","nome":"ROG Phone 5"},
        {"marca":"Asus","modelo":"I005DA","nome":"ROG Phone 5"},
        {"marca":"Asus","modelo":"I005DA","nome":"ROG Phone 5s"},
        {"marca":"Asus","modelo":"I005DB","nome":"ROG Phone 5 Pro"},
        {"marca":"Asus","modelo":"I005DC","nome":"ROG Phone 5 Ultimate"},
        {"marca":"Asus","modelo":"I005DD","nome":"ROG Phone 5s"},
        {"marca":"Asus","modelo":"I005DE","nome":"ROG Phone 5s Pro"},
        {"marca":"Asus","modelo":"ZS590KS","nome":"Zenfone 8"},
        {"marca":"Asus","modelo":"ZS670KS","nome":"Zenfone 7"},
        {"marca":"Asus","modelo":"ZS671KS","nome":"Zenfone 7 Pro"},
        {"marca":"Asus","modelo":"ZS672KS","nome":"Zenfone 8 Flip"},
        {"marca":"Google","modelo":"G025H","nome":"Pixel 4a 5G"},
        {"marca":"Google","modelo":"G025J","nome":"Pixel 4a"},
        {"marca":"Google","modelo":"G1MNW","nome":"Pixel 8 Pro"},
        {"marca":"Google","modelo":"G4EMT","nome":"Pixel 9 Pro Fold"},
        {"marca":"Google","modelo":"G4S1M","nome":"Pixel 5a"},
        {"marca":"Google","modelo":"G6GPR","nome":"Pixel 8a"},
        {"marca":"Google","modelo":"G8V0U","nome":"Pixel 6 Pro"},
        {"marca":"Google","modelo":"G9FPL","nome":"Pixel Fold"},
        {"marca":"Google","modelo":"GA09A","nome":"Pixel 9a"},
        {"marca":"Google","modelo":"GB7N6","nome":"Pixel 6"},
        {"marca":"Google","modelo":"GD1YQ","nome":"Pixel 5"},
        {"marca":"Google","modelo":"GE2AE","nome":"Pixel 7 Pro"},
        {"marca":"Google","modelo":"GKWS6","nome":"Pixel 8"},
        {"marca":"Google","modelo":"GP10A","nome":"Pixel 10"},
        {"marca":"Google","modelo":"GP10F","nome":"Pixel 10 Pro Fold"},
        {"marca":"Google","modelo":"GP10P","nome":"Pixel 10 Pro"},
        {"marca":"Google","modelo":"GP10X","nome":"Pixel 10 Pro XL"},
        {"marca":"Google","modelo":"GQML3","nome":"Pixel 7"},
        {"marca":"Google","modelo":"GWKK3","nome":"Pixel 7a"},
        {"marca":"Google","modelo":"GWV9A","nome":"Pixel 9a"},
        {"marca":"Google","modelo":"GWVK6","nome":"Pixel 9 Pro XL"},
        {"marca":"Google","modelo":"GWVPR","nome":"Pixel 9"},
        {"marca":"Google","modelo":"GWVZS","nome":"Pixel 9 Pro"},
        {"marca":"Google","modelo":"GX7AS","nome":"Pixel 6a"},
        {"marca":"Motorola","modelo":"XT2041","nome":"Moto G Power (2020)"},
        {"marca":"Motorola","modelo":"XT2041-4","nome":"Moto G Power (2020)"},
        {"marca":"Motorola","modelo":"XT2043","nome":"Moto G Stylus (2020)"},
        {"marca":"Motorola","modelo":"XT2043-4","nome":"Moto G Stylus (2020)"},
        {"marca":"Motorola","modelo":"XT2045","nome":"Moto G Fast (2020)"},
        {"marca":"Motorola","modelo":"XT2045","nome":"Moto G Pro (2020)"},
        {"marca":"Motorola","modelo":"XT2061","nome":"Moto Edge+ (2020)"},
        {"marca":"Motorola","modelo":"XT2061-3","nome":"Moto Edge+ 2020"},
        {"marca":"Motorola","modelo":"XT2063","nome":"Moto Edge (2020)"},
        {"marca":"Motorola","modelo":"XT2063-3","nome":"Moto Edge 2020"},
        {"marca":"Motorola","modelo":"XT2071-2","nome":"Razr 2020"},
        {"marca":"Motorola","modelo":"XT2071-4","nome":"Razr 5G (2020)"},
        {"marca":"Motorola","modelo":"XT2115","nome":"Moto G Stylus (2021)"},
        {"marca":"Motorola","modelo":"XT2117","nome":"Moto G Play (2021)"},
        {"marca":"Motorola","modelo":"XT2117","nome":"Moto G Power (2021)"},
        {"marca":"Motorola","modelo":"XT2117-4","nome":"Moto G Play (2021)"},
        {"marca":"Motorola","modelo":"XT2125","nome":"Moto G100"},
        {"marca":"Motorola","modelo":"XT2139","nome":"Moto Edge 20 Lite"},
        {"marca":"Motorola","modelo":"XT2141","nome":"Moto Edge (2021)"},
        {"marca":"Motorola","modelo":"XT2141-1","nome":"Moto Edge 2021"},
        {"marca":"Motorola","modelo":"XT2143","nome":"Moto Edge 20"},
        {"marca":"Motorola","modelo":"XT2153","nome":"Moto Edge 20 Pro"},
        {"marca":"Motorola","modelo":"XT2165","nome":"Moto G Play (2022)"},
        {"marca":"Motorola","modelo":"XT2165","nome":"Moto G Power (2022)"},
        {"marca":"Motorola","modelo":"XT2165-3","nome":"Moto G Power (2022)"},
        {"marca":"Motorola","modelo":"XT2201","nome":"Moto Edge 30 Pro"},
        {"marca":"Motorola","modelo":"XT2201","nome":"Moto Edge+ (2022)"},
        {"marca":"Motorola","modelo":"XT2203","nome":"Moto Edge (2022)"},
        {"marca":"Motorola","modelo":"XT2203-1","nome":"Moto Edge 2022"},
        {"marca":"Motorola","modelo":"XT2211","nome":"Moto G Stylus (2022)"},
        {"marca":"Motorola","modelo":"XT2241","nome":"Moto Edge 30 Ultra"},
        {"marca":"Motorola","modelo":"XT2241-1","nome":"Moto Edge 30 Ultra"},
        {"marca":"Motorola","modelo":"XT2243","nome":"Moto Edge 30 Fusion"},
        {"marca":"Motorola","modelo":"XT2243","nome":"Moto Edge 30"},
        {"marca":"Motorola","modelo":"XT2243-1","nome":"Moto Edge 30"},
        {"marca":"Motorola","modelo":"XT2245","nome":"Moto Edge 30 Neo"},
        {"marca":"Motorola","modelo":"XT2301","nome":"Moto Edge 40 Pro"},
        {"marca":"Motorola","modelo":"XT2301-1","nome":"Moto Edge 40 Pro"},
        {"marca":"Motorola","modelo":"XT2303","nome":"Moto Edge 40"},
        {"marca":"Motorola","modelo":"XT2303-1","nome":"Moto Edge 40"},
        {"marca":"Motorola","modelo":"XT2309","nome":"Moto Edge (2023)"},
        {"marca":"Motorola","modelo":"XT2309-2","nome":"Moto Edge 2023"},
        {"marca":"Motorola","modelo":"XT2313","nome":"Moto Edge 40 Neo"},
        {"marca":"Motorola","modelo":"XT2321-1","nome":"Razr 40"},
        {"marca":"Motorola","modelo":"XT2323-3","nome":"Razr 40 Ultra"},
        {"marca":"Motorola","modelo":"XT2341","nome":"Moto G Stylus (2023)"},
        {"marca":"Motorola","modelo":"XT2343","nome":"Moto G Power 5G (2023)"},
        {"marca":"Motorola","modelo":"XT2343-1","nome":"Moto G Power 5G (2023)"},
        {"marca":"Motorola","modelo":"XT2345","nome":"Moto G 5G (2023)"},
        {"marca":"Motorola","modelo":"XT2347","nome":"Moto G (2023)"},
        {"marca":"Motorola","modelo":"XT2401","nome":"Moto Edge 50"},
        {"marca":"Motorola","modelo":"XT2401-1","nome":"Moto Edge 50"},
        {"marca":"Motorola","modelo":"XT2403","nome":"Moto Edge (2024)"},
        {"marca":"Motorola","modelo":"XT2403-1","nome":"Moto Edge 2024"},
        {"marca":"Motorola","modelo":"XT2405","nome":"Moto Edge 50 Pro"},
        {"marca":"Motorola","modelo":"XT2405-1","nome":"Moto Edge 50 Pro"},
        {"marca":"Motorola","modelo":"XT2407","nome":"Moto Edge 50 Fusion"},
        {"marca":"Motorola","modelo":"XT2409","nome":"Moto Edge 50 Neo"},
        {"marca":"Motorola","modelo":"XT2411","nome":"Moto Edge 50 Ultra"},
        {"marca":"Motorola","modelo":"XT2411-1","nome":"Moto Edge 50 Ultra"},
        {"marca":"Motorola","modelo":"XT2421","nome":"Moto G 5G (2024)"},
        {"marca":"Motorola","modelo":"XT2421-1","nome":"Moto G 5G (2024)"},
        {"marca":"Motorola","modelo":"XT2423","nome":"Moto G Power 5G (2024)"},
        {"marca":"Motorola","modelo":"XT2425","nome":"Moto G Play (2024)"},
        {"marca":"Motorola","modelo":"XT2425-1","nome":"Moto G05"},
        {"marca":"Motorola","modelo":"XT2427","nome":"Moto G Stylus 5G (2024)"},
        {"marca":"Motorola","modelo":"XT2427-1","nome":"Moto G15"},
        {"marca":"Motorola","modelo":"XT2428-1","nome":"Moto G15 Power"},
        {"marca":"Motorola","modelo":"XT2429-1","nome":"Moto E15"},
        {"marca":"Motorola","modelo":"XT2431-1","nome":"Moto G35 5G"},
        {"marca":"Motorola","modelo":"XT2433-1","nome":"Moto G45 5G"},
        {"marca":"Motorola","modelo":"XT2435-1","nome":"Moto G75 5G"},
        {"marca":"Motorola","modelo":"XT2437-1","nome":"Moto G86 5G"},
        {"marca":"Motorola","modelo":"XT2439-1","nome":"Moto G86 Power 5G"},
        {"marca":"Motorola","modelo":"XT2441-1","nome":"Moto G56"},
        {"marca":"Motorola","modelo":"XT2451-1","nome":"Razr 50"},
        {"marca":"Motorola","modelo":"XT2453-1","nome":"Razr 50D"},
        {"marca":"Motorola","modelo":"XT2461-1","nome":"Razr 60"},
        {"marca":"Motorola","modelo":"XT2463-1","nome":"Razr 60 Ultra"},
        {"marca":"Motorola","modelo":"XT2465-1","nome":"ThinkPhone 25"},
        {"marca":"Motorola","modelo":"XT2501","nome":"Moto Edge (2025)"},
        {"marca":"Motorola","modelo":"XT2501-1","nome":"Moto Edge 2025"},
        {"marca":"Motorola","modelo":"XT2503","nome":"Moto Edge 60"},
        {"marca":"Motorola","modelo":"XT2503-1","nome":"Moto Edge 60"},
        {"marca":"Motorola","modelo":"XT2505","nome":"Moto Edge 60 Fusion"},
        {"marca":"Motorola","modelo":"XT2507","nome":"Moto Edge 60 Pro"},
        {"marca":"Motorola","modelo":"XT2507-1","nome":"Moto Edge 60 Pro"},
        {"marca":"Motorola","modelo":"XT2509","nome":"Moto Edge 60 Neo"},
        {"marca":"Motorola","modelo":"XT2521","nome":"Moto G (2025)"},
        {"marca":"Motorola","modelo":"XT2521-1","nome":"Moto G (2025)"},
        {"marca":"Motorola","modelo":"XT2523","nome":"Moto G Power (2025)"},
        {"marca":"Motorola","modelo":"XT2523-1","nome":"Moto G Power (2025)"},
        {"marca":"Motorola","modelo":"XT2525","nome":"Moto G Stylus (2025)"},
        {"marca":"OnePlus","modelo":"AC2001","nome":"OnePlus Nord"},
        {"marca":"OnePlus","modelo":"BE2011","nome":"OnePlus Nord N100"},
        {"marca":"OnePlus","modelo":"BE2025","nome":"OnePlus Nord N10 5G"},
        {"marca":"OnePlus","modelo":"BE2025","nome":"OnePlus Nord N10"},
        {"marca":"OnePlus","modelo":"CPH2381","nome":"OnePlus Nord CE 2 Lite"},
        {"marca":"OnePlus","modelo":"CPH2415","nome":"OnePlus 10T"},
        {"marca":"OnePlus","modelo":"CPH2423","nome":"OnePlus 10R"},
        {"marca":"OnePlus","modelo":"CPH2467","nome":"OnePlus Nord CE 3 Lite 5G"},
        {"marca":"OnePlus","modelo":"CPH2467","nome":"OnePlus Nord CE 3 Lite"},
        {"marca":"OnePlus","modelo":"CPH2469","nome":"OnePlus Nord CE 3 5G"},
        {"marca":"OnePlus","modelo":"CPH2469","nome":"OnePlus Nord CE 3"},
        {"marca":"OnePlus","modelo":"CPH2493","nome":"OnePlus Nord 3 5G"},
        {"marca":"OnePlus","modelo":"CPH2527","nome":"OnePlus Nord N30 5G"},
        {"marca":"OnePlus","modelo":"CPH2527","nome":"OnePlus Nord N30"},
        {"marca":"OnePlus","modelo":"CPH2529","nome":"OnePlus Nord N300 5G"},
        {"marca":"OnePlus","modelo":"CPH2529","nome":"OnePlus Nord N300"},
        {"marca":"OnePlus","modelo":"CPH2573","nome":"OnePlus 12"},
        {"marca":"OnePlus","modelo":"CPH2583","nome":"OnePlus 11R"},
        {"marca":"OnePlus","modelo":"CPH2585","nome":"OnePlus 12R"},
        {"marca":"OnePlus","modelo":"CPH2625","nome":"OnePlus Nord CE 4 5G"},
        {"marca":"OnePlus","modelo":"CPH2625","nome":"OnePlus Nord CE 4"},
        {"marca":"OnePlus","modelo":"CPH2627","nome":"OnePlus Nord CE 4 Lite"},
        {"marca":"OnePlus","modelo":"CPH2631","nome":"OnePlus 13R"},
        {"marca":"OnePlus","modelo":"CPH2631","nome":"OnePlus Nord 4"},
        {"marca":"OnePlus","modelo":"CPH2635","nome":"OnePlus Nord 4"},
        {"marca":"OnePlus","modelo":"CPH2701","nome":"OnePlus Nord 5"},
        {"marca":"OnePlus","modelo":"CPH2705","nome":"OnePlus Nord CE 5 5G"},
        {"marca":"OnePlus","modelo":"CPH2705","nome":"OnePlus Nord CE 5"},
        {"marca":"OnePlus","modelo":"CPH2741","nome":"OnePlus 15R"},
        {"marca":"OnePlus","modelo":"DE2118","nome":"OnePlus Nord N200 5G"},
        {"marca":"OnePlus","modelo":"DN2101","nome":"OnePlus Nord 2 5G"},
        {"marca":"OnePlus","modelo":"EB2101","nome":"OnePlus Nord CE 5G"},
        {"marca":"OnePlus","modelo":"GN2200","nome":"OnePlus Nord N20 5G"},
        {"marca":"OnePlus","modelo":"IN2010","nome":"OnePlus 8"},
        {"marca":"OnePlus","modelo":"IN2020","nome":"OnePlus 8 Pro"},
        {"marca":"OnePlus","modelo":"IV2201","nome":"OnePlus Nord CE 2"},
        {"marca":"OnePlus","modelo":"KB2001","nome":"OnePlus 8T"},
        {"marca":"OnePlus","modelo":"LE2101","nome":"OnePlus 9R"},
        {"marca":"OnePlus","modelo":"LE2111","nome":"OnePlus 9"},
        {"marca":"OnePlus","modelo":"LE2121","nome":"OnePlus 9 Pro"},
        {"marca":"OnePlus","modelo":"MT2111","nome":"OnePlus 9RT"},
        {"marca":"OnePlus","modelo":"NE2211","nome":"OnePlus 10 Pro"},
        {"marca":"OnePlus","modelo":"PHB110","nome":"OnePlus 11"},
        {"marca":"OnePlus","modelo":"PJD110","nome":"OnePlus 13"},
        {"marca":"OnePlus","modelo":"PJE110","nome":"OnePlus 15"},
        {"marca":"OPPO","modelo":"CPH2001","nome":"F15"},
        {"marca":"OPPO","modelo":"CPH2015","nome":"A5 (2020)"},
        {"marca":"OPPO","modelo":"CPH2025","nome":"Find X2 Pro"},
        {"marca":"OPPO","modelo":"CPH2039","nome":"Find X2"},
        {"marca":"OPPO","modelo":"CPH2069","nome":"A73 (2020)"},
        {"marca":"OPPO","modelo":"CPH2095","nome":"A91"},
        {"marca":"OPPO","modelo":"CPH2095","nome":"F17"},
        {"marca":"OPPO","modelo":"CPH2109","nome":"Reno4"},
        {"marca":"OPPO","modelo":"CPH2119","nome":"F17 Pro"},
        {"marca":"OPPO","modelo":"CPH2127","nome":"A55"},
        {"marca":"OPPO","modelo":"CPH2145","nome":"Reno5"},
        {"marca":"OPPO","modelo":"CPH2173","nome":"Find X3 Pro"},
        {"marca":"OPPO","modelo":"CPH2173","nome":"Find X3"},
        {"marca":"OPPO","modelo":"CPH2175","nome":"Find X3 Pro"},
        {"marca":"OPPO","modelo":"CPH2185","nome":"Reno6"},
        {"marca":"OPPO","modelo":"CPH2197","nome":"A74"},
        {"marca":"OPPO","modelo":"CPH2197","nome":"F19"},
        {"marca":"OPPO","modelo":"CPH2199","nome":"A74 5G"},
        {"marca":"OPPO","modelo":"CPH2211","nome":"Reno7"},
        {"marca":"OPPO","modelo":"CPH2239","nome":"A54 5G"},
        {"marca":"OPPO","modelo":"CPH2251","nome":"Find X5"},
        {"marca":"OPPO","modelo":"CPH2269","nome":"A16"},
        {"marca":"OPPO","modelo":"CPH2305","nome":"Find X5 Pro"},
        {"marca":"OPPO","modelo":"CPH2341","nome":"F21 Pro"},
        {"marca":"OPPO","modelo":"CPH2343","nome":"F21 Pro 5G"},
        {"marca":"OPPO","modelo":"CPH2345","nome":"F21s Pro"},
        {"marca":"OPPO","modelo":"CPH2349","nome":"A77 5G"},
        {"marca":"OPPO","modelo":"CPH2351","nome":"A96"},
        {"marca":"OPPO","modelo":"CPH2353","nome":"A76"},
        {"marca":"OPPO","modelo":"CPH2357","nome":"Reno8 Pro 5G"},
        {"marca":"OPPO","modelo":"CPH2359","nome":"Reno8"},
        {"marca":"OPPO","modelo":"CPH2457","nome":"A38"},
        {"marca":"OPPO","modelo":"CPH2459","nome":"A58 4G"},
        {"marca":"OPPO","modelo":"CPH2461","nome":"A78"},
        {"marca":"OPPO","modelo":"CPH2463","nome":"A78 5G"},
        {"marca":"OPPO","modelo":"CPH2465","nome":"A79 5G"},
        {"marca":"OPPO","modelo":"CPH2467","nome":"A98 5G"},
        {"marca":"OPPO","modelo":"CPH2477","nome":"F23"},
        {"marca":"OPPO","modelo":"CPH2491","nome":"Reno9"},
        {"marca":"OPPO","modelo":"CPH2519","nome":"Find X6 Pro"},
        {"marca":"OPPO","modelo":"CPH2519","nome":"Find X6"},
        {"marca":"OPPO","modelo":"CPH2521","nome":"Find X6 Pro"},
        {"marca":"OPPO","modelo":"CPH2525","nome":"Reno10"},
        {"marca":"OPPO","modelo":"CPH2527","nome":"Reno10 Pro"},
        {"marca":"OPPO","modelo":"CPH2529","nome":"Reno10 Pro+"},
        {"marca":"OPPO","modelo":"CPH2569","nome":"A5 5G"},
        {"marca":"OPPO","modelo":"CPH2571","nome":"A5 Pro 5G"},
        {"marca":"OPPO","modelo":"CPH2573","nome":"A6 Pro 5G"},
        {"marca":"OPPO","modelo":"CPH2575","nome":"A60"},
        {"marca":"OPPO","modelo":"CPH2577","nome":"A80 5G"},
        {"marca":"OPPO","modelo":"CPH2579","nome":"F25 Pro"},
        {"marca":"OPPO","modelo":"CPH2601","nome":"Reno11"},
        {"marca":"OPPO","modelo":"CPH2603","nome":"Reno11 Pro"},
        {"marca":"OPPO","modelo":"CPH2605","nome":"Reno11 F 5G"},
        {"marca":"OPPO","modelo":"CPH2611","nome":"Find X7 Ultra"},
        {"marca":"OPPO","modelo":"CPH2611","nome":"Find X7"},
        {"marca":"OPPO","modelo":"CPH2613","nome":"Find X7 Ultra"},
        {"marca":"OPPO","modelo":"CPH2621","nome":"F27 Pro+"},
        {"marca":"OPPO","modelo":"CPH2631","nome":"Reno12"},
        {"marca":"OPPO","modelo":"CPH2633","nome":"Reno12 Pro"},
        {"marca":"OPPO","modelo":"CPH2635","nome":"Reno12 F 5G"},
        {"marca":"OPPO","modelo":"CPH2661","nome":"Reno13"},
        {"marca":"OPPO","modelo":"CPH2663","nome":"Reno13 Pro"},
        {"marca":"OPPO","modelo":"CPH2665","nome":"Reno13 F 5G"},
        {"marca":"OPPO","modelo":"CPH2701","nome":"Reno14"},
        {"marca":"OPPO","modelo":"CPH2703","nome":"Reno14 Pro"},
        {"marca":"OPPO","modelo":"CPH2711","nome":"F29"},
        {"marca":"OPPO","modelo":"CPH2711","nome":"Find X8"},
        {"marca":"OPPO","modelo":"CPH2713","nome":"F29 Pro"},
        {"marca":"OPPO","modelo":"CPH2713","nome":"Find X8 Pro"},
        {"marca":"OPPO","modelo":"CPH2731","nome":"Reno15"},
        {"marca":"OPPO","modelo":"CPH2733","nome":"Reno15 Pro"},
        {"marca":"OPPO","modelo":"CPH2751","nome":"F31 Pro"},
        {"marca":"OPPO","modelo":"CPH2753","nome":"F31 Pro+"},
        {"marca":"Xiaomi","modelo":"21091116AG","nome":"Poco M4 Pro 5G"},
        {"marca":"Xiaomi","modelo":"211033MI","nome":"Poco C31"},
        {"marca":"Xiaomi","modelo":"211035MI","nome":"Poco C33"},
        {"marca":"Xiaomi","modelo":"21121210G","nome":"Poco F3 GT"},
        {"marca":"Xiaomi","modelo":"21121210G","nome":"Poco X3 GT"},
        {"marca":"Xiaomi","modelo":"2201116PG","nome":"Poco X4 Pro 5G"},
        {"marca":"Xiaomi","modelo":"2201116PG","nome":"Poco X4 Pro"},
        {"marca":"Xiaomi","modelo":"2201117PG","nome":"Poco M4 Pro"},
        {"marca":"Xiaomi","modelo":"22021211RG","nome":"Poco F4"},
        {"marca":"Xiaomi","modelo":"220333QPG","nome":"Poco C40"},
        {"marca":"Xiaomi","modelo":"22041216G","nome":"Poco F4 GT"},
        {"marca":"Xiaomi","modelo":"22041216G","nome":"Poco X4 GT"},
        {"marca":"Xiaomi","modelo":"22041219PG","nome":"Poco M4 5G"},
        {"marca":"Xiaomi","modelo":"2207117BPG","nome":"Poco M5s"},
        {"marca":"Xiaomi","modelo":"22071219CG","nome":"Poco M5"},
        {"marca":"Xiaomi","modelo":"220733SPI","nome":"Poco C50"},
        {"marca":"Xiaomi","modelo":"22101320G","nome":"Poco X5 Pro 5G"},
        {"marca":"Xiaomi","modelo":"22101320G","nome":"Poco X5 Pro"},
        {"marca":"Xiaomi","modelo":"22111317PG","nome":"Poco X5 5G"},
        {"marca":"Xiaomi","modelo":"22111317PI","nome":"Poco X5"},
        {"marca":"Xiaomi","modelo":"23049PCD8G","nome":"Poco F5"},
        {"marca":"Xiaomi","modelo":"23053RN02A","nome":"Poco F5 Pro"},
        {"marca":"Xiaomi","modelo":"2305EPCC4G","nome":"Poco C51"},
        {"marca":"Xiaomi","modelo":"23065PC5BG","nome":"Poco C55"},
        {"marca":"Xiaomi","modelo":"23076PC4BI","nome":"Poco M6"},
        {"marca":"Xiaomi","modelo":"23106PC65G","nome":"Poco C65"},
        {"marca":"Xiaomi","modelo":"23122PCD1G","nome":"Poco X6"},
        {"marca":"Xiaomi","modelo":"23122PCD2G","nome":"Poco X6 Pro 5G"},
        {"marca":"Xiaomi","modelo":"23122PCD2G","nome":"Poco X6 Pro"},
        {"marca":"Xiaomi","modelo":"24053PY09G","nome":"Poco F6"},
        {"marca":"Xiaomi","modelo":"24069PC21G","nome":"Poco F6 Pro"},
        {"marca":"Xiaomi","modelo":"24076PC6BG","nome":"Poco M6 Pro 4G"},
        {"marca":"Xiaomi","modelo":"24076PC6BG","nome":"Poco M6 Pro"},
        {"marca":"Xiaomi","modelo":"24078PN4BG","nome":"Poco M7 5G"},
        {"marca":"Xiaomi","modelo":"24078PN4BG","nome":"Poco M7"},
        {"marca":"Xiaomi","modelo":"24078PN5BG","nome":"Poco M7 Pro 5G"},
        {"marca":"Xiaomi","modelo":"24106PC71G","nome":"Poco C71"},
        {"marca":"Xiaomi","modelo":"24122PC61G","nome":"Poco C61"},
        {"marca":"Xiaomi","modelo":"24122PC75G","nome":"Poco C75"},
        {"marca":"Xiaomi","modelo":"24122PC85G","nome":"Poco C85"},
        {"marca":"Xiaomi","modelo":"24122PCD2G","nome":"Poco X7 Pro"},
        {"marca":"Xiaomi","modelo":"24122PCDIG","nome":"Poco X7"},
        {"marca":"Xiaomi","modelo":"25071PCD1G","nome":"Poco F7"},
        {"marca":"Xiaomi","modelo":"25073PCD2G","nome":"Poco F7 Pro"},
        {"marca":"Xiaomi","modelo":"25075PCD3G","nome":"Poco F7 Ultra"},
        {"marca":"Xiaomi","modelo":"25078PN6BG","nome":"Poco M8"},
        {"marca":"Xiaomi","modelo":"25078PN7BG","nome":"Poco M8 Pro 5G"},
        {"marca":"Xiaomi","modelo":"25081PCD3G","nome":"Poco F8"},
        {"marca":"Xiaomi","modelo":"25083PCD4G","nome":"Poco F8 Pro"},
        {"marca":"Xiaomi","modelo":"25085PCD5G","nome":"Poco F8 Ultra"},
        {"marca":"Xiaomi","modelo":"M2002J9G","nome":"Poco X2"},
        {"marca":"Xiaomi","modelo":"M2003J6CI","nome":"Poco M2 Pro"},
        {"marca":"Xiaomi","modelo":"M2004J19PI","nome":"Poco M2"},
        {"marca":"Xiaomi","modelo":"M2006C3MI","nome":"Poco C3"},
        {"marca":"Xiaomi","modelo":"M2007J20CG","nome":"Poco F2 Pro"},
        {"marca":"Xiaomi","modelo":"M2007J20CG","nome":"Poco X3 NFC"},
        {"marca":"Xiaomi","modelo":"M2007J20CG","nome":"Poco X3"},
        {"marca":"Xiaomi","modelo":"M2007J20CT","nome":"Poco X3 NFC"},
        {"marca":"Xiaomi","modelo":"M2010J19CG","nome":"Poco M3"},
        {"marca":"Xiaomi","modelo":"M2012K11AG","nome":"Poco F3"},
        {"marca":"Xiaomi","modelo":"M2102J20SG","nome":"Poco X3 Pro"},
        {"marca":"Xiaomi","modelo":"M2103K19PG","nome":"Poco M3 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX2001","nome":"Realme 6"},
        {"marca":"Xiaomi","modelo":"RMX2002","nome":"Realme 6s"},
        {"marca":"Xiaomi","modelo":"RMX2040","nome":"Realme 6i"},
        {"marca":"Xiaomi","modelo":"RMX2061","nome":"Realme 6 Pro"},
        {"marca":"Xiaomi","modelo":"RMX2076","nome":"Realme X50 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX2151","nome":"Realme 7"},
        {"marca":"Xiaomi","modelo":"RMX2155","nome":"Realme 7i"},
        {"marca":"Xiaomi","modelo":"RMX2170","nome":"Realme 7 Pro"},
        {"marca":"Xiaomi","modelo":"RMX2202","nome":"Realme GT 5G"},
        {"marca":"Xiaomi","modelo":"RMX2202","nome":"Realme GT"},
        {"marca":"Xiaomi","modelo":"RMX3081","nome":"Realme 8 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3085","nome":"Realme 8 5G"},
        {"marca":"Xiaomi","modelo":"RMX3085","nome":"Realme 8"},
        {"marca":"Xiaomi","modelo":"RMX3151","nome":"Realme 9"},
        {"marca":"Xiaomi","modelo":"RMX3286","nome":"Realme Narzo 50A"},
        {"marca":"Xiaomi","modelo":"RMX3301","nome":"Realme GT 2 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3301","nome":"Realme GT 2"},
        {"marca":"Xiaomi","modelo":"RMX3310","nome":"Realme 9 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX3311","nome":"Realme GT 2 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3371","nome":"Realme X7 Max 5G"},
        {"marca":"Xiaomi","modelo":"RMX3381","nome":"Realme 8s 5G"},
        {"marca":"Xiaomi","modelo":"RMX3381","nome":"Realme GT Neo2"},
        {"marca":"Xiaomi","modelo":"RMX3393","nome":"Realme 9 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX3461","nome":"Realme 9 5G SE"},
        {"marca":"Xiaomi","modelo":"RMX3471","nome":"Realme 9 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3474","nome":"Realme 9 5G"},
        {"marca":"Xiaomi","modelo":"RMX3491","nome":"Realme 9i 5G"},
        {"marca":"Xiaomi","modelo":"RMX3501","nome":"Realme C31"},
        {"marca":"Xiaomi","modelo":"RMX3511","nome":"Realme C35"},
        {"marca":"Xiaomi","modelo":"RMX3511","nome":"Realme C55"},
        {"marca":"Xiaomi","modelo":"RMX3516","nome":"Realme Narzo 50A Prime"},
        {"marca":"Xiaomi","modelo":"RMX3561","nome":"Realme GT 2 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX3561","nome":"Realme GT 3"},
        {"marca":"Xiaomi","modelo":"RMX3562","nome":"Realme GT Neo 3 5G"},
        {"marca":"Xiaomi","modelo":"RMX3563","nome":"Realme GT 2"},
        {"marca":"Xiaomi","modelo":"RMX3571","nome":"Realme Narzo 50 5G"},
        {"marca":"Xiaomi","modelo":"RMX3571","nome":"Realme Narzo 50"},
        {"marca":"Xiaomi","modelo":"RMX3621","nome":"Realme Narzo 60"},
        {"marca":"Xiaomi","modelo":"RMX3623","nome":"Realme Narzo 60 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3661","nome":"Realme 10 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX3661","nome":"Realme 10"},
        {"marca":"Xiaomi","modelo":"RMX3663","nome":"Realme 10 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3686","nome":"Realme Narzo 50 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX3710","nome":"Realme Narzo 70 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX3710","nome":"Realme Narzo 70"},
        {"marca":"Xiaomi","modelo":"RMX3712","nome":"Realme Narzo 70 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3771","nome":"Realme 10 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX3771","nome":"Realme 11 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3773","nome":"Realme 11 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX3800","nome":"Realme GT 5"},
        {"marca":"Xiaomi","modelo":"RMX3800","nome":"Realme GT6"},
        {"marca":"Xiaomi","modelo":"RMX3801","nome":"Realme 11"},
        {"marca":"Xiaomi","modelo":"RMX3801","nome":"Realme Narzo 80"},
        {"marca":"Xiaomi","modelo":"RMX3803","nome":"Realme Narzo 80X"},
        {"marca":"Xiaomi","modelo":"RMX3810","nome":"Realme GT 6T"},
        {"marca":"Xiaomi","modelo":"RMX3820","nome":"Realme Note 60"},
        {"marca":"Xiaomi","modelo":"RMX3830","nome":"Realme GT7 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3840","nome":"Realme P2 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3888","nome":"Realme GT 5 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3891","nome":"Realme Narzo 90"},
        {"marca":"Xiaomi","modelo":"RMX3893","nome":"Realme Narzo 90x"},
        {"marca":"Xiaomi","modelo":"RMX3900","nome":"Realme GT 6"},
        {"marca":"Xiaomi","modelo":"RMX3901","nome":"Realme 12"},
        {"marca":"Xiaomi","modelo":"RMX3901","nome":"Realme C65"},
        {"marca":"Xiaomi","modelo":"RMX3911","nome":"Realme 13"},
        {"marca":"Xiaomi","modelo":"RMX3911","nome":"Realme C67"},
        {"marca":"Xiaomi","modelo":"RMX3921","nome":"Realme 13+"},
        {"marca":"Xiaomi","modelo":"RMX3931","nome":"Realme 12 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3931","nome":"Realme 14 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3933","nome":"Realme 12 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX3941","nome":"Realme 14+"},
        {"marca":"Xiaomi","modelo":"RMX3951","nome":"Realme GT 7"},
        {"marca":"Xiaomi","modelo":"RMX3961","nome":"Realme GT 8"},
        {"marca":"Xiaomi","modelo":"RMX3971","nome":"Realme GT 8 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3981","nome":"Realme 15 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX3991","nome":"Realme 13"},
        {"marca":"Xiaomi","modelo":"RMX3991","nome":"Realme 15 5G"},
        {"marca":"Xiaomi","modelo":"RMX3993","nome":"Realme 13 Pro"},
        {"marca":"Xiaomi","modelo":"RMX3995","nome":"Realme 13 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX4001","nome":"Realme 14"},
        {"marca":"Xiaomi","modelo":"RMX4001","nome":"Realme P4 Pro 5G"},
        {"marca":"Xiaomi","modelo":"RMX4003","nome":"Realme 14 Pro"},
        {"marca":"Xiaomi","modelo":"RMX4005","nome":"Realme 14 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX4011","nome":"Realme C85 4G"},
        {"marca":"Xiaomi","modelo":"RMX4011","nome":"Realme Note 70"},
        {"marca":"Xiaomi","modelo":"RMX4013","nome":"Realme C85 5G"},
        {"marca":"Xiaomi","modelo":"RMX4021","nome":"Realme C85 5G"},
        {"marca":"Xiaomi","modelo":"RMX4021","nome":"Realme P4x 5G"},
        {"marca":"Xiaomi","modelo":"RMX4101","nome":"Realme 15"},
        {"marca":"Xiaomi","modelo":"RMX4103","nome":"Realme 15 Pro"},
        {"marca":"Xiaomi","modelo":"RMX4105","nome":"Realme 15 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX4201","nome":"Realme 16"},
        {"marca":"Xiaomi","modelo":"RMX4203","nome":"Realme 16 Pro"},
        {"marca":"Xiaomi","modelo":"RMX4205","nome":"Realme 16 Pro+"},
        {"marca":"Xiaomi","modelo":"RMX4301","nome":"Realme GT 7"},
        {"marca":"Xiaomi","modelo":"RMX4303","nome":"Realme GT 7 Pro"},
        {"marca":"Samsung","modelo":"SM-A035F","nome":"Galaxy A03"},
        {"marca":"Samsung","modelo":"SM-A037F","nome":"Galaxy A03s"},
        {"marca":"Samsung","modelo":"SM-A045F","nome":"Galaxy A04"},
        {"marca":"Samsung","modelo":"SM-A047F","nome":"Galaxy A04s"},
        {"marca":"Samsung","modelo":"SM-A055F","nome":"Galaxy A05"},
        {"marca":"Samsung","modelo":"SM-A057F","nome":"Galaxy A05s"},
        {"marca":"Samsung","modelo":"SM-A066F","nome":"Galaxy A06"},
        {"marca":"Samsung","modelo":"SM-A075F","nome":"Galaxy A07"},
        {"marca":"Samsung","modelo":"SM-A125F","nome":"Galaxy A12"},
        {"marca":"Samsung","modelo":"SM-A135F","nome":"Galaxy A13"},
        {"marca":"Samsung","modelo":"SM-A145F","nome":"Galaxy A14"},
        {"marca":"Samsung","modelo":"SM-A155F","nome":"Galaxy A15"},
        {"marca":"Samsung","modelo":"SM-A165F","nome":"Galaxy A16"},
        {"marca":"Samsung","modelo":"SM-A175F","nome":"Galaxy A17"},
        {"marca":"Samsung","modelo":"SM-A225F","nome":"Galaxy A22"},
        {"marca":"Samsung","modelo":"SM-A226B","nome":"Galaxy A22 5G"},
        {"marca":"Samsung","modelo":"SM-A235F","nome":"Galaxy A23"},
        {"marca":"Samsung","modelo":"SM-A245F","nome":"Galaxy A24"},
        {"marca":"Samsung","modelo":"SM-A256B","nome":"Galaxy A25 5G"},
        {"marca":"Samsung","modelo":"SM-A266B","nome":"Galaxy A26 5G"},
        {"marca":"Samsung","modelo":"SM-A266B","nome":"Galaxy A26"},
        {"marca":"Samsung","modelo":"SM-A325F","nome":"Galaxy A32"},
        {"marca":"Samsung","modelo":"SM-A336B","nome":"Galaxy A33 5G"},
        {"marca":"Samsung","modelo":"SM-A346B","nome":"Galaxy A34 5G"},
        {"marca":"Samsung","modelo":"SM-A356B","nome":"Galaxy A35 5G"},
        {"marca":"Samsung","modelo":"SM-A366B","nome":"Galaxy A36 5G"},
        {"marca":"Samsung","modelo":"SM-A525F","nome":"Galaxy A52"},
        {"marca":"Samsung","modelo":"SM-A526B","nome":"Galaxy A52 5G"},
        {"marca":"Samsung","modelo":"SM-A528B","nome":"Galaxy A52s 5G"},
        {"marca":"Samsung","modelo":"SM-A536B","nome":"Galaxy A53 5G"},
        {"marca":"Samsung","modelo":"SM-A546B","nome":"Galaxy A54 5G"},
        {"marca":"Samsung","modelo":"SM-A556B","nome":"Galaxy A55 5G"},
        {"marca":"Samsung","modelo":"SM-A566B","nome":"Galaxy A56 5G"},
        {"marca":"Samsung","modelo":"SM-A725F","nome":"Galaxy A72"},
        {"marca":"Samsung","modelo":"SM-E156B","nome":"Galaxy F15 5G"},
        {"marca":"Samsung","modelo":"SM-F700F","nome":"Galaxy Z Flip"},
        {"marca":"Samsung","modelo":"SM-F711B","nome":"Galaxy Z Flip3"},
        {"marca":"Samsung","modelo":"SM-F721B","nome":"Galaxy Z Flip4"},
        {"marca":"Samsung","modelo":"SM-F731B","nome":"Galaxy Z Flip5"},
        {"marca":"Samsung","modelo":"SM-F741B","nome":"Galaxy Z Flip6"},
        {"marca":"Samsung","modelo":"SM-F766B","nome":"Galaxy Z Flip7"},
        {"marca":"Samsung","modelo":"SM-F916B","nome":"Galaxy Z Fold2 5G"},
        {"marca":"Samsung","modelo":"SM-F926B","nome":"Galaxy Z Fold3 5G"},
        {"marca":"Samsung","modelo":"SM-F936B","nome":"Galaxy Z Fold4"},
        {"marca":"Samsung","modelo":"SM-F946B","nome":"Galaxy Z Fold5"},
        {"marca":"Samsung","modelo":"SM-F956B","nome":"Galaxy Z Fold6"},
        {"marca":"Samsung","modelo":"SM-F966B","nome":"Galaxy Z Fold7"},
        {"marca":"Samsung","modelo":"SM-G780F","nome":"Galaxy S20 FE"},
        {"marca":"Samsung","modelo":"SM-G981B","nome":"Galaxy S20 5G"},
        {"marca":"Samsung","modelo":"SM-G986B","nome":"Galaxy S20+ 5G"},
        {"marca":"Samsung","modelo":"SM-G988B","nome":"Galaxy S20 Ultra 5G"},
        {"marca":"Samsung","modelo":"SM-G990B","nome":"Galaxy S21 FE 5G"},
        {"marca":"Samsung","modelo":"SM-G991B","nome":"Galaxy S21 5G"},
        {"marca":"Samsung","modelo":"SM-G996B","nome":"Galaxy S21+ 5G"},
        {"marca":"Samsung","modelo":"SM-G998B","nome":"Galaxy S21 Ultra 5G"},
        {"marca":"Samsung","modelo":"SM-M145F","nome":"Galaxy M14 4G"},
        {"marca":"Samsung","modelo":"SM-M156B","nome":"Galaxy M15 5G"},
        {"marca":"Samsung","modelo":"SM-M175B","nome":"Galaxy M17 5G"},
        {"marca":"Samsung","modelo":"SM-M356B","nome":"Galaxy M35 5G"},
        {"marca":"Samsung","modelo":"SM-M366B","nome":"Galaxy M36 5G"},
        {"marca":"Samsung","modelo":"SM-M556B","nome":"Galaxy M55 5G"},
        {"marca":"Samsung","modelo":"SM-M566B","nome":"Galaxy M56 5G"},
        {"marca":"Samsung","modelo":"SM-S711B","nome":"Galaxy S23 FE"},
        {"marca":"Samsung","modelo":"SM-S721B","nome":"Galaxy S24 FE"},
        {"marca":"Samsung","modelo":"SM-S731B","nome":"Galaxy S25 FE"},
        {"marca":"Samsung","modelo":"SM-S901B","nome":"Galaxy S22"},
        {"marca":"Samsung","modelo":"SM-S906B","nome":"Galaxy S22+"},
        {"marca":"Samsung","modelo":"SM-S908B","nome":"Galaxy S22 Ultra"},
        {"marca":"Samsung","modelo":"SM-S911B","nome":"Galaxy S23"},
        {"marca":"Samsung","modelo":"SM-S916B","nome":"Galaxy S23+"},
        {"marca":"Samsung","modelo":"SM-S918B","nome":"Galaxy S23 Ultra"},
        {"marca":"Samsung","modelo":"SM-S921B","nome":"Galaxy S24"},
        {"marca":"Samsung","modelo":"SM-S926B","nome":"Galaxy S24+"},
        {"marca":"Samsung","modelo":"SM-S928B","nome":"Galaxy S24 Ultra"},
        {"marca":"Samsung","modelo":"SM-S931B","nome":"Galaxy S25"},
        {"marca":"Samsung","modelo":"SM-S936B","nome":"Galaxy S25+"},
        {"marca":"Samsung","modelo":"SM-S937B","nome":"Galaxy S25 Edge"},
        {"marca":"Samsung","modelo":"SM-S938B","nome":"Galaxy S25 Ultra"},
        {"marca":"Vivo","modelo":"V2001","nome":"X50 Lite"},
        {"marca":"Vivo","modelo":"V2001","nome":"X50"},
        {"marca":"Vivo","modelo":"V2005","nome":"X50 Pro"},
        {"marca":"Vivo","modelo":"V2018","nome":"Y11s"},
        {"marca":"Vivo","modelo":"V2019","nome":"V19"},
        {"marca":"Vivo","modelo":"V2019","nome":"V20"},
        {"marca":"Vivo","modelo":"V2022","nome":"V20 SE"},
        {"marca":"Vivo","modelo":"V2022","nome":"V20"},
        {"marca":"Vivo","modelo":"V2023","nome":"V20 Pro"},
        {"marca":"Vivo","modelo":"V2024","nome":"V20 SE"},
        {"marca":"Vivo","modelo":"V2025","nome":"X50 Pro+"},
        {"marca":"Vivo","modelo":"V2027","nome":"Y20"},
        {"marca":"Vivo","modelo":"V2032","nome":"Y1s"},
        {"marca":"Vivo","modelo":"V2036","nome":"Y50"},
        {"marca":"Vivo","modelo":"V2036","nome":"Y51"},
        {"marca":"Vivo","modelo":"V2045","nome":"X60 Pro"},
        {"marca":"Vivo","modelo":"V2046","nome":"X60"},
        {"marca":"Vivo","modelo":"V2047","nome":"X60 Pro+"},
        {"marca":"Vivo","modelo":"V2050","nome":"V21"},
        {"marca":"Vivo","modelo":"V2051","nome":"V21e"},
        {"marca":"Vivo","modelo":"V2052","nome":"Y30"},
        {"marca":"Vivo","modelo":"V2056","nome":"X51 5G"},
        {"marca":"Vivo","modelo":"V2104","nome":"X70"},
        {"marca":"Vivo","modelo":"V2105","nome":"X70 Pro"},
        {"marca":"Vivo","modelo":"V2109","nome":"Y31"},
        {"marca":"Vivo","modelo":"V2110","nome":"Y21s"},
        {"marca":"Vivo","modelo":"V2111","nome":"Y21"},
        {"marca":"Vivo","modelo":"V2115","nome":"Y53s"},
        {"marca":"Vivo","modelo":"V2117","nome":"Y70"},
        {"marca":"Vivo","modelo":"V2117","nome":"Y72"},
        {"marca":"Vivo","modelo":"V2118","nome":"Y20T"},
        {"marca":"Vivo","modelo":"V2119","nome":"Y33s"},
        {"marca":"Vivo","modelo":"V2120","nome":"Y15s"},
        {"marca":"Vivo","modelo":"V2124","nome":"Y76 5G"},
        {"marca":"Vivo","modelo":"V2130","nome":"V23 5G"},
        {"marca":"Vivo","modelo":"V2130","nome":"V23"},
        {"marca":"Vivo","modelo":"V2131","nome":"V23e"},
        {"marca":"Vivo","modelo":"V2132","nome":"V23 Pro"},
        {"marca":"Vivo","modelo":"V2145","nome":"X70 Pro+"},
        {"marca":"Vivo","modelo":"V2183","nome":"X80"},
        {"marca":"Vivo","modelo":"V2185","nome":"X Note"},
        {"marca":"Vivo","modelo":"V2186","nome":"X80 Pro"},
        {"marca":"Vivo","modelo":"V2190","nome":"X Fold"},
        {"marca":"Vivo","modelo":"V2201","nome":"V25"},
        {"marca":"Vivo","modelo":"V2202","nome":"V25 Pro"},
        {"marca":"Vivo","modelo":"V2202","nome":"V25e"},
        {"marca":"Vivo","modelo":"V2203","nome":"Y01"},
        {"marca":"Vivo","modelo":"V2204","nome":"Y02"},
        {"marca":"Vivo","modelo":"V2205","nome":"Y16"},
        {"marca":"Vivo","modelo":"V2206","nome":"Y22s"},
        {"marca":"Vivo","modelo":"V2207","nome":"Y22"},
        {"marca":"Vivo","modelo":"V2208","nome":"Y35"},
        {"marca":"Vivo","modelo":"V2227","nome":"X90"},
        {"marca":"Vivo","modelo":"V2229","nome":"X Fold+"},
        {"marca":"Vivo","modelo":"V2241","nome":"X90 Pro+"},
        {"marca":"Vivo","modelo":"V2242","nome":"X90 Pro"},
        {"marca":"Vivo","modelo":"V2250","nome":"V27"},
        {"marca":"Vivo","modelo":"V2251","nome":"V27e"},
        {"marca":"Vivo","modelo":"V2252","nome":"V27 Pro"},
        {"marca":"Vivo","modelo":"V2301","nome":"V29 5G"},
        {"marca":"Vivo","modelo":"V2301","nome":"V29"},
        {"marca":"Vivo","modelo":"V2302","nome":"V29e"},
        {"marca":"Vivo","modelo":"V2303","nome":"V29 Pro"},
        {"marca":"Vivo","modelo":"V2303","nome":"Y27s"},
        {"marca":"Vivo","modelo":"V2305","nome":"Y36"},
        {"marca":"Vivo","modelo":"V2307","nome":"X Fold2"},
        {"marca":"Vivo","modelo":"V2307","nome":"Y100 5G"},
        {"marca":"Vivo","modelo":"V2307","nome":"Y100"},
        {"marca":"Vivo","modelo":"V2308","nome":"X Flip"},
        {"marca":"Vivo","modelo":"V2323","nome":"X100"},
        {"marca":"Vivo","modelo":"V2324","nome":"X100 Pro"},
        {"marca":"Vivo","modelo":"V2325","nome":"X100 Ultra"},
        {"marca":"Vivo","modelo":"V2401","nome":"V30"},
        {"marca":"Vivo","modelo":"V2401","nome":"V40"},
        {"marca":"Vivo","modelo":"V2401","nome":"Y200 5G"},
        {"marca":"Vivo","modelo":"V2401A","nome":"Y200 5G"},
        {"marca":"Vivo","modelo":"V2402","nome":"V30 Lite"},
        {"marca":"Vivo","modelo":"V2403","nome":"V30 Pro"},
        {"marca":"Vivo","modelo":"V2403","nome":"V40e"},
        {"marca":"Vivo","modelo":"V2403","nome":"Y28 5G"},
        {"marca":"Vivo","modelo":"V2405","nome":"Y18"},
        {"marca":"Vivo","modelo":"V2407","nome":"X Fold 3"},
        {"marca":"Vivo","modelo":"V2407","nome":"Y03"},
        {"marca":"Vivo","modelo":"V2409","nome":"Y29 5G"},
        {"marca":"Vivo","modelo":"V2409","nome":"Y300"},
        {"marca":"Vivo","modelo":"V2426","nome":"X200"},
        {"marca":"Vivo","modelo":"V2427","nome":"X200 Pro"},
        {"marca":"Vivo","modelo":"V2428","nome":"X200 FE"},
        {"marca":"Vivo","modelo":"V2429","nome":"X200 Ultra"},
        {"marca":"Vivo","modelo":"V2501","nome":"V40"},
        {"marca":"Vivo","modelo":"V2501","nome":"V50"},
        {"marca":"Vivo","modelo":"V2501","nome":"X200 Ultra"},
        {"marca":"Vivo","modelo":"V2501","nome":"Y500"},
        {"marca":"Vivo","modelo":"V2502","nome":"V40 Pro"},
        {"marca":"Vivo","modelo":"V2526","nome":"X300"},
        {"marca":"Vivo","modelo":"V2527","nome":"X300 Pro"},
        {"marca":"Vivo","modelo":"V2601","nome":"V50"},
        {"marca":"Vivo","modelo":"V2602","nome":"V50 Lite"},
        {"marca":"Vivo","modelo":"V2701","nome":"V60"},
        {"marca":"Vivo","modelo":"V2702","nome":"V60 Lite"},
        {"marca":"Xiaomi","modelo":"2106118C","nome":"Mi Mix 4"},
        {"marca":"Xiaomi","modelo":"2106118C","nome":"Xiaomi MIX 4"},
        {"marca":"Xiaomi","modelo":"2107113SG","nome":"Xiaomi 12"},
        {"marca":"Xiaomi","modelo":"21091116AG","nome":"Redmi Note 11"},
        {"marca":"Xiaomi","modelo":"2112123AG","nome":"Xiaomi 12X"},
        {"marca":"Xiaomi","modelo":"2201116SG","nome":"Redmi Note 11 Pro+"},
        {"marca":"Xiaomi","modelo":"2201116TG","nome":"Redmi Note 11 Pro 5G"},
        {"marca":"Xiaomi","modelo":"2201116TG","nome":"Redmi Note 11 Pro"},
        {"marca":"Xiaomi","modelo":"2201122G","nome":"Xiaomi 12 Pro"},
        {"marca":"Xiaomi","modelo":"2201123G","nome":"Xiaomi 12"},
        {"marca":"Xiaomi","modelo":"2201123G","nome":"Xiaomi 12T"},
        {"marca":"Xiaomi","modelo":"220333QAG","nome":"Redmi 12C"},
        {"marca":"Xiaomi","modelo":"22061218C","nome":"Xiaomi MIX Fold 2"},
        {"marca":"Xiaomi","modelo":"2206122SC","nome":"Xiaomi 12S Ultra"},
        {"marca":"Xiaomi","modelo":"2206123SC","nome":"Xiaomi 12S"},
        {"marca":"Xiaomi","modelo":"22081212PG","nome":"Xiaomi 12T Pro"},
        {"marca":"Xiaomi","modelo":"22081212UG","nome":"Xiaomi 12T Pro"},
        {"marca":"Xiaomi","modelo":"22081212UG","nome":"Xiaomi 12T"},
        {"marca":"Xiaomi","modelo":"22101316C","nome":"Redmi Note 12 Pro+"},
        {"marca":"Xiaomi","modelo":"22101316G","nome":"Redmi Note 12"},
        {"marca":"Xiaomi","modelo":"22101316UG","nome":"Redmi Note 12 Pro 5G"},
        {"marca":"Xiaomi","modelo":"22101316UG","nome":"Redmi Note 12 Pro"},
        {"marca":"Xiaomi","modelo":"22101316UG","nome":"Redmi Note 12 Pro+ 5G"},
        {"marca":"Xiaomi","modelo":"2210132C","nome":"Xiaomi 13 Lite"},
        {"marca":"Xiaomi","modelo":"2210132G","nome":"Xiaomi 13 Pro"},
        {"marca":"Xiaomi","modelo":"22111317PG","nome":"Redmi A1+"},
        {"marca":"Xiaomi","modelo":"2211133G","nome":"Xiaomi 13"},
        {"marca":"Xiaomi","modelo":"23021RAAEG","nome":"Redmi Note 12 Turbo"},
        {"marca":"Xiaomi","modelo":"2304FPN6DC","nome":"Xiaomi 13 Ultra"},
        {"marca":"Xiaomi","modelo":"23077RABDC","nome":"Redmi 13C"},
        {"marca":"Xiaomi","modelo":"23078PK5DC","nome":"Xiaomi 13T"},
        {"marca":"Xiaomi","modelo":"23078PND5G","nome":"Xiaomi 13T Pro"},
        {"marca":"Xiaomi","modelo":"2308CPXD0C","nome":"Xiaomi MIX Fold 3"},
        {"marca":"Xiaomi","modelo":"23090RA98G","nome":"Redmi Note 13 5G"},
        {"marca":"Xiaomi","modelo":"23090RA98G","nome":"Redmi Note 13"},
        {"marca":"Xiaomi","modelo":"23090RA98I","nome":"Redmi Note 13 Pro+ 5G"},
        {"marca":"Xiaomi","modelo":"23090RA98I","nome":"Redmi Note 13 Pro+"},
        {"marca":"Xiaomi","modelo":"23106RN0DA","nome":"Redmi 13C 5G"},
        {"marca":"Xiaomi","modelo":"2311DRK48C","nome":"Xiaomi 14 Ultra"},
        {"marca":"Xiaomi","modelo":"2311DRK48G","nome":"Xiaomi 14"},
        {"marca":"Xiaomi","modelo":"23127PN0CC","nome":"Xiaomi 14 Pro"},
        {"marca":"Xiaomi","modelo":"2312DRA50G","nome":"Redmi Note 13 Pro 5G"},
        {"marca":"Xiaomi","modelo":"2312DRA50G","nome":"Redmi Note 13 Pro"},
        {"marca":"Xiaomi","modelo":"24030PN60G","nome":"Xiaomi 14 Ultra"},
        {"marca":"Xiaomi","modelo":"2405CPX3DC","nome":"Xiaomi MIX Flip"},
        {"marca":"Xiaomi","modelo":"2407FPN8DG","nome":"Xiaomi 14T Pro"},
        {"marca":"Xiaomi","modelo":"2407FPN8EG","nome":"Xiaomi 14T"},
        {"marca":"Xiaomi","modelo":"2407FPN8EI","nome":"Xiaomi 14T Pro"},
        {"marca":"Xiaomi","modelo":"24090RA29G","nome":"Redmi Note 14"},
        {"marca":"Xiaomi","modelo":"24100RA8BC","nome":"Redmi Note 14 Pro"},
        {"marca":"Xiaomi","modelo":"24100RA8CC","nome":"Redmi Note 14 Pro+"},
        {"marca":"Xiaomi","modelo":"25010RA15G","nome":"Redmi Note 15"},
        {"marca":"Xiaomi","modelo":"25010RA16G","nome":"Redmi Note 15 Pro"},
        {"marca":"Xiaomi","modelo":"2501FPN6CG","nome":"Xiaomi 15 Pro"},
        {"marca":"Xiaomi","modelo":"2501FPN6DC","nome":"Xiaomi 15 Ultra"},
        {"marca":"Xiaomi","modelo":"2501FPN6DG","nome":"Xiaomi 15"},
        {"marca":"Xiaomi","modelo":"2501RNA15G","nome":"Redmi Note 15 5G"},
        {"marca":"Xiaomi","modelo":"2503FPN7DC","nome":"Xiaomi 15 Ultra"},
        {"marca":"Xiaomi","modelo":"2503MIX80G","nome":"Xiaomi Mix Flip"},
        {"marca":"Xiaomi","modelo":"2507FPN8DG","nome":"Xiaomi 15T Pro"},
        {"marca":"Xiaomi","modelo":"2507FPN8EG","nome":"Xiaomi 15T Pro"},
        {"marca":"Xiaomi","modelo":"2507FPN8EG","nome":"Xiaomi 15T"},
        {"marca":"Xiaomi","modelo":"M2001J1G","nome":"Mi 10 Pro"},
        {"marca":"Xiaomi","modelo":"M2001J2G","nome":"Mi 10"},
        {"marca":"Xiaomi","modelo":"M2003J15SC","nome":"Redmi Note 10"},
        {"marca":"Xiaomi","modelo":"M2007J1SC","nome":"Mi 10 Ultra"},
        {"marca":"Xiaomi","modelo":"M2007J3SC","nome":"Redmi K30 Ultra"},
        {"marca":"Xiaomi","modelo":"M2007J3SG","nome":"Redmi K30 Pro"},
        {"marca":"Xiaomi","modelo":"M2011K2C","nome":"Mi Mix Fold"},
        {"marca":"Xiaomi","modelo":"M2011K2G","nome":"Mi 11"},
        {"marca":"Xiaomi","modelo":"M2101K6G","nome":"Redmi Note 10 Pro"},
        {"marca":"Xiaomi","modelo":"M2101K6I","nome":"Redmi Note 10 Pro Max"},
        {"marca":"Xiaomi","modelo":"M2101K9AG","nome":"Mi 11 Lite"},
        {"marca":"Xiaomi","modelo":"M2101K9AG","nome":"Mi 11X"},
        {"marca":"Xiaomi","modelo":"M2101K9AI","nome":"Mi 11X Pro"},
        {"marca":"Xiaomi","modelo":"M2102K1AC","nome":"Mi 11 Ultra"},
        {"marca":"Xiaomi","modelo":"M2102K1G","nome":"Mi 11 Pro"},
        {"marca":"Xiaomi","modelo":"M2102K1G","nome":"Mi 11i"},
        {"marca":"Xiaomi","modelo":"M2104K10AC","nome":"Redmi K40"}
    ]
    dispositivo = random.choice(devicesModel)
    return dispositivo

def generate_android_version() -> str:
    """Gera versão do Android"""
    return str(random.randint(11, 15))


def generate_sign(length: int = 64) -> str:
    """Gera assinatura aleatória"""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/"
    return ''.join(random.choice(chars) for _ in range(length))


def random_hex(length: int) -> str:
    """Gera string hexadecimal aleatória"""
    return secrets.token_hex(length // 2)


def generate_random_key() -> str:
    """
    Gera chave aleatória para browserfingerid.
    Igual ao generateRandomKey() do PHP.
    Formato: "GEE3-01-" + 64 caracteres hexadecimais
    """
    prefix = "GEE3-01-"
    random_hex_str = secrets.token_hex(32)  # 64 caracteres hex
    return prefix + random_hex_str


def device_hash() -> str:
    """Gera hash de dispositivo"""
    return random_hex(34)


def codigo_pg() -> str:
    """Gera código PG para traceId"""
    letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    resultado = ''.join(random.choice(letras) for _ in range(6))
    return resultado + str(datetime.now().day)


# ==================== CRIPTOGRAFIA ====================

def pad_zero(data: bytes, block_size: int = 16) -> bytes:
    """Aplica padding com zeros (igual ao PHP - sempre adiciona padding)"""
    pad_len = block_size - (len(data) % block_size)
    # PHP SEMPRE adiciona padding, mesmo quando já alinhado (adiciona 16 zeros)
    # NÃO fazer: if pad_len == block_size: pad_len = 0
    return data + (b'\x00' * pad_len)


def unpad_zero(data: bytes) -> bytes:
    """Remove padding de zeros"""
    return data.rstrip(b'\x00')


def encrypt(json_data: str, key: str = DEFAULT_KEY, iv: str = DEFAULT_IV) -> str:
    """Criptografa dados com AES-128-CBC"""
    key_bytes = key.encode('utf-8')
    iv_bytes = iv.encode('utf-8')
    
    data = json_data.encode('utf-8')
    data = pad_zero(data)
    
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    encrypted = cipher.encrypt(data)
    
    return base64.b64encode(encrypted).decode('utf-8')


def decrypt(encrypted_data: str, key: str = DEFAULT_KEY, iv: str = DEFAULT_IV) -> str:
    """Descriptografa dados com AES-128-CBC"""
    key_bytes = key.encode('utf-8')
    iv_bytes = iv.encode('utf-8')
    
    encrypted = base64.b64decode(encrypted_data)
    
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    decrypted = cipher.decrypt(encrypted)
    
    # Remove caracteres de controle
    decrypted = bytes(b for b in decrypted if b >= 32 or b in (9, 10, 13))
    return decrypted.decode('utf-8', errors='ignore').strip()


def generate_key(token: str, username) -> str:
    """Gera chave de request baseada em token e username"""
    combined = str(token) + str(username)
    return hashlib.md5(combined.encode('utf-8')).hexdigest()[:16]


def encrypt_request(data: str, key: str) -> str:
    """Criptografa request com chave dinâmica"""
    key_bytes = key.encode('utf-8')
    # IV específico: pack("N*", 892613169, 909719605, 842216497, 842348344)
    iv_bytes = struct.pack(">IIII", 892613169, 909719605, 842216497, 842348344)
    
    # Remove caracteres de controle
    data_clean = ''.join(c for c in data if ord(c) >= 32 or c in '\t\n\r')
    data_bytes = data_clean.encode('utf-8')
    data_bytes = pad_zero(data_bytes)
    
    cipher_mode = "AES-256-CBC" if len(key_bytes) == 32 else AES.MODE_CBC
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    encrypted = cipher.encrypt(data_bytes)
    
    return base64.b64encode(encrypted).decode('utf-8')


def decrypt_request(b64_data: str, key: str) -> str:
    """Descriptografa request com chave dinâmica"""
    key_bytes = key.encode('utf-8')
    iv_bytes = struct.pack(">IIII", 892613169, 909719605, 842216497, 842348344)
    
    encrypted = base64.b64decode(b64_data)
    
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    decrypted = cipher.decrypt(encrypted)
    
    # Remove caracteres de controle
    decrypted = bytes(b for b in decrypted if b >= 32 or b in (9, 10, 13))
    return decrypted.decode('utf-8', errors='ignore').strip()


def decrypt_b64_aes128_ecb(cipher_b64: str, key_b64: str) -> str:
    """Descriptografa AES-128-ECB com chave em base64"""
    key = base64.b64decode(key_b64)
    cipher_data = base64.b64decode(cipher_b64)
    
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(cipher_data)
    
    # Remove PKCS7 padding
    if decrypted:
        pad_len = decrypted[-1]
        if 0 < pad_len <= 16:
            decrypted = decrypted[:-pad_len]
    
    return decrypted.decode('utf-8', errors='ignore')


# ==================== HELPERS HTTP ====================

def is_json(text: str) -> Optional[Dict]:
    """Verifica se é JSON válido e retorna dict"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def is_base64(s: str) -> bool:
    """Verifica se é base64 válido"""
    if not isinstance(s, str) or not s:
        return False
    if len(s) % 4 != 0:
        return False
    try:
        decoded = base64.b64decode(s, validate=True)
        return base64.b64encode(decoded).decode() == s
    except Exception:
        return False


def flash_browsers(model: Dict[str, str], speed: str) -> str:
    """
    Gera User-Agent do navegador.
    model: dict com marca/modelo/nome ou string (retrocompatível)
    """
    # Retrocompatibilidade: aceita string ou dict
    if isinstance(model, dict):
        marca = model.get("marca", "Samsung")
        modelo_str = model.get("modelo", "SM-A706F")
    else:
        marca = "Samsung"
        modelo_str = model
    
    a = random.randint(9, 15)
    c = random.randint(140, 145)
    sub = random.randint(1000, 9900)
    min_ver = random.randint(50, 199)
    il = random.randint(0, 9)
    osub = random.randint(1000, 9900)
    omin = random.randint(50, 199)
    omax = random.randint(80000, 99999)
    
    bt = f"Chrome/{c}.{il}.{sub}.{min_ver}"
    mobs = [
        f"{bt} Mobile Safari/537.3",
        f"{bt} Mobile Safari/537.36",
        f"{bt} Mobile Safari/537.36 OPX/2.{il}",
        f"{bt} Mobile Safari/537.36 OPR/{omin}.{il}.{osub}.{omax}",
        f"{bt} Mobile Safari/537.36 EdgA/{c}.0.0.0",
    ]
    mid = random.choice(mobs)
    return f"Mozilla/5.0 (Linux; Android {a}; {modelo_str}) AppleWebKit/537.36 (KHTML, like Gecko) {mid} speed/{speed}"


def flash_headers(
    login_id: str,
    host: str,
    device_id: str,
    device_model,  # Pode ser dict ou str
    url: str,
    sitecode: str,
    speed_version: str,
    app_version: str,
    android_version: str,
    mode: Optional[str] = "cipher",
    token: Optional[str] = None,
    captcha: Optional[str] = None,
    browser_finger_id: str = "",
    uid: str = "",
) -> Dict[str, str]:
    """Gera headers para requisições"""
    # Extrai modelo do dispositivo (aceita dict ou str)
    array = [
        "1-3", "1-4", "1-7", "1-9",
        "2-4", "2-7", "2-9",
        "3-9", "3-9",
        "4-2", "4-3", "4-4", "4-9",
        "5-1", "5-2", "5-3", "5-4", "5-5", "5-6", "5-7", "5-8", "5-9",
        "6-1", "6-2", "6-3", "6-4", "6-5", "6-6", "6-7", "6-8", "6-9",
        "7-1", "7-2", "7-3", "7-4", "7-5", "7-6", "7-7", "7-8", "7-9"
    ]
    sistema = "Android"
    platformtype = 2
    if isinstance(device_model, dict):
        marca = device_model.get("marca", "Samsung")
        modelo = device_model.get("modelo", "")
        nome = device_model.get("nome", "SM-G981B")
        dispositivo = f"{marca} {modelo}".strip()
        if marca == "Apple":
            dispositivo = nome.strip() 
            array = ['3-4', '3-5', '3-7', '4-7']
            sistema = "iOS"
            platformtype = 3
    else:
        marca = device_model.get("marca", "Samsung")
        modelo = device_model.get("modelo", device_model)
        dispositivo = device_model
    escolha_aleatoria = random.choice(array)

    headers = {
        'origin': url,
        'nonce': login_id,
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'pt',
        'appsystem': 'iOS' if marca == "Apple" else f'Android {android_version}',
        'appversion': f'v{app_version}' if not str(app_version).startswith('v') else app_version,
        'browserfingerid': browser_finger_id,  # generateRandomKey(), ativo restringe bonus
        'clienttimezone': '-3',
        'browsertype': f'{sistema} Browser v4.0',
        'content-type': 'text/plain',
        'currency': 'BRL',
        'device': device_id,
        'devicebrand': marca,
        'devicemodel': dispositivo,
        'devicetype': '3',
        'domain': host,
        'language': 'pt',
        'operatingsystem': sistema,
        'physicaldevicemodel': dispositivo,
        'platformtype': '5',
        'priority': 'u=1, i',
        'isspeedpackae': 'true',
        'iswgpackage': 'true',
        'sign': generate_sign(),
        'referer': url,
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': f'"{sistema}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'cross-site',
        'sec-ch-ua': f'"{sistema} WebView";v="150", "Chromium";v="150", "Not A(Brand";v="24"',
        'x-data-mode': mode,
        'sitecode': sitecode,
        'timestamp': int(datetime.now().timestamp()),
        'x-object-id': f'{{"uid":"{uid}","browserLanguage":"pt-BR","init":{{"device":"{device_id}","created":{int(time.time()*1000)},"version":{int(time.time()*1000) - 100000000}}}}}',
        'token': token or 'b2e3d672-9d88-47a7-81b4-9d7ffc62054f',
        'webauthndomain': host,
        'x-custom-referer': f'{url}/?fixed.gaid={device_id}',
        'x-requested-with': f'com.xlqcg.y{sitecode}.txwu',
        'x-device': escolha_aleatoria,
        'newJwt': '',
        'x-request-id': login_id,
        'x-version': app_version if app_version else '7.1.192'
    }
    
    #print(json.dumps(headers, indent=2, ensure_ascii=False))
    
    return headers


def set_headers(data: Dict[str, str]) -> Dict[str, str]:
    """Converte dict de headers para formato correto"""
    return data


# ==================== POSTDATA BUILDERS ====================

def postdata_register(
    url_domain: str,
    device_id: str,
    device_model,
    usuario: str,
    senha: str,
    cpf: Optional[str],
    celular: Optional[str],
    nome_completo: str,
    site_code: str,
    speed_version: str = "1.1.50",
    token: str = "",
    gee_token: str = "disabled",
    tipo: str = "json",
    inviter_id: Optional[str] = None,
    browser_finger_id: str = "",
) -> str:
    """Gera postdata para registro"""
    
    platformtype = 2
    if isinstance(device_model, dict):
        marca = device_model.get("marca", "Samsung")
        modelo = device_model.get("modelo", "SM-G981B")
        nome = device_model.get("nome", "SM-G981B")
        device_model_str = f"{marca} {modelo}".strip()        
        if marca == "Apple":
            platformtype = 3
            device_model_str = nome.strip()             
    else:
        device_model_str = device_model
    #generate_random_key()    
    data = {
        "domain": url_domain,
        "ip": gerar_ip_brasileiro(),
        "clientType": 2,
        "jpush_id": "",
        "loginId": device_id,
        "deviceHash": random_hex(68),
        "os_type": 2,
        "deviceOsType": 2,
        "deviceModel": device_model_str,
        "platformType": 1001,
        "operationId": 0,
        "browserFingerId": browser_finger_id, #generate_random_key(),
        "pkgId": 1,
        "mtpush_id": random_hex(10),
        "fromClub": 2,        
        "version": 8,
        "networkType":'CELLULAR-4G',
        "cpfCode": cpf or "",
        "mobilePhoneNumber": celular or "",
        "realName": nome_completo.upper(),
        "currency": "BRL",
        "registerLink": f"{url_domain}/?versionCode={speed_version}&isFirstInstall={device_id}&siteCode={site_code}&language=pt&source=speed_app&fixed.gaid={device_id}",
        "platformId": usuario,
        "passwd": senha,
        "geeToken": "disabled",
        "token": token or 'b2e3d672-9d88-47a7-81b4-9d7ffc62054f',
        "registerType": 0,
        "time": int(time.time()),
    }
    
    if str(site_code) == "11317":
        data["registerType"] = 2
        data["platformId"] = celular # O usuário é o número de celular
    

    if inviter_id:
        data["inviterId"] = int(inviter_id)
        data["registerLink"] = f"{url_domain}/home/register?id={inviter_id}"
        data["agent_type"] = 2
        data["agent_code"] = str(inviter_id)
    
    if gee_token != "disabled":
        try:
            gee_obj = json.loads(gee_token)
            data["geeToken"] = gee_obj.get("gee_token", gee_token)
        except:
            data["geeToken"] = gee_token
    #print(json.dumps(data, indent=2, ensure_ascii=False))
    json_str = json.dumps(data, separators=(',', ':'))
    return encrypt(json_str)


def postdata_validate(device_id: str, captcha_id: Optional[str] = None, referer: str = "/api/member/login") -> str:    
    data = {
        "account": device_id,
        "referer": referer,
        "lot_number": "000000cabf2f4f37bbb10c358b865c41",
        "gen_time": "1623828054",
        "pass_token": "2cc051e0c885a08dd046f1a789cffa72eddfc266f663cb2ded1ac08a5102bfe9",
        "captcha_output": "1X_RK3ag_IKlW15iHhSywQ==",
        "captcha_id": captcha_id.strip() if captcha_id else "62c528ead784206de7e6db17765b9ac0",
        "isOffline": True,
        "mode": 0,
        "time": int(time.time()),
    }
    
    return encrypt(json.dumps(data, separators=(',', ':')))


# ==================== MSGPACK DECODER ====================

class SimpleMsgPack:
    """Decoder simples de MessagePack"""
    
    def __init__(self, data: bytes):
        self.buffer = data
        self.pos = 0
        self.length = len(data)
    
    def unpack(self) -> Any:
        if self.pos >= self.length:
            return None
        
        byte = self.buffer[self.pos]
        self.pos += 1
        
        if byte == 0xc0:
            return None
        if byte == 0xc2:
            return False
        if byte == 0xc3:
            return True
        if byte <= 0x7f:
            return byte
        
        # fixmap
        if 0x80 <= byte <= 0x8f:
            n = byte - 0x80
            result = {}
            for _ in range(n):
                key = self.unpack()
                val = self.unpack()
                result[key] = val
            return result
        
        # fixarray
        if 0x90 <= byte <= 0x9f:
            n = byte - 0x90
            return [self.unpack() for _ in range(n)]
        
        # fixstr
        if 0xa0 <= byte <= 0xbf:
            n = byte - 0xa0
            return self._read_bytes(n)
        
        # str 8
        if byte == 0xd9:
            n = self.buffer[self.pos]
            self.pos += 1
            return self._read_bytes(n)
        
        return f"Unknown Type: {hex(byte)}"
    
    def _read_bytes(self, n: int) -> str:
        data = self.buffer[self.pos:self.pos + n]
        self.pos += n
        return data.decode('utf-8', errors='ignore')


def extract_value(html: str) -> Optional[str]:
    """Extrai valor base64 do HTML do jogo"""
    if not html:
        return None

    # Limpa espaços e quebras de linha
    html = html.strip()

    # Se for uma Data URI (Base64), decodifica primeiro
    if html.startswith("data:") and "base64," in html[:100]:
        try:
            b64_part = html.split("base64,", 1)[1]
            html = base64.b64decode(b64_part).decode("utf-8", errors="ignore")
        except Exception:
            pass

    # Tenta padrões de início conhecidos (do mais específico para o mais geral)
    start_patterns = [')}})("', '})("', ')("']
    end_pattern = '")}();'
    
    start_idx = -1
    pattern_used_len = 0
    
    for pattern in start_patterns:
        idx = html.find(pattern)
        if idx != -1:
            start_idx = idx
            pattern_used_len = len(pattern)
            break
    
    end_idx = html.find(end_pattern)
    
    # Se não encontrou o início ou o fim, ou se a ordem está errada
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return None
    
    start = start_idx + pattern_used_len
    return html[start:end_idx]


def extract_options_pg(data: Any) -> Dict[str, Any]:
    """Extrai opções do jogo PG"""
    
    def find_url(arr):
        if not isinstance(arr, (list, dict)):
            return None
        
        items = arr.values() if isinstance(arr, dict) else arr
        for v in items:
            if isinstance(v, (list, dict)):
                r = find_url(v)
                if r:
                    return r
            elif isinstance(v, str) and 'ot=' in v:
                return v
        return None
    
    url = find_url(data)
    
    if not url:
        return {'url': None, 'host': None, 'idGame': None, 'params': {}}
    
    parsed = urlparse(url)
    path_segments = [s for s in parsed.path.strip('/').split('/') if s]
    id_game = path_segments[0] if path_segments else None
    params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
    
    return {
        'url': url,
        'host': parsed.netloc,
        'idGame': id_game,
        'params': params,
    }


# ==================== JOGOS ====================

def buscar_jogo_pg(nome_ou_codigo: str) -> Optional[Dict]:
    """
    Busca jogo PG por nome ou código (g0).
    
    Args:
        nome_ou_codigo: Nome do jogo (ex: "fortune ox") ou código (ex: "2000018")
    
    Returns:
        Dict com dados do jogo ou None se não encontrado
    """   
    try:
        with open("jogospg.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    
    if not isinstance(data, dict) or 'data' not in data:
        return None
    
    lista = data.get('data', {}).get('g1', [])
    
    # Verifica se é código numérico
    busca_por_codigo = nome_ou_codigo.isdigit()
    
    for jogo in lista:
        if not all(k in jogo for k in ('g0', 'g1', 'g10')):
            continue
        
        # Busca por código (g0)
        if busca_por_codigo:
            if str(jogo['g0']) == nome_ou_codigo:
                return {
                    "name": jogo['g1'],
                    "os_type": 2,
                    "gameid": jogo['g0'],
                    "platfromid": jogo['g10'],
                    "exitUrl": "",
                    "time": int(time.time()),
                }
        # Busca por nome (g1)
        else:
            if nome_ou_codigo.lower() in jogo['g1'].lower():
                return {
                    "name": jogo['g1'],
                    "os_type": 2,
                    "gameid": jogo['g0'],
                    "platfromid": jogo['g10'],
                    "exitUrl": "",
                    "time": int(time.time()),
                }
    
    return None


def buscar_jogo_pg_aleatorio(excluir: List[str] = None) -> Optional[Dict]:
    """
    Seleciona 1 jogo PG aleatório.
    
    Args:
        excluir: Lista de nomes de jogos para excluir (opcional)
        
    Returns:
        Dict com dados do jogo ou None se não encontrar
    """    
    try:
        with open("jogospg.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    
    if not isinstance(data, dict) or 'data' not in data:
        return None
    
    lista = data.get('data', {}).get('g1', [])
    
    # Filtra jogos válidos
    jogos_validos = []
    excluir_lower = [e.lower() for e in (excluir or [])]
    
    for jogo in lista:
        if not all(k in jogo for k in ('g0', 'g1', 'g10')):
            continue
        
        nome_jogo = jogo['g1'].lower()
        
        # Exclui jogos da lista de exclusão
        if any(exc in nome_jogo for exc in excluir_lower):
            continue
        
        jogos_validos.append(jogo)
    
    if not jogos_validos:
        return None
    
    # Seleciona 1 jogo aleatório
    jogo = random.choice(jogos_validos)
    
    return {
        "name": jogo['g1'],
        "os_type": 2,
        "gameid": jogo['g0'],
        "platfromid": jogo['g10'],
        "exitUrl": "",
        "time": int(time.time()),
    }


def calcular_jogada(
    saldo_atual: float,
    id_play: int,
    info_game: Dict,
    atk: str,
    btt: int = 1,
    bet_maxima: float = 10,
    bonus: bool = False,
) -> Dict:
    """Calcula melhor jogada baseada no saldo"""
    dt = info_game.get('dt', {})
    cs_list = dt.get('cs', [])
    ml_list = dt.get('ml', [])
    mxl = dt.get('mxl', 1)
    wk = dt.get('ls', {}).get('si', {}).get('wk', dt.get('si', {}).get('wk', '0:0:1:0:0:0:0:0:0'))
    
    melhor_jogada = None
    melhor_valor = 0
    
    for cs in cs_list:
        for ml in ml_list:
            valor_aposta = cs * ml * mxl
            if valor_aposta <= saldo_atual and valor_aposta <= bet_maxima and valor_aposta > melhor_valor:
                melhor_valor = valor_aposta
                melhor_jogada = {
                    'id': id_play,
                    'cs': cs,
                    'ml': ml,
                    'wk': wk,
                    'btt': btt,
                    'atk': atk,
                    'pf': 1,
                }
    
    if melhor_jogada is None:
        melhor_jogada = {
            'id': id_play,
            'cs': cs_list[0] if cs_list else 0.4,
            'ml': ml_list[0] if ml_list else 1,
            'wk': wk,
            'btt': btt,
            'atk': atk,
            'pf': 1,
        }
    
    if bonus:
        melhor_jogada['fb'] = 2
    
    return melhor_jogada
