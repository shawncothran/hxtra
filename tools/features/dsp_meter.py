"""DSP meter: each block in the Edit view shows its share of the DSP in per cent, and the top right corner the blocks' total as used/75;
the model browser shows each listed model's share between its icon and name.

Global Settings > DSP Usage Display: Model Browser and Edit Blocks (On, Off) turn the numbers on or off in the model browser and
the Edit view's blocks; Total (Small, Large, Off) the corner's
used/75: Small, the default, draws it in the meter's 3x5 digits at 2x, Large in the title's font, as before these settings,
Off not at all, leaving the corner to the title."""
import types

import patch_menu as pm
from features import Setting

FLAG = 'HX_DSP_METER'
TITLE = 'DSP Usage Display'
XL_PORTED = True
SETTINGS = (
    Setting('browser', b'Browser\nModel', (b'On', b'Off')),     # On first: 0 is what a unit that set 0xd1 reads here
    Setting('blocks', b'Blocks\nEdit', (b'On', b'Off')),
    Setting('total', b'Total', (b'Small', b'Large', b'Off')),     # Small first: 0 is what a unit that set 0xd1 reads here
)
XL_SETTINGS = SETTINGS

EDIT_PAINT_LIT, EDIT_PAINT = 0x28d96da0, 0x28dc27f9     # the Edit view top half's paint function (block slots), as registered
BROWSER_PAINT_LIT, BROWSER_PAINT = 0x28d96df0, 0x28dc4dd1   # the model browser's paint function, as registered
XL_EDIT_PAINT_LIT, XL_EDIT_PAINT = 0x28d99a38, 0x28dc5939
NAMES_X = 0x28d90f72                # the browser constructor's movs r3, #44: its name list's x
NAMES_X_STOCK, NAMES_X_LABELLED = bytes([44, 0x23]), bytes([60, 0x23])     # room for the labels browser draws

STOMP = types.SimpleNamespace(dsp_ptr=0x28449e78, dsp_lock=0x28e07845, dsp_unlock=0x28e0785d,
                                        slot_model=0x2812c590, widget_lock=0x28e24971, widget_unlock=0x28e24ae9,
                              browser_level=0x28df0281, browser_count=0x28e0edcd,
                              browser_item=0x28e01205, browser_cost=0x28e01d51,
                              browser_paint_lit=BROWSER_PAINT_LIT, browser_paint=BROWSER_PAINT,
                              names_x=NAMES_X, names_x_stock=NAMES_X_STOCK, names_x_labelled=NAMES_X_LABELLED,
                                        text_init=0x28e249d1, text_pos=0x28e24a69, text_anchor=0x28e24ac9,
                                        text_font=0x28e249e9, text_color=0x28e24a29, text_set=0x28e24bc1,
                                        text_visible=0x28e24bc9, text_erase=0x28e24c91, text_draw=0x28e24c31)
XL = types.SimpleNamespace(dsp_ptr=0x2844c5e8, dsp_lock=0x28e0db89, dsp_unlock=0x28e0dba1,
                                    slot_model=0x2812d3cc, widget_lock=0x28e2ad41, widget_unlock=0x28e2adf1,
                           browser_level=0x28df62bd, browser_count=0x28e151f5,
                           browser_item=0x28e07325, browser_cost=0x28e07e71,
                           browser_paint_lit=0x28d99ab4, browser_paint=0x28dc7f11,
                           names_x=0x28d93722, names_x_stock=NAMES_X_STOCK, names_x_labelled=NAMES_X_LABELLED,
                                    text_init=0x28e2b009, text_pos=0x28e2af01, text_anchor=0x28e2ade9,
                                    text_font=0x28e2ae41, text_color=0x28e2ae79, text_set=0x28e2adc9,
                                    text_visible=0x28e2ae89, text_erase=0x28e2aef1, text_draw=0x28e2ae39)


def dsp_meter_inc(profile=STOMP):
    return ''.join(f'.equ {name}, {value:#x}\n' for name, value in (
        ('DSP_XL', int(profile is XL)),
        ('DSP_PTR', profile.dsp_ptr), ('DSP_LOCK', profile.dsp_lock), ('DSP_UNLOCK', profile.dsp_unlock),
        ('SLOT_MODEL', profile.slot_model), ('WIDGET_LOCK', profile.widget_lock), ('WIDGET_UNLOCK', profile.widget_unlock),
        ('BROWSER_LEVEL', profile.browser_level), ('BROWSER_COUNT', profile.browser_count),
        ('BROWSER_ITEM', profile.browser_item), ('BROWSER_COST', profile.browser_cost),
        ('TEXT_INIT', profile.text_init), ('TEXT_POS', profile.text_pos), ('TEXT_ANCHOR', profile.text_anchor),
        ('TEXT_FONT', profile.text_font), ('TEXT_COLOR', profile.text_color), ('TEXT_SET', profile.text_set),
        ('TEXT_VISIBLE', profile.text_visible), ('TEXT_ERASE', profile.text_erase), ('TEXT_DRAW', profile.text_draw)))


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    m = p.module('src/m4/dsp_meter.s', inc={'dsp_meter.inc': dsp_meter_inc(profile)})
    if profile is XL:
        p.chain_ptr(XL_EDIT_PAINT_LIT, XL_EDIT_PAINT, after=m['dsp_paint_xl'])
        p.chain_ptr(profile.browser_paint_lit, profile.browser_paint, after=m['dsp_browser'])
        p.expect(profile.names_x, profile.names_x_stock, 'the XL model browser name list\'s x')
        p.put(profile.names_x, profile.names_x_labelled, 'the XL model browser name list\'s x')
        return
    p.chain_ptr(EDIT_PAINT_LIT, EDIT_PAINT, after=m['dsp_paint'])
    p.chain_ptr(BROWSER_PAINT_LIT, BROWSER_PAINT, after=m['dsp_browser'])
    p.expect(NAMES_X, NAMES_X_STOCK, 'the model browser name list\'s x')
    p.put(NAMES_X, NAMES_X_LABELLED, 'the model browser name list\'s x')
