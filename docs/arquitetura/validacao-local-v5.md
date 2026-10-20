# Validação local — demo V5

Data: 19/10/2026 (America/Manaus). Testes executados nesta implementação, sem
commit/push, alteração de workflow, merge, fechamento de PR ou deploy externo.

## Ambiente e verificações

- Python 3.13.16 e PostgreSQL 17.6, isolados em `/tmp`.
- Suíte completa: **56 testes aprovados**.
- Após a proteção adicional das reservas legadas: **14 testes de migração/configuração aprovados**.
- Um aviso de depreciação da dependência Starlette/TestClient sobre HTTPX; não é
  erro de aplicação ou falha de teste. Nenhum aviso foi suprimido.
- Ruff check e format, compileall, `git diff --check` e verificação de `uv.lock`: aprovados.
- `docker compose config --quiet`: aprovado. Imagem/containers não foram executados,
  pois o usuário do ambiente não possui acesso ao daemon Docker.
- Alembic upgrade/check em banco novo e testes de snapshots anteriores: aprovados.
- Os bancos de teste usam schemas isolados; nenhum banco do usuário foi limpo.

## Endpoints com Uvicorn realmente iniciado

API temporária em `127.0.0.1:8001`, banco sintético dedicado, senha/chave geradas em
memória e não impressas. O processo temporário da API foi encerrado após o teste.

`scripts/smoke_demo.py`: **43 verificações HTTP aprovadas**:

1. Administrador cria/publica a variante de alimento seco **Pizza — mistura seca lacrada 400 g**.
2. Conta nova de distribuidora é cadastrada e faz login; cria depósito, recebe
   confirmação administrativa de coordenadas sintéticas, cadastra oferta e estoque.
3. Conta nova de comprador é cadastrada e faz login; consulta distribuidoras,
   produto/ofertas e compra **3 unidades a R$ 29,90 = R$ 89,70**.
4. Repetir checkout/pagamento com a mesma chave retorna o resultado anterior.
5. A distribuidora vê seu pedido, aceita e separa as três unidades, encerrando
   o recorte em **READY_TO_DISPATCH**. Nenhuma entrega é marcada como realizada.
6. Estoque final: **20 declaradas, 3 reservadas, 17 disponíveis**.
7. Outra distribuidora recebe 404 ao acessar o pedido; fornecedor recebe 403 ao
   tentar cadastrar produto canônico administrativo.
8. Refresh/logout nativos, cookie de navegador, CSRF, preflight CORS e revogação
   imediata são exercitados por HTTP.

Pagamentos são sempre identificados como `SIMULATED`, dados como sintéticos.
O teste não demonstra pagamento real, frontend em navegador real ou aplicativo Android.

## Comparação final com o documento técnico

Comparação dos métodos/caminhos do OpenAPI com as tabelas do §21 da V5, normalizando
somente nomes de parâmetros (`{order_id}` equivale a `{id}`):

- **42 operações HTTP publicadas**;
- **38 correspondências com o documento**;
- **4 extensões explícitas**: health, cadastro sintético, diretório de fornecedores
  e criação de capacidade manual da demo;
- **0 divergências de caminho/método não documentadas** no conjunto publicado.

Isso não significa implementar todos os endpoints nem todas as regras da V5.
O recorte e suas pendências constam na [matriz de compatibilidade](compatibilidade-v5-demo.md).
Auditoria global, entregador/tracking, MFA, recuperação de senha, ERP/PSP reais e
demais funcionalidades não implementadas não foram declaradas prontas.

As migrações mantêm UUIDs, senhas e saldos legados; preços são convertidos sem perda
para centavos. Reservas legadas sem registros canônicos ficam `RECONCILING`, sem
inventar pedidos nem liberar unidades comprometidas. Downgrade após uso V5 é bloqueado.
