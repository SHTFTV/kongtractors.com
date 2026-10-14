(() => {
  const toggle = document.querySelector('.k-toggle');
  const menu = document.querySelector('#k-menu');
  toggle?.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    menu.classList.toggle('is-open', open);
  });
  menu?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    toggle.setAttribute('aria-expanded', 'false'); menu.classList.remove('is-open');
  }));
  document.querySelectorAll('.k-word-swap').forEach(button => {
    button.addEventListener('click', () => {
      const revealed = button.classList.toggle('is-revealed');
      button.setAttribute('aria-pressed', String(revealed));
      button.setAttribute('aria-label', revealed ? 'Kong trademark' : 'Conquer');
    });
  });
  const video = document.querySelector('.k-film');
  const button = document.querySelector('.k-motion');
  if (!video || !button) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduced.matches, frame = 0;
  const sync = () => {
    document.body.classList.toggle('motion-paused', paused);
    button.setAttribute('aria-pressed', String(paused));
    button.textContent = paused ? 'Play motion ▷' : 'Pause motion Ⅱ';
    if (paused || document.hidden) video.pause(); else video.play().catch(() => {});
  };
  button?.addEventListener('click', () => { paused = !paused; sync(); });
  reduced.addEventListener('change', e => { paused = e.matches; sync(); });
  document.addEventListener('visibilitychange', sync);
  setInterval(() => {
    if (paused || document.hidden) return;
    frame = (frame + 1) % 3;
    document.querySelectorAll('.k-machine').forEach(panel => {
      panel.querySelectorAll('img').forEach((img, i) => img.classList.toggle('is-active', i === frame));
    });
  }, 5200);
  sync();
})();
