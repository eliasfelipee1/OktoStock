"""Carga didática atômica, sem TRUNCATE; recusa bancos já povoados.

Execute após migrations: python -m scripts.seed_okto.
Para substituir uma carga anterior da demonstração: python -m scripts.seed_okto --recriar
(apaga somente a operação simulada de ID fixo e a carrega de novo).
O token administrativo é obtido de OKTO_DEMO_TOKEN, nunca impresso.
"""
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb
from app.db import connect

OPERATION_ID = UUID('078f3d48-9702-4c40-94a2-c07811202601')
# Cada bloco vende o mesmo mix de 10 porções (R$ 349), permitindo 75% exatos.
DAILY_BLOCKS = [10, 18, 36, 44, 40, 18, 12, 10, 16, 24, 32, 30, 16, 14]
MIX = {'LIN': 3, 'STR': 3, 'BOL': 2, 'VEG': 2}
TZ = ZoneInfo('America/Sao_Paulo')
START = date(2026, 10, 7)


def at(day, hour):
    return datetime.combine(day, time(hour), TZ)


# Ordem respeita as chaves estrangeiras; tudo filtrado pela operação simulada.
DEMO_TABLES = ['movimentacoes', 'perdas', 'pagamentos', 'venda_itens', 'vendas', 'turnos', 'lotes',
               'ingredientes', 'produtos', 'insumos', 'auditoria', 'contextos_operacionais', 'usuarios']


def remove_demo(db):
    """Apaga a operação simulada e devolve o hash do token do gerente, para mantê-lo válido."""
    config = db.execute('SELECT parametros FROM contextos_operacionais WHERE operacao_id=%s',
                        (OPERATION_ID,)).fetchone()
    if not config or config['parametros'].get('natureza_dados') != 'simulados':
        raise RuntimeError('A operação de ID fixo não está marcada como simulada; nada foi apagado.')
    owner = db.execute("SELECT token_hash FROM usuarios WHERE operacao_id=%s AND papel='gerente' "
                       'ORDER BY nome LIMIT 1', (OPERATION_ID,)).fetchone()
    for table in DEMO_TABLES:
        if table in ('pagamentos', 'venda_itens'):
            db.execute(f'DELETE FROM {table} WHERE venda_id IN (SELECT id FROM vendas WHERE operacao_id=%s)',
                       (OPERATION_ID,))
        else:
            db.execute(f'DELETE FROM {table} WHERE operacao_id=%s', (OPERATION_ID,))
    db.execute('DELETE FROM operacoes WHERE id=%s', (OPERATION_ID,))
    return owner['token_hash'] if owner else None


def seed(token, recreate=False):
    catalog = json.loads((Path(__file__).parent / 'data/catalogo_okto.json').read_text(encoding='utf-8'))
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(728194)')
        token_hash = hashlib.sha256(token.encode()).hexdigest() if token else None
        if recreate and db.execute('SELECT 1 FROM operacoes WHERE id=%s', (OPERATION_ID,)).fetchone():
            previous = remove_demo(db)
            token_hash = token_hash or previous
        if not token_hash:
            raise RuntimeError('Defina OKTO_DEMO_TOKEN para criar o gerente da demonstração.')
        if db.execute('SELECT 1 FROM operacoes WHERE id=%s', (OPERATION_ID,)).fetchone():
            return {'estado': 'ja_carregado', 'operacao_id': str(OPERATION_ID)}
        if db.execute('SELECT 1 FROM operacoes LIMIT 1').fetchone():
            raise RuntimeError('Use um banco vazio dedicado à demonstração; nenhum dado foi alterado.')
        db.execute('INSERT INTO operacoes(id,nome) VALUES(%s,%s)',
                   (OPERATION_ID, 'Okto — demonstração simulada 2026'))
        user = db.execute('INSERT INTO usuarios(operacao_id,nome,papel,token_hash) '
                          "VALUES(%s,'Dono da barraca (demo)','gerente',%s) RETURNING id",
                          (OPERATION_ID, token_hash)).fetchone()['id']
        params = {
            'natureza_dados': 'simulados', 'periodo_historico': {'inicio': '2026-10-07', 'fim': '2026-10-20'},
            'publico_total_festa': 500000, 'fonte_publico': 'Premissa informada pelo dono; não verificada externamente',
            'publico_e_clientes': 'Público de toda a festa; não é número de clientes nem taxa de conversão da barraca',
            'dias_maior_movimento_iso': [4, 5, 6, 7], 'participacao_receita_dias_fortes': '0.75',
            'significado_renda': 'Receita bruta de vendas; não lucro',
            'feriado': {'dia_mes': '12-10', 'fim_semana_2026': ['2026-10-09', '2026-10-10', '2026-10-11'],
                        'regra': 'Fim de semana associado ao feriado tem maior movimento, conforme dono'},
            'pre_preparo': {'dia_limite_iso': 3, 'periodo_limite': 'noite', 'fuso': 'America/Sao_Paulo',
                           'regra': 'Concluir pré-preparos até quarta à noite; planejar compras antes disso',
                           'pendencias': ['Horário exato', 'Capacidade', 'Validade e conservação validadas por preparo'],
                           'execucao_registrada': False},
            'sabores': [p[1] for p in catalog['produtos']],
            'premissas_simulacao': ['Mix fixo por bloco: 3 Linguiça Blumenau, 3 Strogonoff de frango, 2 Bolonhesa e 2 Vegetariana',
                'Volume de vendas é hipótese didática independente dos 500 mil visitantes',
                'Descarte independente de insumo: 1% do consumo diário; não rendimento de limpeza',
                'Recebimentos diários e validade de 2 dias são fictícios, não orientação sanitária',
                'Fichas técnicas de docs/OTTO_REQUISITOS.md; custos e preços são didáticos; embalagem, impostos e mão de obra não incluídos'],
            'fornecedores': [{'nome': r[1], 'prazo_dias': int(r[4]), 'natureza': 'simulado'} for r in catalog['fornecedores']],
            'previsao': 'Padrão informado e cenário didático; não modelo preditivo validado',
        }
        db.execute('INSERT INTO contextos_operacionais(operacao_id,parametros) VALUES(%s,%s)',
                   (OPERATION_ID, Jsonb(params)))
        ingredients, products, recipes = {}, {}, defaultdict(list)
        for row in catalog['insumos']:
            code, name, unit, cost, _, _, minimum, _ = row
            factor = D(1000) if unit in ('kg', 'l') else D(1)
            uid = db.execute('INSERT INTO insumos(operacao_id,nome,unidade,estoque_minimo) '
                'VALUES(%s,%s,%s,%s) RETURNING id',
                (OPERATION_ID, name, {'kg': 'g', 'l': 'ml', 'un': 'un'}[unit], D(minimum)*factor)).fetchone()['id']
            ingredients[code] = {'id': uid, 'cost': D(cost)/factor, 'factor': factor, 'minimum': D(minimum)*factor}
        for row in catalog['produtos']:
            code, name, price, *_ = row
            uid = db.execute('INSERT INTO produtos(operacao_id,nome,preco) VALUES(%s,%s,%s) RETURNING id',
                             (OPERATION_ID, name, D(price))).fetchone()['id']
            products[code] = {'id': uid, 'name': name, 'price': D(price)}
        for code, ingredient, amount in catalog['receita_ingredientes']:
            qty = D(amount)*ingredients[ingredient]['factor']
            recipes[code].append((ingredient, qty))
            db.execute('INSERT INTO ingredientes VALUES(%s,%s,%s,%s)',
                       (OPERATION_ID, products[code]['id'], ingredients[ingredient]['id'], qty))
        per_block = defaultdict(lambda: D(0))
        for code, mix in MIX.items():
            for ingredient, qty in recipes[code]:
                per_block[ingredient] += qty * mix

        def movement(lot, kind, qty, cost, stamp, sale=None, loss=None):
            db.execute('''INSERT INTO movimentacoes(operacao_id,lote_id,usuario_id,tipo,quantidade,
                custo_unitario,criado_em,venda_id,perda_id,motivo) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (OPERATION_ID, lot, user, kind, qty, cost, stamp, sale, loss, 'Demonstração simulada'))

        def lot_for(ingredient, day, qty, balance):
            item = ingredients[ingredient]
            lot = db.execute('''INSERT INTO lotes(operacao_id,insumo_id,codigo,fornecedor,validade,
                saldo,custo_unitario,criado_em) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (OPERATION_ID, item['id'], f'DEMO-{day}-{ingredient}', 'Fornecedor didático',
                 day+timedelta(days=2), balance, item['cost'], at(day, 8))).fetchone()['id']
            movement(lot, 'entrada', qty, item['cost'], at(day, 8))
            return lot

        for index, blocks in enumerate(DAILY_BLOCKS):
            day = START + timedelta(days=index)
            shift = db.execute('INSERT INTO turnos(operacao_id,usuario_id,aberto_em,fechado_em) '
                               'VALUES(%s,%s,%s,%s) RETURNING id',
                               (OPERATION_ID, user, at(day, 10), at(day, 23))).fetchone()['id']
            lots, waste = {}, {}
            for ingredient, qty in per_block.items():
                waste[ingredient] = (qty * blocks * D('.01')).quantize(D('.001'))
                lots[ingredient] = lot_for(ingredient, day, qty*blocks+waste[ingredient], D(0))
            for block in range(blocks):
                for pos, (code, mix) in enumerate(MIX.items()):
                    p = products[code]
                    stamp = at(day, 11) + timedelta(seconds=(block*5+pos)*int(36000/(blocks*5)))
                    total = p['price'] * mix
                    cost = sum(qty * ingredients[i]['cost'] for i, qty in recipes[code]) * mix
                    sale = db.execute('''INSERT INTO vendas(operacao_id,turno_id,usuario_id,chave,payload_hash,
                        total,custo,criado_em) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                        (OPERATION_ID, shift, user, uuid4(), 'demo', total, cost, stamp)).fetchone()['id']
                    ficha = [{'insumo_id': str(ingredients[i]['id']), 'quantidade': str(q)} for i, q in recipes[code]]
                    db.execute('''INSERT INTO venda_itens(venda_id,produto_id,nome,versao,quantidade,preco,ficha)
                        VALUES(%s,%s,%s,1,%s,%s,%s)''', (sale, p['id'], p['name'], mix, p['price'], Jsonb(ficha)))
                    db.execute('INSERT INTO pagamentos(venda_id,forma,valor) VALUES(%s,%s,%s)',
                               (sale, ['pix','cartao','dinheiro'][(block+pos)%3], total))
                    for ingredient, qty in recipes[code]:
                        movement(lots[ingredient], 'venda', -qty*mix, ingredients[ingredient]['cost'], stamp, sale)
            for ingredient, qty in waste.items():
                loss = db.execute('''INSERT INTO perdas(operacao_id,turno_id,usuario_id,chave,payload_hash,motivo,criado_em)
                    VALUES(%s,%s,%s,%s,'demo','Descarte de insumo não vendido (simulado)',%s) RETURNING id''',
                    (OPERATION_ID, shift, user, uuid4(), at(day, 22))).fetchone()['id']
                movement(lots[ingredient], 'perda', -qty, ingredients[ingredient]['cost'], at(day, 22), loss=loss)
        # Estoque de abertura do dia 21; não é produção nem venda futura.
        for ingredient, qty in per_block.items():
            balance = qty*D(20)+ingredients[ingredient]['minimum']
            lot_for(ingredient, date(2026, 10, 21), balance, balance)
        db.execute('INSERT INTO auditoria(operacao_id,usuario_id,acao,dados) VALUES(%s,%s,%s,%s)',
                   (OPERATION_ID, user, 'CARGA_DEMONSTRACAO', Jsonb({'fonte': 'fichas dos 4 sabores + premissas do dono',
                    'periodo': params['periodo_historico'], 'simulado': True})))
    return {'estado': 'recriado' if recreate else 'criado', 'operacao_id': str(OPERATION_ID),
            'porcoes': 3200, 'vendas': 1280}


if __name__ == '__main__':
    token = os.environ.get('OKTO_DEMO_TOKEN')
    recreate = '--recriar' in sys.argv
    if not token and not recreate:
        raise SystemExit('Defina OKTO_DEMO_TOKEN localmente antes da carga.')
    print(json.dumps(seed(token or None, recreate=recreate), ensure_ascii=False))
