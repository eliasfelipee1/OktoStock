CREATE TABLE perdas (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 produto_id uuid, turno_id uuid, usuario_id uuid NOT NULL REFERENCES usuarios,
 chave uuid NOT NULL, payload_hash text NOT NULL, motivo text NOT NULL,
 porcoes numeric(18,3) CHECK(porcoes>0), produto_nome text, produto_versao integer,
 criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE(operacao_id,id), UNIQUE(operacao_id,chave),
 FOREIGN KEY(operacao_id,produto_id) REFERENCES produtos(operacao_id,id),
 FOREIGN KEY(operacao_id,turno_id) REFERENCES turnos(operacao_id,id)
);
ALTER TABLE movimentacoes ADD COLUMN perda_id uuid;
ALTER TABLE movimentacoes ADD CONSTRAINT movimento_perda_fk FOREIGN KEY(operacao_id,perda_id) REFERENCES perdas(operacao_id,id);
ALTER TABLE movimentacoes ADD CONSTRAINT movimento_perda_tipo CHECK(perda_id IS NULL OR (tipo='perda' AND venda_id IS NULL));
CREATE INDEX movimentos_perdas_periodo ON movimentacoes(operacao_id,criado_em) WHERE tipo='perda';
