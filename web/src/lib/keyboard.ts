export const VIDEO_MODE = new URLSearchParams(window.location.search).get('record') === '1';

export function isTyping(target: EventTarget | null) {
  return target instanceof HTMLElement && Boolean(target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])'));
}
