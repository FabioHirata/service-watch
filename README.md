# Service Watch — Python + SQLite + JavaScript

Central de operações de portfólio com **coletor HTTP e API escritos em Python**, persistência SQLite transacional e interface responsiva em português, inglês e japonês. Sem clientes, credenciais ou sistemas privados envolvidos.

## Dois modos, sem confundir demonstração com monitoramento

| Modo | Fonte dos dados | Persistência | Onde funciona |
|---|---|---|---|
| **Demo estática** (padrão) | 1.152 observações fictícias fixas e incidentes de exemplo | localStorage do navegador | Qualquer servidor estático / GitHub Pages |
| **API Python** (`?mode=api`) | Respostas HTTP efetivamente coletadas dos destinos da configuração local | SQLite no servidor local | Processo Python abaixo |

**GitHub Pages não executa Python.** A página publicada permanece uma demonstração estática; o seletor de API requer executar o backend local. Se a API estiver indisponível, a interface mostra o erro e **não substitui dados por fixtures estáticas**.

Por padrão, o backend consulta apenas seus próprios quatro endpoints de teste em `127.0.0.1`. São requisições HTTP reais para **serviços de teste locais**, não sistemas de produção. Um endpoint retorna 503 deliberadamente. Não há sondagens externas nem coleta automática ao iniciar.

## Executar o backend completo

Requisitos: **Python 3.11+**. Zero dependências de terceiros, contas ou serviços pagos.

```sh
cd service-watch
python3 -m backend.server
# Abra http://127.0.0.1:8080/?mode=api
```

Clique em **Coletar agora**. A primeira coleta grava quatro respostas no SQLite; as métricas antes da coleta mostram ausência de dados, não 100% inventados. Crie um incidente, registre uma atualização e encerre-o. Ao reiniciar o processo com o mesmo banco, observações e histórico permanecem.

```sh
python3 -m backend.server --port 8090 --db ./service-watch.sqlite3
# Configuração opcional — ajuste as URLs ao seu ambiente autorizado:
python3 -m backend.server --config backend/config.example.json
```

O servidor se vincula exclusivamente a `127.0.0.1`; use essa origem exata no navegador, não `localhost`. `Ctrl+C` encerra. O arquivo SQLite é criado localmente e ignorado pelo Git. Não existe endpoint para apagar o banco ou o histórico. Para uma sessão independente, escolha outro arquivo `--db`.

## Executar só a demonstração estática

```sh
python3 -m http.server 8081 --directory dist
# Abra http://127.0.0.1:8081/ (sem ?mode=api)
```

Sem instalação nem build. Use HTTP: módulos JavaScript não funcionam consistentemente em `file://`.

## Testes

Node.js 20+ é necessário somente para testar o frontend.

```sh
python3 -m unittest discover -s tests_python -v
npm test
npm run check
# Ou os três juntos:
npm run test:all
```

Os testes Python sobem servidores HTTP falsos em portas efêmeras de loopback: sucesso, 503, redirecionamento não seguido, timeout, resposta lenta byte a byte, limite de cabeçalhos, origem/Host, concorrência, persistência e agregação SQL. **Não fazem requisições externas.** Os testes JS cobrem domínio, idiomas, controlador, transporte API, erros e separação entre demo e backend. Veja `docs/QA.md` para limites da verificação visual.

## Arquitetura

```text
Navegador (PT / EN / JA)
  ├─ modo demo → funções puras JS → localStorage
  └─ modo API → fetch same-origin → servidor HTTP Python
                                 ├─ domínio de incidentes → SQLite + histórico
                                 ├─ agregações SQL → métricas da janela completa
                                 └─ coleta manual → allowlist local → HTTP(S)
                                                    → observações SQLite
```

- `backend/config.py`: configuração validada e allowlist de destinos.
- `backend/collector.py`: sockets HTTP(S), deadline absoluto e coleta concorrente limitada a quatro tarefas.
- `backend/repository.py`: esquema SQLite, transações, validação, índice único parcial contra incidentes ativos duplicados, agregação e retenção.
- `backend/server.py`: rotas JSON, servidor de arquivos estáticos, origem/Host e limites de entrada.
- `dist/backend.js`: transporte API, validação de snapshots, status observado.
- `dist/domain.js`: domínio puro e dados da demo estática.
- `dist/app.js`, `dist/i18n.js`, `dist/style.css`: interface e localização.

## API local

Todos os POSTs exigem `Content-Type: application/json`. As respostas bem-sucedidas são snapshots no mesmo formato de `GET /api/state`; erros têm `{"error":"codigo"}`. `?hours=1|6|24` seleciona a janela, inclusive nas respostas de POST.

| Método | Rota | Corpo |
|---|---|---|
| GET | `/api/state?hours=24` | — |
| POST | `/api/collect` | `{}` apenas; URLs nunca são aceitas |
| POST | `/api/incidents` | `serviceId`, `title`, `severity`, `message` |
| POST | `/api/incidents/INC-1/updates` | `status`, `message` |

```sh
curl -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8080/api/collect
curl -H 'Content-Type: application/json' \
  -d '{"serviceId":"checkout","title":"Checkout indisponível","severity":"outage","message":"Fixture local retornando HTTP 503."}' \
  http://127.0.0.1:8080/api/incidents
```

Serviços fixos: `api`, `checkout`, `queue`, `database`. Impacto: `degraded` ou `outage`. Status: `investigating`, `identified`, `monitoring`, `resolved`. Título: 5–100 caracteres; mensagem: 10–600. Incidente resolvido é imutável; uma nova ocorrência requer novo registro. A mesma observação nunca é reescrita ao encerrar incidentes.

## Segurança dos destinos e limites

Apenas um **arquivo de configuração local confiável** pode alterar os destinos. Cada URL precisa corresponder a uma origem exata de `allowed_origins`, com esquema, IP e porta explícitos. São aceitos `127.0.0.1`, `::1` e IPs públicos globais explicitamente autorizados. DNS, credenciais em URL, metadata/link-local, LAN privada, multicast, redirecionamentos e proxies de ambiente não são usados. HTTPS verifica o certificado para o IP informado. Nomes DNS e IPs privados corporativos foram conscientemente excluídos desta versão para reduzir superfície de SSRF; não desative validações para contornar isso.

Cada sonda tem deadline de 0,1–5 segundos (padrão 2), limite de 16 KiB de cabeçalhos e não baixa o corpo da resposta. Status 2xx é normal; demais códigos e falhas são observações malsucedidas. A latência mede até o fim dos cabeçalhos, não a transferência completa. A API não aceita destinos, headers de autenticação nem credenciais. Coletas simultâneas retornam conflito em vez de criar carga duplicada.

A API valida Host/Origin, recusa POSTs cross-site, exige JSON e limita corpos a 16 KiB. Isso reduz CSRF/DNS rebinding, mas **não é autenticação**: processos e pessoas com acesso à máquina podem operar a API. Não exponha essa aplicação sem um projeto próprio de autenticação, autorização, TLS, controle de acesso, rate limiting e deployment. O servidor HTTP da biblioteca padrão não é um servidor de produção.

## Semântica das métricas

- Backend: janela `(agora − duração, agora]`, baseada no horário da consulta; disponibilidade = amostras 2xx ÷ amostras totais. Não é SLA nem disponibilidade contínua medida. Coletas manuais irregulares têm o mesmo peso por amostra.
- SQLite agrega **todas** as amostras da janela; gráficos recebem no máximo as últimas 288 por serviço. A média considera apenas respostas normais.
- Sem observações: métricas nulas e status desconhecido. Última observação malsucedida ou incidente de indisponibilidade aberto sinaliza indisponibilidade; outros incidentes abertos sinalizam degradação.
- Retenção de observações: 30 dias, removidas ao gravar uma nova coleta. Histórico de incidentes permanece. Não há exportação, backup automático, paginação de incidentes nem auditoria inviolável.
- Demo estática: referência fixa em **30/10/2026, 12:00 UTC**, 288 amostras por serviço a cada cinco minutos. O status dessa demo vem de incidentes manuais, separado das observações fictícias.
- Todos os horários aparecem em UTC. Conteúdo digitado pelo usuário não é traduzido automaticamente. Idioma e armazenamento da demo não se misturam com dados SQLite.

## Evolução possível, não implementada

Um coletor agendado com controle de carga, autenticação, observabilidade do próprio coletor, alertas, migrações versionadas, paginação, backups e coleta distribuída seriam etapas separadas. O backend atual é funcional e local, não uma plataforma de produção. Nenhuma integração externa ou informação sensível é necessária para explorar o projeto.

## English

A portfolio project with a real **Python HTTP collector/API, transactional SQLite storage and multilingual JavaScript frontend**. Run `python3 -m backend.server`, open `http://127.0.0.1:8080/?mode=api`, then collect manually. Defaults probe only local test fixtures; checkout deliberately returns 503. No startup probing, external accounts or dependencies. Static hosting runs the separate fictional demo only. Configured targets must be explicitly allowlisted IP literals; redirects/DNS/private-network ranges are blocked. This loopback-only server has no authentication and is not production hosting. Tests: `python3 -m unittest discover -s tests_python -v`, `npm test`, `npm run check`.

## 日本語

**Python 製 HTTP コレクター・API、SQLite のトランザクション処理、多言語 JavaScript UI**を備えたポートフォリオ作品です。`python3 -m backend.server` を実行し、`http://127.0.0.1:8080/?mode=api` を開いて手動で収集してください。初期設定はローカルのテスト用エンドポイントのみを対象とし、決済のテスト用応答は意図的に 503 を返します。起動時の自動収集や外部サービスへのアクセスはありません。静的ホスティングでは、架空データのデモのみが動作します。宛先 IP とオリジンは設定ファイルで明示的に許可する必要があり、DNS・リダイレクト・プライベートネットワークへのアクセスを制限しています。認証のないローカル専用サーバーであり、本番運用向けではありません。
