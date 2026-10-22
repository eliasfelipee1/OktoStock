-- Fichas pendentes não podem ser vendidas. Preços reais ainda não informados ficam NULL.
ALTER TABLE produtos ALTER COLUMN preco DROP NOT NULL;
ALTER TABLE produtos ADD COLUMN ficha_detalhes jsonb NOT NULL DEFAULT '{}';
CREATE TABLE fornecedores (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL REFERENCES operacoes,
 nome text NOT NULL CHECK(length(trim(nome)) BETWEEN 1 AND 120), contato text NOT NULL DEFAULT '',
 ativo boolean NOT NULL DEFAULT true, simulado boolean NOT NULL DEFAULT false,
 UNIQUE(operacao_id,id), UNIQUE(operacao_id,nome)
);
CREATE TABLE cotacoes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL,
 fornecedor_id uuid NOT NULL, insumo_id uuid NOT NULL,
 quantidade_embalagem numeric(18,3) NOT NULL CHECK(quantidade_embalagem>0),
 preco_embalagem numeric(18,2) NOT NULL CHECK(preco_embalagem>0),
 minimo_embalagens integer NOT NULL CHECK(minimo_embalagens>0),
 frete numeric(18,2) CHECK(frete>=0), prazo_dias integer CHECK(prazo_dias>=0),
 cotado_em date NOT NULL DEFAULT CURRENT_DATE, valido_ate date NOT NULL,
 ativo boolean NOT NULL DEFAULT true, simulado boolean NOT NULL DEFAULT false,
 CHECK(valido_ate>=cotado_em),
 FOREIGN KEY(operacao_id,fornecedor_id) REFERENCES fornecedores(operacao_id,id),
 FOREIGN KEY(operacao_id,insumo_id) REFERENCES insumos(operacao_id,id)
);
CREATE TABLE configuracao_reposicao (
 operacao_id uuid PRIMARY KEY REFERENCES operacoes,
 porcoes_por_sabor integer NOT NULL DEFAULT 50 CHECK(porcoes_por_sabor>0)
);
CREATE VIEW estoque_reposicao AS
 WITH metas AS (
  SELECT r.operacao_id,r.insumo_id,sum(r.quantidade*coalesce(c.porcoes_por_sabor,50)) AS minimo
  FROM ingredientes r JOIN produtos p ON p.id=r.produto_id AND p.operacao_id=r.operacao_id AND p.ativo
  LEFT JOIN configuracao_reposicao c ON c.operacao_id=r.operacao_id
  GROUP BY r.operacao_id,r.insumo_id
 )
 SELECT i.operacao_id,i.id AS insumo_id,i.nome,i.unidade,m.minimo,
 coalesce(sum(l.saldo) FILTER(WHERE l.validade>=CURRENT_DATE),0) AS saldo,
 coalesce(sum(l.saldo) FILTER(WHERE l.validade<CURRENT_DATE),0) AS vencido,
 min(l.validade) FILTER(WHERE l.saldo>0 AND l.validade>=CURRENT_DATE) AS proxima_validade
 FROM metas m JOIN insumos i ON i.id=m.insumo_id AND i.operacao_id=m.operacao_id
 LEFT JOIN lotes l ON l.insumo_id=i.id AND l.operacao_id=i.operacao_id
 GROUP BY i.operacao_id,i.id,i.nome,i.unidade,m.minimo;
CREATE TABLE alertas_reposicao (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), operacao_id uuid NOT NULL,
 insumo_id uuid NOT NULL, aberto_em timestamptz NOT NULL DEFAULT now(),
 atualizado_em timestamptz NOT NULL DEFAULT now(), resolvido_em timestamptz,
 saldo numeric(18,3) NOT NULL, minimo numeric(18,3) NOT NULL,
 FOREIGN KEY(operacao_id,insumo_id) REFERENCES insumos(operacao_id,id)
);
CREATE UNIQUE INDEX alerta_aberto_por_insumo ON alertas_reposicao(operacao_id,insumo_id) WHERE resolvido_em IS NULL;
CREATE FUNCTION atualizar_alertas_reposicao(op uuid) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 -- Serializa os monitores da mesma operação. Reentrante na transação de estoque.
 PERFORM 1 FROM operacoes WHERE id=op FOR UPDATE;
 INSERT INTO alertas_reposicao(operacao_id,insumo_id,saldo,minimo)
 SELECT operacao_id,insumo_id,saldo,minimo FROM estoque_reposicao
 WHERE operacao_id=op AND saldo<minimo
 ON CONFLICT(operacao_id,insumo_id) WHERE resolvido_em IS NULL DO UPDATE
 SET saldo=EXCLUDED.saldo,minimo=EXCLUDED.minimo,atualizado_em=now()
 WHERE (alertas_reposicao.saldo,alertas_reposicao.minimo) IS DISTINCT FROM (EXCLUDED.saldo,EXCLUDED.minimo);
 UPDATE alertas_reposicao a SET resolvido_em=now(),atualizado_em=now()
 WHERE a.operacao_id=op AND a.resolvido_em IS NULL AND NOT EXISTS(
  SELECT 1 FROM estoque_reposicao e WHERE e.operacao_id=op AND e.insumo_id=a.insumo_id AND e.saldo<e.minimo);
END $$;
CREATE FUNCTION disparar_alertas_reposicao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM atualizar_alertas_reposicao(COALESCE(NEW.operacao_id,OLD.operacao_id));
 RETURN NULL;
END $$;
CREATE TRIGGER reposicao_lotes AFTER INSERT OR UPDATE OR DELETE ON lotes FOR EACH ROW EXECUTE FUNCTION disparar_alertas_reposicao();
CREATE TRIGGER reposicao_fichas AFTER INSERT OR UPDATE OR DELETE ON ingredientes FOR EACH ROW EXECUTE FUNCTION disparar_alertas_reposicao();
CREATE TRIGGER reposicao_produtos AFTER INSERT OR UPDATE OR DELETE ON produtos FOR EACH ROW EXECUTE FUNCTION disparar_alertas_reposicao();
CREATE TRIGGER reposicao_config AFTER INSERT OR UPDATE OR DELETE ON configuracao_reposicao FOR EACH ROW EXECUTE FUNCTION disparar_alertas_reposicao();
CREATE TRIGGER alertas_notificar AFTER INSERT OR UPDATE OR DELETE ON alertas_reposicao FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER fornecedores_notificar AFTER INSERT OR UPDATE OR DELETE ON fornecedores FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER cotacoes_notificar AFTER INSERT OR UPDATE OR DELETE ON cotacoes FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
