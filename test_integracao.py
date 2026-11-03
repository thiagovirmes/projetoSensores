"""Testes com MongoDB e Redis reais, usando banco e prefixo temporários."""
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from statistics import mean
from unittest.mock import patch
from uuid import uuid4

import main
from agregacoes import CAMPOS, agregar
from mongodb import conectar_mongo, gerar_medicoes, preparar_banco


class Integracao(unittest.TestCase):
    def setUp(self):
        self.mongo = conectar_mongo()
        self.nome = f"QualidadeArTeste_{uuid4().hex}"
        self.banco = self.mongo[self.nome]
        self.redis = main.conectar_redis()
        self.prefixo = f"qualidadear_teste:{uuid4().hex}:"
        self.patch_prefixo = patch.object(main, "PREFIXO", self.prefixo)
        self.patch_prefixo.start()
        self.inicio = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
        self.fim = self.inicio + timedelta(hours=1)
        preparar_banco(self.banco)

    def tearDown(self):
        try:
            chaves = list(self.redis.scan_iter(match=f"{self.prefixo}*"))
            if chaves:
                self.redis.delete(*chaves)
            self.mongo.drop_database(self.nome)
        finally:
            self.patch_prefixo.stop()
            self.redis.close()
            self.mongo.close()

    def medicao(self, sensor, pm25, minutos=0, **campos):
        return {"sensor_id": sensor, "timestamp": self.inicio + timedelta(minutes=minutos),
                "pm25": pm25, "pm10": pm25 + 10, "co2": 500,
                "temperatura": -3.0, "umidade": 65, **campos}

    def test_media_cidade_usa_registros_e_nao_media_das_medias(self):
        self.banco.Medicoes.insert_many([
            self.medicao("S001", 10), self.medicao("S001", 30, 5),
            self.medicao("S002", 100),
        ])
        sensores, cidades = agregar(self.banco, self.inicio, self.fim)
        self.assertEqual(len(sensores), 2)
        self.assertEqual(cidades[0]["qt_medicoes"], 3)
        self.assertAlmostEqual(cidades[0]["pm25_media"], 140 / 3)
        self.assertNotEqual(cidades[0]["pm25_media"], 60)
        self.assertEqual(cidades[0]["temperatura_media"], -3)

    def test_validade_das_medicoes_e_limite_final_exclusivo(self):
        self.banco.Medicoes.insert_many([
            self.medicao("S001", 10),  # temperatura negativa válida
            self.medicao("S001", 20, 60),  # outra janela
            self.medicao("S001", -1),
            self.medicao("S001", 10, umidade=101),
            self.medicao("S001", 10, co2="invalido"),
            self.medicao("S001", 10, co2=None),
            self.medicao("S001", 10, temperatura=math.nan),
            self.medicao("S001", 10, temperatura=math.inf),
            self.medicao("S001", 10, co2=[500]),
            self.medicao("S001", 10, timestamp=[self.inicio]),
        ])
        sensores, cidades = agregar(self.banco, self.inicio, self.fim)
        self.assertEqual(sensores[0]["qt_medicoes"], 1)
        self.assertEqual(cidades[0]["qt_medicoes"], 1)
        self.assertEqual(sensores[0]["inicio_periodo"], self.inicio)
        self.assertEqual(sensores[0]["fim_periodo"], self.fim)

    def test_geracao_idempotente_e_estatisticas_das_24_horas(self):
        with patch("mongodb.ultima_hora_fechada", return_value=self.fim):
            gerar_medicoes(self.banco, 24)
            gerar_medicoes(self.banco, 24)
        self.assertEqual(self.banco.Medicoes.count_documents({}), 1728)
        inicio = self.fim - timedelta(hours=24)
        sensores, cidades = agregar(self.banco, inicio, self.fim)
        self.assertEqual(len(sensores), 144)
        self.assertEqual(len(cidades), 72)
        self.assertTrue(all(r["qt_medicoes"] == 12 for r in sensores))
        self.assertTrue(all(r["qt_medicoes"] == 24 for r in cidades))
        # Confere as cinco médias e os máximos independentemente do pipeline.
        for resumo in sensores + cidades:
            if "sensor_id" in resumo:
                ids = [resumo["sensor_id"]]
            else:
                ids = [s["_id"] for s in self.banco.Sensores.find({
                    "localizacao.cidade": resumo["cidade"], "localizacao.uf": resumo["uf"]})]
            docs = list(self.banco.Medicoes.find({"sensor_id": {"$in": ids}, "timestamp": {
                "$gte": resumo["inicio_periodo"], "$lt": resumo["fim_periodo"]}}))
            for campo in CAMPOS:
                self.assertAlmostEqual(resumo[f"{campo}_media"], mean(d[campo] for d in docs))
            for campo in ("pm25", "pm10"):
                self.assertEqual(resumo[f"{campo}_max"], max(d[campo] for d in docs))
        self.assertEqual(main.salvar_ultimos(self.redis, sensores, cidades), (6, 3))
        self.assertEqual(len(main.ler_resumos(self.redis)), 9)

    def test_redis_guarda_ultima_hora_e_remove_resumo_obsoleto(self):
        self.banco.Medicoes.insert_many([
            self.medicao("S001", 10), self.medicao("S001", 50, 60),
        ])
        sensores, cidades = agregar(self.banco, self.inicio, self.fim + timedelta(hours=1))
        obsoleta = main.chave_sensor("REMOVIDO")
        self.redis.hset(obsoleta, mapping={"qt_medicoes": "1"})
        main.salvar_ultimos(self.redis, list(reversed(sensores)), cidades)
        atual = self.redis.hgetall(main.chave_sensor("S001"))
        self.assertEqual(atual["pm25_media"], "50.00")
        self.assertEqual(atual["inicio_periodo"], "2026-10-20T11:00:00Z")
        self.assertEqual(atual["fim_periodo"], "2026-10-20T12:00:00Z")
        self.assertFalse(self.redis.exists(obsoleta))
        self.assertEqual(self.redis.type(main.chave_sensor("S001")), "hash")

    def test_cidades_homonimas_sao_separadas_por_uf(self):
        self.banco.Sensores.update_one({"_id": "S002"}, {"$set": {"localizacao.uf": "RS"}})
        self.banco.Medicoes.insert_many([self.medicao("S001", 10), self.medicao("S002", 20)])
        sensores, cidades = agregar(self.banco, self.inicio, self.fim)
        self.assertEqual({r["uf"] for r in cidades}, {"SC", "RS"})
        main.salvar_ultimos(self.redis, sensores, cidades)
        self.assertTrue(self.redis.exists(main.chave_cidade("SC", "Chapecó")))
        self.assertTrue(self.redis.exists(main.chave_cidade("RS", "Chapecó")))


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
