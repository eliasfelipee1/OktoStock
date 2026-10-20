"""Cria dados FICTICIOS via API. Execute apenas uma vez em ambiente de demonstracao."""
import os
from datetime import date, timedelta
from uuid import uuid4
import httpx


def main():
    with httpx.Client(base_url=os.getenv('API_URL', 'http://127.0.0.1:8000'),
                      headers={'Authorization': 'Bearer ' + os.environ['API_TOKEN']}, timeout=30) as client:
        def post(path, data=None):
            response = client.post(path, json=data)
            response.raise_for_status()
            return response.json()

        ingredient = post('/insumos', {'nome': 'Batata bruta — EXEMPLO', 'unidade': 'g', 'estoque_minimo': '2000'})
        product = post('/produtos', {'nome': 'Batata simples — EXEMPLO', 'preco': '30.00',
            'ingredientes': [{'insumo_id': ingredient['id'], 'quantidade': '450'}]})
        post('/estoque/recebimentos', {'insumo_id': ingredient['id'], 'codigo': 'DEMO', 'fornecedor': 'Ficticio',
            'validade': str(date.today() + timedelta(days=7)), 'quantidade': '10000', 'custo_unitario': '0.008'})
        shift = post('/turnos')
        sale = post('/vendas', {'idempotency_key': str(uuid4()), 'turno_id': shift['id'],
            'itens': [{'produto_id': product['id'], 'quantidade': 1}], 'pagamentos': [{'forma': 'pix', 'valor': '30.00'}]})
        print('Venda de exemplo:', sale['id'])
        print('Total:', sale['total'], '| Custo de ingredientes:', sale['custo'])
        print('Turno aberto:', shift['id'])


if __name__ == '__main__':
    main()
