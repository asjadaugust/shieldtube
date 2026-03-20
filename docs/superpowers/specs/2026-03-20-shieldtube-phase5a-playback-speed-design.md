# Phase 5a: Playback Speed Controls — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft

---

## Goal

Add playback speed selection during video playback (0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x).

**Success criteria:** During playback, press a button → speed menu appears → select speed → playback adjusts immediately.

---

## Design

Shield app only. No backend changes.

ExoPlayer has `player.setPlaybackSpeed(float)` built in. Just need UI.

**Changes:**

1. **PlaybackFragment.kt** — Add speed control:
   - Track current speed in a field (default 1.0f)
   - On D-pad up press (or a dedicated button): show speed selection dialog/overlay
   - Speed options: 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x
   - On selection: `player.setPlaybackParameters(PlaybackParameters(speed))`
   - Show brief toast confirming speed change

2. **Speed overlay** — Simple vertical list of speed options overlaid on the player. Current speed highlighted. D-pad up/down to navigate, center to select, back to dismiss.

**Files:**

| File | Change |
|------|--------|
| `shield-app/.../player/PlaybackFragment.kt` | Add speed control UI + ExoPlayer integration |

---

## What This Does NOT Include

- Per-video speed memory (always resets to 1x)
- Audio pitch correction (ExoPlayer handles this automatically)
