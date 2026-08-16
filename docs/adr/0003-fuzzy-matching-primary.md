# Fuzzy matching is the primary path, ISRC is opportunistic

The library is mp3/m4a without ISRC tags, so exact identifier matching would hit
near zero. Normalized artist+title fuzzy scoring is therefore the primary match
path, and ISRC exact match stays as a zero-cost fast lane that wins if ever
populated. Consequence: the review UI and the Golden Set carry the product's
accuracy and get budget accordingly. Decided at kickoff (D2), 2026-08-16.
