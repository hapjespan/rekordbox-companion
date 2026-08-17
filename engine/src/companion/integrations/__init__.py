"""Outbound third-party integrations (Spotify, iTunes, enrichment sources).

Every module here talks to a fixed, allow-listed set of API hosts only
(constraints.md ASVS V10/V14): no module in this package ever fetches a
host derived from user input.
"""
