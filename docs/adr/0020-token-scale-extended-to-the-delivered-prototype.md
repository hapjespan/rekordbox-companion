# The type scale is extended to the sizes the delivered prototype actually uses

The delivered shell prototype (`web/design-input/prototype-crate-bridge.dc.html`)
styles almost everything at 10, 12, 13 and 15 pixels, while the delivered token
file beside it defines only 11, 14, 16 and 24. The two halves of the same bundle
disagree, and its handoff note asks for a pixel-accurate rebuild.

The scale is therefore extended with the sizes the prototype uses, under names in
the existing convention, and every one of them is read from a token. ADR 0004
stays intact as written: its point is that the design system is delivered rather
than invented, and these sizes are delivered, in the prototype rather than in the
token file. Rule 5's actual guarantee, that no colour, type, spacing or radius
value is hardcoded at a call site, is what keeps holding, and it would have been
broken by the alternative.

Considered alternative: map the prototype's sizes onto the four existing tokens,
rounding 12 and 13 to 11 or 14. Rejected because it silently changes a
high-fidelity design the owner asked to keep, and because the rounding would land
differently in each component, which is how a token set stops being one.

The same reasoning, applied while actually building the shell, extends to three
more groups the prototype needs and the token file lacked, all added under the
existing naming:

- letter spacing (0.08em eyebrows, 0.06em table headers, 0.04em stat labels,
  -0.01em wordmark), which is typography and was nowhere in the file;
- the shell's fixed dimensions and its off-scale paddings and gaps (300px
  sidebar, 64px top bar, 1180px content column, 252px lockup, 340px search,
  132px hero artwork, 26px logo, 34/30px pill heights, 7px status dot, and
  2/6/9/10/14px), alongside the delivered 4px scale, which already carried one
  such one-off (`--spacing-172`);
- one colour, `--color-chalk: #e6e6e6`, the hover shade the handoff note
  specifies for the white primary pill.

No radius token changed. Where the delivered design and WCAG 2.2 AA disagree,
accessibility wins and the substitution is a token swap, not a new value:
`--color-fog` (#73777c) is 4.16:1 on the `#121212` surface and fails AA for
the small text the prototype puts it on, so that text renders in
`--color-mist` instead.

Decided while applying the shell design, 2026-08-18.
