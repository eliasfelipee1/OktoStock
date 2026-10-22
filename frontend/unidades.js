'use strict';
window.oktoQuantidade = (value, unit) => {
  const amount = Number(value);
  const converted = Math.abs(amount) >= 1000 && (unit === 'g' || unit === 'ml');
  const label = converted ? (unit === 'g' ? 'kg' : 'L') : unit;
  return (converted ? amount / 1000 : amount).toLocaleString('pt-BR', {maximumFractionDigits: 6}) + ' ' + label;
};
