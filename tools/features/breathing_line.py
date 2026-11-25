"""Breathing line: the Home screen's divider animated in Type's pattern, Color's colours and at Speed (src/m4/breathing_line.s)."""
import types

import patch_menu as pm
from features import Setting, gr

FLAG = 'HX_BREATHING_LINE'
XL_PORTED = True
TITLE = 'Breathing Line'
ICON = 'Icon_DualIR'
SETTINGS = (
    Setting('color', b'Color', (b'White', b'Red', b'Green', b'Blue', b'Fire', b'Ice', b'Sunset', b'Ocean', b'Aurora', b'Neon',
                                       b'Rainbow'), default=10),
    Setting('motion', b'Type', (b'Off', b'Steady', b'Breathe', b'Cylon', b'Comet', b'Heart', b'Sparkle'), default=2),
    Setting('speed', b'Speed', tuple(str(n).encode() for n in range(1, 11)) + (b'Tempo',), default=3),
    Setting('thickness', b'Thick', (b'Normal', b'+1 px', b'+2 px', b'+3 px', b'+4 px')),
)

HOME_PAINT_LIT, HOME_PAINT = 0x28d96e28, 0x28dc8d39                  # the Home view's paint function, as registered
EDIT_PAINT_LIT, EDIT_PAINT = 0x28d96da0, 0x28dc27f9                 # the Stomp Edit view's top paint
LED_TICK_CALL, LED_SLEEP = 0x28db7f44, 0x28e24c58                    # the LED task's 1 ms sleep: the animation's clock
STOMP = types.SimpleNamespace(play_segments=0x2812a594, edit_segments=0x2812a594,
                                        play_paint_lit=HOME_PAINT_LIT, play_paint=HOME_PAINT,
                                        edit_paint_lit=EDIT_PAINT_LIT, edit_paint=EDIT_PAINT,
                                        redraw=0x28db8508, clock=0x28da6458, lock=0x28e24970,
                                        unlock=0x28e24ae8, get=0x28e1f844, tick=LED_TICK_CALL, sleep=LED_SLEEP)
XL = types.SimpleNamespace(segments=0x281f927c, redraw=0x28dbb631, clock=0x28da93ad, lock=0x28e2ad41,
                           unlock=0x28e2adf1, get=0x28e25c71,
                                    play_segments=0x281f927c, edit_segments=0x281f927c,
                                    play_paint_lit=0x28d99a44, play_paint=0x28dcc98d,
                           paint_lit=0x28d99a38, paint=0x28dc5939, tick=0x28dbb0a6, sleep=0x28e2aee0,
                           selected=0x281f9298, layout=pm.XL_MENU)


def line_inc(profile=STOMP):
    return ''.join(f'.equ {name}, {value:#x}\n' for name, value in (
        ('LINE_PLAY_SEGMENTS', profile.play_segments), ('LINE_EDIT_SEGMENTS', profile.edit_segments),
        ('LINE_PLAY_Y_OFFSET', 36 if profile is XL else 0),
        ('LINE_REDRAW', profile.redraw | 1), ('LINE_CLOCK', profile.clock | 1),
        ('LINE_LOCK', profile.lock | 1), ('LINE_UNLOCK', profile.unlock | 1), ('LINE_GET', profile.get | 1),
        ('LINE_XL', int(profile is XL)), ('LINE_SELECTED', getattr(profile, 'selected', 0))))


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    meter = p.modules.get(gr.MODULE)
    shown = (meter['data'] + gr.SHOWN if profile is STOMP else meter['gr_line_middle']) if meter else 0
    m = p.module('src/m4/breathing_line.s', inc={'gr.inc': f'.equ GR_SHOWN, {shown:#x}\n',
                                                  'breathing.inc': line_inc(profile)})
    if profile is XL:
        p.chain_ptr(profile.play_paint_lit, profile.play_paint, after=m['bl_paint_play'])
        p.chain_ptr(profile.paint_lit, profile.paint, after=m['bl_paint_edit'])
        p.chain_bl(profile.tick, profile.sleep, after=m['bl_tick'])
        return
    p.chain_ptr(profile.play_paint_lit, profile.play_paint, after=m['bl_paint'])
    p.chain_bl(profile.tick, profile.sleep, after=m['bl_tick'])
