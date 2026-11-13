# Qualidade do ar — MongoDB + Redis + Python

Trabalho prático, Etapa I. Toda a operação ocorre pelo console. Dados e coordenadas são simulados.

## Executar neste computador

Na primeira execução de uma pasta que contém apenas os arquivos de entrega, abra **INSTALAR.cmd** com internet disponível. Depois abra **APRESENTAR.cmd** com dois cliques. Ele inicia MongoDB e Redis em segundo plano, prepara os sensores, gera as últimas 24 horas completas em UTC, consulta o histórico, calcula resumos, atualiza os Hashes e valida o resultado. A saída fica em `evidencias/demonstracao.txt`.

Após a instalação, Python fica no perfil do usuário; MongoDB e Redis ficam na pasta `.local` do projeto. O ambiente Python fica em `.venv`. Os bancos são iniciados somente em `127.0.0.1`. Após reiniciar o Windows, abra novamente `APRESENTAR.cmd`.

## Instalar em outro Windows 11 de 64 bits

Extraia todo o pacote em uma pasta com permissão de escrita. Com internet disponível e `winget` instalado, abra `INSTALAR.cmd` ou execute no PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\instalar.ps1
```

Depois abra `APRESENTAR.cmd`. A instalação não exige Docker nem WSL. O script confere SHA256 dos arquivos baixados dos bancos. Não transfira `.venv` entre computadores; ela será recriada.

**Redis no Windows:** esta instalação usa a compilação comunitária [redis-windows](https://github.com/redis-windows/redis-windows), versão 8.10.3, com runtime Cygwin. Ela não é distribuída pela Redis Ltd. A [documentação oficial](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-windows/) orienta usar WSL; em Linux/WSL também se pode executar o mesmo código Python contra o Redis oficial.

## Comandos individuais

Primeiro inicie os bancos:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\iniciar.ps1
```

Não é necessário ativar o ambiente virtual. Use seu executável diretamente:

```powershell
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe main.py verificar
.\.venv\Scripts\python.exe main.py preparar
.\.venv\Scripts\python.exe main.py gerar --horas 24
.\.venv\Scripts\python.exe main.py consultar --sensor S001 --ultimas-horas 1
.\.venv\Scripts\python.exe main.py consultar --cidade "Chapecó" --uf SC --ultimas-horas 1
.\.venv\Scripts\python.exe main.py agregar --horas 24
.\.venv\Scripts\python.exe main.py agregar --horas 24 --mostrar-todas
.\.venv\Scripts\python.exe main.py redis
.\.venv\Scripts\python.exe main.py validar
.\.venv\Scripts\python.exe test_integracao.py
```

Também há consulta com limites explícitos. Substitua as datas pelo período gerado mostrado no console:

```powershell
.\.venv\Scripts\python.exe main.py consultar --sensor S001 --inicio "2026-11-03T15:00:00Z" --fim "2026-11-03T16:00:00Z" --limite 12
```

Os intervalos incluem o início e excluem o fim. Datas precisam informar fuso horário. O nome da cidade na consulta deve corresponder ao cadastro, inclusive acentos. Nas chaves Redis os nomes ficam sem acentos e em minúsculas.

`validar` confere o cenário didático padrão: seis sensores, três cidades, últimas 24 horas completas e últimos nove Hashes sincronizados. Se os dados ficaram antigos, execute `demonstrar` novamente. O histórico acumulado pode ultrapassar 1.728 documentos ao executar em horas/dias diferentes; a janela de 24 horas continua com 1.728.

`gerar --reiniciar` é opcional e apaga todas as medições da coleção `QualidadeAr.Medicoes` e chaves `qualidadear:*` antes de uma nova demonstração. Não é necessário usá-lo na apresentação normal.

## Estrutura da entrega

| Arquivo | Função |
| --- | --- |
| `mongodb.py` | Conexão, cadastro, índice e geração de medições |
| `agregacoes.py` | Filtros e pipelines horários por sensor e cidade |
| `main.py` | Console, consultas, Hashes e validação |
| `test_integracao.py` | Cinco testes contra bancos reais em espaços temporários |
| `requirements.txt` | Bibliotecas Python com versões fixadas |
| `instalar.ps1` / `iniciar.ps1` | Instalação e inicialização local |
| `APRESENTAR.cmd` / `apresentar.ps1` | Demonstração completa e registro da saída |
| `evidencias/` | Saídas reais da demonstração e testes |

`dados/mongo` armazena o histórico local; `dados/redis` armazena o AOF do Redis; `logs/mongodb.log` contém o log do MongoDB. Os bancos ficam abertos após fechar a janela de apresentação. Essas pastas e os executáveis não fazem parte do pacote de entrega: são recriados pelos scripts.

As conexões podem ser configuradas pelas variáveis de ambiente `MONGODB_URI` e `REDIS_URL`. Os scripts de inicialização provisionam apenas os endereços locais padrão; para servidores externos, inicie os serviços separadamente e use os comandos Python.
