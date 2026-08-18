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

No colour, spacing or radius token changed: the prototype uses only values the
delivered set already defines.

Decided while applying the shell design, 2026-08-18.
