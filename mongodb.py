"""Camada 1 - MongoDB: sensores, histórico e consultas.

Os dados e coordenadas são apenas ilustrativos.
"""
import math
import os
import random
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

NOME_BANCO = "QualidadeAr"
MONGO_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/")


def conectar_mongo():
    cliente = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000,
                          tz_aware=True, tzinfo=timezone.utc)
    try:
        cliente.admin.command("ping")
    except Exception:
        cliente.close()
        raise
    return cliente


# Modelagem e geração de medições ilustrativas.
GRANDEZAS = ["PM2.5", "PM10", "CO2", "temperatura", "umidade"]

# Todos os pontos abaixo são ilustrativos; não são coordenadas de equipamentos reais.
SENSORES = [
    {"_id": "S001", "modelo": "AirMonitor-200", "descricao": "Estação simulada do centro de Chapecó",
     "localizacao": {"cidade": "Chapecó", "uf": "SC", "latitude": -27.1009, "longitude": -52.6157},
     "ativo": True, "grandezas": GRANDEZAS[:]},
    {"_id": "S002", "modelo": "AirMonitor-200", "descricao": "Estação simulada da zona norte de Chapecó",
     "localizacao": {"cidade": "Chapecó", "uf": "SC", "latitude": -27.0748, "longitude": -52.6240},
     "ativo": True, "grandezas": GRANDEZAS[:]},
    {"_id": "S003", "modelo": "AirMonitor-220", "descricao": "Estação simulada da região central de Xanxerê",
     "localizacao": {"cidade": "Xanxerê", "uf": "SC", "latitude": -26.8762, "longitude": -52.4047},
     "ativo": True, "grandezas": GRANDEZAS[:]},
    {"_id": "S004", "modelo": "AirMonitor-220", "descricao": "Estação simulada da região leste de Xanxerê",
     "localizacao": {"cidade": "Xanxerê", "uf": "SC", "latitude": -26.8830, "longitude": -52.3920},
     "ativo": True, "grandezas": GRANDEZAS[:]},
    {"_id": "S005", "modelo": "AirMonitor-300", "descricao": "Estação simulada da região central de Concórdia",
     "localizacao": {"cidade": "Concórdia", "uf": "SC", "latitude": -27.2344, "longitude": -52.0270},
     "ativo": True, "grandezas": GRANDEZAS[:]},
    {"_id": "S006", "modelo": "AirMonitor-300", "descricao": "Estação simulada da região sul de Concórdia",
     "localizacao": {"cidade": "Concórdia", "uf": "SC", "latitude": -27.2480, "longitude": -52.0380},
     "ativo": True, "grandezas": GRANDEZAS[:]},
]


def preparar_banco(banco):
    """Cria/atualiza os seis sensores sem duplicá-los e cria o índice exigido."""
    for sensor in SENSORES:
        banco.Sensores.replace_one({"_id": sensor["_id"]}, sensor, upsert=True)
    nome_indice = banco.Medicoes.create_index(
        [("sensor_id", ASCENDING), ("timestamp", DESCENDING)]
    )
    return nome_indice


def ultima_hora_fechada():
    """Limite final EXCLUSIVO (UTC) da última hora inteira concluída."""
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def intervalo_historico(horas=24):
    if horas <= 0:
        raise ValueError("O número de horas deve ser maior que zero.")
    fim = ultima_hora_fechada()
    return fim - timedelta(hours=horas), fim


def construir_medicao(sensor_id, instante):
    """Valores sintéticos coerentes; o mesmo sensor/instante dá o mesmo resultado."""
    deslocamento = int(sensor_id[1:])
    rng = random.Random(f"qualidade-ar:{sensor_id}:{instante.isoformat()}")
    # Variação diária para demonstrar estatísticas reais sobre dados simulados.
    ciclo = math.sin(2 * math.pi * (instante.hour + instante.minute / 60) / 24)
    pm25 = round(max(1.0, 13.0 + deslocamento * 2.2 + 6.5 * ciclo + rng.uniform(-3.5, 3.5)), 2)
    pm10 = round(pm25 + 12.0 + rng.uniform(4.0, 18.0), 2)
    co2 = round(420 + 19 * deslocamento + 45 * (ciclo + 1) + rng.uniform(0, 75), 2)
    temperatura = round(21 + 4.0 * ciclo + deslocamento * 0.25 + rng.uniform(-1.6, 1.6), 2)
    umidade = round(min(95.0, max(20.0, 66 - 9 * ciclo + rng.uniform(-7, 7))), 2)
    return {
        "_id": f"{sensor_id}:{instante.strftime('%Y%m%dT%H%M%SZ')}",
        "sensor_id": sensor_id,
        "timestamp": instante,  # datetime aware UTC -> BSON Date no MongoDB
        "pm25": pm25, "pm10": pm10, "co2": co2,
        "temperatura": temperatura, "umidade": umidade,
    }


def gerar_medicoes(banco, horas=24, reiniciar=False):
    """Gera 12 medições/hora/sensor; upsert evita duplicar timestamps."""
    if horas <= 0 or horas > 168:
        raise ValueError("Use de 1 a 168 horas.")
    inicio, fim = intervalo_historico(horas)
    if reiniciar:
        banco.Medicoes.delete_many({})
    operacoes = []
    instante = inicio
    while instante < fim:
        for sensor in SENSORES:
            documento = construir_medicao(sensor["_id"], instante)
            operacoes.append(UpdateOne(
                {"_id": documento["_id"]},
                {"$set": {campo: valor for campo, valor in documento.items() if campo != "_id"}},
                upsert=True,
            ))
        instante += timedelta(minutes=5)
    if operacoes:
        # Lotes evitam um comando muito grande quando forem geradas mais horas.
        for posicao in range(0, len(operacoes), 1000):
            banco.Medicoes.bulk_write(operacoes[posicao:posicao + 1000], ordered=False)
    return {"inicio": inicio, "fim": fim, "esperadas": len(operacoes),
            "total_no_banco": banco.Medicoes.count_documents({})}
