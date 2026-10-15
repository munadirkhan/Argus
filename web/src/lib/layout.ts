/** Where the orb should sit on screen, measured from the DOM (.orb-zone).
 *  The 3D camera reads this every frame and shifts its projection to match,
 *  so the orb is framed by the layout at any window size. */
export const frame = { cx: 0, cy: 0, r: 0 };

/** Where the hundred eyes should look instead of the cursor (screen px),
 *  set by whichever sight window Argus is focused on. */
export const gaze = { x: 0, y: 0, until: 0, side: "" as "left" | "right" | "" };

export function watchOrbZone(el: HTMLElement) {
  const update = () => {
    const b = el.getBoundingClientRect();
    frame.cx = b.left + b.width / 2;
    frame.cy = b.top + b.height * 0.47;
    // sphere radius in px: fill most of the zone, leave room for the rings
    frame.r = Math.max(60, Math.min(b.height * 0.36, b.width * 0.3));
  };
  update();
  const ro = new ResizeObserver(update);
  ro.observe(el);
  window.addEventListener("resize", update);
  return () => {
    ro.disconnect();
    window.removeEventListener("resize", update);
  };
}
