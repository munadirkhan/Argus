console.log('  ARGUS demo · desk-dashboard');
console.log('  ready in 412 ms');
console.log('  Local: http://localhost:5173/');

setTimeout(() => {
  const renderWatchlist = require('./watchlist.js');
  // The first response has not arrived yet. Intentionally crash on this input.
  const quotes = { data: undefined, updatedAt: null };
  console.log(renderWatchlist(quotes));
  console.log('✓ Watchlist rendered; waiting for market data.');
}, 1500);
