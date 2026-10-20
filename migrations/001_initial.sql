CREATE TABLE operacoes (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), nome text NOT NULL);
CREATE TABLE usuarios (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 nome text NOT NULL, papel text NOT NULL CHECK(papel IN ('gerente','caixa','estoquista','ia')),
 token_hash text UNIQUE NOT NULL, ativo boolean NOT NULL DEFAULT true
);
CREATE TABLE insumos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 nome text NOT NULL, unidade text NOT NULL CHECK(unidade IN ('g','ml','un')),
 estoque_minimo numeric(18,3) NOT NULL DEFAULT 0 CHECK(estoque_minimo>=0), UNIQUE(operacao_id,id)
);
CREATE TABLE produtos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 nome text NOT NULL, preco numeric(18,2) NOT NULL CHECK(preco>0),
 versao integer NOT NULL DEFAULT 1 CHECK(versao>0), ativo boolean NOT NULL DEFAULT true, UNIQUE(operacao_id,id)
);
-- A ficha tecnica pertence a um produto imutavel; uma revisao cria outro produto.
CREATE TABLE ingredientes (
 operacao_id uuid NOT NULL, produto_id uuid NOT NULL, insumo_id uuid NOT NULL,
 quantidade numeric(18,3) NOT NULL CHECK(quantidade>0), PRIMARY KEY(produto_id,insumo_id),
 FOREIGN KEY(operacao_id,produto_id) REFERENCES produtos(operacao_id,id),
 FOREIGN KEY(operacao_id,insumo_id) REFERENCES insumos(operacao_id,id)
);
CREATE TABLE lotes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL, insumo_id uuid NOT NULL,
 codigo text NOT NULL, fornecedor text NOT NULL, validade date NOT NULL,
 saldo numeric(18,3) NOT NULL CHECK(saldo>=0), custo_unitario numeric(18,6) NOT NULL CHECK(custo_unitario>=0),
 criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE(operacao_id,id),
 FOREIGN KEY(operacao_id,insumo_id) REFERENCES insumos(operacao_id,id)
);
CREATE INDEX lotes_fefo ON lotes(operacao_id,insumo_id,validade,id) WHERE saldo>0;
CREATE TABLE turnos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 usuario_id uuid NOT NULL REFERENCES usuarios, aberto_em timestamptz NOT NULL DEFAULT now(), fechado_em timestamptz,
 UNIQUE(operacao_id,id)
);
CREATE TABLE vendas (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL, turno_id uuid NOT NULL,
 usuario_id uuid NOT NULL REFERENCES usuarios, chave uuid NOT NULL, payload_hash text NOT NULL,
 total numeric(18,2) NOT NULL CHECK(total>=0), custo numeric(18,6) NOT NULL DEFAULT 0 CHECK(custo>=0),
 status text NOT NULL DEFAULT 'confirmada' CHECK(status IN ('confirmada','estornada')),
 criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE(operacao_id,chave), UNIQUE(operacao_id,id),
 FOREIGN KEY(operacao_id,turno_id) REFERENCES turnos(operacao_id,id)
);
CREATE TABLE venda_itens (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), venda_id uuid NOT NULL REFERENCES vendas,
 produto_id uuid NOT NULL REFERENCES produtos, nome text NOT NULL, versao integer NOT NULL,
 quantidade integer NOT NULL CHECK(quantidade>0), preco numeric(18,2) NOT NULL, ficha jsonb NOT NULL
);
CREATE TABLE pagamentos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), venda_id uuid NOT NULL REFERENCES vendas,
 forma text NOT NULL CHECK(forma IN ('pix','dinheiro','cartao')), valor numeric(18,2) NOT NULL CHECK(valor>0)
);
CREATE TABLE movimentacoes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL, lote_id uuid NOT NULL,
 venda_id uuid, usuario_id uuid NOT NULL REFERENCES usuarios,
 tipo text NOT NULL CHECK(tipo IN ('entrada','venda','perda')),
 quantidade numeric(18,3) NOT NULL CHECK((tipo='entrada' AND quantidade>0) OR (tipo IN ('venda','perda') AND quantidade<0)),
 custo_unitario numeric(18,6) NOT NULL, motivo text, criado_em timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(operacao_id,lote_id) REFERENCES lotes(operacao_id,id),
 FOREIGN KEY(operacao_id,venda_id) REFERENCES vendas(operacao_id,id)
);
CREATE TABLE auditoria (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 usuario_id uuid NOT NULL REFERENCES usuarios, acao text NOT NULL, dados jsonb NOT NULL,
 criado_em timestamptz NOT NULL DEFAULT now()
);
