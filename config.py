# -*- coding: utf-8 -*-
"""
Configurações globais do Bot
"""
from dataclasses import dataclass, field
from typing import Optional
import os

from database import get_db


# Modo debug - quando False, só mostra log final de cada conta
# Usar runtime_config["DEBUG_MODE"] para acesso mutável
runtime_config = {
    "DEBUG_MODE": False
}


@dataclass
class ProxyConfig:
    
    usar_proxy: bool = True  # True = Proxy Ativa, False = Proxy Desativada
    
    """Configurações de proxy"""
    host: str = "thehub.proxy-cheap.com"
    port: int = 8080
    username: str = "kTKmtIqFTLQzAmL" #,ph,vn,ca,mx,gb,tr
    password: str = "1EiKsImtP52udYd_country-BR"

    port = 824 if port == 823 else port
    def url(self) -> str:
        if not self.usar_proxy:
            return ""
        return f"{self.username}:{self.password}@{self.host}:{self.port}"
    
    @property
    def full_url(self) -> str:
        if not self.usar_proxy:
            return ""
        return f"socks5://{self.url()}"
    
    def verificar_proxy(self, timeout: int = 10) -> tuple:
        """
        Verifica se o proxy está online e funcionando.
        
        Returns:
            tuple: (sucesso: bool, ip: str, mensagem: str)
        """
        import requests
        
        if not self.usar_proxy:
            return (True, "SEM PROXY", "Proxy desativado")
            
        proxy_url = f"socks5://{self.username}:{self.password}@{self.host}:{self.port}"
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        
        try:
            # Testa com api.ipify.org
            response = requests.get(
                "https://api.ipify.org?format=json",
                proxies=proxies,
                timeout=timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                ip = data.get("ip", "???")
                return (True, ip, f"Proxy OK - IP: {ip}")
            else:
                return (False, "", f"Erro HTTP {response.status_code}")
                
        except requests.exceptions.ProxyError as e:
            return (False, "", f"Erro de Proxy: Credenciais invalidas ou proxy offline")
        except requests.exceptions.ConnectTimeout:
            return (False, "", f"Timeout: Proxy nao respondeu em {timeout}s")
        except requests.exceptions.ConnectionError:
            return (False, "", f"Erro de conexao: Proxy inacessivel")
        except Exception as e:
            return (False, "", f"Erro: {str(e)}")


@dataclass
class GeeTokenConfig:
    """Configurações do sistema de cache do geeToken"""
    enabled: bool = True  # Se False, usa "disabled" como token
    individual: bool = False  # Se True, busca token individual para cada conta via API
    max_uses: int = 100  # Máximo de contas por token
    valid_ttl_seconds: int = 3600  # 1 hora para token válido
    disabled_ttl_seconds: int = 7200  # 2 horas para token "disabled"
    fetch_timeout_seconds: int = 30  # Timeout para buscar novo token
    plataforma_padrao: str = ""
    coleta_por_plataforma_ativa: bool = True
    estoque_por_plataforma: int = 100
    intervalo_sem_run_segundos: int = 30
    tokens_por_coleta: int = 10
    intervalo_com_run_segundos: int = 10

GeetokenConfig = GeeTokenConfig



@dataclass
class GameConfig:
    """Configurações do jogo"""
    nome_jogo: str = "aleatorio"
    subir_banca: float = 1000
    bet_maxima: float = 100.0
    tipo_saque: str = "cpf"  # cpf, telefone, email
    dominio_email: str = "@uorak.com"
    bonus: bool = False  # Ganho certo
    loop_infinito: bool = False  # Se True, joga até zerar saldo (sem limite de ciclos)
    gem_trava: bool = False  # Se True, ativa o modo Gem Trava (tenta travar bônus no Gem Saviour)
    double_fortune_trava: bool = False # Se True, ativa o modo Double Fortune Trava
    fortune_trava_bet: float = 0.0 # Bet alvo para o Double Fortune Trava
    ganesha_gold_trava: bool = False # Se True, ativa o modo Ganesha Gold Trava
    ganesha_trava_bet: float = 0.0 # Bet alvo para o Ganesha Gold Trava
    hood_trava: bool = False  # Se True, ativa o modo Hood vs Wolf Trava (saldo 250-1000)
    emperor_favour_trava: bool = False # Se True, ativa o modo Emperor's Favour Trava
    emperor_trava_bet: float = 0.0 # Bet alvo para o Emperor's Favour Trava
    sunshine_trava: bool = False # Se True, ativa o modo Sunshine Trava
    sunshine_trava_bet: float = 0.0 # Bet alvo para o Sunshine Trava
    sunshine_aleatoria: bool = False # Se True, escolhe bet aleatória para Sunshine Coast
    sunshine_min_bet: float = 15.0 # Bet mínima para o modo aleatório Sunshine Coast
    journey_to_the_wealth_trava: bool = False # Se True, ativa o modo Journey to the Wealth Trava
    journey_trava_bet: float = 0.0 # Bet alvo para o Journey to the Wealth Trava
    bet_aleatoria: bool = False # Se True, escolhe bet aleatória acima de 12 nos jogos suportados
    triple_tigers_recuperacao: bool = False # Se True, tenta recuperação no Triple Tigers com saldo < 0.30
    firestrike_trava: bool = False # Se True, ativa o modo Fire Strike 2 Trava
    firestrike_trava_bet: float = 0.0 # Bet alvo para o Fire Strike 2 Trava
    fire88_trava: bool = False # Se True, ativa o modo Fire 88 All-Win (subir saldo)
    fire88_trava_bet: float = 0.0 # Bet alvo para o Fire 88 (0.0 = All-Win sem limite)
    spirit_trava: bool = False # Se True, ativa o modo Spirit of Adventure Trava
    spirit_trava_bet: float = 0.0 # Bet alvo para o Spirit of Adventure Trava
    voodoo_trava: bool = False # Se True, ativa o modo Voodoo Magic Trava
    voodoo_trava_bet: float = 0.0 # Bet alvo para o Voodoo Magic Trava
    muertos_trava: bool = False # Se True, ativa o modo Muertos Multiplier Megaways Trava
    muertos_trava_bet: float = 0.0 # Bet alvo para o Muertos Multiplier Megaways Trava
    pure_platinum_trava: bool = False # Se True, ativa o modo Pure Platinum Trava (Microgaming)
    pure_platinum_trava_bet: float = 0.0 # Bet alvo para o Pure Platinum Trava
    diamond_trava: bool = False # Se True, ativa o modo Diamond Cluster Luck Trava
    diamond_trava_bet: float = 0.0 # Bet alvo para o Diamond Cluster Luck Trava
    charm_trava: bool = False # Se True, ativa o modo Lucky Charm Trava
    charm_trava_bet: float = 0.0 # Bet alvo para o Lucky Charm Trava
    treasure_house_trava: bool = False # Se True, ativa o modo Treasure House Trava
    treasure_house_trava_bet: float = 0.0 # Bet alvo para o Treasure House Trava
    usar_cpf_arquivo: bool = False
    cpf_arquivo: str = "cpfs.txt"


def get_cpf_from_file(sitecode: str, filename: str = "cpfs.txt") -> Optional[str]:
    path = filename if os.path.isabs(filename) else os.path.join(os.getcwd(), filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return None
    with get_db(sitecode) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS used_cpfs (
                cpf TEXT PRIMARY KEY,
                reserved_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for raw in lines:
            digits = "".join(ch for ch in raw if ch.isdigit())
            if len(digits) != 11:
                continue
            cursor = conn.execute("""
                INSERT INTO used_cpfs(cpf)
                SELECT ?
                WHERE NOT EXISTS (SELECT 1 FROM used_cpfs WHERE cpf = ?)
                  AND NOT EXISTS (SELECT 1 FROM todascontas WHERE cpf = ?)
            """, (digits, digits, digits))
            conn.commit()
            if cursor.rowcount == 1:
                return digits
    return None


@dataclass
class SMSConfig:
    """Configurações de verificação SMS"""
    verificar_sms: bool = False
    provedora: str = "bower"  # bower, sms24h, sms-activate
    ddi: str = "55"
    max_price: str = "0.12"
    provedor_id: int = 3018
    country: int = 73  # Brasil
    api_bower: str = ""
    api_sms24h: str = "a6aa67c175dcea1e01a61fa605dad633"
    api_sms_activate: str = ""


@dataclass
class BotConfig:
    """Configuração principal do bot"""
    url: str = "https://d1kwyxjzq9j4uo.cloudfront.net"
    platform_name: str = ""  # Nome da plataforma (ex: 707bet)
    parallel_count: int = 10  # Número de contas em paralelo
    total_accounts: int = 100  # Total de contas a criar
    save_to_db: bool = True  # Salvar contas no banco SQLite
    
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    gee_token: GeeTokenConfig = field(default_factory=GeeTokenConfig)
    game: GameConfig = field(default_factory=GameConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    
    # Telegram
    telegram_code: str = ""
    active_id: int = 0
    
    # Turbo mode (pula delays artificiais)
    turbo_mode: bool = False
    
    # Timeouts
    request_timeout: int = 15
    
    # Diretórios
    cookies_dir: str = "./cookies"
    cache_dir: str = "./cache"
    
    # API externa
    #flash_api_url: str = "https://flashbotcpa.com/online_api.php"
    #flash_api_key: str = "FlashBOT0fa1eb4D4EE0fa3405a0c1A1DF9ca6217a517a534C969Cf272524a5e4a14FdaE"


# Endpoints que usam proxy
PROXY_ENDPOINTS = [
    "/hall/api/member/register",
    "/hall/api/member/geetest/validate/v4"
]

# Chaves de criptografia padrão
DEFAULT_KEY = "46233ef7d5e864a0"
DEFAULT_IV = "5421698523412578"
CONFIG_KEY_B64 = "dGhhbmtzLHBpZzRjbG91ZA=="

# Listas de nomes para geração
FIRST_NAMES_MALE = [
    "João","Pedro","Lucas","Gabriel","Matheus","Gustavo","Felipe","Rafael","Bruno","Thiago",
    "Caio","Diego","André","Rodrigo","Leonardo","Eduardo","Marcelo","Victor","Vitor","Henrique",
    "Daniel","Igor","Luiz","Ermenson","Kauan","Samuel","Murilo","Enzo","Benício","Renato",
    "Ricardo","Fábio","Alexandre","Tiago","Jorge","Paulo","Sérgio","Fernando","Robson",
    "Márcio","Allan","Patrick","Wesley","Jonathan","Maurício","César","Leandro","William","Cristiano",
    "Otávio","Heitor","Davi","Emanuel","Everton","Nilson","Luciano","Alan","Estevão","Mateus",
    "Aaron","Danilo","Júlio","Antônio","Carlos","Hugo","Elias","Isaque","Josué","Adriel",
    "Ruan","Rian","Bryan","Kevin","Cristian","Nicolas","Ryan","Ian","Erick","Vinícius",
    "Rômulo","Eliseu","Anderson","Adriano","Rodolfo","Valmir","Cleyton","Wagner","Gilberto","Aquiles",
    "Ícaro","Tales","Natan","Saulo","Breno","Caetano","Augusto","Dionísio","Tarcísio","Benjamim",
    "Félix","Sandro","Douglas","Fabricio","Cairo","Luan","Yago","Yuri","Jonas","Miguel",
    "Gael","Anthony","Thierry","Otto","Jadiel","Ezequiel","Tomás","Cauã","Álvaro","Theodoro",
    "Raul","Pietro","Alessandro","Álex","Jeferson","Dirceu","Edivaldo","Darlan","Régis","Ademir",
    "Arnaldo","Cássio","Dener","Edgar","Naldo","Nélio","Osvaldo","Renan","Sávio","Túlio",
    "Valter","Wallace","Geraldo","Ivan","Jairo","Ladislau","Mário","Orlando","Plínio","Quirino",
    "Ronaldo","Santino","Tancredo","Ubirajara","Valdemar","Zaqueu","Almir","Roberto","Érico","Ismael",
    "Joel","Natanael","Abner","Abel","Eliel","Salomão","Gideão","Levi","Joaquim","Pascoal",
    "Serafim","Valentim","Manoel","Nicolau","Bernardo","Cícero","Eurico","Jadson","Muricy","Severino",
    "Zacarias","Agenor","Alfredo","Benedito","Dorival","Gerson","Hélio","Isidoro","Ari","Caedmon",
    "Tibério","Apolo","Damião","Gonçalo","Ivo","Lázaro","Omar","Rufus","Amauri","Bernardino",
    "Celso","Dário","Edson","Flávio","Heraldo","Jerônimo","Kleber","Lindomar","Maurilo","Nivaldo",
    "Olavo","Péricles","Quintino","Eron","Fabrício","Giraldo","Hernani","Idelmar","Janderson","Kainan",
    "Lairton","Marcos","Nilberto","Oziel","Pablo","Ueslei","Vanderson","Willian","Ycaro","Zander",
    "Adryel","Bartolomeu","Calixto","Dimitri","Ettore","Fioravante","Gaspar","Horácio","Isandro","Jairo",
    "Kaique","Lorenzo","Noah","Oton","Ravi","Tito","Ulrico","Vicente","Weslley","Yann",
    "Zyan","Abimael","Aldair","Allisson","Amadeu","Aristides","Balthazar","Braz","Celestino","Ciro",
    "Dávio","Diogo","Edvaldo","Emanoel","Evandro","Ezra","Fabrizio","Feliciano","Filipe","Francesco",
    "Galdino","Giovani","Giovanni","Guido","Heverton","Ido","Inácio","Isaías","Jandir","Juvêncio",
    "Kauê","Kawan","Kleiton","Ladson","Lamartine","Lennon","Lionel","Lucivaldo","Maciel","Marcondes",
    "Mauro","Nael","Nataniel","Norberto","Ozeias","Paolo","Réginaldo","Rivaldo","Romário","Santhiago",
    "Sebastião","Soares","Tássio","Teylor","Uelinton","Vandré","Washington","Ygor","Yohan","Ziraldo",
    "Adonias","Afonso","Agostinho","Alcides","Aleph","Aluísio","Américo","Ângelo","Anselmo",
    "Argemiro","Ariovaldo","Atílio","Bonifácio","Bóris","Braulio","Camilo","Cassiano","Cézar","Cláudio",
    "Cleiton","Cornélio","Dácio","Délcio","Dercy","Dorgival","Ebert","Edemar",
    "Edgard","Egnaldo","Eliezer","Elisandro","Elpídio","Elton","Erickson","Etevaldo","Eurípedes","Fausto",
    "Federico","Feijó","Ferdinando","Floriano","Fortunato","Gaetano","Gaspare","Gian","Gilmar","Giordano",
    "Gomes","Gonçalo","Gregório"
]

FIRST_NAMES_FEMALE = [
    "Maria","Ana","Julia","Beatriz","Larissa","Carla","Patrícia","Fernanda","Camila","Aline",
    "Carolina","Bruna","Letícia","Mariana","Luana","Sabrina","Tatiane","Bianca","Raquel","Renata",
    "Gabriela","Natália","Isabela","Isadora","Amanda","Priscila","Eduarda","Talita","Jéssica","Débora",
    "Verônica","Helena","Lívia","Clarice","Yasmin","Vitória","Catarina","Nicole","Michele","Simone",
    "Andreia","Roberta","Elaine","Adriana","Danielle","Kelly","Tainá","Camille","Brenda","Tatiana",
    "Evelyn","Giovana","Alessandra","Rafaela","Melissa","Carine","Jaqueline","Mônica","Rayssa","Ingrid",
    "Valentina","Lara","Eloá","Alana","Manuela","Rebeca","Lorena","Esther","Agatha","Sophia",
    "Alice","Flávia","Cecília","Pérola","Érica","Fátima","Iara","Clara","Cíntia",
    "Joana","Mirela","Heloísa","Laís","Paloma","Fabiana","Sheila","Marisa","Rafaella","Samara",
    "Tássia","Luiza","Isis","Rosana","Nádia","Mara","Ivana","Solange","Roseane","Denise",
    "Vera","Lidiane","Giselle","Mirian","Janayna","Elisangela","Iracema","Tereza","Emanuelle","Karina",
    "Viviane","Angélica","Aparecida","Emilly","Stella","Malu","Antônia","Aurora","Brigite","Cássia",
    "Dalila","Doralice","Efigênia","Filipa","Geovana","Heloise","Ilana","Jandira","Karla","Ludmila",
    "Magda","Noemi","Odete","Penélope","Quitéria","Rosângela","Selena","Taliana","Úrsula","Valesca",
    "Waleska","Zuleica","Neide","Norma","Sueli","Josefina","Ivete","Glória","Marilda","Zenaide",
    "Bernadete","Genoveva","Magnólia","Clotilde","Déia","Jussara","Joelma","Darlene","Kaline","Maitê",
    "Nayara","Thatiana","Rúbia","Lavínia","Carol","Bárbara","Yara","Ariele","Fabíola",
    "Lorraine","Ariane","Rhanielly","Nicolly","Pollyanna","Maressa","Hanny","Stefany","Isabella",
    "Ester","Brendha","Hellen","Mirelle","Naiara","Marcela","Larisse",
    "Jhenifer","Karoline","Paula","Nathalia","Sarah","Evelin","Iris",
    "Geisa","Daiane","Daniela","Marli","Celina","Célia","Zoraide",
    "Eliana","Zulema","Marjorie","Hortência","Joice","Liviane","Dayane","Janice","Elisa",
    "Camelia","Lina","Talita","Heloá","Maísa","Kauane","Mariane","Antonella",
    "Ellen","Mabelle","Ramona","Rafaely","Tessália","Anita","Clarissa","Charlene","Marília",
    "Fernandha","Tainara","Elizabete","Honorina","Graziela","Mireli","Eloise","Joanice","Nayane",
    "Kamily","Mila","Daniella","Fabiane","Luzia","Sebastiana","Carmina","Ivonete",
    "Lucimara","Joelina","Karol","Bia","Jaine","Marcelina","Ivonara","Ilse","Rosileide","Florinda",
    "Graciela","Jucélia","Maurina","Neuzilene","Rosilda","Janiara","Ely","Maira","Guadalupe","Eliete",
    "Alzira","Gildete","Felícia","Petra","Marceli","Elvira","Sônia","Zilda","Neuma","Almerinda",
    "Adelaide","Aracy","Belmira","Celeste","Jolanda","Mercedes","Flora","Mafalda","Ornella","Serena",
    "Vittoria","Elena","Ariadna","Naiade","Flaviane","Janaina","Nayhara",
    "Brigida","Solana","Mel","Georgia","Ayla","Amélia","Louise","Naira",
    "Talissa","Katarina","Nadja","Olga","Hanna","Cristiane","Janaína","Carlinha","Ketlin","Brunna",
    "Emanuella","Anelise","Clarinha","Juliene","Josiane","Miria",
    "Selminha","Vívian","Joyce","Ludmylla","Violeta","Rute","Ariadne","Neblina",
    "Luara","Mayumi","Monalisa","Angeline","Eloisa","Aurélia","Leandra",
    "Nilza","Nina","Lícia","Giovannna","Michelli","Cristal","Natasha","Lorrane",
    "Jamily","Emily","Késia","Bela","Rosália","Alaide",
    "Marina","Valquíria","Betina","Kimberly","Darina","Claudia","Marileide","Nara",
    "Agnes","Hérica","Lorraine","Viviene","Maia","Loris","Jovita","Elenice",
    "Fernandha","Camila","Erenice","Suelen","Keliane","Jorgina","Yanna","Alessia","Grasielle",
    "Malú","Carina","Anastácia","Lunna","Alanna","Eldina",
    "Jussanam","Ivonise","Odilene","Elen"
]

MIDDLE_NAMES_BR = [
    "Alves","Souza","Silva","Santos","Oliveira","Pereira","Lima","Costa","Cardoso","Teixeira",
    "Martins","Barbosa","Mendes","Rocha","Araújo","Correia","Nascimento","Moreira","Sales","Xavier",
    "Farias","Monteiro","Ferreira","Vieira","Ramos","Batista","Campos","Azevedo","Duarte","Tavares",
    "Figueiredo","Pinto","Ribeiro","Cavalcante","Moraes","Dias","Fonseca","Carvalho","Moura","Freitas",
    "Neves","Viana","Queiroz","Siqueira","Gonçalves","Magalhães","Sampaio","Nogueira","Barros","Pacheco",
    "Peixoto","Prado","Lopes","Soares","Borges","Rezende","Garcia","Lacerda","Assis","Brandão"
]

LAST_NAMES_BR = [
    "Silva","Santos","Souza","Oliveira","Pereira","Lima","Carvalho","Almeida","Ferreira","Rodrigues",
    "Gomes","Martins","Barbosa","Rocha","Araújo","Ribeiro","Alves","Cavalcante","Moura","Melo",
    "Costa","Cardoso","Teixeira","Mendes","Vieira","Dias","Monteiro","Freitas","Ramos","Campos",
    "Nascimento","Figueiredo","Batista","Tavares","Pinto","Moraes","Farias","Fonseca","Moreira","Duarte",
    "Azevedo","Lopes","Siqueira","Prado","Garcia","Sampaio","Borges","Nogueira","Neves",
    "Rezende","Queiroz","Lacerda","Assis","Magalhães","Peixoto","Pacheco","Xavier","Brandão","Gasparotto",
    "Rodrigues Junior","da Silva","da Costa","da Rocha","da Mata","da Cunha","da Luz",
    "dos Santos","dos Reis","do Nascimento","do Carmo","de Oliveira","de Souza","de Almeida","de Campos",
    "Moretti","Ferraz","Falcão","Guimarães","Macedo","Menezes","Pinheiro","Valente","Cunha","Filho",
    "Machado","Barcellos","Amaral","Rangel","Sodré","Corrêa","Mota","Naves","Pires","Porto", "Neto", "Junior"
]

# DDDs do Brasil
DDDS_BRASIL = [
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46,
    47, 48, 49,
    51, 53, 54, 55,
    61, 62, 64, 63, 65, 66, 67,
    68, 69,
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
]

# Faixas de IP brasileiras
FAIXAS_IP_BR = [
    "177.0.0.0/8",
    "179.0.0.0/8",
    "187.0.0.0/8",
    "189.0.0.0/8",
    "191.0.0.0/8",
    "200.128.0.0/10",
    "201.0.0.0/8",
]
