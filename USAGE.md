# FlashAPIPy - Guia de Uso

## O que é

Um **bot de automação** para plataformas de jogos/apostas online. Ele cria contas automaticamente, coleta bônus de cadastro e joga slots para tentar multiplicar o saldo.

## Fluxo de Execução (5 etapas)

1. **Obter Config da Plataforma** - Detecta APIs disponíveis e seleciona a mais rápida
2. **Registro** - Cria conta nova com dados brasileiros fictícios (CPF, nome, telefone, email)
3. **Configurar Conta** - Define senha de saque, vincula chave PIX, configura perfil
4. **Coletar Bônus** - Resgata bônus de boas-vindas/missões da plataforma
5. **Jogar** - Joga automaticamente slots (Fortune Ox/Tiger/Rabbit, Gem Saviour) tentando multiplicar o saldo até atingir uma meta

## Funcionalidades Principais

| Recurso | Descrição |
|---------|-----------|
| **Multi-plataforma** | Suporta várias plataformas de jogos |
| **Paralelismo** | Executa múltiplos bots simultaneamente |
| **Proxy** | Usa proxies para evitar bloqueios |
| **Criptografia** | Comunicação criptografada com as APIs |
| **Gem Trava** | Estratégia especial para "travar" bônus no jogo Gem Saviour |
| **Banco de dados** | Salva todas as contas criadas em SQLite |
| **Contas salvas** | Exporta contas que atingem a meta para arquivos `.txt` |

---

## Opções de Execução

### Opções Principais

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--url` | `-u` | - | URL da plataforma (ex: `https://look.app587.com`) |
| `--platform` | `-P` | - | Nome da plataforma (ex: `587bet`, `707bet`) |
| `--count` | `-c` | 10 | Quantidade de contas a criar |
| `--parallel` | `-n` | 5 | Quantidade de bots rodando em paralelo |

### Opções de Jogo

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--game` | `-g` | Fortune Ox | Nome do jogo |
| `--bet-max` | - | 100.0 | Aposta máxima em R$ |
| `--target` | - | 1000.0 | Saldo alvo para parar (meta) |
| `--pix-type` | - | cpf | Tipo de chave PIX (`cpf`, `telefone`, `email`) |

### Opções de Rede

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--proxy` | - | - | Proxy no formato `usuario:senha@host:porta` |
| `--gee-max-uses` | - | 100 | Máximo de usos por geeToken |
| `--no-gee-token` | - | false | Desativa uso de geeToken |
| `--no-save-db` | - | false | Desativa salvamento no banco SQLite |

### Opções de Saída

| Opção | Atalho | Padrão | Descrição |
|-------|--------|--------|-----------|
| `--output` | `-o` | resultados.json | Arquivo de saída JSON |
| `--verbose` | `-v` | false | Modo debug (mostra logs detalhados) |
| `--quiet` | `-q` | false | Modo silencioso (só resultado final) |

### Utilitários

| Opção | Atalho | Descrição |
|-------|--------|-----------|
| `--list-platforms` | `-l` | Lista todas as plataformas disponíveis |
| `--search-platform` | `-s` | Busca plataformas por nome parcial |

---

## Exemplos de Uso

### Básico

```bash
# Criar 10 contas (padrão) na plataforma 587bet
python main.py --platform 587bet

# Criar 50 contas
python main.py --platform 587bet --count 50

# Usando URL direta ao invés do nome da plataforma
python main.py --url https://look.app587.com --count 20
```

### Controle de Paralelismo

```bash
# 100 contas com 20 bots simultâneos (mais rápido)
python main.py -P 587bet -c 100 -n 20

# 50 contas com 3 bots (mais lento, menos detectável)
python main.py -P 587bet -c 50 -n 3
```

### Configurações de Jogo

```bash
# Meta de R$ 500 ao invés de R$ 1000
python main.py -P 587bet -c 100 --target 500

# Aposta máxima de R$ 50
python main.py -P 587bet -c 100 --bet-max 50

# Jogo específico
python main.py -P 587bet -c 100 --game "Fortune Tiger"
```

### Chave PIX

```bash
# Usar telefone como chave PIX
python main.py -P 587bet -c 100 --pix-type telefone

# Usar email como chave PIX
python main.py -P 587bet -c 100 --pix-type email
```

### Com Proxy

```bash
# Proxy com autenticação
python main.py -P 587bet -c 100 --proxy usuario:senha@proxy.com:8080

# Proxy simples
python main.py -P 587bet -c 100 --proxy 192.168.1.1:8080
```

### GeeToken

```bash
# Desativar geeToken
python main.py -P 587bet -c 100 --no-gee-token

# Limitar usos do geeToken
python main.py -P 587bet -c 100 --gee-max-uses 50
```

### Modos de Saída

```bash
# Modo verbose (debug completo)
python main.py -P 587bet -c 10 -v

# Modo silencioso (só resumo final)
python main.py -P 587bet -c 100 -q

# Salvar resultado em arquivo específico
python main.py -P 587bet -c 100 -o meus_resultados.json
```

### Descobrir Plataformas

```bash
# Listar todas as plataformas
python main.py --list-platforms

# Buscar plataformas com "bet" no nome
python main.py --search-platform bet

# Buscar plataformas com "777"
python main.py -s 777
```

### Exemplos Combinados (Produção)

```bash
# Setup completo para produção
python main.py \
  --platform 587bet \
  --count 500 \
  --parallel 15 \
  --target 800 \
  --bet-max 80 \
  --pix-type cpf \
  --proxy user:pass@proxy:8080 \
  --output resultado_587bet.json \
  --quiet

# Teste rápido com debug
python main.py -P 587bet -c 1 -v
```

---

## Objetivo Final

Criar contas em massa, coletar bônus gratuitos, e jogar até transformar o bônus em um saldo maior (meta configurável). As contas bem-sucedidas são salvas na pasta `contas/` para uso posterior.
