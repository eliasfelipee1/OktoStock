"""Baseline DEV4: sugestoes explicaveis, somente leitura; nao realiza compras."""
import argparse
import json
import os
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
import httpx


def suggest(stock, consumption, today, history_days=7, horizon=3):
    start = today - timedelta(days=history_days)
    used = {}
    for row in consumption:
        day = date.fromisoformat(row['dia'])
        # Janela de dias completos; dias sem consumo entram como zero.
        if start <= day < today and row['tipo'] == 'venda':
            key = row['insumo_id']
            used[key] = used.get(key, Decimal(0)) + Decimal(str(row['quantidade']))
    result = []
    for row in stock:
        average = used.get(row['insumo_id'], Decimal(0)) / history_days
        demand = average * horizon
        purchase = max(Decimal(0), demand + Decimal(str(row['estoque_minimo'])) - Decimal(str(row['saldo_utilizavel'])))
        result.append({'insumo_id': row['insumo_id'], 'nome': row['nome'], 'unidade': row['unidade'],
                       'media_diaria': str(average.quantize(Decimal('0.001'))),
                       'compra_sugerida': str(purchase.quantize(Decimal('0.001'), rounding=ROUND_CEILING)),
                       'proxima_validade': row['proxima_validade'],
                       'metodo': f'media de {history_days} dias completos; cobertura de {horizon} dias + estoque minimo'})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=date.fromisoformat, required=True, help='Dia de referencia no fuso da barraca (AAAA-MM-DD)')
    parser.add_argument('--historico', type=int, default=7)
    parser.add_argument('--cobertura', type=int, default=3)
    args = parser.parse_args()
    if args.historico < 1 or args.cobertura < 1:
        parser.error('Periodos devem ser positivos')
    with httpx.Client(base_url=os.getenv('API_URL', 'http://127.0.0.1:8000'),
                      headers={'Authorization': 'Bearer ' + os.environ['API_TOKEN']}, timeout=30) as client:
        stock_response = client.get('/relatorios/estoque')
        consumption_response = client.get('/relatorios/consumo')
        stock_response.raise_for_status()
        consumption_response.raise_for_status()
    print(json.dumps(suggest(stock_response.json(), consumption_response.json(), args.data, args.historico, args.cobertura), indent=2, ensure_ascii=False))
