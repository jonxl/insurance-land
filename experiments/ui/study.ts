function choose(name: string) {
  document
    .querySelectorAll<HTMLElement>('.world-section')
    .forEach((s) => (s.hidden = s.id !== name));
  document
    .querySelectorAll<HTMLElement>('[data-world]')
    .forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.world === name)));
  history.replaceState(null, '', '#' + name);
}
document
  .querySelectorAll<HTMLElement>('[data-world]')
  .forEach((b) => (b.onclick = () => choose(b.dataset.world)));
choose(
  ['peace', 'standard', 'chaos'].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : 'standard',
);
addEventListener('load', () => scrollTo(0, 0));
