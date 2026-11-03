# Roteiro por integrante — 5 de novembro de 2026

## Divisão e tempo

Sugestão: oito a dez minutos no total, cerca de dois minutos por integrante. A ordem acompanha o caminho dos dados. As falas abaixo servem para ensaiar; expliquem com suas palavras e apontem o resultado na tela.

| Ordem | Integrante | Responsabilidade | Código principal |
| --- | --- | --- | --- |
| 1 | Gabriel Correa Bussularo | Banco, modelagem e cadastro dos sensores | `mongodb.py` |
| 2 | João Paulo Mascarello | Geração, armazenamento e consulta das medições | `mongodb.py` e `consultar` em `main.py` |
| 3 | Erik Peter Diniz | Agregações horárias, médias e máximos | `agregacoes.py` |
| 4 | Thiago Antonio Virmes | Redis, Hashes, atualização e testes | `main.py` e `test_integracao.py` |

**Ajuste da divisão original:** a geração está em `mongodb.py`, mas a consulta está na função `consultar` de `main.py`. João Paulo apresenta essa função também. Thiago apresenta a validação de `main.py` e os testes de `test_integracao.py`. A divisão organiza a apresentação, sem declarar autoria individual dos arquivos.

## Antes de começar

1. Neste computador, usar a pasta **`projetoSensores-ambiente`**, que contém o ambiente instalado. `projetoSensores` é a pasta limpa para entrega.
2. Abrir `APRESENTAR.cmd` na pasta de ambiente antes da aula e conferir `[SUCESSO] Demonstração concluída!`. Isso gera dados recentes e verifica os bancos.
3. Deixar um PowerShell aberto em `projetoSensores-ambiente` e os três programas no editor. Os comandos abaixo pressupõem essa pasta. Não é necessário ativar a `.venv`.
4. Na apresentação, usar os comandos individuais para cada pessoa explicar sua etapa. `APRESENTAR.cmd` executa tudo sem pausas e é melhor para a conferência inicial.
5. Em outro computador, extrair `entrega.zip` e executar `INSTALAR.cmd` com internet antes da aula. Na máquina preparada, a execução normal não precisa de internet.

## 1. Gabriel — MongoDB e sensores

**Na tela:** abrir `mongodb.py` em `conectar_mongo`, `SENSORES` e `preparar_banco`. Mostrar um cadastro completo e a criação do índice, sem ler os seis cadastros.

**Executar:**

```powershell
.\.venv\Scripts\python.exe main.py verificar
.\.venv\Scripts\python.exe main.py preparar
```

**Fala sugerida:**

> Nosso trabalho simula sensores ambientais que medem PM2.5, PM10, CO₂, temperatura e umidade. Tudo funciona pelo console. O MongoDB guarda os dados históricos e o Redis guarda os resumos mais recentes.
>
> No MongoDB, usamos o banco QualidadeAr e duas coleções: Sensores e Medicoes. O cadastro tem identificação, modelo, descrição, localização, situação de atividade e grandezas medidas. O sensor é identificado pelo campo _id, que aparece como sensor_id nas medições.
>
> Cadastramos seis sensores: dois em Chapecó, dois em Xanxerê e dois em Concórdia. Os dados e as coordenadas são ilustrativos. O cadastro usa upsert: atualiza um sensor existente ou insere um novo, permitindo executar a preparação novamente.
>
> Também criamos o índice por sensor e timestamp. Ele apoia as consultas por sensor e intervalo temporal. No console podemos ver os seis sensores cadastrados e a conexão com os dois bancos funcionando.

**Apontar:** `MongoClient`, o `ping`, um documento de `SENSORES`, `replace_one(..., upsert=True)` e o índice `{sensor_id: 1, timestamp: -1}`. O índice composto mostrado não é responsável por impedir duplicatas; a geração faz isso pelo `_id` determinístico.

**Passagem:** “Com os sensores cadastrados, o João Paulo vai mostrar como geramos e consultamos as medições.”

## 2. João Paulo — geração e consulta

**Na tela:** abrir `mongodb.py` em `intervalo_historico`, `construir_medicao` e `gerar_medicoes`. Depois mostrar `consultar` em `main.py`.

**Executar:**

```powershell
.\.venv\Scripts\python.exe main.py gerar --horas 24
.\.venv\Scripts\python.exe main.py consultar --sensor S001 --ultimas-horas 1 --limite 3
.\.venv\Scripts\python.exe main.py consultar --cidade "Chapecó" --uf SC --ultimas-horas 1 --limite 3
```

**Fala sugerida:**

> Geramos uma medição a cada cinco minutos, durante 24 horas completas, para cada sensor. São 12 medições por hora, 288 por sensor e 1.728 na janela inteira.
>
> construir_medicao produz valores artificiais para as cinco grandezas. gerar_medicoes percorre os horários de cinco em cinco minutos e grava os documentos. Cada documento contém sensor_id, timestamp e os valores medidos.
>
> As datas usam UTC, e a janela termina no início da hora atual para considerar somente horas completas. O identificador combina sensor e instante, e a escrita usa upsert. Assim, repetir os mesmos horários não duplica os documentos.
>
> A consulta de S001 encontrou 12 registros na última hora completa. Pedi para exibir apenas três, mas o total aparece antes da lista. Para Chapecó, são 24 medições, porque temos dois sensores na cidade.
>
> Na função consultar, o filtro inclui o início e exclui o fim do período. Uma leitura exatamente às 11 horas entra na janela seguinte e não é contada nas duas horas.

**Apontar:** os campos retornados por `construir_medicao`, `timedelta(minutes=5)`, `UpdateOne`, `upsert=True` e, em `consultar`, os operadores `$gte` e `$lt`.

**Cuidado:** o total histórico acumulado pode ultrapassar 1.728 após execuções em horas diferentes. Destaquem a quantidade da janela de 24 horas. Se pedirem datas explícitas, usem `--inicio` e `--fim` com datas recém-mostradas no console, em vez das datas antigas do relatório.

**Passagem:** “Agora que temos o histórico e conseguimos consultá-lo, o Erik vai mostrar como produzimos os resumos horários.”

## 3. Erik — médias e estatísticas

**Na tela:** abrir `agregacoes.py` em `grupo_estatisticas`, `pipeline_por_sensor` e `pipeline_por_cidade`.

**Executar:**

```powershell
.\.venv\Scripts\python.exe main.py agregar --horas 24
```

O comando também publica os resultados no Redis. Erik explica os cálculos do MongoDB; Thiago explica a publicação em seguida. Escolher um resumo de sensor e um de cidade para detalhar no console.

**Fala sugerida:**

> Os cálculos acontecem no próprio MongoDB, usando pipelines de agregação. O Python envia o pipeline e recebe os resumos prontos.
>
> O match seleciona as medições válidas no intervalo. O group reúne as leituras por sensor e hora. Usamos sum para contar, avg para as cinco médias e max para os máximos de PM2.5 e PM10. O project organiza o documento de saída.
>
> As janelas são fixas em UTC. O dateTrunc identifica o início da hora e o dateAdd calcula o fim exclusivo. Cada resumo tem quantidade, cinco médias, dois máximos e os limites do período.
>
> Para calcular por cidade, o lookup associa as medições ao cadastro do sensor, de onde obtemos cidade e UF. Depois agrupamos diretamente essas medições por cidade e hora.
>
> Não fazemos a média simples das médias dos sensores. Por exemplo, se um sensor tem 10 e 30 e outro tem apenas 100, a média global é 140 dividido por 3, aproximadamente 46,67. A média das médias daria 60, pois atribuiria o mesmo peso a sensores com quantidades diferentes de registros.
>
> Em 24 horas, temos 144 resumos de sensor, pois são seis vezes 24, e 72 de cidade, pois são três vezes 24. No cenário gerado, cada resumo de sensor tem 12 medições e cada resumo de cidade tem 24.

**Apontar:** `$match`, `$group`, `$avg`, `$max`, `$project`, `$lookup` e `$unwind`. Explicar que `filtro_validos` aceita temperatura negativa e rejeita dados não numéricos ou não finitos. No console, apontar uma média e um máximo com a unidade correspondente.

**Passagem:** “Os resumos já estão calculados. O Thiago vai mostrar como guardamos os mais recentes no Redis e como validamos o resultado.”

## 4. Thiago — Redis e testes

**Na tela:** abrir `main.py` em `chave_sensor`, `chave_cidade`, `mapa_resumo`, `salvar_ultimos` e `validar`. Deixar `test_integracao.py` disponível.

**Executar:**

```powershell
.\.venv\Scripts\python.exe main.py redis
.\.venv\Scripts\python.exe main.py validar
.\.venv\Scripts\python.exe test_integracao.py
```

Mostrar um Hash de cidade e um de sensor, sem ler todos os nove. Depois destacar a validação aprovada e os cinco testes com resultado `OK`.

**Fala sugerida:**

> Depois da agregação, selecionamos a última hora disponível de cada sensor e cidade e gravamos no Redis. Usamos Hashes, que guardam campos e valores dentro de uma chave.
>
> Temos seis chaves de sensores e três de cidades. Um exemplo é qualidadear:sensor:S001. Para cidade, usamos UF e nome normalizado, como qualidadear:cidade:SC:chapeco, sem acento e em minúsculas.
>
> Cada Hash contém os limites do período, a quantidade, cinco médias e dois máximos. As estatísticas são armazenadas como texto com duas casas decimais. O histórico completo continua no MongoDB; o Redis guarda somente a visão recente.
>
> A publicação usa uma transação Redis para substituir os resumos da sincronização. Ela ocorre quando executamos agregar ou demonstrar. Nesta etapa ainda não existe um agendador automático.
>
> O comando validar confere os 288 horários de cada sensor, os resumos das 24 horas e todos os campos da última hora entre MongoDB e Redis.
>
> Também executamos cinco testes de integração com bancos reais. Eles verificam geração sem duplicatas, médias e máximos, sensores com quantidades diferentes de registros, dados inválidos, cidades separadas por UF e armazenamento da última hora. Usam dados temporários e preservam o histórico da apresentação.

**Apontar:** normalização das chaves, seleção dos últimos resumos, `pipeline(transaction=True)` e `hset`. Se pedirem um teste específico, mostrar `test_media_cidade_usa_registros_e_nao_media_das_medias`, que comprova o exemplo de Erik.

**Encerramento:** “Demonstramos o fluxo da Etapa I: histórico no MongoDB, estatísticas horárias por pipelines e últimos resumos em Hashes Redis, com consulta e validação pelo console. O pacote entregue contém os programas, as instruções, as evidências e o relatório com referências e declaração de uso de IA.”

## Versão de cinco minutos

| Integrante | Tempo | Manter na fala |
| --- | --- | --- |
| Gabriel | 1 minuto | Arquitetura, coleções, seis sensores e índice |
| João Paulo | 1 minuto | Conta dos 1.728 registros, upsert e uma consulta |
| Erik | 1 minuto e 30 segundos | Pipeline, lookup e exemplo da média global |
| Thiago | 1 minuto e 30 segundos | Um Hash, nove chaves, validação e encerramento |

Deixar resultados prontos no console antes de começar e usar `evidencias/testes.txt` para mostrar os testes. Manter pelo menos uma execução ao vivo, como uma consulta e a validação. Evitar explicar cada linha do código.

## Se algo falhar

- Erro de conexão: executar `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\iniciar.ps1` na pasta de ambiente.
- Janela antiga na validação: executar `.\.venv\Scripts\python.exe main.py demonstrar` para gerar e sincronizar a janela atual.
- Falta da `.venv`: conferir se estão na pasta `projetoSensores-ambiente`, em vez da pasta limpa de entrega.
- Outro computador sem instalação: mostrar as evidências registradas e informar que são de uma execução anterior; não apresentá-las como execução ao vivo.
- Não usar `--reiniciar` na apresentação: ele apaga o histórico do projeto e não é necessário.

## Perguntas que a equipe deve saber responder

- Por que dois bancos? MongoDB guarda documentos históricos; Redis oferece acesso rápido a um resumo recente.
- Por que usar UTC? Evita ambiguidade ao comparar e agrupar horários de localidades diferentes.
- Por que não duplicam os registros? O `_id` é derivado de sensor e instante, e a escrita usa `upsert`.
- O Redis é atualizado sozinho? Nesta etapa, a atualização é explícita pelo comando `agregar` ou pela demonstração; não há agendador.
- Os valores são medições reais? Não. Foram gerados artificialmente, assim como as coordenadas são ilustrativas.
- Qual Redis está instalado? Redis compilado para Windows pelo projeto comunitário redis-windows; a escolha está descrita no relatório.
- Como foi usada IA? Como apoio à revisão, correções, instalação, testes e documentação. A equipe precisa compreender e revisar o material entregue.
