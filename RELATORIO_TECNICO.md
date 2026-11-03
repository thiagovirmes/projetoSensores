# Integração MongoDB + Redis com Python

## Identificação

Trabalho prático — Etapa I: monitoramento ambiental por sensores IoT.

Instituição: Universidade Comunitária da Região de Chapecó (Unochapecó)

Curso: Sistemas de Informação — 4º período, turma AX

Disciplina: Banco de Dados e Novas Tecnologias — componente 1030941

Professora: Monica Tissiani de Toni Pereira

Integrantes: Thiago Antonio Virmes; João Paulo Mascarello; Erik Peter Diniz; Gabriel Correa Bussularo.

Data da verificação técnica: 3 de novembro de 2026.

Apresentação prevista: 5 de novembro de 2026.

## 1. Objetivo e contexto

O protótipo simula dispositivos IoT de monitoramento de PM2.5, PM10, CO₂, temperatura e umidade. O objetivo é manter um histórico de medições no MongoDB, consultar esse histórico e produzir estatísticas horárias por sensor e cidade, publicando os resumos mais recentes em Hashes no Redis. A aplicação apresenta os resultados pelo console, conforme o escopo da Etapa I.

Dados e coordenadas são ilustrativos. PM2.5 e PM10 são expressos em µg/m³; CO₂ em ppm; temperatura em °C; umidade relativa em %. Os resultados não representam avaliação de qualidade do ar de localidades reais.

## 2. Arquitetura e ferramentas

Fluxo: gerador Python → MongoDB (`QualidadeAr.Sensores` e `QualidadeAr.Medicoes`) → pipelines de agregação executados no MongoDB → publicação por Python → Redis (Hashes recentes) → consulta pelo console.

O MongoDB é a fonte do histórico. Os resumos do Redis podem ser reconstruídos executando novamente a agregação. A atualização é acionada manualmente; nesta etapa não há interface gráfica, comunicação com equipamentos físicos nem processamento contínuo.

| Ferramenta | Versão verificada | Uso |
| --- | --- | --- |
| Windows 11 Pro x64 | Ambiente local | Execução dos programas |
| Python | 3.13.17 | Gerador, console, integração e testes |
| MongoDB Community Server | 8.0.34 | Histórico e agregações |
| Redis | 8.10.3 | Hashes dos últimos resumos |
| PyMongo | 4.19.0 | Driver de acesso ao MongoDB |
| redis-py | 8.1.0 | Cliente Redis em Python |
| dnspython | 2.9.1 | Dependência do PyMongo |
| PowerShell e winget | Ferramentas do Windows | Instalação e inicialização |
| OpenAI Codex | Modelo específico não registrado | Apoio de IA à revisão e implementação |
| python-docx | 1.2.0 | Exportação do relatório para Word |
| ReportLab | 5.1.0 | Exportação do relatório para PDF |
| PyMuPDF | 2.1 | Conferência de conteúdo e prévia visual do PDF |

Python foi instalado pelo winget a partir do pacote da Python Software Foundation. MongoDB foi obtido no site oficial. O ambiente Python do projeto foi isolado em `.venv`, com dependências registradas em `requirements.txt`.

Como não havia WSL ou Docker instalado, foi usada a compilação comunitária Redis para Windows, do repositório redis-windows, com runtime Cygwin. Ela não é uma distribuição oficial da Redis Ltd.; a orientação oficial para Redis em Windows utiliza WSL. Essa escolha viabilizou a demonstração local sem reinicialização para instalar um subsistema Linux. As referências de instalação estão na seção 10. Os arquivos dos bancos foram verificados com SHA256: MongoDB contra o checksum do fornecedor e Redis contra o digest publicado na versão do repositório.

MongoDB e Redis escutam em `127.0.0.1`, nas portas 27017 e 6379. Os dados do MongoDB ficam em `dados/mongo`; o Redis usa AOF em `dados/redis`. Os executáveis portáteis ficam em `.local`. Não foram instalados serviços de inicialização automática; `iniciar.ps1` inicia os processos locais quando necessário.

### Divisão da apresentação

Gabriel Correa Bussularo apresenta a configuração do MongoDB, a modelagem e o cadastro dos sensores em `mongodb.py`. João Paulo Mascarello apresenta a geração de medições em `mongodb.py` e a consulta implementada em `main.py`. Erik Peter Diniz apresenta os pipelines e as estatísticas em `agregacoes.py`. Thiago Antonio Virmes apresenta a integração com Redis e a validação em `main.py`, além dos testes em `test_integracao.py`. Essa distribuição organiza a apresentação; não atribui autoria individual dos arquivos. As falas, comandos e transições estão em `ROTEIRO_APRESENTACAO.md`.

## 3. Modelagem no MongoDB

O banco chama-se `QualidadeAr` e contém as coleções `Sensores` e `Medicoes`.

`Sensores` possui `_id` textual, modelo, descrição, localização com cidade/UF/latitude/longitude, situação de atividade e lista de grandezas. Foram cadastrados S001 e S002 em Chapecó/SC; S003 e S004 em Xanxerê/SC; S005 e S006 em Concórdia/SC. A preparação usa substituição com `upsert` para permitir reexecução sem duplicar sensores.

Exemplo resumido do cadastro:

```json
{"_id":"S001","modelo":"AirMonitor-200","localizacao":{"cidade":"Chapecó","uf":"SC","latitude":-27.1009,"longitude":-52.6157},"ativo":true,"grandezas":["PM2.5","PM10","CO2","temperatura","umidade"]}
```

Cada documento de `Medicoes` contém `sensor_id`, `timestamp`, `pm25`, `pm10`, `co2`, `temperatura` e `umidade`. O timestamp é armazenado como BSON Date, a partir de um datetime com fuso UTC. O `_id` é composto pelo sensor e instante, como `S001:20261020T100000Z`.

O índice composto é `{sensor_id: 1, timestamp: -1}`, chamado `sensor_id_1_timestamp_-1`. Ele atende ao padrão de consulta por sensor e período. Os resumos são calculados sob demanda e não são gravados como uma terceira coleção.

## 4. Geração e consulta

O gerador percorre uma grade de cinco minutos para cada sensor. Em 24 horas, cada sensor recebe `24 × 12 = 288` medições, totalizando `6 × 288 = 1.728` documentos. O período termina no início da hora UTC atual, para utilizar apenas horas completas.

Valores artificiais combinam uma variação diária e um gerador pseudoaleatório com semente derivada de sensor e instante. Assim, o mesmo sensor no mesmo instante produz os mesmos dados. As escritas usam `UpdateOne` com `upsert` e lotes de até mil operações. Reexecutar a mesma janela atualiza os registros existentes, sem multiplicar documentos. Executar em horas posteriores acrescenta histórico, de modo que o total acumulado pode superar 1.728.

O comando `consultar` aceita sensor ou cidade, UF opcional para a cidade e intervalo temporal. Os limites usam `$gte` para início e `$lt` para fim: `[início, fim)`. Datas sem fuso são rejeitadas. As consultas apresentam quantidade total e uma lista limitada de registros, com unidades de medida.

Exemplos:

```powershell
.\.venv\Scripts\python.exe main.py consultar --sensor S001 --ultimas-horas 1
.\.venv\Scripts\python.exe main.py consultar --cidade "Chapecó" --uf SC --ultimas-horas 1
```

## 5. Agregações e validade dos registros

Os pipelines são executados pelo MongoDB usando `Medicoes.aggregate`, conforme o modelo de processamento por etapas da documentação oficial. O Python recebe os resultados prontos, sem calcular as estatísticas do protótipo em memória.

Por sensor, o pipeline aplica `$match`, agrupa por sensor e hora com `$group`, projeta os campos e ordena os resultados. A hora é determinada com `$dateTrunc` em UTC; `$dateAdd` produz o fim exclusivo da janela. Os operadores exigem MongoDB 5.0 ou superior, condição conferida pelo comando `verificar`.

Por cidade, o pipeline associa medições e sensores com `$lookup`, usando `sensor_id` e `_id`, e aplica `$unwind`. Em seguida agrupa diretamente os registros por cidade, UF e hora. Isso calcula a média global das medições, inclusive quando os sensores possuem quantidades diferentes de registros.

Por exemplo, dois registros 10 e 30 de S001 e um registro 100 de S002 resultam em `(10 + 30 + 100) / 3 = 46,6667`. A média simples das médias dos sensores seria `(20 + 100) / 2 = 60`, inadequada para a média global solicitada.

Cada resumo contém `qt_medicoes`, as cinco médias, `pm25_max`, `pm10_max`, `inicio_periodo` e `fim_periodo`. A contagem usa `$sum: 1`; as médias usam `$avg`; os máximos usam `$max`; `$project` organiza o documento retornado.

São aceitos registros com identificador textual não vazio, timestamp do tipo data e as cinco grandezas numéricas escalares e finitas. PM2.5, PM10 e CO₂ precisam ser não negativos; umidade deve estar entre 0 e 100. Temperaturas negativas são válidas. Campos ausentes, tipos incorretos, arrays e valores NaN/infinito são excluídos da agregação. A regra descarta o registro inteiro quando alguma grandeza não é válida. Na agregação por cidade, registros sem cadastro correspondente de sensor são descartados pela associação.

## 6. Hashes no Redis

O prefixo do projeto é `qualidadear:`. As chaves são `qualidadear:sensor:<ID>` e `qualidadear:cidade:<UF>:<cidade-normalizada>`. A normalização remove acentos, transforma em minúsculas e substitui espaços por hífens. Exemplos: `qualidadear:sensor:S001` e `qualidadear:cidade:SC:chapeco`.

Cada Hash contém os dez campos de resumo: os dois limites da janela, quantidade de medições, cinco médias e dois máximos. Datas são strings ISO 8601 UTC terminadas em `Z`; quantidades são inteiros em texto; estatísticas são textos com duas casas decimais. O formato segue a estrutura de campos e valores dos Hashes Redis documentada na referência oficial.

Entre os resumos calculados na janela solicitada, apenas a última hora disponível de cada sensor/cidade é publicada. Uma transação Redis remove as chaves de entidades que deixaram de aparecer e substitui os Hashes atuais. A operação é uma sincronização completa da janela solicitada: deve-se utilizar uma janela que contenha todas as entidades desejadas. Para o cenário padrão são seis Hashes de sensores e três de cidades. Não há TTL; a atualização é feita explicitamente pelo comando `agregar` ou `demonstrar`.

## 7. Execução e resultados observados

A demonstração foi executada com sucesso em 3 de novembro de 2026, usando os bancos reais instalados neste computador. A janela registrada foi de `2026-11-02T16:00:00Z` até `2026-11-03T16:00:00Z`, com fim exclusivo. Novas execuções usam a janela correspondente à hora atual.

| Verificação | Resultado observado |
| --- | --- |
| Sensores cadastrados | 6 em 3 cidades |
| Medições na janela | 1.728 |
| Grade temporal | 288 horários por sensor, espaçados de cinco minutos |
| Resumos horários por sensor | 144, com 12 medições cada |
| Resumos horários por cidade | 72, com 24 medições cada |
| Hashes recentes no Redis | 9 |
| Consulta de S001 na última hora | 12 medições |
| Consulta de Chapecó na última hora | 24 medições |
| Correspondência Redis/MongoDB | Campos conferidos pela validação |
| Testes de integração | 5 aprovados |

Exemplo observado para Chapecó/SC, na janela `15:00–16:00 UTC` de 3 de novembro: 24 medições, PM2.5 médio de 11,39 µg/m³, PM10 médio de 35,73 µg/m³, CO₂ médio de 492,22 ppm, temperatura média de 18,26 °C e umidade média de 73,05%. PM2.5 máximo foi 15,93 µg/m³ e PM10 máximo foi 42,59 µg/m³.

As evidências completas estão em `evidencias/demonstracao.txt` e `evidencias/testes.txt`. O comando `validar` verifica a distribuição temporal por sensor, o total de registros válidos, a quantidade e o tamanho dos resumos em todas as 24 horas e cada campo do resumo da última hora no Redis, incluindo os dois limites do período.

Os testes usam um banco MongoDB e prefixo Redis temporários, removidos ao final. Foram verificados: separação de cidades por UF; geração idempotente e comparação independente das cinco médias e dois máximos de todos os 216 resumos; média por cidade com número desigual de registros; seleção da última hora e remoção de Hash obsoleto; exclusão de dados inválidos e do limite final, mantendo temperaturas negativas.

Para reproduzir a demonstração, basta abrir `APRESENTAR.cmd`. Para executar os testes, usar `.\.venv\Scripts\python.exe test_integracao.py`. As instruções de instalação estão no README.

## 8. Dificuldades encontradas e soluções

| Dificuldade observada | Solução aplicada |
| --- | --- |
| Comando Python apontava para o atalho da Microsoft Store | Instalação do Python no perfil do usuário e uso direto do interpretador da `.venv` |
| MongoDB e Redis não estavam disponíveis | Download, verificação de integridade, extração local e script para iniciar os bancos |
| Windows não tinha WSL/Docker | Uso documentado de compilação comunitária Redis para Windows para a demonstração local |
| Filtro original rejeitava temperatura abaixo de zero | Separação das regras de temperatura, poluentes e umidade; teste com temperatura negativa |
| Tipos inválidos poderiam comprometer as estatísticas | Exigência de valores numéricos escalares finitos e datas válidas no filtro |
| Contagem total não comprovava frequência de cada sensor | Validação de toda a grade de cinco minutos e dos resumos das 24 horas |
| Sensores podem possuir números diferentes de registros | Agregação direta das medições por cidade e teste específico com quantidades desiguais |
| Reexecução poderia duplicar dados ou deixar cache antigo | Identificador determinístico, `upsert` e substituição dos Hashes recentes |
| Faltavam documentação e dependências reproduzíveis | README, versões fixadas, roteiro e este relatório com evidências e referências |

Essas dificuldades correspondem à revisão e preparação realizadas nesta sessão. Não foram atribuídas à equipe experiências de desenvolvimento que não tenham sido relatadas.

## 9. Uso de inteligência artificial e limites

Foi utilizado OpenAI Codex como assistente de IA para analisar o enunciado e o código fornecido, localizar pendências, propor e aplicar correções, instalar ferramentas, escrever e executar testes e auxiliar na documentação. O modelo específico e eventuais usos anteriores de IA não foram informados e não são presumidos neste relatório. Esta declaração deve ser complementada pela equipe caso outras ferramentas tenham sido utilizadas.

A comprovação de funcionamento baseia-se na execução local e nos arquivos de evidência. A IA não substitui a responsabilidade dos integrantes por compreender o código, conferir a documentação, preencher a identificação e explicar o protótipo em aula.

O protótipo atende ao cenário didático configurado. Não inclui autenticação dos bancos locais, sensores físicos, agendamento ou implantação para acesso pela rede. A situação de atividade do cadastro é armazenada, mas não filtra o histórico; as estatísticas consideram medições válidas registradas no período. O relatório não estabelece limites sanitários para poluentes.

## 10. Referências consultadas

Consultas realizadas em 3 de novembro de 2026. O enunciado fornecido pelo usuário foi a referência dos requisitos; autoria e dados institucionais não foram informados.

- PYTHON SOFTWARE FOUNDATION. Python Releases for Windows. Disponível em: https://www.python.org/downloads/windows/ . Fonte de instalação do interpretador.
- MONGODB. MongoDB Community Downloads. Disponível em: https://www.mongodb.com/try/download/community-edition/releases . Fonte do pacote do servidor e checksum.
- MONGODB. Aggregation Pipeline. Disponível em: https://www.mongodb.com/docs/manual/core/aggregation-pipeline/ . Referência do processamento por etapas.
- MONGODB. $dateTrunc (expression operator). Disponível em: https://www.mongodb.com/docs/manual/reference/operator/aggregation/datetrunc/ . Referência das janelas horárias em UTC.
- MONGODB. MongoDB PyMongo Documentation. Disponível em: https://www.mongodb.com/docs/languages/python/pymongo-driver/current/ . Referência do driver Python.
- REDIS. Redis hashes. Disponível em: https://redis.io/docs/latest/develop/data-types/hashes/ . Referência das estruturas de campos e valores.
- REDIS. Install Redis on Windows. Disponível em: https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-windows/ . Orientação oficial para WSL.
- REDIS-WINDOWS. Redis for Windows. Disponível em: https://github.com/redis-windows/redis-windows . Versão usada: https://github.com/redis-windows/redis-windows/releases/tag/8.10.3 . Fonte da compilação comunitária.
- PYTHON SOFTWARE FOUNDATION. Python 3.13.12 release page. Disponível em: https://www.python.org/downloads/release/python-31312/ . Página consultada durante a pesquisa inicial; o interpretador efetivamente instalado foi o 3.13.17.
- MONGODB. Download MongoDB Community Server. Disponível em: https://www.mongodb.com/try/download/community . Página consultada para localizar o servidor Community.
- OPENAI. Codex. Disponível em: https://openai.com/codex/ . Ferramenta de IA utilizada nesta preparação; não usada como fonte de requisitos ou comprovação de execução.
- PYTHON-DOCX. Documentation. Disponível em: https://python-docx.readthedocs.io/en/latest/ . Referência da exportação para DOCX.
- REPORTLAB. ReportLab Docs. Disponível em: https://docs.reportlab.com/ . Referência da exportação para PDF.
- PYMUPDF. PyMuPDF Documentation. Disponível em: https://pymupdf.readthedocs.io/en/latest/ . Referência da conferência do documento PDF.

## Apêndice — programas e scripts entregues

Os programas principais são `mongodb.py`, `agregacoes.py` e `main.py`. As exportações PDF e DOCX incluem seu conteúdo integral ao final. O pacote também entrega `test_integracao.py`, dependências e scripts de instalação/inicialização/apresentação. Os arquivos editáveis são a referência para execução e reprodução dos resultados.
