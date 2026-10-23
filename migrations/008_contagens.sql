-- Inventario e contagem ciclica: cada contagem de um lote registra o saldo do sistema, o contado e a diferenca.
-- Quando ha diferenca, um movimento 'ajuste' (positivo ou negativo) corrige o saldo sem editar lotes.saldo as cegas.
CREATE TABLE contagens (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 lote_id uuid NOT NULL, usuario_id uuid NOT NULL REFERENCES usuarios,
 chave uuid NOT NULL, payload_hash text NOT NULL,
 saldo_sistema numeric(18,3) NOT NULL CHECK(saldo_sistema>=0),
 saldo_contado numeric(18,3) NOT NULL CHECK(saldo_contado>=0),
 diferenca numeric(18,3) NOT NULL CHECK(diferenca=saldo_contado-saldo_sistema),
 custo_unitario numeric(18,6) NOT NULL, motivo text NOT NULL,
 criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE(operacao_id,id), UNIQUE(operacao_id,chave),
 FOREIGN KEY(operacao_id,lote_id) REFERENCES lotes(operacao_id,id)
);
CREATE INDEX contagens_lote ON contagens(operacao_id,lote_id,criado_em);

-- Ao recriar as regras, manter todos os tipos ja aceitos (006 acrescentou 'producao'); omitir um quebraria aquele fluxo.
ALTER TABLE movimentacoes DROP CONSTRAINT movimentacoes_tipo_check;
ALTER TABLE movimentacoes DROP CONSTRAINT movimentacoes_check;
ALTER TABLE movimentacoes ADD CONSTRAINT movimentacoes_tipo_check CHECK(tipo IN ('entrada','venda','perda','producao','ajuste'));
ALTER TABLE movimentacoes ADD CONSTRAINT movimentacoes_check CHECK(
 (tipo='entrada' AND quantidade>0) OR (tipo IN ('venda','perda','producao') AND quantidade<0) OR (tipo='ajuste' AND quantidade<>0));

ALTER TABLE movimentacoes ADD COLUMN contagem_id uuid;
ALTER TABLE movimentacoes ADD CONSTRAINT movimento_contagem_fk FOREIGN KEY(operacao_id,contagem_id) REFERENCES contagens(operacao_id,id);
ALTER TABLE movimentacoes ADD CONSTRAINT movimento_contagem_tipo CHECK((tipo='ajuste')=(contagem_id IS NOT NULL));
