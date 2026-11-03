"""Pipelines do MongoDB: resumos horários por sensor e por cidade."""

CAMPOS = ("pm25", "pm10", "co2", "temperatura", "umidade")
CAMPOS_RESUMO = (
    "qt_medicoes", "pm25_media", "pm10_media", "co2_media",
    "temperatura_media", "umidade_media", "pm25_max", "pm10_max",
)


def filtro_validos(inicio, fim):
    """Conta somente medições com timestamp e todas as cinco grandezas numéricas."""
    filtro = {"timestamp": {"$type": "date", "$gte": inicio, "$lt": fim},
              "sensor_id": {"$type": "string", "$ne": ""}}
    # Temperaturas negativas são válidas. Limites finitos excluem NaN/Infinity.
    for campo in CAMPOS:
        filtro[campo] = {"$type": "number", "$gt": float("-inf"), "$lt": float("inf")}
        if campo != "temperatura":
            filtro[campo]["$gte"] = 0
    filtro["umidade"]["$lte"] = 100
    # $type em filtros também pode casar elementos de arrays; aqui exigimos escalares.
    filtro["$expr"] = {"$and": [
        *({"$isNumber": f"${campo}"} for campo in CAMPOS),
        {"$eq": [{"$type": "$timestamp"}, "date"]},
        {"$eq": [{"$type": "$sensor_id"}, "string"]},
    ]}
    return filtro


def expressao_hora():
    return {"$dateTrunc": {"date": "$timestamp", "unit": "hour", "timezone": "UTC"}}


def grupo_estatisticas():
    return {
        "qt_medicoes": {"$sum": 1},
        "pm25_media": {"$avg": "$pm25"},
        "pm10_media": {"$avg": "$pm10"},
        "co2_media": {"$avg": "$co2"},
        "temperatura_media": {"$avg": "$temperatura"},
        "umidade_media": {"$avg": "$umidade"},
        "pm25_max": {"$max": "$pm25"},
        "pm10_max": {"$max": "$pm10"},
    }


def projetar(campos_entidade):
    return {"_id": 0,
            **{campo: f"$_id.{campo}" for campo in campos_entidade},
            "inicio_periodo": "$_id.hora",
            "fim_periodo": {"$dateAdd": {"startDate": "$_id.hora", "unit": "hour", "amount": 1, "timezone": "UTC"}},
            **{campo: 1 for campo in CAMPOS_RESUMO}}


def pipeline_por_sensor(inicio, fim):
    return [
        {"$match": filtro_validos(inicio, fim)},
        {"$group": {"_id": {"sensor_id": "$sensor_id", "hora": expressao_hora()},
                    **grupo_estatisticas()}},
        {"$project": projetar(("sensor_id",))},
        {"$sort": {"sensor_id": 1, "inicio_periodo": 1}},
    ]


def pipeline_por_cidade(inicio, fim):
    return [
        {"$match": filtro_validos(inicio, fim)},
        {"$lookup": {"from": "Sensores", "localField": "sensor_id",
                     "foreignField": "_id", "as": "sensor"}},
        {"$unwind": "$sensor"},
        {"$group": {"_id": {"cidade": "$sensor.localizacao.cidade",
                             "uf": "$sensor.localizacao.uf", "hora": expressao_hora()},
                    **grupo_estatisticas()}},
        {"$project": projetar(("cidade", "uf"))},
        {"$sort": {"uf": 1, "cidade": 1, "inicio_periodo": 1}},
    ]


def agregar(banco, inicio, fim):
    """Efetivamente executa os dois pipelines no MongoDB (não agrega em Python)."""
    sensores = list(banco.Medicoes.aggregate(pipeline_por_sensor(inicio, fim)))
    cidades = list(banco.Medicoes.aggregate(pipeline_por_cidade(inicio, fim)))
    return sensores, cidades


def ultimos_resumos(registros, campos_identidade):
    """Retorna apenas a última hora disponível para cada sensor ou cidade."""
    recentes = {}
    for registro in registros:
        identificador = tuple(registro[campo] for campo in campos_identidade)
        if (identificador not in recentes or
                registro["inicio_periodo"] > recentes[identificador]["inicio_periodo"]):
            recentes[identificador] = registro
    return recentes
