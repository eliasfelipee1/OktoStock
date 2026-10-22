"""Consultas de leitura para o painel; todos os dados limitados à operação."""
from datetime import timedelta
from fastapi import HTTPException
from app.db import connect
from app.losses import report
from app.operation_context import read

WEEKDAYS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira',
            'sexta-feira', 'sábado', 'domingo']


def sales_filter(operation_id, start, end, product=None, payment=None, weekday=None):
    """Condição SQL sobre vendas `v`; o período é inclusivo e usa o fuso da conexão."""
    sql = 'v.operacao_id=%s AND v.criado_em>=%s::date AND v.criado_em<%s::date'
    args = [operation_id, start, end + timedelta(days=1)]
    if product:
        sql += ' AND EXISTS(SELECT 1 FROM venda_itens x WHERE x.venda_id=v.id AND x.produto_id=%s)'
        args.append(product)
    if payment:
        sql += ' AND EXISTS(SELECT 1 FROM pagamentos y WHERE y.venda_id=v.id AND y.forma=%s)'
        args.append(payment)
    if weekday:
        sql += ' AND extract(isodow FROM v.criado_em)=%s'
        args.append(weekday)
    return sql, args


def load(operation_id, page=1, start=None, end=None, product=None, payment=None, weekday=None):
    with connect() as db:
        db.commit()
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        operation = db.execute('SELECT id,nome FROM operacoes WHERE id=%s', (operation_id,)).fetchone()
        bounds = db.execute('''SELECT coalesce(min(criado_em)::date,CURRENT_DATE) AS inicio,
            coalesce(max(criado_em)::date,CURRENT_DATE) AS fim FROM vendas WHERE operacao_id=%s''',
            (operation_id,)).fetchone()
        start, end = start or bounds['inicio'], end or bounds['fim']
        if start > end:
            raise HTTPException(422, detail={'codigo': 'PERIODO_INVALIDO'})
        period = {'inicio': start, 'fim': end}
        context = read(db, operation_id, start, end + timedelta(days=1))
        where, args = sales_filter(operation_id, start, end, product, payment, weekday)
        summary = db.execute(f'''SELECT count(*) AS vendas,
            coalesce(sum(total) FILTER(WHERE status='confirmada'),0) AS receita,
            coalesce(sum(custo),0) AS custo FROM vendas v WHERE {where}''', args).fetchone()
        item_filter = ' AND i.produto_id=%s' if product else ''
        item_args = args + ([product] if product else [])
        summary['porcoes'] = db.execute(f'''SELECT coalesce(sum(i.quantidade),0) AS n
            FROM venda_itens i JOIN vendas v ON v.id=i.venda_id
            WHERE {where} AND v.status='confirmada'{item_filter}''', item_args).fetchone()['n']
        daily = db.execute(f'''SELECT v.criado_em::date AS dia,
            extract(isodow FROM v.criado_em)::int AS dia_semana_iso,
            count(*) AS vendas, sum(v.total) AS receita, sum(v.custo) AS custo_ingredientes
            FROM vendas v WHERE {where} AND v.status='confirmada' GROUP BY 1,2 ORDER BY 1''', args).fetchall()
        for row in daily:
            row['dia_semana'] = WEEKDAYS[row['dia_semana_iso'] - 1]
            row['dia_forte'] = row['dia_semana_iso'] >= 4
        context['vendas_por_dia'] = daily
        context['ranking_sabores'] = db.execute(f'''SELECT i.produto_id,i.nome,sum(i.quantidade) AS porcoes,
            sum(i.quantidade*i.preco) AS receita FROM venda_itens i JOIN vendas v ON v.id=i.venda_id
            WHERE {where} AND v.status='confirmada'{item_filter}
            GROUP BY 1,2 ORDER BY porcoes DESC,i.nome LIMIT 100''', item_args).fetchall()
        total = sum(row['receita'] for row in daily)
        high = sum(row['receita'] for row in daily if row['dia_forte'])
        context['receita_total_periodo'], context['receita_quinta_a_domingo'] = total, high
        context['percentual_receita_quinta_a_domingo'] = high * 100 / total if total else None
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
        for item in products:
            item['ingredientes'] = [r for r in recipes if r['produto_id'] == item['id']]
            item['custo_estimado'] = (sum(r['quantidade']*r['custo_unitario'] for r in item['ingredientes'])
                if item['ingredientes'] and all(r['custo_unitario'] is not None for r in item['ingredientes']) else None)
        payments = [r['forma'] for r in db.execute('''SELECT DISTINCT p.forma FROM pagamentos p
            JOIN vendas v ON v.id=p.venda_id WHERE v.operacao_id=%s ORDER BY 1''', (operation_id,)).fetchall()]
        sales = db.execute(f'''SELECT v.id,v.criado_em,v.total,v.custo,v.status,
            (SELECT string_agg(i.quantidade::text || ' × ' || i.nome, ', ' ORDER BY i.nome)
             FROM venda_itens i WHERE i.venda_id=v.id) AS itens,
            (SELECT string_agg(p.forma, ', ' ORDER BY p.forma) FROM pagamentos p WHERE p.venda_id=v.id) AS pagamento
            FROM vendas v WHERE {where} ORDER BY v.criado_em DESC,v.id LIMIT 50 OFFSET %s''',
            args + [(page-1)*50]).fetchall()
        losses = report(db, operation_id, start, end)
        for row in losses['registros']:
            row.pop('usuario_id', None)
        return {'operacao': operation, 'periodo': period, 'periodo_total': bounds, 'contexto': context,
                'filtros': {'inicio': start, 'fim': end, 'produto_id': product, 'forma': payment,
                            'dia_semana': weekday},
                'formas_pagamento': payments, 'resumo': summary,
                'estoque': stock, 'produtos': products, 'vendas': sales, 'pagina': page,
                'paginas': max(1, (summary['vendas']+49)//50), 'perdas': losses}
