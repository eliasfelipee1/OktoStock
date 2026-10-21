"""Contexto cadastrado e agregados; isolados por operação e período."""

REPORT_QUESTION = 'Você deseja receber um relatório da barraca todo domingo à noite?'


def read(db, operation_id, start, end):
    config = db.execute('SELECT parametros,deseja_relatorio_domingo FROM contextos_operacionais '
                        'WHERE operacao_id=%s', (operation_id,)).fetchone()
    daily = db.execute('''SELECT criado_em::date AS dia,
        extract(isodow FROM criado_em)::int AS dia_semana_iso,
        count(*) AS vendas, sum(total) AS receita, sum(custo) AS custo_ingredientes
        FROM vendas WHERE operacao_id=%s AND status='confirmada'
        AND criado_em>=%s::date AND criado_em<%s::date GROUP BY 1,2 ORDER BY 1''',
        (operation_id, start, end)).fetchall()
    flavors = db.execute('''SELECT vi.produto_id,vi.nome,sum(vi.quantidade) AS porcoes,
        sum(vi.quantidade*vi.preco) AS receita FROM venda_itens vi
        JOIN vendas v ON v.id=vi.venda_id WHERE v.operacao_id=%s AND v.status='confirmada'
        AND v.criado_em>=%s::date AND v.criado_em<%s::date
        GROUP BY 1,2 ORDER BY porcoes DESC,vi.nome LIMIT 100''', (operation_id, start, end)).fetchall()
    total = sum(row['receita'] for row in daily)
    high = sum(row['receita'] for row in daily if row['dia_semana_iso'] >= 4)
    weekdays = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira',
                'sexta-feira', 'sábado', 'domingo']
    for row in daily:
        row['dia_semana'] = weekdays[row['dia_semana_iso'] - 1]
        row['dia_forte'] = row['dia_semana_iso'] >= 4
    preference = config['deseja_relatorio_domingo'] if config else None
    return {'parametros': config['parametros'] if config else {}, 'vendas_por_dia': daily,
            'ranking_sabores': flavors,
            'receita_total_periodo': total, 'receita_quinta_a_domingo': high,
            'percentual_receita_quinta_a_domingo': high * 100 / total if total else None,
            'relatorio_semanal': {'deseja_receber': preference, 'envio_automatico_ativo': False,
                'pergunta': REPORT_QUESTION if preference is None else None,
                'pendencias': ['Definir horário, canal e implementar envio após aceite'] if preference else []}}
