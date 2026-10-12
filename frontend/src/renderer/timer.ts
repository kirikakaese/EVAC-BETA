// SPDX-License-Identifier: AGPL-3.0-or-later
// The slide timer element ("progress", ADR-0051): a bar that shrinks (or grows) over the time the current
// playlist slide stays on screen. The player passes the slide's start and end (server-synchronised), so every
// screen shows the same remaining time. The bar runs as one CSS animation (cheap on small players); with reduced
// motion it is set once a second instead. Without a slide (editor, previews) it loops over the layout's duration.
import type { RenderContext } from "./types";
import { EvacWidget, WIDGETS } from "./widgets";

export interface SlideTiming { start: number; total: number; loop: boolean }

/** How the timer runs at ``now``: the slide's window, a loop (editor, previews) or null (no end: untimed). */
export function slideTiming(ctx: Pick<RenderContext, "slide" | "loopMs">, now: number): SlideTiming | null {
  if (ctx.slide === null) return null;
  if (ctx.slide) {
    const total = ctx.slide.end - ctx.slide.start;
    return total > 0 ? { start: ctx.slide.start, total, loop: false } : null;
  }
  const loop = Math.max(1000, ctx.loopMs ?? 10_000);
  return { start: now - (((now % loop) + loop) % loop), total: loop, loop: true };
}

/** The part of the bar that is filled at ``now`` (1 = full, 0 = empty). */
export function filled(timing: SlideTiming, now: number, grow: boolean): number {
  const done = Math.max(0, Math.min(1, (now - timing.start) / timing.total));
  return grow ? done : 1 - done;
}

export class ProgressWidget extends EvacWidget {
  draw(): void {
    const p = this.props;
    const vertical = p.orientation === "vertical";
    const grow = p.mode === "grow";
    const bar = document.createElement("span");
    bar.className = "evac-progress-bar";
    this.dataset.orientation = vertical ? "vertical" : "horizontal";
    this.dataset.mode = grow ? "grow" : "shrink";
    this.toggleAttribute("data-reverse", p.reverse === true);
    this.replaceChildren(bar);
    const box = this.parentElement;
    const now = this.ctx.now();
    const timing = slideTiming(this.ctx, now);
    box?.classList.toggle("evac-off", !timing && p.untimed === "hide");
    const axis = vertical ? "Y" : "X";
    const set = (part: number) => { bar.style.transform = `scale${axis}(${part.toFixed(4)})`; };
    if (!timing) {
      set(1);
      return;
    }
    if (this.ctx.reducedMotion || this.ctx.motion === false) {
      // no smoothing: one step a second (still counts down)
      const step = () => set(filled(timing.loop ? (slideTiming(this.ctx, this.ctx.now()) ?? timing) : timing,
                                    this.ctx.now(), grow));
      step();
      this.every(1000, step);
      return;
    }
    const st = bar.style;
    st.animationName = `evac-timer-${grow ? "grow" : "shrink"}-${axis.toLowerCase()}`;
    st.animationDuration = `${timing.total}ms`;
    st.animationDelay = `${-Math.round(now - timing.start)}ms`;
    st.animationTimingFunction = "linear";
    st.animationIterationCount = timing.loop ? "infinite" : "1";
    st.animationFillMode = "both";
  }
}
WIDGETS.progress = ProgressWidget;
