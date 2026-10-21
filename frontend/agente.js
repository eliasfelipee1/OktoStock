'use strict';
const el = (id) => document.getElementById(id);
let token = '';
let connected = false;
const errors = {
  IA_CREDENCIAL_RECUSADA: 'A credencial da Anthropic foi recusada. Verifique a configuração no servidor.',
  IA_LIMITE_DO_PROVEDOR: 'Limite da Anthropic atingido. Verifique o saldo ou tente depois.',
  IA_NAO_CONFIGURADA: 'A IA ainda não está configurada no servidor.',
  IA_INDISPONIVEL: 'O provedor de IA está indisponível.',
  IA_TEMPO_ESGOTADO: 'O provedor demorou demais. Tente novamente.',
  CREDENCIAL_INVALIDA: 'Token de usuário inválido.',
  SEM_PERMISSAO: 'Somente o gerente pode salvar a preferência.'
};
async function request(path, body, method = 'POST') {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errors[data.detail?.codigo] || `Não foi possível concluir a consulta (HTTP ${response.status}).`);
  return data;
}
function invalidate() {
  connected = false;
  token = '';
  el('pergunta').disabled = true;
  el('send-otto').disabled = true;
  el('report-preference').hidden = true;
  el('otto-answer').textContent = '';
  el('operation-status').textContent = 'Conecte a operação.';
  el('data-nature').textContent = 'Aguardando conexão';
}
el('api-token').addEventListener('input', invalidate);
el('connect-otto').addEventListener('click', async () => {
  invalidate();
  token = el('api-token').value.trim();
  if (!token) { el('operation-status').textContent = 'Informe seu token de usuário.'; return; }
  el('connect-otto').disabled = true;
  el('operation-status').textContent = 'Consultando dados…';
  try {
    const data = await request('/ia/contexto?dias_historico=14');
    connected = true;
    el('pergunta').disabled = false;
    el('send-otto').disabled = false;
    el('operation-status').textContent = `Conectado: ${data.cadastros.produtos} sabores, ${data.cadastros.vendas} vendas cadastradas.`;
    el('data-nature').textContent = data.operacao.parametros.natureza_dados || 'Não informada';
    el('report-preference').hidden = !data.operacao.relatorio_semanal.pergunta;
  } catch (error) { el('operation-status').textContent = error.message; }
  finally { el('connect-otto').disabled = false; }
});
async function preference(choice) {
  el('report-yes').disabled = el('report-no').disabled = true;
  try {
    const data = await request('/ia/preferencias/relatorio-semanal', { deseja_receber: choice }, 'PUT');
    el('report-preference').hidden = true;
    el('operation-status').textContent = data.mensagem;
  } catch (error) { el('operation-status').textContent = error.message; }
  finally { el('report-yes').disabled = el('report-no').disabled = false; }
}
el('report-yes').addEventListener('click', () => preference(true));
el('report-no').addEventListener('click', () => preference(false));
el('send-otto').addEventListener('click', async () => {
  const question = el('pergunta').value.trim();
  if (!connected || question.length < 3 || question.length > 2000) {
    el('otto-answer').textContent = 'Conecte-se e escreva uma pergunta de 3 a 2.000 caracteres.'; return;
  }
  el('send-otto').disabled = true;
  el('otto-answer').textContent = 'Otto está consultando o contexto…';
  try {
    const result = await request('/ia/perguntar', { pergunta: question, dias_historico: 14 });
    el('otto-answer').textContent = result.resposta;
  } catch (error) { el('otto-answer').textContent = error.message; }
  finally { el('send-otto').disabled = !connected; }
});
