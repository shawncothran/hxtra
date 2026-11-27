"""BPM: the tempo as text at the top left of the Home screen, and a beat dot that follows the TAP footswitch's ring (src/m4/bpm.s)."""
import types

from features import Setting, tap_color
import patch_menu as pm

FLAG = 'HX_BPM'
TITLE = 'BPM Display'
ICON = 'Icon_Tempo'
ORDER = 20
XL_PORTED = True
SETTINGS = (     # 'Position\nDot' reads Dot over Position: the line after the newline is the top one
    Setting('font', b'Size\nFont', (b'XL', b'L', b'M', b'S', b'Off'), default=1),
    Setting('color', b'Color', (b'White', b'Gray', b'Red', b'Orange', b'Yellow', b'Green', b'Cyan', b'Blue', b'Purple',
                                b'Tempo')),
    Setting('dot', b'Position\nDot', (b'Left', b'Right', b'Both', b'Off')),
)
XL_SETTINGS = SETTINGS

HOME_CTOR_CALL, HOME_CTOR = 0x28d96c44, 0x28dc91d0                  # bl to the Home view's constructor at boot
HOME_PAINT_LIT, HOME_PAINT = 0x28d96e28, 0x28dc8d39                  # the Home view's paint function, as registered
# The settings store's write (ID, value, how); its only callers are the three setters. A tempo write asks for a repaint.
STORE_WRITE, STORE_WRITE_CALLS = 0x28e1f0d8, (0x28e1f492, 0x28e1f936, 0x28e1fbce)
LED_TICK_CALL, LED_SLEEP = 0x28db7f44, 0x28e24c58                    # the LED task's 1 ms sleep: where the dot follows the TAP ring
# The two reads of Tap Tempo LED (26) that decide whether the stock blinks the tap LED: the dot needs the blink either way.
TAP_LED_ID, TAP_LED_READS = 26, (0x28d9c116, 0x28dd0ae2)
TAP_CORE, TAP_CORE_STOCK = 0x28d9bfa8, bytes.fromhex('10b5 86b0')   # push {r4,lr}; sub sp,#0x18
# The LED send (LED, colour): owned, as the hook rewrites the colour; its prologue loads a literal, so bpm_ledsend runs it itself.
LED_SEND, LED_SEND_STOCK, LED_SEND_LIT, LED_SEND_LIT_VALUE = 0x28d98f74, bytes.fromhex('00b5 234b'), 0x28d99004, 0x281c90a4
STOMP = types.SimpleNamespace(
    home_paint_lit=HOME_PAINT_LIT, home_paint=HOME_PAINT, tick_call=LED_TICK_CALL, sleep=LED_SLEEP,
    get=0x28e1f845, redraw=0x28db8509, external=0x28d9685d, xl=False, dots=18,
    ring_id=2, ring_slot=0, fs_functions=0x28128a74,
    clock=0x28da6459, last_turn=0x281cd074,
    led_send=LED_SEND, led_send_stock=LED_SEND_STOCK, led_send_literal=LED_SEND_LIT,
    led_send_literal_value=LED_SEND_LIT_VALUE, led_send_rest=0x28d98f79,
    tap_core=TAP_CORE, tap_core_stock=TAP_CORE_STOCK, tap_reads=TAP_LED_READS,
    text_init=0x28e249d1, text_pos=0x28e24a69, text_anchor=0x28e24ac9, text_font=0x28e249e9,
    text_color=0x28e24a29, text_set=0x28e24bc1, text_visible=0x28e24bc9, text_erase=0x28e24c91,
    text_draw=0x28e24c31, dot_init=0x28e24989, dot_anchor=0x28e24a19, dot_visible=0x28e24b01,
    dot_pos=0x28e24af1, dot_size=0x28e24b29, dot_color=0x28e24b99,
    dot_erase=0x28e24b41, dot_draw=0x28e24b59, widget_lock=0x28e24971, widget_unlock=0x28e24ae9)
XL = types.SimpleNamespace(
    home_paint_lit=0x28d99a44, home_paint=0x28dcc98d, tick_call=0x28dbb0a6, sleep=0x28e2aee0,
    redraw_first=1, xl=True, dots=18,
    get=0x28e25c71, redraw=0x28dbb631, external=0,
    ring_id=7, ring_slot=0, fs_functions=0x28128d7a,
    clock=0x28da93ad, last_turn=0x281cdd84,
    led_send=0x28d9bc64, led_send_stock=bytes.fromhex('00b5 234b'), led_send_literal=0x28d9bcf4,
    led_send_literal_value=0x281ca1cc, led_send_rest=0x28d9bc69,
    tap_core=0x28d9eed4, tap_core_stock=bytes.fromhex('10b5 86b0'),
    tap_reads=((0x28d9f044, 0x28e25c70), (0x28dd7cca, 0x28e25c70)),
    text_init=0x28e2b009, text_pos=0x28e2af01, text_anchor=0x28e2ade9, text_font=0x28e2ae41,
    text_color=0x28e2ae79, text_set=0x28e2adc9, text_visible=0x28e2ae89, text_erase=0x28e2aef1,
    text_draw=0x28e2ae39, dot_init=0x28e2aea1, dot_anchor=0x28e2afd1, dot_visible=0x28e2afc1,
    dot_pos=0x28e2aeb9, dot_size=0x28e2aed1, dot_color=0x28e2ad91,
    dot_erase=0x28e2ad99, dot_draw=0x28e2ae11, widget_lock=0x28e2ad41, widget_unlock=0x28e2adf1,
    view_mutex=0x281f5d80, mutex_lock=0x28e2af31, mutex_unlock=0x28e2ad69, view_sync=0x28dbb67d,
    transition_locks=(0x28dcc8ee, 0x28dcc96e), transition_syncs=(0x28dcc930, 0x28dcc976))


def bpm_inc(profile):
    values = {'BPM_XL': int(profile.xl), 'BPM_DOTS': profile.dots,
              'BPM_REDRAW_FIRST': getattr(profile, 'redraw_first', 0),
              'BPM_GET': profile.get, 'BPM_REDRAW': profile.redraw, 'BPM_EXTERNAL': profile.external,
              'BPM_RING_ID': profile.ring_id, 'BPM_RING_SLOT': profile.ring_slot,
              'BPM_FS_FUNCTIONS': profile.fs_functions, 'BPM_LED_SEND_VALUE': profile.led_send_literal_value,
              'BPM_LED_SEND_REST': profile.led_send_rest, 'BPM_CLOCK': profile.clock,
              'BPM_LAST_TURN': profile.last_turn}
    values.update({f'BPM_{key.upper()}': getattr(profile, key) for key in (
        'text_init', 'text_pos', 'text_anchor', 'text_font', 'text_color', 'text_set', 'text_visible',
        'text_erase', 'text_draw', 'dot_init', 'dot_anchor', 'dot_visible', 'dot_pos', 'dot_size', 'dot_color',
        'dot_erase', 'dot_draw', 'widget_lock', 'widget_unlock')})
    values.update({f'BPM_{key.upper()}': getattr(profile, key, 0) for key in (
        'view_mutex', 'mutex_lock', 'mutex_unlock', 'view_sync')})
    return ''.join(f'.equ {name}, {address:#x}\n' for name, address in values.items())


def apply(p):
    tap = p.modules.get(tap_color.MODULE)     # Color Tempo takes the TAP footswitch's colour, stock red without Tap LED Color
    now = tap[tap_color.NOW] if tap else 0
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    m = p.module('src/m4/bpm.s', inc={'tap.inc': f'.equ TAP_NOW, {now:#x}\n', 'bpm.inc': bpm_inc(profile)})
    if profile is XL:
        p.chain_ptr(profile.home_paint_lit, profile.home_paint, before=m['bpm_before_xl'], after=m['bpm_after_xl'])
        p.chain_bl(profile.tick_call, profile.sleep, after=m['bpm_tick_xl'])
        for site in profile.transition_locks:
            p.own_call(site, profile.widget_lock & ~1, f'the XL transition lock at {site:#x}', m['bpm_xl_transition_lock'])
        for site in profile.transition_syncs:
            p.own_call(site, profile.view_sync & ~1, f'the XL transition sync at {site:#x}', m['bpm_xl_transition_sync'])
        if p.u32(profile.led_send_literal) != profile.led_send_literal_value:
            raise SystemExit('patch-menu: the XL LED send does not load its stock literal')
        p.own_entry(profile.led_send, profile.led_send_stock, 'the XL LED send', m['bpm_ledsend'])
        p.chain_entry(profile.tap_core, profile.tap_core_stock, before=m['bpm_tap'])
        for site, stock in profile.tap_reads:
            p.own_call(site, stock, f'the XL Tap Tempo LED read at {site:#x}', m['bpm_tapled_xl'])
        return
    p.chain_bl(HOME_CTOR_CALL, HOME_CTOR, after=m['bpm_construct'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, before=m['bpm_before'], after=m['bpm_after'])
    for site in STORE_WRITE_CALLS:
        p.chain_bl(site, STORE_WRITE, after=m['bpm_written'])
    p.chain_bl(LED_TICK_CALL, LED_SLEEP, after=m['bpm_tick'])
    for site in TAP_LED_READS:
        p.expect(site - 2, bytes([TAP_LED_ID, 0x20]), 'a read of Tap Tempo LED')
        p.chain_bl(site, pm.GET_VALUE, after=m['bpm_tapled'])
    p.chain_entry(TAP_CORE, TAP_CORE_STOCK, before=m['bpm_tap'])
    if p.u32(LED_SEND_LIT) != LED_SEND_LIT_VALUE:      # own_entry checks only the prologue; bpm_ledsend repeats its literal load
        raise SystemExit('patch-menu: the LED send does not load its stock literal')
    p.own_entry(LED_SEND, LED_SEND_STOCK, 'the LED send', m['bpm_ledsend'])
