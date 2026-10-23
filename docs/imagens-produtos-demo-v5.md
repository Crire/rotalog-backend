# Imagens de produtos — endpoints da demo V5

Implementação exclusiva do backend, como incremento do PR #13. Base: plano `implementar_imagem.md` e V5 §§12.1, 20, 21.12 e 23.1. As rotas de galeria são extensões do contrato V5; não existem mudanças no frontend ou mobile neste incremento.

## Regras e limites

- Imagem pertence ao `Product` canônico, não à oferta. Administrador (`ROTALOG_ADMIN`) escreve; atores autenticados que consultam o catálogo podem ler imagens de produtos publicados. Produto em rascunho é visível somente à administração competente.
- Produto pode continuar sem imagem e ser publicado normalmente. Galeria mantém ordem, até cinco imagens por padrão e uma principal quando não vazia. Ofertas referenciam a principal do produto, sem cadastro duplicado por fornecedor.
- PNG/JPEG **estáticos**, até 8 MiB e 16 megapixels. Nome original, path, URL remota e MIME informado pelo cliente não autorizam um arquivo. O servidor verifica bytes, SHA-256, tamanho, formato real e integridade.
- Limites podem ser reduzidos por ambiente; há tetos de segurança de 8 MiB/16 megapixels e vinte imagens configuráveis por produto. Até vinte intenções pendentes e vinte intenções por minuto por usuário administrador.
- Uploads são privados, vinculados a produto, organização e `DemoRun`. Não há pasta estática pública nem upload arbitrário de evidência por este fluxo.
- Escritas exigem `Idempotency-Key`. Galeria exige também `expected_version` do produto. Mesma chave/conteúdo retorna o resultado anterior; conteúdo diferente com a mesma chave gera conflito. Upload recebido é imutável, mesmo com outra chave.

## Ciclo de arquivo

```text
POST intenção → PENDING_UPLOAD
PUT conteúdo privado → QUARANTINED
POST confirmação → verifica arquivo e agenda processamento (202)
worker → SCANNING → AVAILABLE ou REJECTED
AVAILABLE → associação administrativa à galeria
```

A confirmação **não** torna o arquivo disponível. `GET /files/{id}` é a fonte atual do estado, inclusive após reenvio idempotente de uma confirmação antiga. A expiração de quinze minutos da intenção limita envio/confirmação, não a duração de uma imagem já aprovada.

O worker usa uma fila persistente na própria tabela de arquivos, com claim por `SKIP LOCKED` e lease de dois minutos. Se um processo cair durante o processamento, outro pode recuperar a tarefa após o lease. Leitura do volume, hash e decodificação acontecem **fora** de transações/locks PostgreSQL. A API grava bytes por publicação atômica de arquivo imutável, revalidando sessão e contexto antes de confirmar os metadados.

**Atenção:** `SYNTHETIC_IMAGE_VALIDATION_ONLY` é validação simplificada para arquivos sintéticos da demo; não é antivírus nem comprova ausência de malware. O piloto continua exigindo scanner real, storage privado compatível com S3, retenção e demais controles da V5. Os endpoints não habilitam uso de dados pessoais/reais.

## Configuração local e Docker

Atualizar o código e instalar dependências existentes do PR, depois:

```bash
uv run --locked alembic upgrade head
uv run --locked python -m rotalog.demo.worker
```

O worker mantém a expiração de checkout/pedido e agora processa imagens. Para uma rodada manual de teste:

```bash
uv run --locked python -m rotalog.demo.worker --once
```

Sem Docker, API e worker devem usar o mesmo `ROTALOG_PRODUCT_IMAGES_ROOT` privado, por padrão `.local-runtime/product-images`. O diretório/objetos novos usam permissões 0700/0600. Não coloque esse diretório em servidor estático, Git ou imagem Docker.

No Compose:

```bash
docker compose config --quiet
docker compose up --build -d
```

API e worker compartilham o volume nomeado `product_images`, em `/var/lib/rotalog/product-images`; o Dockerfile prepara o diretório para o usuário não-root da aplicação. O banco e o volume de imagens precisam de backup consistente. **Não execute `down -v` para atualizar.** O diretório privado é excluído do Git e do contexto de build.

Configurações disponíveis no ambiente e no `.env.example`:

| Variável | Padrão |
|---|---|
| `ROTALOG_PRODUCT_IMAGES_ROOT` | `.local-runtime/product-images` fora do Docker; caminho fixo do volume no Compose |
| `ROTALOG_PRODUCT_IMAGES_PER_PRODUCT` | `5` |
| `ROTALOG_PRODUCT_IMAGE_MAX_BYTES` | `8388608` |
| `ROTALOG_PRODUCT_IMAGE_MAX_PIXELS` | `16000000` |
| `ROTALOG_PRODUCT_IMAGE_UPLOAD_TTL_SECONDS` | `900` |

## Contratos HTTP

Prefixo: `/api/v1`. Todos exigem autenticação; as permissões são revalidadas em cada caso de uso. Campos de finalidade, produto e limites pertencem à intenção; o cliente não escolhe chave física ou estado.

### 1. Criar intenção — `POST /files/upload-intents`

Administrador, header `Idempotency-Key`, resposta `201`:

```json
{
  "purpose": "PRODUCT_IMAGE",
  "product_id": "UUID_DO_PRODUTO",
  "size_bytes": 12345,
  "mime_type": "image/png",
  "sha256": "SHA256_HEXADECIMAL_MINUSCULO_DOS_BYTES_EXATOS"
}
```

Usar o tamanho/hash real; não copiar os valores de exemplo. A resposta inclui `file_id`, `status`, `upload_url` relativa, método `PUT`, headers de conteúdo, limites e expiração. Não inclui path físico, senha ou bearer token. No shell, `wc -c < imagem_sintetica.png` e `sha256sum imagem_sintetica.png` ajudam a obter os metadados.

### 2. Enviar bytes — `PUT /files/{file_id}/content`

Administrador, bearer token e `Idempotency-Key`. Body binário `application/octet-stream`, resposta `204`. Não enviar JSON/base64, multipart ou um path como texto. O Swagger documenta o body como arquivo binário; por curl, usar `--data-binary @imagem_sintetica.png`.

Há limite mesmo para envio em chunks/sem `Content-Length`. Reenvio idêntico não reescreve o objeto; tentativa de alterar bytes retorna conflito. Somente o responsável/contexto autorizado recebe ou confirma o arquivo.

### 3. Confirmar — `POST /files/{file_id}/confirm-upload`

Administrador, bearer token e `Idempotency-Key`, sem body. Retorna `202` em quarentena com processamento pendente. Divergência de tamanho/hash/MIME ou imagem inválida retorna `422` e persiste `REJECTED`; nesse caso criar outra intenção. Somente reenviar a confirmação não promove o arquivo a `AVAILABLE`.

### 4. Consultar — `GET /files/{file_id}`

Retorna finalidade, produto, estado, tamanho, hash, MIME e motivo seguro de rejeição. Antes da associação, somente o administrador do contexto autorizado consulta. Depois da associação a produto publicado, leitores autorizados do catálogo também consultam. Não retorna bytes, paths físicos ou informações internas do scanner.

### 5. Associar — `POST /admin/products/{product_id}/images`

Administrador, `Idempotency-Key`, resposta `201` com galeria e nova versão:

```json
{
  "expected_version": 2,
  "file_id": "UUID_DO_ARQUIVO_AVAILABLE_DESTE_PRODUTO",
  "alt_text": "Descrição da embalagem sintética"
}
```

Arquivo deve estar `AVAILABLE` e pertencer ao mesmo produto/contexto. Primeira imagem torna-se principal; novas imagens entram no fim. Associar não duplica bytes, não altera preço/estoque e não modifica snapshots comerciais já existentes.

### 6. Consultar galeria — `GET /products/{product_id}/images`

Retorna `product_id`, `product_version`, `primary_image_id` e `images` ordenadas. Cada imagem inclui ID, `file_id`, posição, principal, texto alternativo, MIME, tamanho, hash, dimensões e `content_url` autenticada.

`GET /products` e `GET /products/{id}` também incluem `images` e `primary_image`. `GET /offers` inclui `product_image`, a principal do produto. A ausência de imagem é representada por lista vazia/`null`, não por URL de placeholder inventada. São campos aditivos, sem mudança do contrato monetário.

### 7. Ordenar — `POST /admin/products/{product_id}/images/reorder`

Administrador e `Idempotency-Key`. Body com `expected_version` e `image_ids` contendo **exatamente todas** as imagens ativas, na ordem desejada, sem duplicação. Reordenar não muda a escolha da principal.

### 8. Principal — `POST /admin/products/{product_id}/images/{image_id}/set-primary`

Administrador, `Idempotency-Key`, body `{"expected_version": 3}`. Retorna galeria atualizada. Lock por produto e índice único parcial impedem duas principais simultâneas.

### 9. Remover — `DELETE /admin/products/{product_id}/images/{image_id}`

Administrador, `Idempotency-Key`, body `{"expected_version": 4}`. Retorna `200` com galeria/nova versão. Remove logicamente a associação e mantém arquivo/trilha; não apaga fisicamente evidência ou mídia. Ao remover a principal, a primeira restante assume; ao remover a última, a galeria fica vazia.

### 10. Ler a imagem — proxy ou acesso curto

- `GET /products/{product_id}/images/{image_id}/content`: proxy autenticado da associação ativa. Responde PNG/JPEG, `no-store` e `nosniff`.
- `GET /files/{file_id}/download-access`: contrato V5 para acesso curto. Responde URL relativa, método, expiração de 60 segundos e header `X-Download-Token` aleatório de uso único.
- `GET /files/{file_id}/content`: exige bearer token **e** esse header, vinculado ao mesmo usuário, sessão e organização. Token expirado/usado retorna `403`. Remoção da associação ou produto não publicado invalida o acesso de leitor na nova consulta, mesmo com token ainda não expirado.

O token curto não é enviado na URL/query nem gravado em claro no banco. A resposta que o emite usa `Cache-Control: no-store`. O proxy revalida autorização e integridade dos bytes antes de responder.

No frontend, uma URL relativa autenticada não pode ser usada como se fosse imagem pública. O consumidor deve buscar com a sessão/bearer, transformar a resposta em `Blob` e usar uma URL de objeto temporária, liberando-a depois. No mobile, configurar o cliente de imagens com autenticação. Este incremento apenas oferece os contratos: não altera esses repositórios.

## Erros e recuperação

- `401/403`: sessão ou capacidade inválida.
- `404`: arquivo/produto/associação não visível no contexto; não enumera recursos de outra execução.
- `409`: versão antiga, arquivo não disponível, intenção expirada, sobrescrita, limite da galeria ou repetição incompatível. Consultar o recurso antes de tentar outro comando.
- `413`: transporte acima do limite.
- `422`: metadados, tipo/tamanho/hash ou imagem inválidos.
- `429`: cota de upload/intenção por administrador.

Sem worker, a confirmação permanece em quarentena; não corrigir isso mudando o estado no banco. Se faltar o volume ou houver corrupção, o servidor não serve o conteúdo como imagem válida. Arquivos rejeitados/sem associação continuam privados; política de expurgo automático, antivírus real e retenção/hold completos são evolução do piloto, não um endpoint genérico para apagar dados.

## Persistência e verificação

Migration aditiva `20261023_0008`: arquivos, eventos de arquivo, concessões de download, associações e eventos de galeria. Não converte nem altera arquivos/provas de entrega do PR #13. O downgrade é bloqueado quando houver registros de arquivo/galeria a preservar; volume não é apagado por migration.

Testes em PostgreSQL/PostGIS dedicado verificam ciclo completo, imagem nas ofertas, ordem/principal, limite, versões, IDOR/permissões, rascunhos, expiração, idempotência, conteúdo imutável, MIME/hash/integridade, concorrência e retomada de worker. Testes sem banco verificam formatos, animação, limites, permissões do diretório e escrita atômica.

```bash
uv run --locked ruff check src tests migrations scripts
# ROTALOG_TEST_DATABASE_URL deve apontar para banco exclusivo contendo 'test' no nome.
uv run --locked pytest --tb=short
```

Nenhum workflow foi alterado. Resultados locais e limites da demo devem acompanhar o comentário do incremento no PR #13; não equivalem a conformidade integral do piloto V5.
