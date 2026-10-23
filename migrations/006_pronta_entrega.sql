ALTER TABLE configuracao_reposicao ADD COLUMN controle_prontos boolean NOT NULL DEFAULT false;
ALTER TABLE configuracao_reposicao ADD COLUMN meta_calmo integer NOT NULL DEFAULT 250 CHECK(meta_calmo>0);
ALTER TABLE configuracao_reposicao ADD COLUMN meta_movimento integer NOT NULL DEFAULT 1000 CHECK(meta_movimento>0);
ALTER TABLE configuracao_reposicao ADD COLUMN percentual_alerta numeric(5,2) NOT NULL DEFAULT 30 CHECK(percentual_alerta>0 AND percentual_alerta<=100);
ALTER TABLE configuracao_reposicao ADD COLUMN dias_movimento integer[] NOT NULL DEFAULT ARRAY[4,5,6,7] CHECK(dias_movimento <@ ARRAY[1,2,3,4,5,6,7]);
CREATE TABLE lotes_prontos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL, produto_id uuid NOT NULL,
 chave uuid NOT NULL, payload_hash text NOT NULL, codigo text NOT NULL,
 origem text NOT NULL CHECK(origem IN ('saldo_inicial','producao')),
 quantidade integer NOT NULL CHECK(quantidade>=0), saldo integer NOT NULL CHECK(saldo>=0 AND saldo<=quantidade),
 custo_unitario numeric(18,6) NOT NULL CHECK(custo_unitario>=0), validade timestamptz NOT NULL,
 criado_em timestamptz NOT NULL DEFAULT now(), usuario_id uuid NOT NULL REFERENCES usuarios,
 UNIQUE(operacao_id,id), UNIQUE(operacao_id,chave),
 FOREIGN KEY(operacao_id,produto_id) REFERENCES produtos(operacao_id,id)
);
CREATE TABLE movimentos_prontos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL, lote_id uuid NOT NULL,
 venda_id uuid, usuario_id uuid NOT NULL REFERENCES usuarios, quantidade integer NOT NULL CHECK(quantidade<0),
 tipo text NOT NULL CHECK(tipo IN ('venda','perda')), motivo text,
 chave uuid, criado_em timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(operacao_id,lote_id) REFERENCES lotes_prontos(operacao_id,id),
 FOREIGN KEY(operacao_id,venda_id) REFERENCES vendas(operacao_id,id)
);
ALTER TABLE movimentacoes DROP CONSTRAINT movimentacoes_tipo_check;
ALTER TABLE movimentacoes DROP CONSTRAINT movimentacoes_check;
ALTER TABLE movimentacoes ADD CONSTRAINT movimentacoes_tipo_check CHECK(tipo IN ('entrada','venda','perda','producao'));
ALTER TABLE movimentacoes ADD CONSTRAINT movimentacoes_check CHECK((tipo='entrada' AND quantidade>0) OR (tipo IN ('venda','perda','producao') AND quantidade<0));
ALTER TABLE movimentacoes ADD COLUMN producao_lote_id uuid;
ALTER TABLE movimentacoes ADD FOREIGN KEY(operacao_id,producao_lote_id) REFERENCES lotes_prontos(operacao_id,id);
CREATE VIEW estoque_prontos AS
 SELECT p.operacao_id,p.id AS produto_id,p.nome,
 count(l.id)>0 AS contagem_informada,
 coalesce(sum(l.saldo) FILTER(WHERE l.validade>now()),0) AS saldo,
 coalesce(sum(l.saldo) FILTER(WHERE l.validade<=now()),0) AS vencido,
 min(l.validade) FILTER(WHERE l.saldo>0 AND l.validade>now()) AS proxima_validade,
 CASE WHEN extract(isodow FROM CURRENT_DATE)::int=ANY(c.dias_movimento) THEN c.meta_movimento ELSE c.meta_calmo END AS meta,
 c.percentual_alerta,
 extract(isodow FROM CURRENT_DATE)::int=ANY(c.dias_movimento) AS dia_movimento
 FROM produtos p JOIN configuracao_reposicao c ON c.operacao_id=p.operacao_id AND c.controle_prontos
 LEFT JOIN lotes_prontos l ON l.produto_id=p.id AND l.operacao_id=p.operacao_id
 WHERE p.ativo GROUP BY p.id,c.operacao_id,c.meta_movimento,c.meta_calmo,c.dias_movimento,c.percentual_alerta;
CREATE TABLE alertas_prontos (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL, produto_id uuid NOT NULL,
 aberto_em timestamptz NOT NULL DEFAULT now(), atualizado_em timestamptz NOT NULL DEFAULT now(),
 resolvido_em timestamptz, saldo integer NOT NULL, meta integer NOT NULL, limite numeric(18,3) NOT NULL,
 FOREIGN KEY(operacao_id,produto_id) REFERENCES produtos(operacao_id,id)
);
CREATE UNIQUE INDEX alerta_pronto_aberto ON alertas_prontos(operacao_id,produto_id) WHERE resolvido_em IS NULL;
CREATE FUNCTION atualizar_alertas_prontos(op uuid) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM operacoes WHERE id=op FOR UPDATE;
 INSERT INTO alertas_prontos(operacao_id,produto_id,saldo,meta,limite)
 SELECT operacao_id,produto_id,saldo,meta,meta*percentual_alerta/100 FROM estoque_prontos
 WHERE operacao_id=op AND contagem_informada AND saldo<meta*percentual_alerta/100
 ON CONFLICT(operacao_id,produto_id) WHERE resolvido_em IS NULL DO UPDATE SET
 saldo=EXCLUDED.saldo,meta=EXCLUDED.meta,limite=EXCLUDED.limite,atualizado_em=now()
 WHERE (alertas_prontos.saldo,alertas_prontos.meta,alertas_prontos.limite) IS DISTINCT FROM (EXCLUDED.saldo,EXCLUDED.meta,EXCLUDED.limite);
 UPDATE alertas_prontos a SET resolvido_em=now(),atualizado_em=now()
 WHERE operacao_id=op AND resolvido_em IS NULL AND NOT EXISTS(
 SELECT 1 FROM estoque_prontos e WHERE e.operacao_id=op AND e.produto_id=a.produto_id
 AND e.contagem_informada AND e.saldo<e.meta*e.percentual_alerta/100);
END $$;
-- Mantém os nomes/tipos da view anterior, mas o planejamento novo desconta porções já prontas.
CREATE OR REPLACE VIEW estoque_reposicao AS
 WITH metas AS (
 SELECT r.operacao_id,r.insumo_id,
 sum(r.quantidade*CASE WHEN coalesce(c.controle_prontos,false)
 THEN greatest(0,ep.meta-ep.saldo) ELSE coalesce(c.porcoes_por_sabor,50) END) AS minimo
 FROM ingredientes r JOIN produtos p ON p.id=r.produto_id AND p.operacao_id=r.operacao_id AND p.ativo
 LEFT JOIN configuracao_reposicao c ON c.operacao_id=r.operacao_id
 LEFT JOIN estoque_prontos ep ON ep.produto_id=p.id AND ep.operacao_id=p.operacao_id
 GROUP BY r.operacao_id,r.insumo_id)
 SELECT i.operacao_id,i.id AS insumo_id,i.nome,i.unidade,m.minimo,
 coalesce(sum(l.saldo) FILTER(WHERE l.validade>=CURRENT_DATE),0) AS saldo,
 coalesce(sum(l.saldo) FILTER(WHERE l.validade<CURRENT_DATE),0) AS vencido,
 min(l.validade) FILTER(WHERE l.saldo>0 AND l.validade>=CURRENT_DATE) AS proxima_validade
 FROM metas m JOIN insumos i ON i.id=m.insumo_id AND i.operacao_id=m.operacao_id
 LEFT JOIN lotes l ON l.insumo_id=i.id AND l.operacao_id=i.operacao_id
 GROUP BY i.operacao_id,i.id,i.nome,i.unidade,m.minimo;
CREATE FUNCTION disparar_alertas_prontos() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM atualizar_alertas_prontos(coalesce(NEW.operacao_id,OLD.operacao_id));
 PERFORM atualizar_alertas_reposicao(coalesce(NEW.operacao_id,OLD.operacao_id));
 RETURN NULL;
END $$;
CREATE TRIGGER prontos_recalcular AFTER INSERT OR UPDATE OR DELETE ON lotes_prontos FOR EACH ROW EXECUTE FUNCTION disparar_alertas_prontos();
CREATE TRIGGER config_prontos_recalcular AFTER INSERT OR UPDATE OR DELETE ON configuracao_reposicao FOR EACH ROW EXECUTE FUNCTION disparar_alertas_prontos();
CREATE TRIGGER produtos_prontos_recalcular AFTER INSERT OR UPDATE OR DELETE ON produtos FOR EACH ROW EXECUTE FUNCTION disparar_alertas_prontos();
CREATE TRIGGER prontos_notificar AFTER INSERT OR UPDATE OR DELETE ON lotes_prontos FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER alertas_prontos_notificar AFTER INSERT OR UPDATE OR DELETE ON alertas_prontos FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
ALTER TABLE fornecedores ADD COLUMN cidade text;
ALTER TABLE fornecedores ADD COLUMN fonte_url text;
ALTER TABLE cotacoes ADD COLUMN fonte_url text;
ALTER TABLE cotacoes ADD COLUMN observacoes text NOT NULL DEFAULT '';
ALTER TABLE cotacoes ADD COLUMN referencia_publica boolean NOT NULL DEFAULT false;
ALTER TABLE cotacoes ADD COLUMN local_confirmado boolean NOT NULL DEFAULT true;
ALTER TABLE cotacoes ALTER COLUMN valido_ate DROP NOT NULL;
ALTER TABLE cotacoes ALTER COLUMN minimo_embalagens DROP NOT NULL;
