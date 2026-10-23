-- Avisa a dashboard em tempo real quando dados de uma operacao mudam (API, pgAdmin ou scripts).
-- O payload e so o ID da operacao; o PostgreSQL agrupa avisos iguais da mesma transacao.
CREATE OR REPLACE FUNCTION okto_notificar_mudanca() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('okto_mudancas', COALESCE(NEW.operacao_id, OLD.operacao_id)::text);
  RETURN NULL;
END $$;

CREATE TRIGGER vendas_notificar AFTER INSERT OR UPDATE OR DELETE ON vendas
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER movimentacoes_notificar AFTER INSERT OR UPDATE OR DELETE ON movimentacoes
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER lotes_notificar AFTER INSERT OR UPDATE OR DELETE ON lotes
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER insumos_notificar AFTER INSERT OR UPDATE OR DELETE ON insumos
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER produtos_notificar AFTER INSERT OR UPDATE OR DELETE ON produtos
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER ingredientes_notificar AFTER INSERT OR UPDATE OR DELETE ON ingredientes
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER perdas_notificar AFTER INSERT OR UPDATE OR DELETE ON perdas
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
CREATE TRIGGER contextos_notificar AFTER INSERT OR UPDATE OR DELETE ON contextos_operacionais
  FOR EACH ROW EXECUTE FUNCTION okto_notificar_mudanca();
