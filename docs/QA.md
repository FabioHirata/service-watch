# Verificação — Python + SQLite + JavaScript

## Testes automatizados

`npm run test:all`: **26 testes JavaScript + 13 testes Python passando**, além da verificação de sintaxe JavaScript. Python também passou `python3 -m py_compile backend/*.py`.

### Python (servidores locais reais de teste)
- HTTP 200/503, redirecionamento recusado, timeout, resposta lenta byte a byte, limite de cabeçalhos e conexão recusada.
- Allowlist exata por origem, recusa de DNS, metadata, IP privado, multicast, credenciais e destinos não autorizados.
- SQLite: disponibilidade por janela `(início, fim]`, média de sucessos, ausência de dados e métricas calculadas além do limite de 288 pontos do gráfico.
- Criação/atualização/resolução de incidentes, imutabilidade do encerramento, persistência entre instâncias e duplicidade concorrente protegida por transação/índice.
- API HTTP real: coleta das fixtures locais, domínio de incidentes, Host/Origin/cross-site, rejeição de formulário e de URL arbitrária, limite lógico de janela, path traversal, coleta concorrente e ausência de sondagem automática.

Nenhum teste faz sondagens externas. O caso de configuração com IP público apenas valida o objeto, sem conectar.

### JavaScript
- Dados fixos, regras de domínio, cálculos, histórico, recuperação de armazenamento e escape de HTML.
- PT/EN/JA, datas/números, singular PT/EN e preservação literal de conteúdo do usuário.
- Cliente API: caminhos same-origin, validação de snapshots, falhas de rede, erros de domínio e status sem amostras.
- Adaptador DOM: API não lê/grava dados demo, usa métricas completas do servidor, cria e resolve via snapshots, não inventa dados em erro e bloqueia troca de janela durante requisição pendente.

O adaptador DOM não substitui CSS, foco, teclado ou leitor de tela.

## Chromium — backend real

Executado com `sites-preview` iniciando `python3 -m backend.server` na origem local de preview:
1. `?mode=api` conectado ao Python, sem observações iniciais, métricas vazias e nenhum incidente fictício.
2. Botão de coleta fez quatro requisições HTTP locais reais. Três retornaram 200 e a fixture checkout retornou 503; disponibilidade amostral global de **75%**.
3. Incidente criado pela interface em português e persistido no SQLite. Recarga da página manteve o registro e as observações.
4. Idioma japonês conferido visualmente; conteúdo do usuário continuou literal.
5. Incidente resolvido pela interface japonesa; contador aberto voltou a zero, status manual atualizado e métricas históricas preservadas em 75%.
6. Servidor parado ao concluir; banco de QA removido. Nenhum destino externo foi consultado.

Um ajuste final posterior desabilitou a janela durante requisições e corrigiu singular PT/EN. Esses ajustes passaram regressões automatizadas; não houve nova rodada visual completa após eles.

## Chromium — demo estática (rodada anterior)

- Desktop PT/EN/JA, criação, erro de título, resolução, recarga, mudança de idioma e reset.
- Janela de 1 hora com 12 amostras por serviço e disponibilidade global de 75%.
- Largura efetiva de 393 CSS px via zoom nativo: cabeçalho, resumo e cartão inspecionados; `scrollWidth === clientWidth === 393` (sem overflow). Não é teste em aparelho móvel real.
- Capturas históricas da demo: `desktop-pt.jpg`, `desktop-ja.jpg`; não representam o modo Python.

## Limites

Sem deployment de backend, autenticação, testes externos de produção, telefone físico, Safari/Firefox ou auditoria completa de acessibilidade. HTTPS usa validação padrão do Python, mas não foi exercitado com um servidor TLS público; testes de rede desta rodada foram HTTP local. Não há alegação de prontidão para produção.

## Correções após revisão
- IDs de incidentes validados antes de conversão numérica: dígitos ASCII, até 19 caracteres, intervalo SQLite 1..2^63−1. Teste HTTP cobre zero, overflow e 5.000 dígitos; todos retornam JSON 404, sem queda da conexão.
- Editor bloqueado durante mutação API pendente: cancelar e tentar abrir outro incidente não permite que uma resposta antiga feche um novo rascunho. Regressão com resposta atrasada passando.
- Rodada final: 26 testes JS, 13 Python, check de sintaxe e py_compile aprovados.
