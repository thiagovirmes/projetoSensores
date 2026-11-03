#!/usr/bin/env python3
"""Projeto com 3 arquivos - entrada pelo terminal e resumos Redis.

Use: python3 main.py --help
"""
import argparse
import os
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

import redis
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from agregacoes import CAMPOS_RESUMO, agregar, filtro_validos, ultimos_resumos
from mongodb import (NOME_BANCO, SENSORES, conectar_mongo, gerar_medicoes,
                     intervalo_historico, preparar_banco)

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
PREFIXO = "qualidadear:"


def conectar_redis():
    cliente = redis.from_url(REDIS_URL, decode_responses=True,
                            socket_connect_timeout=5, socket_timeout=10)
    try:
        cliente.ping()
    except Exception:
        cliente.close()
        raise
    return cliente


def normalizar_cidade(cidade):
    normalizado = unicodedata.normalize("NFKD", cidade.casefold())
    return "".join(caractere for caractere in normalizado
                   if not unicodedata.combining(caractere)).replace(" ", "-")


def chave_sensor(sensor_id):
    return f"{PREFIXO}sensor:{sensor_id}"


def chave_cidade(uf, cidade):
    return f"{PREFIXO}cidade:{uf.upper()}:{normalizar_cidade(cidade)}"


def iso_utc(data):
    if data.tzinfo is None:
        raise ValueError("Data sem fuso horário: esperado UTC.")
    return data.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mapa_resumo(resumo):
    mapeamento = {
        "inicio_periodo": iso_utc(resumo["inicio_periodo"]),
        "fim_periodo": iso_utc(resumo["fim_periodo"]),
        "qt_medicoes": str(int(resumo["qt_medicoes"])),
    }
    for campo in CAMPOS_RESUMO:
        if campo == "qt_medicoes":
            continue
        # Os valores ficam em string, como previsto no Redis.
        mapeamento[campo] = f"{float(resumo[campo]):.2f}"
    return mapeamento


def limpar_resumos(cliente_redis):
    """Remove SOMENTE os Hashes com prefixo do projeto, sem usar FLUSHDB."""
    chaves = list(cliente_redis.scan_iter(match=f"{PREFIXO}*"))
    if chaves:
        cliente_redis.delete(*chaves)
    return len(chaves)


def salvar_ultimos(cliente_redis, sensores, cidades):
    por_sensor = ultimos_resumos(sensores, ("sensor_id",))
    por_cidade = ultimos_resumos(cidades, ("uf", "cidade"))
    esperadas = {chave_sensor(sid) for (sid,) in por_sensor}
    esperadas.update(chave_cidade(uf, cidade) for (uf, cidade) in por_cidade)
    anteriores = set(cliente_redis.scan_iter(match=f"{PREFIXO}sensor:*"))
    anteriores.update(cliente_redis.scan_iter(match=f"{PREFIXO}cidade:*"))
    # Uma sincronização completa recalcula os resumos e substitui seus campos.
    with cliente_redis.pipeline(transaction=True) as pipeline:
        obsoletas = anteriores - esperadas
        if obsoletas:
            pipeline.delete(*obsoletas)
        for (sensor_id,), registro in por_sensor.items():
            pipeline.delete(chave_sensor(sensor_id))
            pipeline.hset(chave_sensor(sensor_id), mapping=mapa_resumo(registro))
        for (uf, cidade), registro in por_cidade.items():
            pipeline.delete(chave_cidade(uf, cidade))
            pipeline.hset(chave_cidade(uf, cidade), mapping=mapa_resumo(registro))
        pipeline.execute()
    return len(por_sensor), len(por_cidade)


def ler_resumos(cliente_redis):
    chaves = sorted(cliente_redis.scan_iter(match=f"{PREFIXO}*"))
    return [(chave, cliente_redis.hgetall(chave)) for chave in chaves]

def exibir_medicoes(registros):
    for doc in registros:
        print(f"  {doc['sensor_id']}  {iso_utc(doc['timestamp'])}  "
              f"PM2.5={doc['pm25']:>6.2f} µg/m³  PM10={doc['pm10']:>6.2f} µg/m³  "
              f"CO₂={doc['co2']:>6.2f} ppm  T={doc['temperatura']:>5.2f} °C  "
              f"UR={doc['umidade']:>5.2f}%")


def exibir_resumo(rotulo, dados):
    print(f"\n{rotulo} | {iso_utc(dados['inicio_periodo'])} → {iso_utc(dados['fim_periodo'])}")
    print(f"  Medições: {dados['qt_medicoes']}  "
          f"PM2.5 média/máx: {dados['pm25_media']:.2f}/{dados['pm25_max']:.2f} µg/m³  "
          f"PM10 média/máx: {dados['pm10_media']:.2f}/{dados['pm10_max']:.2f} µg/m³")
    print(f"  CO₂ médio: {dados['co2_media']:.2f} ppm  "
          f"Temperatura média: {dados['temperatura_media']:.2f} °C  "
          f"Umidade média: {dados['umidade_media']:.2f}%")

def conectar_banco():
    cliente = conectar_mongo()
    return cliente, cliente[NOME_BANCO]


def verificar():
    print("Verificando serviços locais (sem Docker)...")
    erros = 0
    try:
        mongo = conectar_mongo()
        versao = mongo.server_info()["version"]
        print(f"[OK] MongoDB acessível em localhost — versão {versao}")
        if int(versao.split(".")[0]) < 5:
            print("[ERRO] É necessário MongoDB 5.0+ para $dateTrunc e $dateAdd.")
            erros += 1
        mongo.close()
    except Exception as erro:
        print(f"[ERRO] MongoDB: {erro}")
        erros += 1
    try:
        cache = conectar_redis()
        versao = cache.info("server").get("redis_version", "desconhecida")
        print(f"[OK] Redis acessível em localhost — versão {versao} | ping=PONG")
        cache.close()
    except Exception as erro:
        print(f"[ERRO] Redis: {erro}")
        erros += 1
    return erros == 0


def preparar():
    cliente, banco = conectar_banco()
    try:
        indice = preparar_banco(banco)
        print(f"[OK] Banco {NOME_BANCO}: {banco.Sensores.count_documents({})} sensores cadastrados.")
        print(f"[OK] Índice: {indice} (sensor_id crescente, timestamp decrescente).")
        for sensor in SENSORES:
            print(f"  {sensor['_id']} → {sensor['localizacao']['cidade']}/SC")
    finally:
        cliente.close()


def gerar(horas, reiniciar=False):
    cliente, banco = conectar_banco()
    try:
        if banco.Sensores.count_documents({"_id": {"$in": [s["_id"] for s in SENSORES]}}) < 6:
            preparar_banco(banco)
        dados = gerar_medicoes(banco, horas=horas, reiniciar=reiniciar)
    finally:
        cliente.close()
    if reiniciar:
        cache = conectar_redis()
        try:
            removidas = limpar_resumos(cache)
        finally:
            cache.close()
        print(f"[OK] Limpeza solicitada: {removidas} chave(s) Redis do projeto removidas.")
    print(f"[OK] {dados['esperadas']} medições geradas/atualizadas na janela.")
    print(f"     {iso_utc(dados['inicio'])} → {iso_utc(dados['fim'])} (fim exclusivo)")
    print(f"     Total histórico no MongoDB: {dados['total_no_banco']} documentos.")
    print("     O mesmo sensor/horário não é duplicado ao reexecutar.")


def interpretar_data(entrada):
    try:
        data = datetime.fromisoformat(entrada.strip().replace("Z", "+00:00"))
    except ValueError as erro:
        raise ValueError(f"Data ISO 8601 inválida: {entrada!r}") from erro
    if data.tzinfo is None:
        raise ValueError("Informe um fuso horário; exemplo: 2026-10-20T10:00:00Z")
    return data.astimezone(timezone.utc)


def consultar(sensor_id, inicio_texto, fim_texto, ultimas_horas, limite, cidade=None, uf=None):
    if uf and not cidade:
        raise ValueError("Use --uf junto de --cidade.")
    if bool(inicio_texto) != bool(fim_texto):
        raise ValueError("Use --inicio e --fim juntos, ou apenas --ultimas-horas.")
    if inicio_texto:
        inicio, fim = interpretar_data(inicio_texto), interpretar_data(fim_texto)
    else:
        inicio, fim = intervalo_historico(ultimas_horas)
    if inicio >= fim:
        raise ValueError("O início deve ser anterior ao fim.")
    if limite <= 0 or limite > 500:
        raise ValueError("O limite deve ficar entre 1 e 500.")

    cliente, banco = conectar_banco()
    try:
        filtro = {"timestamp": {"$gte": inicio, "$lt": fim}}
        if cidade:
            filtro_local = {"localizacao.cidade": cidade}
            if uf:
                filtro_local["localizacao.uf"] = uf.upper()
            ids = [s["_id"] for s in banco.Sensores.find(filtro_local, {"_id": 1})]
            filtro["sensor_id"] = {"$in": ids}
        else:
            filtro["sensor_id"] = sensor_id
        total = banco.Medicoes.count_documents(filtro)
        registros = list(banco.Medicoes.find(filtro).sort("timestamp", 1).limit(limite))
    finally:
        cliente.close()
    entidade = f"Cidade {cidade}" if cidade else f"Sensor {sensor_id}"
    print(f"{entidade}: {total} medições em [{iso_utc(inicio)}, {iso_utc(fim)})")
    print(f"Exibindo {len(registros)} registro(s):")
    exibir_medicoes(registros)
    if total > limite:
        print(f"... {total - limite} registro(s) não exibidos. Aumente --limite.")


def atualizar_resumos(horas, mostrar_todas=False):
    inicio, fim = intervalo_historico(horas)
    cliente, banco = conectar_banco()
    try:
        resumos_sensor, resumos_cidade = agregar(banco, inicio, fim)
    finally:
        cliente.close()

    if not resumos_sensor or not resumos_cidade:
        raise ValueError("Nenhuma agregação encontrada; execute 'preparar' e 'gerar' primeiro.")
    cache = conectar_redis()
    try:
        ns, nc = salvar_ultimos(cache, resumos_sensor, resumos_cidade)
    finally:
        cache.close()
    print(f"[OK] MongoDB: {len(resumos_sensor)} resumos horários por sensor e "
          f"{len(resumos_cidade)} por cidade calculados.")
    print(f"[OK] Redis: {ns} Hash(es) de sensor + {nc} Hash(es) de cidade atualizados.")
    if mostrar_todas:
        registros_sensor, registros_cidade = resumos_sensor, resumos_cidade
    else:
        registros_sensor = list(ultimos_resumos(resumos_sensor, ("sensor_id",)).values())
        registros_cidade = list(ultimos_resumos(resumos_cidade, ("uf", "cidade")).values())
    for doc in sorted(registros_sensor, key=lambda r: (r["sensor_id"], r["inicio_periodo"])):
        exibir_resumo(f"SENSOR {doc['sensor_id']}", doc)
    for doc in sorted(registros_cidade, key=lambda r: (r["uf"], r["cidade"], r["inicio_periodo"])):
        exibir_resumo(f"CIDADE {doc['cidade']}/{doc['uf']}", doc)


def mostrar_redis():
    cliente = conectar_redis()
    try:
        hashes = ler_resumos(cliente)
    finally:
        cliente.close()
    if not hashes:
        print("Nenhum Hash do projeto. Execute 'agregar' primeiro.")
        return
    print(f"Redis: {len(hashes)} Hashes armazenados:")
    for chave, campos in hashes:
        print(f"\n{chave}")
        for campo, valor in sorted(campos.items()):
            print(f"  {campo:20} = {valor}")


def validar():
    """Confere volumes e os valores do Redis contra o MongoDB na última hora."""
    inicio, fim = intervalo_historico(24)
    ultima_inicio = fim - timedelta(hours=1)
    cliente, banco = conectar_banco()
    cache = None
    problemas = []
    try:
        cache = conectar_redis()
        ids = [sensor["_id"] for sensor in SENSORES]
        for sensor in SENSORES:
            if not banco.Sensores.find_one({"_id": sensor["_id"]}):
                problemas.append(f"Sensor {sensor['_id']} não está cadastrado.")
        quantidade = banco.Medicoes.count_documents({
            "sensor_id": {"$in": ids}, "timestamp": {"$gte": inicio, "$lt": fim}
        })
        if quantidade != 1728:
            problemas.append(f"Quantidade da janela de 24h: {quantidade} (esperado 1728).")
        # Compara toda a grade temporal: detecta lacunas, duplicatas e deslocamentos.
        grade = [inicio + timedelta(minutes=5 * i) for i in range(288)]
        for sensor_id in ids:
            filtro = {"sensor_id": sensor_id, "timestamp": {"$gte": inicio, "$lt": fim}}
            instantes = [d["timestamp"] for d in banco.Medicoes.find(filtro, {"timestamp": 1}).sort("timestamp", 1)]
            if instantes != grade:
                problemas.append(f"{sensor_id}: esperado 288 registros na grade de cinco minutos em 24h.")
        validas = banco.Medicoes.count_documents({**filtro_validos(inicio, fim), "sensor_id": {"$in": ids}})
        if validas != 1728:
            problemas.append(f"Medições válidas na janela: {validas} (esperado 1728).")
        todas_sensor, todas_cidade = agregar(banco, inicio, fim)
        if len(todas_sensor) != 144 or any(r["qt_medicoes"] != 12 for r in todas_sensor):
            problemas.append("Esperados 144 resumos de sensor, cada um com 12 medições.")
        if len(todas_cidade) != 72 or any(r["qt_medicoes"] != 24 for r in todas_cidade):
            problemas.append("Esperados 72 resumos de cidade, cada um com 24 medições.")
        sensores, cidades = agregar(banco, ultima_inicio, fim)
        if len(sensores) != 6 or len(cidades) != 3:
            problemas.append(f"Resumos da última hora: {len(sensores)} sensores / "
                             f"{len(cidades)} cidades (esperado 6/3).")
        for registro in sensores + cidades:
            eh_sensor = "sensor_id" in registro
            chave = (chave_sensor(registro["sensor_id"]) if eh_sensor else
                     chave_cidade(registro["uf"], registro["cidade"]))
            atual = cache.hgetall(chave)
            if not atual:
                problemas.append(f"Redis: Hash ausente {chave}")
                continue
            esperado_qt = 12 if eh_sensor else 24
            if registro["qt_medicoes"] != esperado_qt:
                problemas.append(f"MongoDB {chave}: {registro['qt_medicoes']} != {esperado_qt} medições.")
            for campo, esperado in mapa_resumo(registro).items():
                if atual.get(campo) != esperado:
                    problemas.append(f"Redis {chave}: {campo} ausente ou diferente do MongoDB.")
        if len(list(cache.scan_iter(match=f"{PREFIXO}*"))) != 9:
            problemas.append("Esperados exatamente nove Hashes do projeto no Redis.")
        print(f"MongoDB: {quantidade} medições nas últimas 24h completas.")
        print(f"Agregações da hora {iso_utc(ultima_inicio)}: "
              f"{len(sensores)} sensores, {len(cidades)} cidades.")
    finally:
        cliente.close()
        if cache is not None:
            cache.close()
    if problemas:
        print("[FALHA] Validação encontrou problemas:")
        for problema in problemas:
            print("  -", problema)
        return False
    print("[OK] Todos os requisitos quantitativos e Hashes Redis conferem com o MongoDB!")
    print("[OK] 12 medições por sensor/hora; 24 por cidade/hora; 72 no total por hora.")
    return True


def demonstrar():
    print("\n==== 1/6 SERVIÇOS ====")
    if not verificar():
        raise ValueError("Verifique se MongoDB e Redis estão iniciados.")
    print("\n==== 2/6 SENSORES E ÍNDICE ====")
    preparar()
    print("\n==== 3/6 DADOS HISTÓRICOS ====")
    gerar(24)
    print("\n==== 4/6 CONSULTA NO MONGODB ====")
    consultar("S001", None, None, 1, 3)
    consultar(None, None, None, 1, 3, cidade="Chapecó", uf="SC")
    print("\n==== 5/6 AGREGAÇÃO E ATUALIZAÇÃO NO REDIS ====")
    atualizar_resumos(24)
    print("\n==== 6/6 VALIDAÇÃO DO PROTÓTIPO ====")
    if not validar():
        raise ValueError("A validação falhou; revise os dados acima.")
    mostrar_redis()
    print("\n[SUCESSO] Demonstração concluída!")


def montar_parser():
    parser = argparse.ArgumentParser(description="Estudo de caso: qualidade do ar (MongoDB + Redis).")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("verificar", help="Testa conectividade e versões dos servidores.")
    sub.add_parser("preparar", help="Cadastra 6 sensores e cria índice MongoDB.")
    gerador = sub.add_parser("gerar", help="Gera histórico UTC a cada 5 minutos.")
    gerador.add_argument("--horas", type=int, default=24)
    gerador.add_argument("--reiniciar", action="store_true",
                         help="CUIDADO: apaga as medições e Hashes anteriores deste projeto.")
    consulta = sub.add_parser("consultar", help="Consulta medições por sensor e período UTC.")
    entidade = consulta.add_mutually_exclusive_group(required=True)
    entidade.add_argument("--sensor")
    entidade.add_argument("--cidade", help="Nome da cidade como cadastrado, com acentos.")
    consulta.add_argument("--uf", help="UF opcional para consulta por cidade.")
    consulta.add_argument("--inicio", help="ISO UTC, exemplo 2026-10-20T10:00:00Z")
    consulta.add_argument("--fim", help="ISO UTC, exemplo 2026-10-20T11:00:00Z")
    consulta.add_argument("--ultimas-horas", type=int, default=2)
    consulta.add_argument("--limite", type=int, default=12)
    agreg = sub.add_parser("agregar", help="Agrega horários em MongoDB e grava últimos Hashes Redis.")
    agreg.add_argument("--horas", type=int, default=24)
    agreg.add_argument("--mostrar-todas", action="store_true", help="Mostra todas as horas; saída longa.")
    sub.add_parser("redis", help="Mostra os Hashes gravados no Redis.")
    sub.add_parser("validar", help="Valida requisitos e compara Redis com MongoDB.")
    sub.add_parser("demonstrar", help="Executa uma demonstração completa para apresentar.")
    return parser


def main():
    args = montar_parser().parse_args()
    try:
        if args.comando == "verificar":
            return 0 if verificar() else 1
        if args.comando == "preparar":
            preparar()
        elif args.comando == "gerar":
            gerar(args.horas, args.reiniciar)
        elif args.comando == "consultar":
            consultar(args.sensor, args.inicio, args.fim, args.ultimas_horas, args.limite,
                      args.cidade, args.uf)
        elif args.comando == "agregar":
            atualizar_resumos(args.horas, args.mostrar_todas)
        elif args.comando == "redis":
            mostrar_redis()
        elif args.comando == "validar":
            return 0 if validar() else 1
        elif args.comando == "demonstrar":
            demonstrar()
        return 0
    except (PyMongoError, RedisError, ValueError, OSError) as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExecução interrompida.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
