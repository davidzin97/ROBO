# -*- coding: utf-8 -*-
"""
Configurações de plataformas
Baseado em urlBase.js
"""
from dataclasses import dataclass
from typing import Optional, List


"""
Ponto de entrada principal - Execução paralela com CLI

py main.py --platform 15win --count 100000 --parallel 200 --no-gee-token --pix-type email --target 1000

py main.py --platform 707bet --count 10 --parallel 5
py main.py -P 707bet -c 100 -n 20 --game "Fortune Tiger"
py main.py --url https://exemplo.com --count 5 --verbose
py main.py --list-platforms

TESTE DE PLATAFORMA
py main.py --count 100 --parallel 10 --pix-type email --target 24 --platform 587bet

RODAR PRA FRITAR
--count = QUANTIDADE DE CONTAS A CRIAR
--parallel = QUANTIDADE DE BOTS PARALELOS 
--target = META DE BONUS NA CONTA
--pix-type email
--platform 587bet
--no-save-db = MODO TURBO
py main.py --count 100000 --parallel 200 --pix-type email --target 50 --platform ejcassino

// SEM GEE TOKEN
py main.py --count 10 --parallel 10 --pix-type telefone --target 200 --platform s7bet --no-save-db

// COM GEE TOKEN INDIVIDUAL PRA CADA CONTA
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 500 --platform 707bet --no-save-db --gee-token-individual
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 500 --platform 391bet --no-save-db --gee-token-individual
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 500 --platform 148bet --no-save-db --gee-token-individual

// INVITE ID
py main.py --count 10 --parallel 10 --pix-type telefone --target 200 --platform s7bet --no-save-db --gee-token-individual --invite-id 797227092

// GEM TRAVA 
py main.py --count 10 --parallel 10 --pix-type telefone --target 200 --platform s7bet --no-save-db --gee-token-individual --gem-trava

// HOOD TRAVA
py main.py --count 10 --parallel 10 --pix-type telefone --target 200 --platform s7bet --no-save-db --gee-token-individual --hood-trava

// RODAR SEM PROXY
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 500 --platform 148bet --no-save-db --gee-token-individual --no-proxy


py main.py --count 1 --parallel 1 --pix-type telefone --target 1000 --platform 922bet --gee-token-individual --no-save-db
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 707bet --gee-token-individual --no-save-db --hood-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 587bet --gee-token-individual --no-save-db --hood-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 5099bet --no-save-db --gee-token-individual --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform xixbet --no-save-db --gee-token-individual --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 587bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 587bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 300 --pix-type telefone --target 1500 --platform 2abet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 148bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 587bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 55bb --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 333bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 166win --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 898bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 0066bet --gee-token-individual --no-save-db --gem-trava
py main.py --count 1000000 --parallel 200 --pix-type telefone --target 1500 --platform 67bet --gee-token-individual --no-save-db --gem-trava


"""

@dataclass
class PlatformRecord:
    """Registro de configuração de uma plataforma"""
    name: str
    site: str
    gee_token: bool


# Lista de plataformas disponíveis
#
# py main.py --platform 587bet --count 100 --parallel 50 --no-gee-token
#
PLATFORM_RECORDS: List[PlatformRecord] = [
    
    PlatformRecord("963bet", "https://d3dx3hzook8b8l.cloudfront.net", gee_token=False),
    PlatformRecord("678rio", "https://678riok.vip", gee_token=False),
    PlatformRecord("920bet", "https://d11dm6tasib5wm.cloudfront.net", gee_token=False),
    PlatformRecord("5099bet", "https://look.5099app.com", gee_token=False),
    PlatformRecord("xixbet", "https://look.appxixbet.com", gee_token=False),
    PlatformRecord("789br", "https://789br.bet", gee_token=False),
    PlatformRecord("caderno777", "https://caderno777.bet", gee_token=False),
    PlatformRecord("win222", "https://www.win222t.com", gee_token=False),
    PlatformRecord("tese777", "https://tese777.com", gee_token=False),
    PlatformRecord("kab777", "https://www.kab777.win", gee_token=False),	
    PlatformRecord("pvbet", "https://d2ouav7k8ncvtr.cloudfront.net", gee_token=False),
    PlatformRecord("15win", "https://15win.win", gee_token=False),    
    PlatformRecord("0066bet", "https://0066bet.com", gee_token=False),
    PlatformRecord("00real11", "https://00real11.com", gee_token=False),
    PlatformRecord("013bet", "https://013bet.win", gee_token=False),
    PlatformRecord("017bet", "https://017bet.win", gee_token=False),
    PlatformRecord("017brl", "https://017brl222.com", gee_token=False),
    PlatformRecord("017win", "https://017win.win", gee_token=False),
    PlatformRecord("018win", "https://018win.vip", gee_token=False),
    PlatformRecord("027win", "https://027win.win", gee_token=False),
    PlatformRecord("037win", "https://037win.win", gee_token=False),
    PlatformRecord("044br", "https://044br.me", gee_token=False),
    PlatformRecord("047win", "https://047win.win", gee_token=False),
    PlatformRecord("048win", "https://048win.vip", gee_token=False),
    PlatformRecord("077win", "https://077win.win", gee_token=False),
    PlatformRecord("083win", "https://083win.vip", gee_token=False),
    PlatformRecord("085win", "https://085win.vip", gee_token=False),
    PlatformRecord("088br", "https://088br.org", gee_token=False),
    PlatformRecord("095bet", "https://095bet.vip", gee_token=False),
    PlatformRecord("104pg", "https://www.104pg.com", gee_token=False),
    PlatformRecord("10pmbet", "https://a50pmbet.com", gee_token=False),
    PlatformRecord("114bet", "https://114bet.com", gee_token=False),
    PlatformRecord("1157bet", "https://1157bet.vip", gee_token=False),
    PlatformRecord("57bet", "https://57bet555.win/", gee_token=False),    
    PlatformRecord("117brl", "https://b117brl.com", gee_token=False),
    PlatformRecord("119bet", "https://d17ee4z712yehh.cloudfront.net", gee_token=False),
    PlatformRecord("1213bet", "https://1213bet.vip", gee_token=False),
    PlatformRecord("121bet", "https://121bet.win", gee_token=False),
    PlatformRecord("1239bet", "https://1239bet.com", gee_token=False),
    PlatformRecord("123game", "https://123.game", gee_token=False),
    PlatformRecord("125bet", "https://125bet.win", gee_token=False),
    PlatformRecord("1279bet", "https://1279bet.vip", gee_token=False),
    PlatformRecord("1316bet", "https://1316bet.vip", gee_token=False),
    PlatformRecord("131bet", "https://131bet.cc", gee_token=False),
    PlatformRecord("133br", "https://133br.com", gee_token=False),
    PlatformRecord("136bet", "https://136bet.vip", gee_token=False),
    PlatformRecord("136win", "https://136win.vip", gee_token=False),
    PlatformRecord("1400win", "https://1400win.vip", gee_token=False),
    PlatformRecord("144bet", "https://144bet.com", gee_token=False),
    PlatformRecord("1477bet", "https://1477bet.vip", gee_token=False),
    PlatformRecord("148bet", "https://look.148betapp.com", gee_token=False),
    PlatformRecord("1555bet", "https://d1kwyxjzq9j4uo.cloudfront.net", gee_token=False),    
    PlatformRecord("161bet", "https://x6cy401537-e5aefdczbrgfhmgx.a01.azurefd.net", gee_token=False),
    PlatformRecord("1633bet", "https://1633bet.vip", gee_token=False),
    PlatformRecord("166bet", "https://d1hrntjl3nif0z.cloudfront.net", gee_token=False),
    PlatformRecord("166mouse", "https://166mouse.com", gee_token=False),
    PlatformRecord("166win", "https://look.app166.net", gee_token=False),
    PlatformRecord("1685bet", "https://1685bet.vip", gee_token=False),
    PlatformRecord("16bet", "https://16bet.co", gee_token=False),
    PlatformRecord("1715win", "https://1715win.vip", gee_token=False),
    PlatformRecord("1766win", "https://1766win.vip", gee_token=False),
    PlatformRecord("1795bet", "https://1795bet.vip", gee_token=False),
    PlatformRecord("1865bet", "https://1865bet.cc", gee_token=False),
    PlatformRecord("186bet", "https://cook.186api.com", gee_token=False),
    PlatformRecord("187bet", "https://187bet.com", gee_token=False),
    PlatformRecord("1900bet", "https://1900bet.win", gee_token=False),
    PlatformRecord("1900win", "https://1900win.win", gee_token=False),
    PlatformRecord("1911bet", "https://1911bet.win", gee_token=False),
    PlatformRecord("1916bet", "https://1916bet.vip", gee_token=False),
    PlatformRecord("1919bet", "https://1919bet.win", gee_token=False),
    PlatformRecord("1929bet", "https://1929bet.win", gee_token=False),
    PlatformRecord("1963bet", "https://1963bet.vip", gee_token=False),
    PlatformRecord("1977bet", "https://1977bet.vip", gee_token=False),
    PlatformRecord("1977win", "https://1977win.win", gee_token=False),
    PlatformRecord("1988win", "https://1988win.win", gee_token=False),
    PlatformRecord("1992bet", "https://1992bet.com", gee_token=False),
    PlatformRecord("1993bet", "https://1993bet.vip", gee_token=False),
    PlatformRecord("1999bet", "https://1999bet.vip", gee_token=False),
    PlatformRecord("199win", "https://d3cf6o3akvfdzv.cloudfront.net", gee_token=False),
    PlatformRecord("19bet", "https://19bet.com", gee_token=False),
    PlatformRecord("2007win", "https://2007win.vip", gee_token=False),
    PlatformRecord("2017win", "https://2017win.vip", gee_token=False),
    PlatformRecord("2025tiger", "https://www.2025tiger.net", gee_token=False),
    PlatformRecord("2026bet", "https://2026bet.cc", gee_token=False),
    PlatformRecord("204win", "https://204win.win", gee_token=False),
    PlatformRecord("2068bet", "https://2068bet.vip", gee_token=False),
    PlatformRecord("207bet", "https://207bet.com", gee_token=False),
    PlatformRecord("208win", "https://208win.win", gee_token=False),
    PlatformRecord("2090win", "https://2090win.vip", gee_token=False),
    PlatformRecord("20okbet", "https://20okbet.top", gee_token=False),
    PlatformRecord("2128bet", "https://2128bet.vip", gee_token=False),
    PlatformRecord("2155bet", "https://2155bet.vip", gee_token=False),
    PlatformRecord("2210bet", "https://2210bet.vip", gee_token=False),
    PlatformRecord("223vv", "https://www.223vv.com", gee_token=False),
    PlatformRecord("2288bet", "https://d2c8jbkcrsepbw.cloudfront.net", gee_token=False),
    PlatformRecord("22a", "https://22-a.com", gee_token=False),
    PlatformRecord("2325bet", "https://2325bet.vip", gee_token=False),
    PlatformRecord("2335bet", "https://2335bet.vip", gee_token=False),
    PlatformRecord("234bet", "https://234bet.win", gee_token=False),
    PlatformRecord("234tiger", "https://234tiger66.com", gee_token=False),
    PlatformRecord("236bet", "https://236bet.com", gee_token=False),
    PlatformRecord("23bet", "https://23bet.com", gee_token=False),
    PlatformRecord("2466bet", "https://2466bet.com", gee_token=False),
    PlatformRecord("2511bet", "https://2511bet.vip", gee_token=False),
    PlatformRecord("256bet", "https://256bet.com", gee_token=False),
    PlatformRecord("257bet", "https://257bet.com", gee_token=False),
    PlatformRecord("2587win", "https://2587win.vip", gee_token=False),
    PlatformRecord("2652bet", "https://2652bet.vip", gee_token=False),
    PlatformRecord("266br", "https://266br.site", gee_token=False),
    PlatformRecord("2899bet", "https://2899bet.vip", gee_token=False),
    PlatformRecord("289win", "https://289win.win", gee_token=False),
    PlatformRecord("2abet", "https://gcj2036674-ewbpcdbkaxbecvcb.a01.azurefd.net", gee_token=False),
    PlatformRecord("448bet", "https://d1lejfukzie898.cloudfront.net", gee_token=False),
    PlatformRecord("30win", "https://30win.win", gee_token=False),
    PlatformRecord("312bet", "https://312bet.win", gee_token=False),
    PlatformRecord("318bet", "https://d13fq0f2bz9kvi.cloudfront.net", gee_token=False),
    PlatformRecord("817bet", "https://d1m53f51vex1dl.cloudfront.net", gee_token=False),
    PlatformRecord("333bet", "https://d2sx5299z63d6w.cloudfront.net", gee_token=False),
    PlatformRecord("3355bet", "https://3355bet.com", gee_token=False),
    PlatformRecord("3355win", "https://3355win.com", gee_token=False),
    PlatformRecord("348bet", "https://348bet.com", gee_token=False),
    PlatformRecord("355bet", "https://355bet.cc", gee_token=False),
    PlatformRecord("3588win", "https://3588win.vip", gee_token=False),
    PlatformRecord("361", "https://361.bet", gee_token=False),
    PlatformRecord("362bet", "https://362bet.win", gee_token=False),
    PlatformRecord("3766bet", "https://3766bet.win", gee_token=False),
    PlatformRecord("377bet", "https://377bet.win", gee_token=False),
    PlatformRecord("3788bet", "https://3788bet1.com", gee_token=False),
    PlatformRecord("389win", "https://389win.bet", gee_token=False),    
    PlatformRecord("38brl", "https://38brl.vip", gee_token=False),
    PlatformRecord("3900bet", "https://3900bet.vip", gee_token=False),
    PlatformRecord("391bet", "https://look.app391bet.com/", gee_token=False),
    PlatformRecord("393bet", "https://www.393bet15.com", gee_token=False),
    PlatformRecord("40win", "https://40win.vip", gee_token=False),
    PlatformRecord("4131bet", "https://4131bet2.com", gee_token=False),
    PlatformRecord("418bet", "https://dyhonhg6qujoi.cloudfront.net", gee_token=False),
    PlatformRecord("425luck", "https://b166luck.com", gee_token=False),
    PlatformRecord("42bet", "https://42bet.com", gee_token=False),
    PlatformRecord("4444win", "https://4444win.win", gee_token=False),
    PlatformRecord("444win", "https://444win.com", gee_token=False),
    PlatformRecord("4492bet", "https://4492bet.vip", gee_token=False),
    PlatformRecord("44u", "https://44uwin.com", gee_token=False),
    PlatformRecord("456bra", "https://www.456bra222.com", gee_token=False),
    PlatformRecord("45br", "https://955br.com", gee_token=False),
    PlatformRecord("468bet", "https://468bet.com", gee_token=False),
    PlatformRecord("474bet", "https://474bet.com", gee_token=False),
    PlatformRecord("484win", "https://484win.win", gee_token=False),
    PlatformRecord("488bet", "https://dsvm29sfmdakq.cloudfront.net", gee_token=False),
    PlatformRecord("4987bet", "https://4987bet.vip", gee_token=False),
    PlatformRecord("505bet", "https://505bet.cc", gee_token=False),
    PlatformRecord("508win", "https://508win.win", gee_token=False),
    PlatformRecord("510bet", "https://510bet.cc", gee_token=False),
    PlatformRecord("510bet1", "https://510bet1.com", gee_token=False),
    PlatformRecord("515bet", "https://515bet.win", gee_token=False),
    PlatformRecord("5177bet", "https://5177bet.vip", gee_token=False),
    PlatformRecord("517bet", "https://517bet.win", gee_token=False),
    PlatformRecord("518bet", "https://d314a5gqmh0956.cloudfront.net", gee_token=False),
    PlatformRecord("521bet", "https://521bet.com", gee_token=False),
    PlatformRecord("522bet", "https://522bet.vip", gee_token=False),
    PlatformRecord("5299bet", "https://5299bet.vip", gee_token=False),
    PlatformRecord("52bet", "https://211.43.149.106:5002", gee_token=False),
    PlatformRecord("535bet", "https://535bet.com", gee_token=False),
    PlatformRecord("538bet", "https://538bet.com", gee_token=False),
    PlatformRecord("54bet", "https://03t9359041-eaazcah8eyfcgdda.a01.azurefd.net", gee_token=False),
    PlatformRecord("5500bet", "https://5500bet.com", gee_token=False),
    PlatformRecord("5500win", "https://5500win.com", gee_token=False),
    PlatformRecord("551bet", "https://551bet.com", gee_token=False),
    PlatformRecord("552bet", "https://522bet.com", gee_token=False),
    PlatformRecord("5564bet", "https://5564bet.cc", gee_token=False),
    PlatformRecord("556brl", "https://556brl.vip", gee_token=False),
    PlatformRecord("5573bet", "https://5573bet.vip", gee_token=False),
    PlatformRecord("5584bet", "https://5584bet.vip", gee_token=False),
    PlatformRecord("5588bet", "https://dnmenduwapiim.cloudfront.net", gee_token=False),
    PlatformRecord("55bb", "https://dqoqeb38ntdqc.cloudfront.net", gee_token=False),
    PlatformRecord("5677win", "https://5677win.com", gee_token=False),
    PlatformRecord("567win", "https://www.567win777.com", gee_token=False),
    PlatformRecord("571bet", "https://look.571betapp.com", gee_token=False),
    PlatformRecord("5757win", "https://5757win.com", gee_token=False),
    PlatformRecord("575bet", "https://575bet.org", gee_token=False),
    PlatformRecord("577bet", "https://577bet.win", gee_token=False),
    PlatformRecord("578bet", "https://www.578bet.me", gee_token=False),
    PlatformRecord("57zbet", "https://57zbet.top", gee_token=False),
    PlatformRecord("580", "http://580.com", gee_token=False),
    PlatformRecord("5811bet", "https://5811bet.vip", gee_token=False),
    PlatformRecord("585bet", "https://585bet.net", gee_token=False),
    PlatformRecord("587bet", "https://look.app587.com", gee_token=False),
    PlatformRecord("5884bet", "https://5884bet.vip", gee_token=False),
    PlatformRecord("58bet", "https://58bet.com", gee_token=False),
    PlatformRecord("591bet", "https://591bet.vip", gee_token=False),
    PlatformRecord("592bet", "https://592bet.win", gee_token=False),
    PlatformRecord("59bet", "https://59bet.com", gee_token=False),
    PlatformRecord("5hbet", "https://5hbet.tv", gee_token=False),
    PlatformRecord("5mpg", "https://c5mpg.com", gee_token=False),
    PlatformRecord("6096bet", "https://6096bet.com", gee_token=False),
    PlatformRecord("615bet", "https://615bet.win", gee_token=False),
    PlatformRecord("616bet", "https://foot616.616apps.com", gee_token=False),
    PlatformRecord("6177bet", "https://6177bet.vip", gee_token=False),
    PlatformRecord("622bet", "https://622bet.com", gee_token=False),
    PlatformRecord("6299bet", "https://6299bet.vip", gee_token=False),
    PlatformRecord("645bet", "https://645bet.win", gee_token=False),
    PlatformRecord("6553bet", "https://6553bet.vip", gee_token=False),
    PlatformRecord("655bet", "https://655bet.win", gee_token=False),
    PlatformRecord("658bet", "https://658bet.com", gee_token=False),
    PlatformRecord("661bet", "https://661bet.vip", gee_token=False),
    PlatformRecord("662bet", "https://662bet.com", gee_token=False),
    PlatformRecord("6655bet", "https://6655bet.vip", gee_token=False),
    PlatformRecord("919win", "https://919win.fun", gee_token=False),
    PlatformRecord("667bet", "https://667bet.com", gee_token=False),
    PlatformRecord("668bet", "https://668bet.com", gee_token=False),
    PlatformRecord("6691bet", "https://6691bet.vip", gee_token=False),
    PlatformRecord("669bet", "https://669bet.com", gee_token=False),
    PlatformRecord("66gbet", "https://66gbet.com", gee_token=False),
    PlatformRecord("6722bet", "https://6722bet.vip", gee_token=False),
    PlatformRecord("6788win", "https://6788win.com", gee_token=False),
    PlatformRecord("6790bet", "https://6790bet.vip", gee_token=False),
    PlatformRecord("67bet", "https://67bet.com", gee_token=False),
    PlatformRecord("686bet", "https://d2xpe82e4pgktw.cloudfront.net", gee_token=False),
    PlatformRecord("687bet", "https://cook.687api.com", gee_token=False),
    PlatformRecord("6883bet", "https://6883bet.vip", gee_token=False),
    PlatformRecord("688bet", "https://688bet.com", gee_token=False),
    PlatformRecord("6969bet", "https://6969bet.vip", gee_token=False),
    PlatformRecord("6989bet", "https://6989bet.com", gee_token=False),
    PlatformRecord("6993bet", "https://6993bet.vip", gee_token=False),
    PlatformRecord("6993bet456", "https://6993bet456.com", gee_token=False),
    PlatformRecord("699win", "https://699win.com", gee_token=False),
    PlatformRecord("700bra", "https://a700bra.com", gee_token=False),
    PlatformRecord("707bet", "https://thq6947265-h8a4h3eugpfdh0b2.a01.azurefd.net", gee_token=False),
    PlatformRecord("70bet", "https://70bet.com", gee_token=False),
    PlatformRecord("70pmbet", "https://www.a70pmbet.com", gee_token=False),
    PlatformRecord("715bet", "https://58b5870786-dta2bfa6bkgufqhn.a01.azurefd.net", gee_token=False),
    PlatformRecord("7188win", "https://7188win.com", gee_token=False),
    PlatformRecord("718br", "https://718br.com", gee_token=False),
    PlatformRecord("7199bet", "https://7199bet.vip", gee_token=False),
    PlatformRecord("719bet", "https://719bet.com", gee_token=False),
    PlatformRecord("7311bet", "https://7311bet.vip", gee_token=False),
    PlatformRecord("735bet", "https://735bet.com", gee_token=False),
    PlatformRecord("73bet", "https://73bet.cc", gee_token=False),
    PlatformRecord("74bet", "https://74bet.com", gee_token=False),
    PlatformRecord("755bet", "https://dbld3o781v83e.cloudfront.net", gee_token=False),
    PlatformRecord("7566win", "https://7566win.vip", gee_token=False),
    PlatformRecord("7577win", "https://7577win.vip", gee_token=False),
    PlatformRecord("7588win", "https://7588win.vip", gee_token=False),
    PlatformRecord("765bet", "https://765bet.win", gee_token=False),
    PlatformRecord("7667win", "https://7667win.vip", gee_token=False),
    PlatformRecord("766bet", "https://766bet.win", gee_token=False),
    PlatformRecord("7700bet", "https://7700bet.com", gee_token=False),
    PlatformRecord("7700win", "https://7700win.com", gee_token=False),
    PlatformRecord("770win", "https://770win.vip", gee_token=False),
    PlatformRecord("771win", "https://771win.win", gee_token=False),
    PlatformRecord("7728bet", "https://7728bet.cc", gee_token=False),
    PlatformRecord("772win", "https://772win.win", gee_token=False),
    PlatformRecord("7731bet", "https://7731bet.vip", gee_token=False),
    PlatformRecord("7739bet", "https://www.7739bet3.com", gee_token=False),
    PlatformRecord("773win", "https://773win.win", gee_token=False),
    PlatformRecord("7753bet", "https://7753bet.com", gee_token=False),
    PlatformRecord("775bet", "https://775bet51.com", gee_token=False),
    PlatformRecord("7766win", "https://7766win.vip", gee_token=False),
    PlatformRecord("777gold", "https://777gold.com", gee_token=False),
    PlatformRecord("777hop", "https://777hop.com", gee_token=False),
    PlatformRecord("777pig", "https://777pig.com", gee_token=False),
    PlatformRecord("777rio", "https://777rio.com", gee_token=False),
    PlatformRecord("777ua", "https://777ua.com", gee_token=False),
    PlatformRecord("777win", "https://777win.com", gee_token=False),
    PlatformRecord("7788bet", "https://7788bet.com", gee_token=False),
    PlatformRecord("779win", "https://779win.win", gee_token=False),
    PlatformRecord("77bra", "https://77bra.com", gee_token=False),
    PlatformRecord("787br", "https://787br.com", gee_token=False),
    PlatformRecord("79bet", "https://79bet.com", gee_token=False),
    PlatformRecord("7lua", "https://7lua.net", gee_token=False),
    PlatformRecord("7x777", "https://7x777.com", gee_token=False),
    PlatformRecord("802win", "https://802win.win", gee_token=False),
    PlatformRecord("804win", "https://804win.win", gee_token=False),
    PlatformRecord("809win", "https://809win.win", gee_token=False),
    PlatformRecord("80pmbet", "https://80pmbet333.com", gee_token=False),
    PlatformRecord("80win", "https://80win.win", gee_token=False),
    PlatformRecord("811bet", "https://811bet.com", gee_token=False),
    PlatformRecord("8154bet", "https://8154bet.vip", gee_token=False),
    PlatformRecord("81bet", "https://81bet.com", gee_token=False),
    PlatformRecord("8200bet", "https://8200bet.vip", gee_token=False),
    PlatformRecord("8233win", "https://8233win.vip", gee_token=False),
    PlatformRecord("835bet", "https://dbh1xrhovww84.cloudfront.net", gee_token=False),
    PlatformRecord("848win", "https://848win.win", gee_token=False),
    PlatformRecord("850bet", "https://850bet.vip", gee_token=False),
    PlatformRecord("8633win", "https://8633win.vip", gee_token=False),
    PlatformRecord("8636win", "https://8636win.vip", gee_token=False),
    PlatformRecord("8654bet", "https://8654bet.vip", gee_token=False),
    PlatformRecord("8674bet", "https://8674bet.vip", gee_token=False),
    PlatformRecord("868br", "https://868br05.com", gee_token=False),
    PlatformRecord("878bet", "https://878bet.win", gee_token=False),
    PlatformRecord("8808win", "https://8808win.com", gee_token=False),
    PlatformRecord("881bet", "https://took.881apps.com", gee_token=False),
    PlatformRecord("882bet", "https://882bet.top", gee_token=False),
    PlatformRecord("8855bet", "https://8855bet.vip", gee_token=False),
    PlatformRecord("8865win", "https://8865win.vip", gee_token=False),
    PlatformRecord("887bet", "https://887bet.com", gee_token=False),
    PlatformRecord("888hot", "https://888hotak.com", gee_token=False),
    PlatformRecord("888rio", "https://www.888riol.com", gee_token=False),
    PlatformRecord("888win", "https://888win.win", gee_token=False),
    PlatformRecord("898bet", "https://d1nfme950fdsd0.cloudfront.net", gee_token=False),
    PlatformRecord("8cassino", "https://d2b3i3mys8qfkr.cloudfront.net", gee_token=False),
    PlatformRecord("8fclub", "https://8fclub.com", gee_token=False),
    PlatformRecord("901bet", "https://901bet.com", gee_token=False),
    PlatformRecord("9083bet", "https://9083bet.vip", gee_token=False),
    PlatformRecord("90bet", "https://90bet555.win", gee_token=False),
    PlatformRecord("90win", "https://90win.cc", gee_token=False),
    PlatformRecord("90win5", "https://90win5.com", gee_token=False),
    PlatformRecord("910bet", "https://d2omtgmpwgwhtm.cloudfront.net", gee_token=False),
    PlatformRecord("9155win", "https://9155win.vip", gee_token=False),
    PlatformRecord("915bet", "https://cook.915api.com", gee_token=False),
    PlatformRecord("9189bet", "https://9189bet.vip", gee_token=False),
    PlatformRecord("918bet", "https://918bet.com", gee_token=False),
    PlatformRecord("922bet", "https://l66b372802-fue5a8atbnc3gpdb.a01.azurefd.net", gee_token=False),
    PlatformRecord("930bet", "https://930bet.com", gee_token=False),
    PlatformRecord("939bet", "https://d2xthj1d0lr9p5.cloudfront.net", gee_token=False),
    PlatformRecord("944bet", "https://944bet.com", gee_token=False),
    PlatformRecord("9464", "https://9464.com", gee_token=False),
    PlatformRecord("9464bet", "https://9464bet.com", gee_token=False),
    PlatformRecord("9556bet", "https://9556bet.com", gee_token=False),
    PlatformRecord("9688win", "https://9688win.cc", gee_token=False),
    PlatformRecord("9775bet", "https://9775bet.com", gee_token=False),
    PlatformRecord("9797bet", "https://9797bet.com", gee_token=False),
    PlatformRecord("982bet", "https://982bet.com", gee_token=False),
    PlatformRecord("9866win", "https://9866win.vip", gee_token=False),
    PlatformRecord("992bet", "https://992bet.vip", gee_token=False),
    PlatformRecord("995bet", "https://995bet.vip", gee_token=False),
    PlatformRecord("996bet", "https://996bet.win", gee_token=False),
    PlatformRecord("9989win", "https://9989win.vip", gee_token=False),
    PlatformRecord("9991bet", "https://9991bet.vip", gee_token=False),
    PlatformRecord("9992bet", "https://9992bet.biz", gee_token=False),
    PlatformRecord("9993bet", "https://9993bet.vip", gee_token=False),
    PlatformRecord("9994bet", "https://9994bet.vip", gee_token=False),
    PlatformRecord("9996bet", "https://9996bet.vip", gee_token=False),
    PlatformRecord("9997bet", "https://9997bet.com", gee_token=False),
    PlatformRecord("999bb", "https://999bb.cc", gee_token=False),
    PlatformRecord("999kkg", "https://999kkg.com", gee_token=False),
    PlatformRecord("999mm", "https://999mm.com", gee_token=False),
    PlatformRecord("99kbrazil", "https://99kbrazil.com", gee_token=False),
    PlatformRecord("99rio", "https://99rio.com", gee_token=False),
    PlatformRecord("99win", "https://99win.win", gee_token=False),
    PlatformRecord("9nbet", "https://d1pt2d44fsffen.cloudfront.net", gee_token=False),
    PlatformRecord("9rbet", "https://9rbet.com", gee_token=False),
    PlatformRecord("aa7bet", "https://aa7bet.com", gee_token=False),
    PlatformRecord("aaario", "https://aaariow.vip", gee_token=False),
    PlatformRecord("a66bet", "https://a66bet11.com", gee_token=False),
    PlatformRecord("aaabet", "https://aaa8.bet", gee_token=False),
    PlatformRecord("aagrupo", "https://aagrupo.bet", gee_token=False),
    PlatformRecord("aatop", "https://aa.top", gee_token=False),
    PlatformRecord("ambet33", "https://ambet33.com", gee_token=False),
    PlatformRecord("bae777", "https://bae777.com", gee_token=False),
    PlatformRecord("bet000", "https://bet000.win", gee_token=False),
    PlatformRecord("bet03", "https://bet03.com", gee_token=False),
    PlatformRecord("bet0377", "https://bet0377.com", gee_token=False),
    PlatformRecord("bet09", "https://bet09.com", gee_token=False),
    PlatformRecord("bet0966", "https://bet0966.com", gee_token=False),
    PlatformRecord("bet10", "https://bet10.com", gee_token=False),
    PlatformRecord("bet100", "https://bet100.com", gee_token=False),
    PlatformRecord("bet1071", "https://bet1071.vip", gee_token=False),
    PlatformRecord("bet157", "https://bet157.win", gee_token=False),
    PlatformRecord("bet1798", "https://bet1798.vip", gee_token=False),
    PlatformRecord("bet29", "https://bet29.com", gee_token=False),
    PlatformRecord("bet317", "https://bet317.vip", gee_token=False),
    PlatformRecord("bet323", "https://bet323.vip", gee_token=False),
    PlatformRecord("bet33", "https://bet3333c.com", gee_token=False),
    PlatformRecord("bet3333", "https://bet3333.com", gee_token=False),
    PlatformRecord("bet345", "https://bet345.win", gee_token=False),
    PlatformRecord("bet36", "https://bet36.win", gee_token=False),
    PlatformRecord("bet362", "https://bet362.vip", gee_token=False),
    PlatformRecord("bet4444", "https://bet4444.win", gee_token=False),
    PlatformRecord("bet4448", "https://bet4448.com", gee_token=False),
    PlatformRecord("bet478", "https://bet478.com", gee_token=False),
    PlatformRecord("bet505", "https://bet505.cc", gee_token=False),
    PlatformRecord("bet55", "https://bet55.com", gee_token=False),
    PlatformRecord("bet558", "https://bet558.com", gee_token=False),
    PlatformRecord("bet559", "https://bet559.com", gee_token=False),
    PlatformRecord("bet585", "https://bet585.com", gee_token=False),
    PlatformRecord("bet595", "https://bet595.shop", gee_token=False),
    PlatformRecord("bet60", "https://bet60.win", gee_token=False),
    PlatformRecord("bet6009", "https://bet6009.vip", gee_token=False),
    PlatformRecord("bet61", "https://bet61.win", gee_token=False),
    PlatformRecord("bet613", "https://bet613.com", gee_token=False),
    PlatformRecord("bet625", "https://bet625.vip", gee_token=False),
    PlatformRecord("bet687", "https://bet687.com", gee_token=False),
    PlatformRecord("bet70", "https://bet70.win", gee_token=False),
    PlatformRecord("bet7198", "https://bet7198.com", gee_token=False),
    PlatformRecord("bet756", "https://bet756.com", gee_token=False),
    PlatformRecord("bet783", "https://bet783.win", gee_token=False),
    PlatformRecord("bet8245", "https://bet8245.cc", gee_token=False),
    PlatformRecord("bet8826", "https://bet8826.com", gee_token=False),
    PlatformRecord("bet917", "https://bet917.com", gee_token=False),
    PlatformRecord("bet922", "https://bet922.com", gee_token=False),
    PlatformRecord("bet939", "https://bet939.com", gee_token=False),
    PlatformRecord("bet959", "https://bet959.com", gee_token=False),
    PlatformRecord("bet969", "https://bet969.com", gee_token=False),
    PlatformRecord("bet979", "https://bet979.com", gee_token=False),
    PlatformRecord("betweb", "https://betweb.com", gee_token=False),
    PlatformRecord("bom5577", "https://bom5577.com", gee_token=False),
    PlatformRecord("br444", "https://br44401.com", gee_token=False),
    PlatformRecord("br739", "https://br739f.com", gee_token=False),
    PlatformRecord("brl55", "https://brl55.com", gee_token=False),
    PlatformRecord("bw900", "https://bw900.com", gee_token=False),
    PlatformRecord("0055bet", "https://took.0055api.com", gee_token=False),
    PlatformRecord("c588brl", "https://c588brl.com", gee_token=False),
    PlatformRecord("club77", "https://club77.com", gee_token=False),
    PlatformRecord("cn777", "https://d374jgaur8x9nn.cloudfront.net", gee_token=False),
    PlatformRecord("ebapg", "https://www.ebapg.game", gee_token=False),
    PlatformRecord("ejcassino", "https://d15ilya0r3jxfg.cloudfront.net", gee_token=False),
    PlatformRecord("game244", "https://game244.com", gee_token=False),
    PlatformRecord("gtwin", "https://da7siwtsqh748.cloudfront.net", gee_token=False),
    PlatformRecord("hh55", "https://hh55.com", gee_token=False),
    PlatformRecord("hrbet", "https://www.hrbet7.com", gee_token=False),
    PlatformRecord("hwbet", "https://hwbet.co", gee_token=False),
    PlatformRecord("jili117", "https://www.jili1117.com", gee_token=False),
    PlatformRecord("jjjbet", "https://jjj-web886.hjjj.bet", gee_token=False),
    PlatformRecord("jogo69", "https://www.jogo69.cc", gee_token=False),
    PlatformRecord("jqkbet", "https://8585wjkk.cda.bet", gee_token=False),
    PlatformRecord("k5389", "https://k5389.com", gee_token=False),
    PlatformRecord("kg52", "https://kg52.site", gee_token=False),
    PlatformRecord("kk500", "https://140.150.30.35:5012", gee_token=False),
    PlatformRecord("l6bet", "https://d36ddxs77aubr1.cloudfront.net", gee_token=False),
    PlatformRecord("new878", "https://new878.com", gee_token=False),
    PlatformRecord("njr", "http://njr44.com", gee_token=False),
    PlatformRecord("nn55", "https://33nn55.com", gee_token=False),
    PlatformRecord("nnnbet", "https://www.nnnabc.com", gee_token=False),
    PlatformRecord("okokbro", "https://okokbro.bet", gee_token=False),
    PlatformRecord("okokgema", "https://okokgema.com", gee_token=False),
    PlatformRecord("pg258", "https://pg258.com", gee_token=False),
    PlatformRecord("pgbet", "https://pg.bet", gee_token=False),
    PlatformRecord("pgvip", "https://1212pg.com", gee_token=False),
    PlatformRecord("pgsss", "https://pgsss7.com", gee_token=False),
    PlatformRecord("pijamapg", "https://www.10okbet10.com", gee_token=False),
    PlatformRecord("rr55", "https://d36a3fxu2akegy.cloudfront.net", gee_token=False),
    PlatformRecord("s7bet", "https://lvgbet.com", gee_token=False),
    PlatformRecord("slotbet", "https://slotbet.com", gee_token=False),
    PlatformRecord("sttbet", "https://look.sttbetapp.com", gee_token=False),
    PlatformRecord("tigre00", "https://tigre00.com", gee_token=False),
    PlatformRecord("tim55", "https://tim55.com", gee_token=False),
    PlatformRecord("tpsbet", "https://tpsbet0.com", gee_token=False),
    PlatformRecord("utbet", "https://utbet32.com", gee_token=False),
    PlatformRecord("xjwin", "https://d1nrbdh72k133o.cloudfront.net", gee_token=False),
    PlatformRecord("xo009", "https://xo009.com", gee_token=False),
    PlatformRecord("xtbet6", "https://xtbet6.com", gee_token=False),
    PlatformRecord("zelo101", "https://www.zelo101.com", gee_token=False),
    PlatformRecord("55jogo", "https://55jogo.bet", gee_token=False),
    PlatformRecord("1984pg", "https://www.1984pg.casino", gee_token=False),
    PlatformRecord("777dna", "https://777dna.com", gee_token=False),
    PlatformRecord("777max", "https://777max.cc", gee_token=False),
    PlatformRecord("777rifa", "https://777rifa.com", gee_token=False),
    PlatformRecord("777luc", "https://777luc.com", gee_token=False),
    PlatformRecord("777lov", "https://777lov.com", gee_token=False),
    PlatformRecord("777bem", "https://777bem.com", gee_token=False),
    PlatformRecord("777ufc", "https://777ufc.com", gee_token=False),
    PlatformRecord("777feb", "https://777feb.com", gee_token=False),
    PlatformRecord("777full", "https://777fullq.vip", gee_token=False),
    PlatformRecord("777blu", "https://777blu.com", gee_token=False),
    PlatformRecord("777paz", "https://777paz.com", gee_token=False),
    PlatformRecord("777ola", "https://777ola.com", gee_token=False),
    PlatformRecord("zx777", "https://www.zx777.com", gee_token=False),
    PlatformRecord("88cbf", "https://88cbf.com", gee_token=False),
    PlatformRecord("qrbet", "https://qrbet55.org", gee_token=False),
    PlatformRecord("qazbet", "https://qaz.bet", gee_token=False),
    PlatformRecord("7fay", "https://7fay.vip", gee_token=False),
    PlatformRecord("146bet", "https://d20qvniw26jklp.cloudfront.net", gee_token=False),
    PlatformRecord("okokcarnaval", "https://okokcarnaval.com", gee_token=False),
    PlatformRecord("55rio", "https://55rioa.vip", gee_token=False),
    PlatformRecord("cis777", "https://cis777.com", gee_token=False),
    PlatformRecord("777gd", "https://777gd.tw/?a=vmddqw5p", gee_token=False),
    PlatformRecord("666w", "https://www.666w00.com", gee_token=False),
    PlatformRecord("bonito777", "https://bonito777.com", gee_token=False),
    PlatformRecord("777tiger", "https://777tiger.com", gee_token=False),
    PlatformRecord("kk888pg", "https://kk888pg.com", gee_token=False),
    PlatformRecord("bar222", "https://bar222.net", gee_token=False),
    PlatformRecord("8zny", "https://8zny.vip", gee_token=False),
    PlatformRecord("win44", "https://rr0110.com", gee_token=False),
    PlatformRecord("6gbet", "https://6gbet14.com", gee_token=False),
    PlatformRecord("bb8bet", "https://bb8bet.vip", gee_token=False),
    PlatformRecord("777sug", "https://www.777sug.cc", gee_token=False),
    PlatformRecord("toppeixes", "https://www.toppeixes.win", gee_token=False),
    PlatformRecord("777mcu", "https://777mcu.vip", gee_token=False),
    PlatformRecord("777dub", "https://www.777dub.com", gee_token=False),
    PlatformRecord("topaquario", "https://www.topaquario.com", gee_token=False),
    PlatformRecord("toparies", "https://toparies.me", gee_token=False),
    PlatformRecord("toplibra", "https://www.toplibra.net", gee_token=False),
    PlatformRecord("topgemeos", "https://topgemeos.vip", gee_token=False),
    PlatformRecord("win575", "https://www.win575.win", gee_token=False),
    PlatformRecord("new2026b", "https://new2026b.com", gee_token=False),
    PlatformRecord("123rio", "https://123rio.vip", gee_token=False),
    PlatformRecord("bet559", "https://www.bet55916.com", gee_token=False),
]


# Cache da plataforma selecionada
_selected_platform: Optional[PlatformRecord] = None


def get_platform_by_name(name: str) -> Optional[PlatformRecord]:
    """
    Busca uma plataforma pelo nome.
    
    Args:
        name: Nome da plataforma (case-insensitive)
        
    Returns:
        PlatformRecord se encontrada, None caso contrário
    """
    normalized = name.lower().replace(".", "").replace(" ", "")
    
    for platform in PLATFORM_RECORDS:
        if platform.name.lower().replace(".", "").replace(" ", "") == normalized:
            return platform
    
    return None


def select_platform(name: str) -> PlatformRecord:
    """
    Seleciona uma plataforma pelo nome.
    
    Args:
        name: Nome da plataforma
        
    Returns:
        PlatformRecord da plataforma selecionada
        
    Raises:
        ValueError: Se a plataforma não for encontrada
    """
    global _selected_platform
    
    platform = get_platform_by_name(name)
    if not platform:
        raise ValueError(f"Plataforma não encontrada: {name}")
    
    _selected_platform = platform
    return platform


def get_selected_platform() -> Optional[PlatformRecord]:
    """Retorna a plataforma selecionada"""
    return _selected_platform


def list_platforms() -> List[str]:
    """Lista todos os nomes de plataformas disponíveis"""
    return sorted([p.name for p in PLATFORM_RECORDS])


def search_platforms(query: str) -> List[PlatformRecord]:
    """
    Busca plataformas por nome parcial.
    
    Args:
        query: Termo de busca
        
    Returns:
        Lista de plataformas que correspondem à busca
    """
    normalized = query.lower()
    return [p for p in PLATFORM_RECORDS if normalized in p.name.lower()]
