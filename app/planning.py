"""Calculo explicavel de pre-assamento. Nao preve demanda nem altera estoque."""
from typing import Optional
from pydantic import Field
from app.schemas import Model


class PlanoPreAssadas(Model):
    demanda_prevista_porcoes: Optional[int] = Field(default=None, ge=0, le=100000)
    pre_assadas_utilizaveis: Optional[int] = Field(default=None, ge=0, le=100000)
    em_preparo_prontas_no_prazo: Optional[int] = Field(default=None, ge=0, le=100000)
    margem_seguranca_porcoes: Optional[int] = Field(default=None, ge=0, le=100000)
    capacidade_disponivel_forno: Optional[int] = Field(default=None, ge=0, le=100000)
    limite_insumos_porcoes: Optional[int] = Field(default=None, ge=0, le=100000)
    espaco_disponivel_porcoes: Optional[int] = Field(default=None, ge=0, le=100000)
    minutos_ate_atendimento: Optional[int] = Field(default=None, ge=0, le=1440)
    tempo_pre_assamento_minutos: Optional[int] = Field(default=None, gt=0, le=1440)


def calculate(body: PlanoPreAssadas):
    values = body.model_dump()
    missing = [name for name, value in values.items() if value is None]
    base = {'origem': 'parametros_informados_na_requisicao', 'dados': values,
            'executado': False, 'confirmacao_do_dono_necessaria': True,
            'escopo': 'Uma fornada; previsao de demanda e validade precisam ser validadas na origem.'}
    if missing:
        return {**base, 'status': 'dados_pendentes', 'pendencias': missing,
                'produzir_agora_porcoes': None}
    ready = body.pre_assadas_utilizaveis + body.em_preparo_prontas_no_prazo
    target = body.demanda_prevista_porcoes + body.margem_seguranca_porcoes
    need = max(0, target - ready)
    limits = {'forno': body.capacidade_disponivel_forno, 'insumos': body.limite_insumos_porcoes,
              'armazenamento': body.espaco_disponivel_porcoes}
    fits = body.tempo_pre_assamento_minutos <= body.minutos_ate_atendimento
    produce = min(need, *limits.values()) if fits else 0
    reasons = [key for key, value in limits.items() if value < need]
    if not fits and need:
        reasons.append('tempo_insuficiente')
    return {**base, 'status': 'atencao' if reasons else 'calculado', 'pendencias': [],
            'necessidade_adicional_porcoes': need, 'produzir_agora_porcoes': produce,
            'restricoes': reasons, 'deficit_demanda_porcoes': max(0, body.demanda_prevista_porcoes-ready-produce),
            'deficit_meta_com_seguranca_porcoes': max(0, target-ready-produce),
            'sobra_prevista_antes_nova_fornada': max(0, ready-body.demanda_prevista_porcoes),
            'iniciar_em_ate_minutos': max(0, body.minutos_ate_atendimento-body.tempo_pre_assamento_minutos) if need else None,
            'formula': 'max(0, demanda + seguranca - pre_assadas_utilizaveis - em_preparo_no_prazo), limitado por forno, insumos, armazenamento e tempo'}
