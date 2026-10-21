from app.planning import PlanoPreAssadas, calculate


def params(**changes):
    data = dict(demanda_prevista_porcoes=100, pre_assadas_utilizaveis=30,
        em_preparo_prontas_no_prazo=20, margem_seguranca_porcoes=0,
        capacidade_disponivel_forno=80, limite_insumos_porcoes=100,
        espaco_disponivel_porcoes=80, minutos_ate_atendimento=40,
        tempo_pre_assamento_minutos=30)
    return PlanoPreAssadas(**dict(data, **changes))


def test_pending_is_not_zero():
    result = calculate(PlanoPreAssadas())
    assert result['status'] == 'dados_pendentes'
    assert result['produzir_agora_porcoes'] is None
    assert len(result['pendencias']) == 9


def test_ready_and_in_progress_not_double_counted():
    r = calculate(params())
    assert r['produzir_agora_porcoes'] == 50
    assert r['iniciar_em_ate_minutos'] == 10
    assert r['executado'] is False


def test_capacity_and_demand_shortage():
    r = calculate(params(capacidade_disponivel_forno=40, espaco_disponivel_porcoes=10))
    assert r['produzir_agora_porcoes'] == 10
    assert r['deficit_demanda_porcoes'] == 40
    assert 'armazenamento' in r['restricoes']


def test_no_late_supply_claimed():
    r = calculate(params(minutos_ate_atendimento=20))
    assert r['produzir_agora_porcoes'] == 0
    assert r['deficit_demanda_porcoes'] == 50
    assert 'tempo_insuficiente' in r['restricoes']


def test_no_production_if_surplus():
    r = calculate(params(demanda_prevista_porcoes=10))
    assert r['produzir_agora_porcoes'] == 0
    assert r['sobra_prevista_antes_nova_fornada'] == 40


def test_security_buffer_not_reported_as_customer_shortage():
    r = calculate(params(demanda_prevista_porcoes=50, margem_seguranca_porcoes=10, capacidade_disponivel_forno=0))
    assert r['deficit_demanda_porcoes'] == 0
    assert r['deficit_meta_com_seguranca_porcoes'] == 10


def test_authorized_calculator_endpoint(setup):
    c = setup
    assert c.post('/planejamento/pre-assadas', json={}).json()['status'] == 'dados_pendentes'
    c.headers['Authorization'] = 'Bearer caixa'
    assert c.post('/planejamento/pre-assadas', json={}).status_code == 403
    c.headers['Authorization'] = 'Bearer ia'
    assert c.post('/planejamento/pre-assadas', json=params().model_dump()).json()['produzir_agora_porcoes'] == 50
