"""Cadastro das fichas reais: quantidades por porção, sem inferir rendimento."""
from typing import List, Optional
from decimal import Decimal
from pydantic import Field, model_validator
from app.schemas import Model, Ingrediente


class Recipe(Model):
    preco: Optional[Decimal] = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    ingredientes: List[Ingrediente] = Field(min_length=1, max_length=100)
    preparo: str = Field(min_length=1, max_length=4000)
    observacoes: str = Field(default='', max_length=2000)
    validada: bool = False

    @model_validator(mode='after')
    def unique_ingredients(self):
        if len({i.insumo_id for i in self.ingredientes}) != len(self.ingredientes):
            raise ValueError('Ingrediente duplicado')
        if self.validada and self.preco is None:
            raise ValueError('Informe preço de venda antes de ativar')
        return self
