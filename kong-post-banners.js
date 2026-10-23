(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('[data-kong-banner]').forEach(banner => {
    const video = banner.querySelector('video');
    const button = banner.querySelector('.kb-motion');
    if (!video || !button) return;
    let userPaused = false;
    const sync = () => {
      const paused = userPaused || reduce.matches || document.hidden;
      button.hidden = reduce.matches;
      button.textContent = paused ? 'Play ▷' : 'Pause Ⅱ';
      button.setAttribute('aria-label', paused ? 'Play Kong brand animation' : 'Pause Kong brand animation');
      button.setAttribute('aria-pressed', String(paused));
      if (paused) video.pause(); else video.play().catch(() => { button.textContent = 'Play ▷'; });
    };
    button.addEventListener('click', () => { userPaused = !userPaused; sync(); });
    reduce.addEventListener('change', sync);
    document.addEventListener('visibilitychange', sync);
    sync();
  });
})();
