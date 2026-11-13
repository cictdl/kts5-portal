/* The page of Valluvar's Pond: the game is asked from the site of its makers only when the player presses Play (about 42 MB the
   first time), and shown in a frame that may run its scripts and keep its own score, and nothing else: no window of its own, no
   form, no change of the address of this page. */
(() => {
  'use strict';
  const stage = document.getElementById('stage'), play = document.getElementById('play'), full = document.getElementById('full');
  if (!stage || !play) return;
  play.addEventListener('click', () => {
    const frame = document.createElement('iframe');
    frame.title = "Valluvar's Pond";
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    frame.setAttribute('allow', 'autoplay; fullscreen');
    frame.setAttribute('referrerpolicy', 'no-referrer');
    frame.src = stage.dataset.src;
    stage.textContent = '';
    stage.append(frame);
    stage.classList.add('on');
    if (full && stage.requestFullscreen) full.hidden = false;
    frame.focus();
  });
  if (full) full.addEventListener('click', () => { if (stage.requestFullscreen) stage.requestFullscreen().catch(() => {}); });
})();
