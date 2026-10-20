# Compatibilidade V5 — recorte comprador/distribuidora

Referência: documento técnico V5.0 de 12/09/2026. Esta matriz não declara
conformidade integral com a demo completa (§31.1) ou com o piloto (§31.2).

## Implementado no recorte

| Referência | Implementação | Limite |
|---|---|---|
| §5, §6.2 | monólito modular, PostgreSQL 17, SQLAlchemy síncrono, uv.lock | Sem Kubernetes/PostGIS |
| §9.2 | Membership, contexto de organização e autorização revalidada na transação | Cadastro de vínculos/convites ainda não exposto |
| §11.1 | BIGINT em centavos, moeda BRL, strings decimais no HTTP | Sem PSP real, frete/desconto/taxas |
| §12.1 | variante exata, publicação administrativa, oferta por fornecedor/depósito e histórico de preço | Categoria seca industrializada; sem ERP |
| §12.2–12.3 | depósito, revisão manual de coordenadas sintéticas, projeção, segurança, reservas e capacidade | Sem lote/validade/FEFO ou origem ERP |
| §10, §21.5 | CheckoutSession → Purchase/SupplierOrder/OrderItem → Fulfillment | Um fornecedor/depósito; termina antes do despacho |
| §20 | transações, locks, versões, idempotência no checkout/pagamento/aceite | Sem outbox ou auditoria global nesta entrega |
| §21.1–21.2 | /api/v1, JSON snake_case, paginação 25/100, X-Request-Id, erros e OpenAPI | Compatibilidade dos clientes precisa ser validada nos outros repositórios |
| §22.1–22.4 | Argon2id, JWT 10 min, session_id/auth_version, refresh rotativo, revogação, cookie/CSRF, CORS exato | MFA/recuperação de senha ainda ausentes |
| §30.2 | dados com DemoRun, execução encerrada somente leitura | Sem reset, novo cenário ou relógio controlado |

## Endpoints revisados contra o §21

Todos têm prefixo `/api/v1`. Os nomes de parâmetros (`order_id`, `product_id` etc.)
são descritivos e equivalem a `{id}` das tabelas do documento.

- Autenticação: `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/logout-all`,
  `/auth/password/change`; `GET /me`, `/me/sessions`; `DELETE /me/sessions/{session_id}`.
- Catálogo: `GET /products`, `/products/{id}`; `POST /admin/products`,
  `/admin/products/{id}/publish`; `GET /offers`; `POST /suppliers/{id}/offers`,
  `/offers/{id}/price-changes`, `/offers/{id}/pause`.
- Estoque: `GET /warehouses`, `/inventory`, `/capacity-slots`;
  `POST /suppliers/{id}/warehouses`, `/warehouses/{id}/geocoding-review`,
  `/inventory/manual-adjustments`, `/capacity-slots/{id}/adjustments`.
- Comercial: `POST /checkouts`; `GET /checkouts/{id}`;
  `POST /checkouts/{id}/confirm-payment`; `GET /purchases`, `/purchases/{id}`,
  `/supplier-orders`, `/supplier-orders/{id}`; `POST /supplier-orders/{id}/acceptance`,
  `/start-separation`, `/fulfillments`, `/cancel`;
  `POST /fulfillments/{id}/separation-results`, `/mark-ready`.
- Financeiro simulado: `GET /purchases/{id}/payments`,
  `/supplier-orders/{id}/financial-summary`.

## Extensões explícitas da demo

Estes endpoints não são apresentados como rotas listadas no §21:

- `POST /auth/register`: somente domínio `.invalid`, comprador/fornecedor; cria
  organização nova e vínculo. Não concede papel administrativo nem acesso a tenant existente.
- `GET /suppliers`: consulta paginada do diretório sintético sem usuários/credenciais.
- `POST /demo/capacity-slots`: criação de janela manual própria, para testar sem editar SQL.
- `GET /health`: liveness técnico, não atesta disponibilidade do banco/PSP.

## Pendências deliberadas

Auditoria global e outbox; aceite parcial; convites e gestão de vínculos; MFA/reset de senha;
revisões/avaliações; cenários/reset/relógio; ERP/PSP reais; checkout multi-fornecedor;
geocodificação externa e PostGIS; lotes/FEFO; frete/descontos; logística, custódia,
provas, motorista, tracking, offline e disputas. Não há endpoint genérico que possa
marcar uma entrega fictícia como real. O frontend/mobile deve mockar essas áreas.

Os movimentos nominais de estoque e a revisão de origem guardam motivo/ator,
mas **não substituem AuditEvent append-only**. A ausência de auditoria foi aceita
para este recorte, não deve ser considerada conforme ao §26.2.

## Verificação

`tests/test_catalog_ordering.py` cobre os três cenários solicitados e preparação;
`tests/test_demo.py` cobre sessões/refresh/revogação/navegador;
`tests/test_migrations.py` cobre vazio e snapshots anteriores. O script
`scripts/smoke_demo.py` executa o mesmo fluxo contra uma API HTTP já iniciada.

Testes locais de backend não atestam integração com builds reais do frontend ou
Android, que não foram modificados nesta entrega. Docker/Caddy precisam ser
validados no host escolhido; nenhum deploy é realizado por esta alteração.
