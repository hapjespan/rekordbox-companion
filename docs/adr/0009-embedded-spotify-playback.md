# Embedded Spotify playback in the review UI via the Web Playback SDK

Resolving a doubtful Match by ear requires hearing both versions: the local
candidate and the Spotify original. The owner has Spotify Premium, so the review
UI embeds full-track Spotify playback through the Web Playback SDK instead of
linking out to the Spotify app. Considered alternatives: 30-second preview URLs
(unreliable for new API apps since late 2024) and external links (breaks the
keyboard-only review flow). Consequence: a Premium account is a runtime
dependency of the review feature, and the SDK's browser DRM requirements are a
named unknown to spike early. Decided in phase 1 grilling (D9), 2026-08-16.
