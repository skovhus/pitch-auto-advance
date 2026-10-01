(() => {
  if (location.origin !== 'https://app.pitch.com' || !location.pathname.includes(DECK_ID)) {
    throw new Error('Open this deck in Pitch presentation mode first.');
  }
  if (ACTION === 'prepare' && location.pathname.includes('/app/presentation/')) {
    document.querySelector('[data-test-id="title-bar-play-btn"]')?.click();
    return JSON.stringify({ ready: false });
  }
  if (!location.pathname.includes('/app/player/')) {
    throw new Error('Pitch left presentation mode. Press Open deck to reconnect.');
  }
  const read = () => {
    const counter = document.querySelector('[data-test-id="player-slide-count"]');
    const next = document.querySelector('[data-test-id="player-button-next"]');
    const previous = document.querySelector('[data-test-id="player-button-previous"]');
    const match = counter?.textContent.match(/(\d+)\s*\/\s*(\d+)/);
    if (!match || !next || !previous) throw new Error('Pitch slide controls are unavailable.');
    return { slide: Number(match[1]), total: Number(match[2]), url: location.href, canNext: !next.disabled };
  };
  const before = read();
  if (ACTION === 'next' || ACTION === 'previous') {
    const button = document.querySelector(`[data-test-id="player-button-${ACTION}"]`);
    if (!button.disabled) button.click();
  }
  return JSON.stringify(before);
})()
