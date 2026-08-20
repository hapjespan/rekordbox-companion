# Embedded Spotify playback in the review UI via the Web Playback SDK

Resolving a doubtful Match by ear requires hearing both versions: the local
candidate and the Spotify original. The owner has Spotify Premium, so the review
UI embeds full-track Spotify playback through the Web Playback SDK instead of
linking out to the Spotify app. Considered alternatives: 30-second preview URLs
(unreliable for new API apps since late 2024) and external links (breaks the
keyboard-only review flow). Consequence: a Premium account is a runtime
dependency of the review feature, and the SDK's browser DRM requirements are a
named unknown to spike early. Decided in phase 1 grilling (D9), 2026-08-16.

**Update, phase 6 (T034), 2026-08-18**: the named DRM/EME unknown was not
resolved by spiking -- the phase 6 build container has no real Spotify
Premium account, no browser with Widevine/EME, and no guaranteed path to
Spotify's CDN, so no throwaway-page pass/fail there would be genuine
evidence. The owner committed directly to this ADR's embedded approach
instead of running the spike; `DualPlayback.tsx` (T040) is built straight
against the Web Playback SDK, with real playback verified on the owner's
Mac rather than in this sandbox (same pattern as quickstart.md's
owner-supplied-fixture tasks).
