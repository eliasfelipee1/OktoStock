"""Consultas de leitura para o painel; todos os dados limitados à operação."""
from datetime import timedelta
from app.db import connect
from app.losses import report
from app.operation_context import read


def load(operation_id, page=1):
    with connect() as db:
        db.commit()
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        operation = db.execute('SELECT id,nome FROM operacoes WHERE id=%s', (operation_id,)).fetchone()
        period = db.execute('''SELECT coalesce(min(criado_em)::date,CURRENT_DATE) AS inicio,
            coalesce(max(criado_em)::date,CURRENT_DATE) AS fim FROM vendas WHERE operacao_id=%s''',
            (operation_id,)).fetchone()
        context = read(db, operation_id, period['inicio'], period['fim']+timedelta(days=1))
        summary = db.execute('''SELECT count(*) AS vendas,
            coalesce(sum(total) FILTER(WHERE status='confirmada'),0) AS receita,
            coalesce(sum(custo),0) AS custo FROM vendas WHERE operacao_id=%s''', (operation_id,)).fetchone()
        summary['porcoes'] = db.execute('''SELECT coalesce(sum(i.quantidade),0) AS n
            FROM venda_itens i JOIN vendas v ON v.id=i.venda_id
            WHERE v.operacao_id=%s AND v.status='confirmada' ''', (operation_id,)).fetchone()['n']
        stock = db.execute('''SELECT i.id,i.nome,i.unidade,i.estoque_minimo,
            coalesce(sum(l.saldo) FILTER(WHERE l.validade>=CURRENT_DATE),0) AS saldo,
            coalesce(sum(l.saldo) FILTER(WHERE l.validade<CURRENT_DATE),0) AS vencido,
            min(l.validade) FILTER(WHERE l.saldo>0 AND l.validade>=CURRENT_DATE) AS validade
            FROM insumos i LEFT JOIN lotes l ON l.insumo_id=i.id AND l.operacao_id=i.operacao_id
            WHERE i.operacao_id=%s GROUP BY i.id ORDER BY i.nome''', (operation_id,)).fetchall()
        products = db.execute('SELECT id,nome,preco,versao,ativo FROM produtos WHERE operacao_id=%s ORDER BY nome',
                              (operation_id,)).fetchall()
        recipes = db.execute('''SELECT r.produto_id,r.quantidade,i.nome,i.unidade,c.custo_unitario
            FROM ingredientes r JOIN insumos i ON i.id=r.insumo_id AND i.operacao_id=r.operacao_id
            LEFT JOIN LATERAL (SELECT custo_unitario FROM lotes l WHERE l.insumo_id=i.id
                AND l.operacao_id=i.operacao_id ORDER BY criado_em DESC,id LIMIT 1) c ON true
            WHERE r.operacao_id=%s ORDER BY i.nome''', (operation_id,)).fetchall()
        for product in products:
            product['ingredientes'] = [r for r in recipes if r['produto_id']==product['id']]
            product['custo_estimado'] = (sum(r['quantidade']*r['custo_unitario'] for r in product['ingredientes'])
                if product['ingredientes'] and all(r['custo_unitario'] is not None for r in product['ingredientes']) else None)
        sales = db.execute('''SELECT v.id,v.criado_em,v.total,v.custo,v.status,
            (SELECT string_agg(i.quantidade::text || ' × ' || i.nome, ', ' ORDER BY i.nome)
             FROM venda_itens i WHERE i.venda_id=v.id) AS itens,
            (SELECT string_agg(p.forma, ', ' ORDER BY p.forma) FROM pagamentos p WHERE p.venda_id=v.id) AS pagamento
            FROM vendas v WHERE v.operacao_id=%s ORDER BY v.criado_em DESC,v.id LIMIT 50 OFFSET %s''',
            (operation_id, (page-1)*50)).fetchall()
        losses = report(db, operation_id, period['inicio'], period['fim'])
        for row in losses['registros']:
            row.pop('usuario_id', None)
        return {'operacao': operation, 'periodo': period, 'contexto': context, 'resumo': summary,
                'estoque': stock, 'produtos': products, 'vendas': sales, 'pagina': page,
                'paginas': max(1, (summary['vendas']+49)//50), 'perdas': losses}
