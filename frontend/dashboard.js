'use strict';
// Dashboard gráfica: lê /demo/dados e se atualiza quando o banco avisa (/demo/eventos).
const dash = document.getElementById('dash');
const status = document.getElementById('connection-status');
const money = (n) => n == null ? '—' : Number(n).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const moneyShort = (n) => Number(n) >= 1000 ? 'R$ ' + (Number(n) / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil' : money(n);
const number = (n) => n == null ? '—' : Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
const day = (s) => new Date(s + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
const time = (s) => new Date(s).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
const PAYMENTS = { pix: 'Pix', cartao: 'Cartão', dinheiro: 'Dinheiro' };
const SVG = 'http://www.w3.org/2000/svg';
// Cores validadas (dataviz/validate_palette.js, modo claro, vizinhos fixos): cada item mantém sua cor.
const FLAVOR_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']; // sabores em ordem alfabética
const PAYMENT_COLORS = { cartao: '#e87ba4', dinheiro: '#008300', pix: '#6250d6' }; // ordem alfabética fixa
const COLOR = { weekday: '#2a78d6', strong: '#eb6834', hours: '#2a78d6', losses: '#eb6834', stockOk: '#1baf7a' };

function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function svg(tag, attrs) {
  const e = document.createElementNS(SVG, tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  return e;
}

// Dica flutuante única, para barras e colunas.
const tip = node('div', null, 'chart-tip');
tip.hidden = true;
document.body.append(tip);
document.addEventListener('pointermove', (event) => {
  const target = event.target.closest?.('[data-tip]');
  if (!target) { tip.hidden = true; return; }
  tip.textContent = target.dataset.tip;
  tip.hidden = false;
  const x = Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + 'px';
  tip.style.top = (event.clientY - tip.offsetHeight - 12) + 'px';
});

function card(title, subtitle, wide) {
  const section = node('section', null, 'panel dash-card' + (wide ? ' wide' : ''));
  const head = node('div', null, 'dash-head');
  head.append(node('h2', title));
  if (subtitle) head.append(node('p', subtitle));
  section.append(head);
  return section;
}
function dataTable(headers, rows) {
  const details = node('details', null, 'dash-table');
  details.append(node('summary', 'Ver tabela'));
  const table = node('table');
  const tr = node('tr');
  headers.forEach((h) => tr.append(node('th', h)));
  const thead = node('thead'); thead.append(tr);
  const tbody = node('tbody');
  rows.forEach((row) => { const r = node('tr'); row.forEach((v) => r.append(node('td', v))); tbody.append(r); });
  table.append(thead, tbody);
  details.append(table);
  return details;
}
function empty(text) { return node('p', text, 'dash-empty'); }

// Colunas verticais (série temporal ou hora do dia); "strong" escurece a coluna.
function columns(items, format, legend, width = 640) {
  const wrap = node('div', null, 'columns-chart');
  if (!items.length) return empty('Sem vendas no período.');
  const W = width, H = 220, top = 12, bottom = 28, left = 74;
  const max = Math.max(...items.map((i) => Number(i.value))) || 1;
  const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', class: 'columns-svg' });
  for (let k = 0; k <= 3; k++) {
    const y = top + (H - top - bottom) * (1 - k / 3);
    chart.append(svg('line', { x1: left, x2: W, y1: y, y2: y, class: 'grid-line' }));
    const label = svg('text', { x: left - 8, y: y + 4, 'text-anchor': 'end', class: 'axis-label' });
    label.textContent = moneyShortOrNumber(max * k / 3, format);
    chart.append(label);
  }
  const step = (W - left) / items.length, bar = Math.max(6, Math.min(36, step - 6));
  items.forEach((item, i) => {
    const h = (H - top - bottom) * Number(item.value) / max;
    const x = left + i * step + (step - bar) / 2, y = H - bottom - h;
    const rect = svg('rect', { x, y, width: bar, height: Math.max(h, 1), rx: 4, class: 'column', fill: item.color });
    rect.dataset.tip = `${item.tip}: ${format(item.value)}`;
    chart.append(rect);
    const hit = svg('rect', { x: left + i * step, y: top, width: step, height: H - top - bottom, class: 'hit' });
    hit.dataset.tip = rect.dataset.tip;
    chart.append(hit);
    if (items.length <= 16 || i % 2 === 0) {
      const label = svg('text', { x: x + bar / 2, y: H - 8, 'text-anchor': 'middle', class: 'axis-label' });
      label.textContent = item.label;
      chart.append(label);
    }
  });
  chart.setAttribute('aria-label', items.map((i) => `${i.tip}: ${format(i.value)}`).join('; '));
  wrap.append(chart);
  if (legend) {
    const l = node('div', null, 'chart-legend');
    legend.forEach(([color, text]) => {
      const s = node('span', null, 'legend-item'), sw = node('i', null, 'swatch');
      sw.style.background = color; s.append(sw, text); l.append(s);
    });
    wrap.append(l);
  }
  return wrap;
}
function moneyShortOrNumber(v, format) { return format === money ? moneyShort(v) : number(Math.round(v)); }

// Barras horizontais com rótulo e valor diretos.
function bars(items, format, opts = {}) {
  if (!items.length) return empty(opts.empty || 'Nada registrado no período.');
  const max = opts.max || Math.max(...items.map((i) => Number(i.value))) || 1;
  const list = node('div', null, 'bar-list');
  items.forEach((item) => {
    const row = node('div', null, 'bar-row');
    row.dataset.tip = `${item.label}: ${item.tip || format(item.value)}`;
    row.append(node('span', item.label, 'bar-label'));
    const track = node('span', null, 'bar-track');
    const fill = node('span', null, 'bar-fill' + (item.cls ? ' ' + item.cls : ''));
    if (item.color && !item.cls) fill.style.background = item.color;
    fill.style.width = Math.max(1.5, Math.min(100, 100 * Number(item.value) / max)) + '%';
    track.append(fill);
    if (opts.marker) { const m = node('span', null, 'bar-marker'); m.style.left = (100 * opts.marker / max) + '%'; track.append(m); }
    row.append(track, node('span', item.text || format(item.value), 'bar-value'));
    list.append(row);
  });
  return list;
}

function kpis(data) {
  const r = data.resumo, l = data.perdas;
  const low = data.estoque.filter((i) => Number(i.saldo) < Number(i.estoque_minimo)).length;
  const confirmed = data.contexto.vendas_por_dia.reduce((s, d) => s + Number(d.vendas), 0);
  const items = [
    ['Receita', money(r.receita), 'Vendas confirmadas'],
    ['Vendas', number(r.vendas), `${number(r.porcoes)} porções`],
    ['Ticket médio', money(confirmed ? Number(r.receita) / confirmed : null), 'Receita ÷ vendas confirmadas'],
    ['Margem s/ ingredientes', money(Number(r.receita) - Number(r.custo)), 'Não é lucro líquido'],
    ['Custo das perdas', money(l.custo_total_perdas), `${number(l.percentual_sobre_receita_confirmada)}% da receita`],
    ['Abaixo do mínimo', number(low), low ? 'Ingredientes para repor' : 'Estoque em dia', low ? 'alert' : ''],
  ];
  const wrap = node('div', null, 'kpi-grid');
  items.forEach(([label, value, foot, cls]) => {
    const k = node('article', null, 'kpi' + (cls ? ' ' + cls : ''));
    k.append(node('span', label, 'kpi-label'), node('strong', value, 'kpi-value'), node('span', foot, 'kpi-foot'));
    wrap.append(k);
  });
  return wrap;
}

function render(data) {
  const c = data.contexto, l = data.perdas;
  const grid = node('div', null, 'dash-grid');

  const daily = card('Receita por dia', 'Quinta a domingo concentram o movimento', true);
  daily.append(columns(c.vendas_por_dia.map((d) => ({ label: day(d.dia), value: d.receita,
    color: d.dia_forte ? COLOR.strong : COLOR.weekday,
    tip: `${day(d.dia)} (${d.dia_semana}) • ${number(d.vendas)} vendas` })), money,
    [[COLOR.strong, 'Quinta a domingo'], [COLOR.weekday, 'Segunda a quarta']]),
    dataTable(['Data', 'Dia', 'Vendas', 'Receita'], c.vendas_por_dia.map((d) => [day(d.dia), d.dia_semana, number(d.vendas), money(d.receita)])));

  const flavorColor = Object.fromEntries(data.produtos.map((p, i) => [p.id, FLAVOR_COLORS[i % FLAVOR_COLORS.length]]));
  const flavorRows = [...c.ranking_sabores].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
  const flavors = card('Porções por sabor', 'Porções vendidas • cada sabor tem cor fixa');
  flavors.append(bars(flavorRows.map((f) => ({ label: f.nome, value: f.porcoes, color: flavorColor[f.produto_id],
    text: number(f.porcoes), tip: `${number(f.porcoes)} porções, ${money(f.receita)}` })), number),
    dataTable(['Sabor', 'Porções', 'Receita'], c.ranking_sabores.map((f) => [f.nome, number(f.porcoes), money(f.receita)])));

  const payments = card('Formas de pagamento', 'Valor recebido por forma');
  const totalPaid = data.por_pagamento.reduce((s, p) => s + Number(p.valor), 0) || 1;
  const paymentRows = [...data.por_pagamento].sort((a, b) => a.forma.localeCompare(b.forma));
  payments.append(bars(paymentRows.map((p) => ({ label: PAYMENTS[p.forma] || p.forma, value: p.valor,
    color: PAYMENT_COLORS[p.forma] || '#52514e',
    text: `${Math.round(100 * p.valor / totalPaid)}% • ${moneyShort(p.valor)}`, tip: `${money(p.valor)} em ${number(p.vendas)} vendas` })), money),
    dataTable(['Forma', 'Vendas', 'Valor'], data.por_pagamento.map((p) => [PAYMENTS[p.forma] || p.forma, number(p.vendas), money(p.valor)])));

  const hours = card('Vendas por hora do dia', 'Soma de todos os dias do período');
  hours.append(columns(data.por_hora.map((h) => ({ label: h.hora + 'h', value: h.vendas, color: COLOR.hours, tip: `${h.hora}h • ${number(h.vendas)} vendas, ${money(h.receita)}` })), number),
    dataTable(['Hora', 'Vendas', 'Receita'], data.por_hora.map((h) => [h.hora + 'h', number(h.vendas), money(h.receita)])));

  // Cobertura = saldo utilizável ÷ mínimo; os 10 mais apertados primeiro.
  const coverage = data.estoque.filter((i) => Number(i.estoque_minimo) > 0)
    .map((i) => ({ ...i, ratio: Number(i.saldo) / Number(i.estoque_minimo) }))
    .sort((a, b) => a.ratio - b.ratio).slice(0, 10);
  const stock = card('Estoque mais apertado', 'Saldo ÷ mínimo • o traço marca o mínimo (1×)');
  const scale = Math.max(2, Math.min(4, ...coverage.map((i) => i.ratio)) * 1.25);
  stock.append(bars(coverage.map((i) => ({ label: i.nome, value: Math.min(i.ratio, scale), cls: i.ratio < 1 ? 'alert' : '',
    color: COLOR.stockOk,
    text: i.ratio < 1 ? `Abaixo • ${number(i.ratio * 100)}%` : `${number(i.ratio)}×`,
    tip: `${window.oktoQuantidade(i.saldo,i.unidade)} (mínimo ${window.oktoQuantidade(i.estoque_minimo,i.unidade)})` })), number, { max: scale, marker: 1 }),
    dataTable(['Ingrediente', 'Saldo', 'Mínimo', 'Validade'], coverage.map((i) => [i.nome, `${window.oktoQuantidade(i.saldo,i.unidade)}`, `${window.oktoQuantidade(i.estoque_minimo,i.unidade)}`, i.validade ? day(i.validade) : '—'])));

  const losses = card('Perdas por ingrediente', 'Maiores custos de descarte no período');
  const topLosses = [...l.por_insumo].sort((a, b) => Number(b.custo) - Number(a.custo)).slice(0, 8);
  losses.append(bars(topLosses.map((i) => ({ label: i.nome, value: i.custo, color: COLOR.losses, tip: `${window.oktoQuantidade(i.quantidade,i.unidade)}, ${money(i.custo)}` })), money,
    { empty: 'Nenhuma perda registrada no período.' }),
    dataTable(['Ingrediente', 'Quantidade', 'Custo'], topLosses.map((i) => [i.nome, `${window.oktoQuantidade(i.quantidade,i.unidade)}`, money(i.custo)])));

  const recent = card('Últimas vendas', 'As mais recentes primeiro', true);
  const table = node('table', null, 'recent-table');
  const head = node('tr'); ['Quando', 'Itens', 'Pagamento', 'Valor', 'Status'].forEach((h) => head.append(node('th', h)));
  const thead = node('thead'); thead.append(head);
  const tbody = node('tbody');
  data.vendas.slice(0, 8).forEach((v) => {
    const tr = node('tr');
    [time(v.criado_em), v.itens, (v.pagamento || '').split(', ').map((f) => PAYMENTS[f] || f).join(', '), money(v.total), v.status]
      .forEach((x) => tr.append(node('td', x)));
    tbody.append(tr);
  });
  table.append(thead, tbody);
  const scroll = node('div', null, 'table-scroll'); scroll.append(table);
  recent.append(data.vendas.length ? scroll : empty('Nenhuma venda registrada.'));

  grid.append(daily, flavors, payments, hours, stock, losses, recent);
  dash.replaceChildren(kpis(data), grid);
}

// Tempo real: o servidor avisa quando a operação muda; a página busca os dados de novo.
const indicator = document.getElementById('live-indicator');
const liveText = document.getElementById('live-text');
let loading = null, pending = false, lastUpdate = null;
function setLive(state, text) { indicator.dataset.state = state; liveText.textContent = text; }

async function load() {
  if (loading) { pending = true; return loading; }
  loading = (async () => {
    try {
      const response = await fetch('/demo/dados', { cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 403
        ? 'Os dados não estão disponíveis para este computador. No servidor, confira LOCAL_DEMO_OPERATION_ID e DEMO_ACESSO_REMOTO.'
        : `Não foi possível consultar os dados (HTTP ${response.status}).`);
      const data = await response.json();
      document.querySelector('.workspace strong').textContent = data.operacao.nome;
      const simulated = data.contexto.parametros.natureza_dados === 'simulados';
      document.querySelector('.demo-badge').textContent = simulated ? 'DEMONSTRAÇÃO • DADOS SIMULADOS' : 'DADOS DA OPERAÇÃO';
      lastUpdate = new Date();
      status.textContent = `Período: ${day(data.periodo.inicio)} a ${day(data.periodo.fim)} • última atualização às ${lastUpdate.toLocaleTimeString('pt-BR',{timeZone:'America/Sao_Paulo'})}.` +
        (simulated ? ' Registros simulados para demonstração.' : '');
      render(data);
      dash.classList.remove('flash'); void dash.offsetWidth; dash.classList.add('flash');
    } catch (error) {
      status.textContent = error.message;
    } finally {
      loading = null;
      if (pending) { pending = false; load(); }
    }
  })();
  return loading;
}

function listen() {
  if (!('EventSource' in window)) { setLive('offline', 'Atualizando a cada 30 s'); setInterval(load, 30000); return; }
  const events = new EventSource('/demo/eventos');
  events.addEventListener('pronto', () => setLive('online', 'Ao vivo'));
  events.addEventListener('mudanca', () => { setLive('online', 'Ao vivo • dados novos'); load(); });
  events.addEventListener('lotado', () => { events.close(); setLive('offline', 'Ao vivo indisponível • atualizando a cada 30 s'); setInterval(load, 30000); });
  events.onerror = () => setLive('offline', 'Reconectando…');
}

load();
window.addEventListener('okto:estoque', () => {setLive('online','Atualização automática'); load();});
// Rede de segurança: mesmo sem avisos, recarrega a cada 2 minutos.
setInterval(() => { if (!lastUpdate || Date.now() - lastUpdate > 110000) load(); }, 120000);
