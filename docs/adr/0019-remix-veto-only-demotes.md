# The remix/edit veto only demotes, never promotes

FR-008 forbids auto-matching a pair whose remix/edit markers differ and says
such pairs are "forced into the Review Queue". Read literally that promotes any
score into `review`, including a best candidate scoring in the single digits.
Phase 7 review found the implementation doing exactly that: a remix-marked
Spotify track absent from the Collection came back as `review` with three
meaningless candidates instead of `missing`, so it never became a Missing Track
and never entered the US4 purchase flow.

The veto therefore only ever demotes. A pair that would clear a bar is pushed
down into the Review Queue; a pair scoring below 75 stays a Missing Track. Two
things in the spec settle the reading: FR-007 and scenario 5 are unconditional
that below 75 becomes a Missing Track, and FR-008 is phrased as a prohibition on
auto-matching rather than as a routing rule. The promoting reading also
contradicts the product intent, because it makes a remix-marked track that the
DJ does not own impossible to buy.

Considered alternative: keep the literal reading and give the Review Queue a
relevance floor of its own. Rejected as two thresholds where the spec has one.

Decided in phase 7 review, 2026-08-18.
