import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from supabase import Client, create_client

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Atualizado para ler a ETHERSCAN_API_KEY
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Endpoint unificado V2 da Etherscan (suporta Polygon via chainid=137)
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"
POLYGON_CHAIN_ID = 137

CONTRATOS_STABLECOINS = {
    "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
}

cache_cotacoes = {}


def obter_cotacao_usd_brl(data_unix: int) -> float:
    data_str = datetime.fromtimestamp(data_unix).strftime("%Y%m%d")
    if data_str in cache_cotacoes:
        return cache_cotacoes[data_str]

    url = f"https://economia.awesomeapi.com.br/json/daily/USD-BRL/?start_date={data_str}&end_date={data_str}"
    try:
        dados = requests.get(url, timeout=8).json()
        if dados and isinstance(dados, list):
            cotacao = float(dados[0]["bid"])
            cache_cotacoes[data_str] = cotacao
            return cotacao
    except Exception:
        pass

    res_atual = requests.get(
        "https://economia.awesomeapi.com.br/last/USD-BRL", timeout=8
    ).json()
    cotacao = float(res_atual["USDBRL"]["bid"])
    cache_cotacoes[data_str] = cotacao
    return cotacao


@app.get("/api/sincronizar")
def sincronizar_carteira(carteira: str, token: str = "USDT"):
    token = token.upper()
    contrato = CONTRATOS_STABLECOINS.get(token)

    if not contrato:
        raise HTTPException(
            status_code=400, detail="Token inválido. Use USDT ou USDC."
        )

    if not carteira.startswith("0x") or len(carteira) != 42:
        raise HTTPException(
            status_code=400, detail="Endereço de carteira Polygon inválido."
        )

    parametros = {
        "chainid": POLYGON_CHAIN_ID,  # Identifica a rede Polygon na API V2
        "module": "account",
        "action": "tokentx",
        "contractaddress": contrato,
        "address": carteira,
        "page": 1,
        "offset": 30,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }

    resposta = requests.get(
        ETHERSCAN_V2_URL, params=parametros, timeout=10
    ).json()

    if resposta.get("status") != "1":
        return {
            "status": "vazio",
            "mensagem": resposta.get("message"),
            "detalhe": resposta.get("result"),
            "novas_transacoes": 0,
        }

    carteira_lower = carteira.lower()
    registros_para_salvar = []

    for tx in resposta["result"]:
        if tx["to"].lower() == carteira_lower:
            decimais = int(tx["tokenDecimal"])
            valor_usd = int(tx["value"]) / (10**decimais)
            timestamp = int(tx["timeStamp"])
            data_iso = datetime.fromtimestamp(timestamp).isoformat()

            cotacao_brl = obter_cotacao_usd_brl(timestamp)
            valor_brl = round(valor_usd * cotacao_brl, 2)

            registros_para_salvar.append({
                "tx_hash": tx["hash"],
                "carteira_destino": carteira_lower,
                "remetente": tx["from"].lower(),
                "token": token,
                "valor_usd": round(valor_usd, 4),
                "cotacao_brl": round(cotacao_brl, 4),
                "valor_brl": valor_brl,
                "data_transacao": data_iso,
            })

    if registros_para_salvar:
        supabase.table("transacoes_stablecoin").upsert(
            registros_para_salvar, on_conflict="tx_hash"
        ).execute()

    return {
        "status": "sucesso",
        "carteira": carteira_lower,
        "token": token,
        "total_processado": len(registros_para_salvar),
        "dados": registros_para_salvar,
    }
