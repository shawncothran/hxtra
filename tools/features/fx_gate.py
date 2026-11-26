"""FX gate: a noise gate built into the FX Loop and Return blocks (issue #69), with Gate, Threshold and Decay knobs as the Input
block's, gating the returned signal before its Return level and Mix (tools/patch_gate.py, after the Metronome and before the GR knobs).
A checkbox in the web page's DSP features (WEB 'dsp': its code takes Block 3 room, tools/block3.py) and HX_FX_GATE for build.py.
The gate wraps the blocks' return reader (src/sharc/fx_gate.asm), and each block's DSP cost rises by patch_gate.GATE_COST a reader.

Nothing on the M4 side: the knobs live in the blocks."""
FLAG = 'HX_FX_GATE'
WEB = 'dsp'
XL_PORTED = True
