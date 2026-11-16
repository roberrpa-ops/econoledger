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

from fastapi import FastAPI, Header, HTTPException
# ... (mantenha as importações anteriores) ...


@app.get("/api/sincronizar")
def sincronizar_carteira(
    carteira: str,
    token: str = "USDT",
    authorization: str = Header(
        None
    ),  # Recebe "Bearer <access_token>" do Supabase Auth
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Token de autenticação ausente."
        )

    jwt_token = authorization.split(" ")[1]

    # Valida o usuário diretamente no Supabase Auth usando o token enviado pelo frontend
    user_response = supabase.auth.get_user(jwt_token)
    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="Sessão inválida.")

    user_id = user_response.user.id
    carteira_lower = carteira.lower()

    # 1. Garante que a carteira está registrada para este usuário e obtém o carteira_id
    res_carteira = (
        supabase.table("carteiras_usuario")
        .upsert(
            {"user_id": user_id, "endereco_carteira": carteira_lower},
            on_conflict="user_id,endereco_carteira",
        )
        .execute()
    )

    carteira_id = res_carteira.data[0]["id"]

    # ... (mantenha a consulta à Etherscan V2 e cálculo de cotação exatamente iguais) ...

    # No loop de montagem de `registros_para_salvar`, inclua `user_id` e `carteira_id`:
    # registros_para_salvar.append({
    #     "user_id": user_id,
    #     "carteira_id": carteira_id,
    #     "tx_hash": tx["hash"],
    #     ...
    # })

    if registros_para_salvar:
        supabase.table("transacoes_stablecoin").upsert(
            registros_para_salvar, on_conflict="user_id,tx_hash"
        ).execute()

    return {
        "status": "sucesso",
        "total_processado": len(registros_para_salvar),
        "dados": registros_para_salvar,
    }
