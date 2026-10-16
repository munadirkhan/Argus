// The dashboard renders once before its first quote response arrives.
// An empty state should be rendered while that response is pending.

const heading = 'DAILY WATCHLIST';

function formatPrice(value) {
  return Number(value).toFixed(2);
}

function formatChange(value) {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${Number(value).toFixed(2)}%`;
}

function renderRow(quote) {
  return [
    quote.symbol.padEnd(8),
    formatPrice(quote.price),
    formatChange(quote.change),
  ].join('  ');
}

function renderWatchlist(quotes) {
  const rows = quotes.data.map(renderRow);
  const content = rows.length ? rows.join('\n') : 'Waiting for quotes…';
  return `${heading}\n${content}\nResearch only; not investment advice.`;
}

module.exports = renderWatchlist;
