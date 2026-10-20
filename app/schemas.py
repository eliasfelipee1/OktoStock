from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Insumo(Model):
    nome: str = Field(min_length=1, max_length=120)
    unidade: Literal['g', 'ml', 'un']
    estoque_minimo: Decimal = Field(default=Decimal('0'), ge=0, max_digits=18, decimal_places=3)


class Ingrediente(Model):
    insumo_id: UUID
    quantidade: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class Produto(Model):
    nome: str = Field(min_length=1, max_length=120)
    preco: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    versao: int = Field(default=1, gt=0)
    ingredientes: List[Ingrediente] = Field(min_length=1)


class Recebimento(Model):
    insumo_id: UUID
    codigo: str = Field(min_length=1, max_length=120)
    fornecedor: str = Field(min_length=1, max_length=120)
    validade: date
    quantidade: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    custo_unitario: Decimal = Field(ge=0, max_digits=18, decimal_places=6)


class Item(Model):
    produto_id: UUID
    quantidade: int = Field(gt=0, le=10000)


class Pagamento(Model):
    forma: Literal['pix', 'dinheiro', 'cartao']
    valor: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class Venda(Model):
    idempotency_key: UUID
    turno_id: UUID
    itens: List[Item] = Field(min_length=1, max_length=100)
    pagamentos: List[Pagamento] = Field(min_length=1, max_length=10)


class Perda(Model):
    produto_id: Optional[UUID] = None
    turno_id: Optional[UUID] = None
    idempotency_key: Optional[UUID] = None
    lote_id: UUID
    quantidade: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    motivo: str = Field(min_length=3, max_length=500)


class Motivo(Model):
    motivo: str = Field(min_length=3, max_length=500)


class PerdaReceita(Model):
    produto_id: UUID
    porcoes: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    motivo: str = Field(min_length=3, max_length=500)
    turno_id: Optional[UUID] = None
    idempotency_key: UUID
