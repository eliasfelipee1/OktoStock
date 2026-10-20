"""Execute com python -m scripts.migrate. Migrations aplicadas nao podem ser alteradas."""
import hashlib
from pathlib import Path
from app.db import connect


def migrate():
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(728193)')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(nome text PRIMARY KEY, checksum text NOT NULL, aplicado_em timestamptz DEFAULT now())')
        for file in sorted((Path(__file__).resolve().parents[1] / 'migrations').glob('*.sql')):
            sql = file.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            previous = db.execute('SELECT checksum FROM schema_migrations WHERE nome=%s', (file.name,)).fetchone()
            if previous:
                if previous['checksum'] != checksum:
                    raise RuntimeError(f'Migration alterada: {file.name}')
                continue
            db.execute(sql)
            db.execute('INSERT INTO schema_migrations(nome,checksum) VALUES(%s,%s)', (file.name, checksum))
            print(f'Aplicada: {file.name}')


if __name__ == '__main__':
    migrate()
