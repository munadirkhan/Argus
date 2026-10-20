import { useEffect } from "react";
import { useArgus } from "./store";
import { speaker } from "./speaker";

/** Say Argus's replies, its offers and its questions out loud.
 *  Mount it in exactly one window (the orb on desktop, the hub in a browser). */
export function useVoiceOut(active: boolean) {
  useEffect(() => {
    if (!active) return;
    let liveAt = useArgus.getState().conn === "live" ? Date.now() : 0;
    return useArgus.subscribe((s, prev) => {
      if (s.conn === "live" && prev.conn !== "live") liveAt = Date.now();
      if (s.conn !== "live") liveAt = 0;
      if (s.source !== "live") return;
      // Stop means silence, everywhere.
      if (s.stoppedAt !== prev.stoppedAt) {
        speaker.hush(false);
        return;
      }
      // On connect the core replays its history in a burst: old news.
      if (!liveAt || Date.now() - liveAt < 1500) return;

      if (s.approval && s.approval.id !== prev.approval?.id) {
        const a = s.approval;
        speaker.sayNow(a.kind === "handoff"
          ? `Your turn. ${a.title}. Press done when you're in.`
          : `I need your go-ahead. ${a.title}.`);
      }
      if (s.prophecy && s.prophecy !== prev.prophecy) {
        const o = s.observations[s.prophecy];
        if (o) speaker.say(o.suggestion);
      }
      if (s.entries !== prev.entries && s.entries.length) {
        const last = s.entries[s.entries.length - 1];
        const before = prev.entries[prev.entries.length - 1];
        if (last !== before && last.kind === "message") {
          if (last.role === "user") speaker.hush(false);
          else if (last.text && last.text !== "Stopped.") speaker.say(last.text);
        }
      }
    });
  }, [active]);
}
