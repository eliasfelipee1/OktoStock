CREATE TABLE propostas_precos_otto (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 operacao_id uuid NOT NULL REFERENCES operacoes(id),
 dados jsonb NOT NULL,
 assinatura_anterior text NOT NULL,
 criado_em timestamptz NOT NULL DEFAULT now(),
 expira_em timestamptz NOT NULL DEFAULT now() + interval '24 hours',
 status text NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','confirmada','cancelada')),
 cotacao_id uuid REFERENCES cotacoes(id),
 confirmado_por uuid REFERENCES usuarios(id),
 confirmado_em timestamptz
);
CREATE INDEX propostas_precos_operacao ON propostas_precos_otto(operacao_id,criado_em);
