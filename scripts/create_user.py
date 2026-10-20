"""Credencial individual: token aleatorio, apenas hash persistido."""
import argparse
import hashlib
import secrets
from uuid import UUID
from app.db import connect

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--nome', required=True)
    parser.add_argument('--papel', choices=['gerente', 'caixa', 'estoquista', 'ia'], required=True)
    parser.add_argument('--operacao', type=UUID)
    parser.add_argument('--nova-operacao', help='Cria uma barraca; alternativa a --operacao')
    args = parser.parse_args()
    if bool(args.operacao) == bool(args.nova_operacao):
        parser.error('Informe exatamente --operacao ou --nova-operacao')
    token = secrets.token_urlsafe(32)
    with connect() as db:
        operation = args.operacao
        if args.nova_operacao:
            operation = db.execute('INSERT INTO operacoes(nome) VALUES(%s) RETURNING id', (args.nova_operacao,)).fetchone()['id']
        row = db.execute('INSERT INTO usuarios(operacao_id,nome,papel,token_hash) VALUES(%s,%s,%s,%s) RETURNING id',
                        (operation, args.nome, args.papel, hashlib.sha256(token.encode()).hexdigest())).fetchone()
    print(f'Operacao: {operation}\nUsuario: {row["id"]}\nToken (guarde; exibido apenas agora): {token}')
