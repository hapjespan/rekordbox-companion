# Rekordbox play history is ignored entirely

Booking-related ranking reads exactly two signals from the Rekordbox database:
lifetime per-track play counts and playlist membership across the existing tree.
The full play history (sessions, dates) is ignored by explicit owner decision:
no session linking, no archive folders, no booking backfill import. The play
count is a lifetime total with no per-context dimension, so it ranks tracks
within a structure and never splits them by occasion. Decided at kickoff (D4,
superseding an earlier history-based design), 2026-08-16.
