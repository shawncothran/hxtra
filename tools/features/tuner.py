"""Tuner Activation (Hold or Press) and Lock Tuner Settings (Off or On), on a third page of the tuner's own settings (src/m4/tuner.s)."""
from dataclasses import dataclass, replace

from features import Setting
import patch_menu as pm

FLAG = 'HX_TUNER'
XL_PORTED = True
ORDER = 0
MENU = False
SETTINGS = (     # labels and values as src/m4/tuner.s draws them
    Setting('activate', b'Activate', (b'Hold', b'Press')),
    Setting('lock', b'Lock', (b'Off', b'On')),
)

# The tap in the footswitch case for function TAP/Tunr is a tail call; Press mode turns it into a tuner request.
TAP_SITE, TAP_CORE = 0x28dd1656, 0x28d9bfa8
GUARD, REQUEST_TUNER = 0x28d96134, 0x28d96588

# The tuner's settings (Output, Refrnc, Type, Trails, Offsets): knob turns are handled at TURN_FN, and a knob press resets the
# item to its default in one of three cases of the event handler. Lock Tuner Settings On skips both; page changes stay.
TURN_FN, TURN_FN_STOCK, TURN_FN_CONT = 0x28d916d4, bytes.fromhex('f8b5 4678'), 0x28d916d8      # push {r3-r7,lr}; ldrb r6,[r0,#1]
RESET_SITES = {0x28d917fa: 2, 0x28d9183e: 1, 0x28d91854: 0}                       # site: the knob it resets
RESET_STOCK, RESET_RET = bytes.fromhex('91f8 7430'), 0x28d9176e     # ldrb.w r3,[r1,#0x74]; pop {r3,r4,r5,pc}

# The view has four pages of three knobs, the page at [view+0x74]; these settings are a fifth, page 4, its knob 2 empty. Paging
# and the page dots go by each page's place in the order instead, where page 4 is third (SHOWN_AT) and the string pages follow it.
PAGE, PAGES, SHOWN_AT = 4, 5, 2      # third, ahead of the per-string offsets, which few players use, so these are quick to reach
NEXT_PAGE, NEXT_PAGE_STOCK = 0x28d91784, bytes.fromhex('022b')                    # cmp r3,#2: the last page with a next one
PAGE_READ = bytes.fromhex('91f8 7430')                                            # ldrb.w r3,[r1,#0x74]
NEXT_READ, PREV_READ = 0x28d91780, 0x28d917c2                                     # the next- and previous-page cases' reads of it
PAGE_STORE, PAGE_STORE_STOCK = 0x28d917ca, bytes.fromhex('0125 2046')            # movs r5,#1; mov r0,r4: before both cases' store
DOTS_READ, DOTS_READ_STOCK = 0x28dccd52, bytes.fromhex('94f8 7400')              # ldrb.w r0,[r4,#0x74]: the page dots' current one
PAGE_CLAMPS, PAGE_CLAMP_STOCK = (0x28dcca6c, 0x28dccfd4), bytes.fromhex('032b')  # cmp r3,#3: the paint and redraw zero pages above
PAGE_DOTS, PAGE_DOTS_STOCK = 0x28dccd4c, bytes.fromhex('0420')                    # movs r0,#4: the page indicator's count
PAINT = 0x28dcca60                                                                # (view): takes the widget lock itself
PAINT_SWITCH, PAINT_SWITCH_STOCK = 0x28dcca8e, bytes.fromhex('032b 68d8')        # cmp r3,#3; bhi end: the paint's switch on the page
PAINT_TBH, PAINT_END = 0x28dcca92, 0x28dccb64
STEPS = 0x28dfe2d8                                  # (raw knob delta) -> detents, as the stock turn counts them
SHOW, VALUE_TEXT, POSITION, LABEL = 0x28dc6598, 0x28dc654c, 0x28dc648c, 0x28dc63d0   # (knob, shown / text / 0.0f..1.0f / text)
LABEL_COLOR = 'src/m4/label_color.s'               # its label_any colours the page's labels when label_color is built
KNOB_COLOURS = ((0x28dc6454, 0xffffff), (0x28dc651c, 0x6b6b6b), (0x28dc6534, 0x4d4d4d), (0x28dc6504, 0xb1b1b1),
                (0x28dc6568, 0xb1b1b1))           # (knob, colour), as the stock paints a knob that can be turned


@dataclass(frozen=True)
class TunerLayout:
    tap_site: int
    tap_core: int
    guard: int
    request: int
    turn: int
    reset_ret: int
    reset_sites: dict
    next_page: int
    next_read: int
    prev_read: int
    page_store: int
    dots_read: int
    page_clamps: tuple
    page_dots: int
    paint: int
    paint_switch: int
    paint_tbh: int
    paint_end: int
    steps: int
    show: int
    value_text: int
    position: int
    label: int
    knob_colours: tuple


STOMP = TunerLayout(TAP_SITE, TAP_CORE, GUARD, REQUEST_TUNER, TURN_FN, RESET_RET, RESET_SITES, NEXT_PAGE, NEXT_READ,
                    PREV_READ, PAGE_STORE, DOTS_READ, PAGE_CLAMPS, PAGE_DOTS, PAINT, PAINT_SWITCH, PAINT_TBH, PAINT_END,
                    STEPS, SHOW, VALUE_TEXT, POSITION, LABEL, KNOB_COLOURS)
XL = replace(STOMP, tap_site=0x28dd9676, tap_core=0x28d9eed4, guard=0x28d98ce4, request=0x28d9919c,
             turn=TURN_FN + 0x27b8, reset_ret=RESET_RET + 0x27b8,
             reset_sites={site + 0x27b8: knob for site, knob in RESET_SITES.items()}, next_page=NEXT_PAGE + 0x27b8,
             next_read=NEXT_READ + 0x27b8, prev_read=PREV_READ + 0x27b8, page_store=PAGE_STORE + 0x27b8,
             dots_read=DOTS_READ + 0x5ab4, page_clamps=tuple(site + 0x5ab4 for site in PAGE_CLAMPS),
             page_dots=PAGE_DOTS + 0x5ab4, paint=PAINT + 0x5ab4, paint_switch=PAINT_SWITCH + 0x5ab4,
             paint_tbh=PAINT_TBH + 0x5ab4, paint_end=PAINT_END + 0x5ab4, steps=0x28e043fc,
             show=SHOW + 0x3140, value_text=VALUE_TEXT + 0x3140, position=POSITION + 0x3140, label=LABEL + 0x3140,
             knob_colours=tuple((fn + 0x3140, colour) for fn, colour in KNOB_COLOURS))


def label_inc(label_any=None, layout=STOMP):
    addresses = {'GUARD': layout.guard, 'REQUEST_TUNER': layout.request, 'TAP_CORE': layout.tap_core,
                 'TURN_FN_CONT': layout.turn + 4, 'RESET_RET': layout.reset_ret, 'PAINT': layout.paint,
                 'PAINT_TBH': layout.paint_tbh, 'PAINT_END': layout.paint_end, 'STEPS': layout.steps,
                 'SHOW': layout.show, 'VALUE_TEXT': layout.value_text, 'POSITION': layout.position, 'LABEL': layout.label,
                 'NEXT_CONT': layout.next_read + 4, 'PREV_CONT': layout.prev_read + 4, 'STORE_CONT': layout.page_store + 4,
                 'DOTS_CONT': layout.dots_read + 4}
    addresses.update({f'RESET{knob}_CONT': site + 4 for site, knob in layout.reset_sites.items()})
    lines = [f'.equ LABEL_COLOUR_FN, {(label_any or layout.knob_colours[0][0]) | 1:#x}']
    lines += [f'.equ {name}, {address | 1:#x}' for name, address in addresses.items()]
    lines += ['.macro TUNER_COLOURS'] + [f'.word {fn | 1:#x}, {colour:#x}' for fn, colour in layout.knob_colours[1:]] + ['.endm']
    return '\n'.join(lines) + '\n'


def apply(p):
    layout = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    lc = p.modules.get(LABEL_COLOR)
    m = p.module('src/m4/tuner.s', inc={'tuner_label.inc': label_inc(lc and lc['label_any'], layout)})
    p.own_call(layout.tap_site, layout.tap_core, 'the tap-tempo call', m['tuner_tap'])
    p.own_entry(layout.turn, TURN_FN_STOCK, 'the tuner settings knob handler', m['tuner_turn_hook'])
    p.expect(layout.reset_ret, b'\x38\xbd', 'the tuner event handler epilogue')
    for site, knob in layout.reset_sites.items():
        p.expect(site, RESET_STOCK, 'a tuner settings reset case')
        p.put(site, pm.thumb_bw(site, m[f'tuner_reset{knob}']), 'a tuner settings reset case')
    p.expect(layout.paint_switch, PAINT_SWITCH_STOCK, 'the tuner settings\' paint switch')
    p.put(layout.paint_switch, pm.thumb_bw(layout.paint_switch, m['tuner_switch']), 'the tuner settings\' paint switch')
    for site, stock, handler in ((layout.next_read, PAGE_READ, 'tuner_next_page'), (layout.prev_read, PAGE_READ, 'tuner_prev_page'),
                                 (layout.page_store, PAGE_STORE_STOCK, 'tuner_store_page'), (layout.dots_read, DOTS_READ_STOCK, 'tuner_dots')):
        p.expect(site, stock, 'the tuner settings\' page order')
        p.put(site, pm.thumb_bw(site, m[handler]), 'the tuner settings\' page order')
    p.expect(layout.next_page, NEXT_PAGE_STOCK, 'the tuner settings\' next page')
    p.put(layout.next_page, bytes([PAGE - 1, 0x2b]), 'the tuner settings\' next page')
    for site in layout.page_clamps:
        p.expect(site, PAGE_CLAMP_STOCK, 'the tuner settings\' page clamp')
        p.put(site, bytes([PAGE, 0x2b]), 'the tuner settings\' page clamp')
    p.expect(layout.page_dots, PAGE_DOTS_STOCK, 'the tuner settings\' page count')
    p.put(layout.page_dots, bytes([PAGES, 0x20]), 'the tuner settings\' page count')
