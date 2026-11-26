"""Gate sidechain: Input Sidechain on the Noise Gate block (issue #131), keying its gate by the input, as the Input block's gate
hears it, instead of by its own signal (tools/patch_sidechain.py, after the FX Loop gate and before the GR knobs).
A checkbox in the web page's DSP features (WEB 'dsp': its code takes Block 3 room, tools/block3.py) and HX_GATE_SC for build.py.
The knob's writers and the Input block's source marks reach a wrapper around the gate core (src/sharc/gate_sc.asm), and each
Noise Gate's DSP cost rises by patch_sidechain.SC_COST a core.

Nothing on the M4 side: the knob lives in the block."""
FLAG = 'HX_GATE_SC'
WEB = 'dsp'
XL_PORTED = True
