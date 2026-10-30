# Verificação

## Testes automatizados
`npm test`: 15 testes passando.
- Domínio: dados determinísticos, limites temporais, disponibilidade, latência, ausência de amostras.
- Incidentes: criação, validação, duplicidade, atualização, encerramento, imutabilidade e datas.
- Persistência: esquema, recuperação, recarga e erro de armazenamento.
- Idiomas: chaves, mensagens de erro, status e serviços em PT/EN/JA.
- Adaptador DOM leve: renderização, mudança de idioma, criar/cancelar/resolver, buscar, resetar e escape de texto.

`npm run check`: sintaxe de JavaScript verificada.

Os testes com adaptador DOM exercitam os controladores de interface, mas não equivalem a testes de navegador, CSS, foco ou acessibilidade assistiva. A validação visual está registrada abaixo.

## Não verificado / não aplicável
- Sem ambiente de produção, deploy, autenticação, backend ou URLs monitoradas.
- Sem alegação de auditoria completa de acessibilidade, testes em todos os navegadores ou segurança de produção.

## Navegador — Chromium
- Layout desktop observado em português e japonês; conteúdo e controles conferidos também em inglês.
- Criação de incidente, validação de título em inglês, inclusão de atualização de resolução e persistência após recarga verificadas na interface.
- Seletor de idioma persistido e janela de 1 hora verificados: 12 amostras por serviço e disponibilidade global de 75%.
- Reset confirmado em japonês: retorno aos dois incidentes iniciais, com títulos traduzidos após a correção de proveniência.
- Largura efetiva de 393 CSS px via zoom nativo do Chromium: cabeçalho, resumo e cartão inspecionados; `scrollWidth === clientWidth === 393` (sem transbordamento horizontal). Isso não equivale a teste em aparelho móvel real.
- Capturas desktop guardadas em `docs/desktop-pt.jpg` e `docs/desktop-ja.jpg`.

Não foram feitos testes completos em telefone físico, Safari/Firefox ou leitor de tela.
