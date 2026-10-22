"""Reavalia vencimentos sem depender do navegador; os movimentos disparam via PostgreSQL."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from app.db import connect

log = logging.getLogger(__name__)


def refresh_all():
    with connect() as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='10s'")
        for row in db.execute('SELECT id FROM operacoes ORDER BY id').fetchall():
            db.execute('SELECT atualizar_alertas_prontos(%s)', (row['id'],))
            db.execute('SELECT atualizar_alertas_reposicao(%s)', (row['id'],))


async def monitor():
    while True:
        try:
            await asyncio.to_thread(refresh_all)
        except Exception as exc:
            log.error('Falha no monitor de reposição (%s); nova tentativa em 15s', type(exc).__name__)
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(monitor()) if os.getenv('OTTO_MONITOR_ATIVO', '1') == '1' else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
