"""Long press: in Stomp mode, holding a stomp footswitch 1..5 for 1 s opens the tuner, presses FS4/FS5 or presses a virtual
footswitch FS6..FS10; a tap still toggles its blocks, on release (src/m4/long_press.s). FS6..FS10 Function give each virtual
footswitch a stock footswitch function; as Stomp it toggles the blocks assigned to MIDI CC 20..24, and GlobalEQ opens Global EQ."""
from dataclasses import replace

from features import Setting
import patch_menu as pm

FLAG = 'HX_LONG_PRESS'
MENU = 'Footswitches'
XL_ORDER = 100                      # after More Snapshots, whose XL module data it reads
XL_PORTED = True
MODULE = 'src/m4/long_press.s'
XL_MODULE = 'src/m4/long_press_xl.s'
VALUES = (b'Off', b'Tuner', b'FS4', b'FS5', b'FS6', b'FS7', b'FS8', b'FS9', b'FS10')
VIRTUAL_CC = 20                     # FS6..FS10 are MIDI CC 20..24 (undefined in the MIDI spec), as Bypass Assign > MIDI In sets them
# FS1..FS5 Hold default to FS6..FS10 (values 4..8): virtual settings read their default until first set.
HOLDS = tuple(Setting(f'fs{n}', f'Function\nFS{n} Hold'.encode(), VALUES, default=n + 3) for n in (1, 2, 3, 4, 5))
# FS3..FS5 Function's values with Tuner for TAP/Tunr, as a hold has no use for a tap; from Stomp on, value v is function v + 1 of the
# stock dispatch 0x28dd14a0. Stomp, the default, toggles CC 20..24. GlobalEQ comes last, so stored values keep their meaning.
FUNCTIONS = tuple(Setting(f'fs{n}_function', f'Function\nFS{n}'.encode(),
                          (b'Tuner', f'Stomp {n}'.encode(), b'Bank Up', b'Bank Dn', b'PresetUp', b'PresetDn', b'SnpshtUp', b'SnpshtDn',
                           b'FS Mode>', b'<FS Mode', b'AllBypas', b'TogglEXP', b'GlobalEQ'), default=1) for n in (6, 7, 8, 9, 10))
SETTINGS = HOLDS + FUNCTIONS
XL_HOLD_VALUES = (b'Off', b'Tuner', b'FS9', b'FS10', b'FS11', b'FS12', b'FS13', b'FS4', b'FS5')
XL_FUNCTION_VALUES = (b'Tuner', b'Stomp', b'SnpshtUp', b'SnpshtDn', b'GlobalEQ', b'PresetUp', b'PresetDn', b'Bank Up',
                      b'Bank Dn', b'AllBypas', b'TogglEXP', b'FS Mode>', b'<FS Mode')
XL_HOLDS = tuple(replace(setting, values=XL_HOLD_VALUES, default=0) for setting in HOLDS) + tuple(
    Setting(f'fs{n}_hold', f'Function\nFS{n} Hold'.encode(), XL_HOLD_VALUES, default=0) for n in (6, 7, 8))
XL_FUNCTIONS = tuple(replace(setting, label=f'Function\nFS{n}'.encode(), values=XL_FUNCTION_VALUES)
                     for n, setting in zip((9, 10, 11, 12, 13), FUNCTIONS))
XL_SETTINGS = XL_HOLDS + XL_FUNCTIONS

# The footswitch event handler (event, object): owned, as a held-back press means not running it for that event.
HANDLER, HANDLER_STOCK = 0x28dd1978, bytes.fromhex('2de9 f043')    # push.w {r4-r9,lr}
# Bypass Assign > MIDI In: the first step up from Off is CC 4 (movs r2,#4); it lands on FS6's CC instead, and CC 4..19 stay below it.
MIDI_IN_FIRST, MIDI_IN_FIRST_STOCK = 0x28dbc2b4, bytes.fromhex('0422')
# A CC shows as "CC" then the digits itoa writes; after it, CC 20..24 read FS6..FS10. Bypass Assign's redraw and knob refresh, and
# Controller Assign's CC# (a parameter on CC 20 follows FS6 too). The Command Center's CCs are ones it sends, so they keep their numbers.
ITOA, CC_TEXT_CALLS = 0x28daaf6c, (0x28dbb6b2, 0x28dbbcd6, 0x28d8ff4c)
# A virtual footswitch's function runs in the stock dispatch's own code (src/m4/long_press.s enters it at these addresses), so the
# hooks other features put in it hold: its switch on the function byte, and TogglEXP's body past its press check.
SWITCH, SWITCH_STOCK = 0x28dd14d2, bytes.fromhex('00eb4400 6500 0379 013b 0d2b f4d8 dfe8 13f0 b000 2e00 bb00 3b00 6500 7c00 9300 ed00 0701 2201 3101 4201')
TOGGLE_EXP, TOGGLE_EXP_STOCK = 0x28dd17fc, bytes.fromhex('c5f7 4cf8 0228 40d0')
# Bypass Assign's redraw and knob refresh label the MIDI In knob "MIDI In" just after its text; on FS6..FS10 the label reads FootswIn.
LABEL = 0x28dc63d0
LABEL_CALLS = ((0x28dbb6c2, 'lp_label_redraw'), (0x28dbbce6, 'lp_label_refresh'))

XL_HANDLER, XL_HANDLER_STOCK = 0x28dd9c08, bytes.fromhex('2de9f043')
XL_LISTENER = 0x28ddb358
XL_MIDI_IN_FIRST, XL_MIDI_IN_STOCK = 0x28dbf358, bytes.fromhex('042225f0c5fe')
XL_ASSIGNMENT_CALLS = (
    (0x28dbe73e, 0x28dadf08, 'the XL Bypass Assign CC label'),
    (0x28dbed7a, 0x28dadf08, 'the XL Bypass Assign CC refresh label'),
    (0x28d926fc, 0x28dadf08, 'the XL Controller Assign CC label'),
    (0x28dbe74e, 0x28dc9510, 'the XL Bypass Assign redraw label'),
    (0x28dbed8a, 0x28dc9510, 'the XL Bypass Assign refresh label'),
)
XL_STOCK_CHECKS = (
    (0x28dd3fbe, '0520c4f794ff072002b0bde81040c4f7bebf'),
    (0x28dd54ca, '0820c3f70efdbde808400020c3f739bd'),
    (0x28dd96e6, '1cf0cdfd0499013100208029'),
    (0x28dd98f4, '1cf0c6fc049b013b'),
    (0x28dd9620, '96f84d10012914d0'),
    (0x28dd9686, '96f84d30012b00f0e181'),
    (0x28dd970c, 'bff7e4fe00287ff40caf0120'),
    (0x28dd9a14, 'bff778fd02283ad00220'),
    (0x28dd9ab8, '802be428902be428'),
    (0x28dd9300, '10b580f84d10'),
    (0x28dd99ac, '062302aa15214cf0b5f9'),
)


def long_press_inc(layout=pm.STOMP_MENU):
    first = 9 if layout.base == pm.XL_MENU.base else 6
    return f'.equ VIRTUAL_FIRST, {first}\n'


def xl_long_press_inc(snapshot_cc69=0):
    return f'.equ XL_SNAP_CC69, {snapshot_cc69:#x}\n'


def apply_xl(p):
    snapshot = p.modules.get('src/m4/more_snapshots.s')
    snapshot_cc69 = snapshot['snaps_xl_cc69'] if snapshot else 0
    module = p.module(XL_MODULE, inc={
        'long_press_xl.inc': xl_long_press_inc(snapshot_cc69)})
    for address, stock in XL_STOCK_CHECKS:
        p.expect(address, bytes.fromhex(stock), 'an XL footswitch function')
    p.expect(XL_LISTENER, (XL_HANDLER | 1).to_bytes(4, 'little'), 'the XL footswitch event listener')
    p.own_entry(XL_HANDLER, XL_HANDLER_STOCK, 'the XL footswitch event handler', module['xl_hold_event'])
    p.expect(XL_MIDI_IN_FIRST, XL_MIDI_IN_STOCK, 'the XL MIDI In knob first CC')
    p.put(XL_MIDI_IN_FIRST, bytes.fromhex('1422'), 'the XL virtual footswitch CC range')
    for site, stock, what in XL_ASSIGNMENT_CALLS:
        symbol = 'vfs_cc_text' if stock == 0x28dadf08 else 'vfs_label_redraw'
        if site == 0x28dbed8a:
            symbol = 'vfs_label_refresh'
        p.own_call(site, stock, what, module[symbol])


def apply(p):
    if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base:
        return apply_xl(p)
    hook = p.own_entry(HANDLER, HANDLER_STOCK, 'the footswitch event handler')
    m = p.module(MODULE, inc={'long_press.inc': long_press_inc(getattr(p, 'layout', pm.STOMP_MENU))})
    p.expect(SWITCH, SWITCH_STOCK, 'the footswitch dispatch\'s switch on the function')
    p.expect(TOGGLE_EXP, TOGGLE_EXP_STOCK, 'the footswitch dispatch\'s TogglEXP')
    p.expect(MIDI_IN_FIRST, MIDI_IN_FIRST_STOCK, 'the MIDI In knob\'s first CC')
    p.put(MIDI_IN_FIRST, bytes([VIRTUAL_CC, 0x22]), 'the MIDI In knob\'s first CC')
    for site in CC_TEXT_CALLS:
        p.chain_bl(site, ITOA, after=m['lp_cc_text'])
    for site, handler in LABEL_CALLS:
        p.own_call(site, LABEL, 'the MIDI In knob\'s label', m[handler])
    a = pm.Asm(p.next())
    a.movw_movt(2, hook.stock | 1)
    a.bw(m['lp_event'])
    hook.to(p.add(a.bytes()))
