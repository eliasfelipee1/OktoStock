from datetime import date
from decimal import Decimal
from scripts.dev4_compras import suggest


def test_complete_days_include_zero_exclude_today_and_losses():
    stock = [{'insumo_id': 'x', 'nome': 'Batata', 'unidade': 'g', 'estoque_minimo': 10,
              'saldo_utilizavel': 30, 'proxima_validade': None}]
    consumption = [
        {'insumo_id': 'x', 'dia': '2026-10-18', 'tipo': 'venda', 'quantidade': 100},
        {'insumo_id': 'x', 'dia': '2026-10-19', 'tipo': 'perda', 'quantidade': 500},
        {'insumo_id': 'x', 'dia': '2026-10-20', 'tipo': 'venda', 'quantidade': 1000},
        {'insumo_id': 'x', 'dia': '2026-10-01', 'tipo': 'venda', 'quantidade': 1000},
    ]
    result = suggest(stock, consumption, date(2026, 10, 20), history_days=2, horizon=3)[0]
    assert Decimal(result['media_diaria']) == 50
    assert Decimal(result['compra_sugerida']) == 130


def test_no_negative_purchase():
    stock = [{'insumo_id': 'x', 'nome': 'Batata', 'unidade': 'g', 'estoque_minimo': 10,
              'saldo_utilizavel': 30, 'proxima_validade': None}]
    assert Decimal(suggest(stock, [], date(2026, 10, 20))[0]['compra_sugerida']) == 0
