CREATE TABLE contextos_operacionais (
 operacao_id uuid PRIMARY KEY REFERENCES operacoes,
 parametros jsonb NOT NULL DEFAULT '{}',
 deseja_relatorio_domingo boolean,
 atualizado_em timestamptz NOT NULL DEFAULT now()
);
