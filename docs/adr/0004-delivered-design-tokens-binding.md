# The delivered design token set is binding, with Inter as font substitute

The design source of truth is the delivered Spotify-style token set in
web/design-input/ (DESIGN.md, tokens.json, variables.css, theme.css), not a
design system to be invented. Every rendered color, typography, spacing and
radius value traces to those tokens. The SpotifyMixUI font is proprietary and is
never bundled or referenced; Inter plus system-ui ships under the original token
names, which keeps the tokens stable if the substitute ever changes. Rekordbox
contributes information density and keyboard-first workflow, not its color
scheme. Decided at kickoff (D3), 2026-08-16.
