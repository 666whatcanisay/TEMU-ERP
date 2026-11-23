/* Presentation only: show backend ledger rows already embedded by ProfitUI. */
(() => {
  let active = null, pinned = false, timer = null, ignoreFocus = false;
  const panel = document.createElement('div');
  panel.id = 'profit-breakdown-popover';
  panel.className = 'profit-breakdown-popover';
  panel.hidden = true;
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'false');
  panel.setAttribute('aria-labelledby', 'profit-breakdown-title');
  document.body.append(panel);
  const triggerFor = target => target instanceof Element ? target.closest('[data-profit-breakdown]') : null;
  const cancel = () => clearTimeout(timer);

  function position() {
    if (!active || panel.hidden) return;
    const rect = active.getBoundingClientRect();
    const chart = active.closest('.profit-waterfall').getBoundingClientRect();
    panel.style.width = '';
    const rightSpace = innerWidth - chart.right - 24;
    const leftSpace = chart.left - 24;
    if (rightSpace >= 360) panel.style.width = `${Math.min(620, rightSpace)}px`;
    else if (leftSpace >= 360) panel.style.width = `${Math.min(620, leftSpace)}px`;
    const width = panel.offsetWidth, height = panel.offsetHeight;
    let left = rightSpace >= 360 ? chart.right + 12 : leftSpace >= 360 ? chart.left - width - 12 : rect.right + 10;
    if (left + width > innerWidth - 12) left = rect.left - width - 10;
    left = Math.max(12, Math.min(left, innerWidth - width - 12));
    const top = Math.max(12, Math.min(rect.top, innerHeight - height - 12));
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  }
  function hide(returnFocus = false) {
    cancel();
    const previous = active;
    previous?.setAttribute('aria-expanded', 'false');
    panel.hidden = true;
    active = null;
    pinned = false;
    if (returnFocus && previous?.isConnected) {
      ignoreFocus = true;
      previous.focus({preventScroll:true});
      ignoreFocus = false;
    }
  }
  function show(trigger) {
    cancel();
    if (active === trigger && !panel.hidden) return;
    const template = trigger.closest('.profit-waterfall')?.querySelector(
      `template[data-breakdown-content="${trigger.dataset.profitBreakdown}"]`);
    if (!template) return;
    active?.setAttribute('aria-expanded', 'false');
    active = trigger;
    pinned = false;
    panel.replaceChildren(template.content.cloneNode(true));
    panel.querySelector('h4').id = 'profit-breakdown-title';
    trigger.setAttribute('aria-controls', panel.id);
    trigger.setAttribute('aria-expanded', 'true');
    panel.hidden = false;
    panel.scrollTop = 0;
    position();
  }
  const deferHide = () => {
    cancel();
    timer = setTimeout(() => {
      if (!pinned && !panel.contains(document.activeElement)) hide();
    }, 240);
  };
  document.addEventListener('pointerover', event => {
    if (event.pointerType === 'touch') return;
    const trigger = triggerFor(event.target);
    if (trigger) show(trigger);
    else if (panel.contains(event.target)) cancel();
  });
  document.addEventListener('pointerout', event => {
    if (!active || event.pointerType === 'touch') return;
    if (active.contains(event.relatedTarget) || panel.contains(event.relatedTarget)) return;
    if (active.contains(event.target) || panel.contains(event.target)) deferHide();
  });
  document.addEventListener('focusin', event => {
    if (ignoreFocus) return;
    const trigger = triggerFor(event.target);
    if (trigger) show(trigger);
    else if (panel.contains(event.target)) cancel();
    else if (active) hide();
  });
  document.addEventListener('click', event => {
    const trigger = triggerFor(event.target);
    if (trigger) {
      if (active === trigger && pinned) hide();
      else { show(trigger); pinned = true; }
    } else if (event.target.closest?.('.profit-breakdown-close')) hide(true);
    else if (!panel.contains(event.target)) hide();
  });
  document.addEventListener('keydown', event => {
    const trigger = triggerFor(event.target);
    if (event.key === 'Escape' && active) { hide(true); event.preventDefault(); }
    else if (trigger && ['Enter', ' '].includes(event.key)) {
      event.preventDefault();
      if (active === trigger && pinned) hide();
      else { show(trigger); pinned = true; }
    }
  });
  window.addEventListener('resize', position);
  document.addEventListener('scroll', event => {
    if (active && event.target !== panel && !panel.contains(event.target)) position();
  }, true);
  new MutationObserver(() => {
    if (active && !active.isConnected) hide();
  }).observe(document.body, {childList:true, subtree:true});
})();
