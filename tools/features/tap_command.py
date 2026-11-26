"""Tap command: a Tap command for FS1..FS5 in the Command Center, so tap tempo lives in the presets that want it (issue #108). A
Stomp footswitch whose slot holds it taps the tempo as the TAP footswitch does, and its ring blinks the tempo as the TAP ring does,
in Tap LED Color's colour when that is built (src/m4/tap_command.s). The preset keeps it as type 9, the Helix's CV Out, complete in
every Command Center table but never offered on the HX Stomp; stock firmware gives it no footswitch node, so there it does nothing.
A footswitch with no block reads Tap on the Home screen, as one with another command reads that command's name. The Command
Center's code: docs/research/m4/command-center.md."""
import types

import patch_menu as pm
from features import tap_color

FLAG = 'HX_CC_TAP'
XL_PORTED = True
MENU = False
ORDER = 120                         # after tap_color, whose ring colour handlers it calls
MODULE = 'src/m4/tap_command.s'

TAP = 9
CC = 0x281252b8
CC_GET = 0x28d96094                 # () -> the Command Center
FS_SLOTS = range(6, 11)
# The FS slots' Command knob: how many places (words, one a slot, read only by 0x28de57bc), and type 9's name and knob count
CHOICES, FS_CHOICES = 0x28e3c5f4, 10
NAMES, NAME = 0x28e3c628, b'Tap'
COUNTS, CV_OUT_COUNT = 0x28e3c6d8, 2                    # the Command knob and CV Value: Tap has the Command knob alone
FIRE, FIRE_CALL = 0x28de5cd4, 0x28dd1342                # the stomp toggle's fire of every command but Looper and Snapshot's
NODE_NAME, NODE_CALLS = 0x28dd568c, (0x28dd88d2, 0x28dd8a68)    # the footswitch node insert naming a command's node: 0 for type 9
CHOICE, CHOICE_CALLS = 0x28de57d0, (0x28dbd366, 0x28dbd4d0, 0x28dbd9fa)     # type -> place: the knob, paste checks
STEP, STEP_CALL = 0x28de64a0, 0x28dbd6bc                # the Command knob's turn
FS_STATE = 0x28d9607c
BEAT_RUN_CALLS = (0x28d9be3a, 0x28d9be4c)               # the stock beat's "is FS3 TAP" before it works out a turn
BEAT_ON_CALL = 0x28d9be92                               # its turn on, before FS3's colour and on
LED_MODE, BEAT_OFF_CALL = 0x28db8260, 0x28d9beba        # its turn off: LED 2 off
REFRESH_CALL = 0x28dd0b70                               # the footswitch LED refresh, before each ring's function
SETTING_CALL = 0x28dd276c                               # a tempo setting's change (external clock too) looking for a TAP footswitch

STOMP = types.SimpleNamespace(
    layout=pm.STOMP_MENU,
    cc=CC, cc_get=CC_GET, choices=CHOICES, slots=range(6, 11), choice_count=FS_CHOICES,
    names=NAMES, stock_name=b'CV Out\0\0', counts=COUNTS, stock_count=CV_OUT_COUNT,
    function_slots=0x28128a74,
    rings=3, footswitches=5, dedicated_tap=8, dedicated_ring=2, fs_state=0x28d9607c,
    fs_object=0x28d96084, fs_node=0x28dd7218, fire=FIRE, node_name=NODE_NAME,
    strcpy=0x28daad94, choice=CHOICE, step=STEP, tap_core=0x28d9bfa8, get=0x28e1f844,
    external=0x28d9685c, led_colour=0x28db81fc, led_mode=LED_MODE, red=0x28e280b0, blue=0x28e280ac,
    beat_period=0x281ccc44, beat_on=0x281ccc48, refresh_next=FS_STATE, tap_setting_first=False,
    hook_calls=((FIRE_CALL, FIRE, 'tc_fire'), *((site, NODE_NAME, 'tc_node') for site in NODE_CALLS),
                *((site, CHOICE, 'tc_choice') for site in CHOICE_CALLS), (STEP_CALL, STEP, 'tc_step'),
                *((site, FS_STATE, 'tc_running') for site in BEAT_RUN_CALLS), (BEAT_ON_CALL, FS_STATE, 'tc_on'),
                (BEAT_OFF_CALL, LED_MODE, 'tc_off'), (REFRESH_CALL, FS_STATE, 'tc_refresh'),
                (SETTING_CALL, FS_STATE, 'tc_setting')),
    sync_on=None, type_list=None)
XL = types.SimpleNamespace(
    layout=pm.XL_MENU,
    cc=0x28125340, cc_get=0x28d98c24, choices=0x28e42d18, slots=range(6, 14), choice_count=10,
    names=0x28e42d58, stock_name=b'CV Out\0\0', counts=0x28e42e08, stock_count=2,
    function_slots=0x28128d6c, rings=6, footswitches=8, dedicated_tap=0x12, dedicated_ring=7,
    fs_state=0x28d98c0c, fs_object=0x28d98c14, fs_node=0x28ddfba4, fire=0x28debb5c,
    node_name=0x28dde6f0, strcpy=0x28dadcec, choice=0x28deb664, step=0x28dec4a0,
    tap_core=0x28d9eed4, get=0x28e25c71, external=0x28d994cc, led_colour=0x28dbb308,
    led_mode=0x28dbb36c, red=0x28e2e4f8, blue=0x28e2e4f4, beat_period=0x281cdd84,
    beat_on=0x281cdd88, refresh_next=0x28dd8638, tap_setting_first=True,
    hook_calls=((0x28dd911a, 0x28debb5c, 'tc_fire'), (0x28de0aba, 0x28dde6f0, 'tc_node'),
                (0x28de0c52, 0x28dde6f0, 'tc_node'), (0x28dc040a, 0x28deb664, 'tc_choice'),
                (0x28dc057a, 0x28deb664, 'tc_choice'), (0x28dc0ab6, 0x28deb664, 'tc_choice'),
                (0x28dc0770, 0x28dec4a0, 'tc_step'), (0x28d9ed6e, 0x28d98c0c, 'tc_running'),
                (0x28d9ed80, 0x28d98c0c, 'tc_running'), (0x28d9edc6, 0x28d98c0c, 'tc_on'),
                (0x28d9ede4, 0x28dbb36c, 'tc_sync_on'), (0x28d9edee, 0x28dbb36c, 'tc_off'),
                (0x28dd89d6, 0x28dd8638, 'tc_refresh'), (0x28ddafa6, 0x28d98c0c, 'tc_setting')),
    sync_on=(0x28d9ede4, 0x28dbb36c),
    type_list=(0x28e438d9, bytes((1, 2, 4, 5, 6, 12, 14, 15, 16))))


def tap_inc(p):
    tap = p.modules.get(tap_color.MODULE)
    led, again = (tap['tap_led'] | 1, tap['tap_led_again'] | 1) if tap else (0, 0)
    return f'.equ TAP_LED, {led:#x}\n.equ TAP_LED_AGAIN, {again:#x}\n'


def command_inc(profile):
    callable_names = {'FS_STATE', 'FS_OBJ', 'FS_NODE', 'FIRE', 'NODE_NAME', 'STRCPY', 'CHOICE', 'STEP', 'TAP_CORE',
                      'GET_VALUE', 'EXT_CLOCK', 'LED_COLOUR', 'LED_MODE', 'REFRESH_NEXT'}
    values = {
        'XL_TAP_COMMAND': int(profile is XL), 'RINGS': profile.rings, 'FOOTSWITCHES': profile.footswitches,
        'DEDICATED_TAP': profile.dedicated_tap, 'DEDICATED_RING': profile.dedicated_ring,
        'CC': profile.cc, 'FS_FUNCTIONS': profile.function_slots, 'FS_STATE': profile.fs_state,
        'FS_OBJ': profile.fs_object, 'FS_NODE': profile.fs_node, 'FIRE': profile.fire,
        'NODE_NAME': profile.node_name, 'STRCPY': profile.strcpy, 'CHOICE': profile.choice, 'STEP': profile.step,
        'TAP_CORE': profile.tap_core, 'GET_VALUE': profile.get, 'EXT_CLOCK': profile.external,
        'LED_COLOUR': profile.led_colour, 'LED_MODE': profile.led_mode, 'RED': profile.red, 'BLUE': profile.blue,
        'BEAT_PERIOD': profile.beat_period, 'BEAT_ON': profile.beat_on, 'REFRESH_NEXT': profile.refresh_next,
        'SETTING_FIRST': int(profile.tap_setting_first),
    }
    return ''.join(f'.equ {name}, {(address | 1) if name in callable_names else address:#x}\n'
                   for name, address in values.items())


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    if p.u32(profile.cc_get + 4) != profile.cc:          # ldr r0, [pc, #0]; bx lr; then the word
        raise SystemExit('patch-menu: the Command Center is not where tap_command.s looks for it')
    m = p.module(MODULE, inc={'tap.inc': tap_inc(p), 'tap_command.inc': command_inc(profile)})
    for slot in profile.slots:
        p.expect(profile.choices + 4 * slot, profile.choice_count.to_bytes(4, 'little'), "an FS slot's Command knob places")
        p.put(profile.choices + 4 * slot, (profile.choice_count + 1).to_bytes(4, 'little'), "an FS slot's Command knob places")
    p.expect(profile.names + 8 * TAP, profile.stock_name, "type 9's name")
    p.put(profile.names + 8 * TAP, NAME.ljust(8, b'\0'), "type 9's name")
    p.expect(profile.counts + TAP, bytes([profile.stock_count]), "type 9's knob count")
    p.put(profile.counts + TAP, b'\x01', "type 9's knob count")
    if getattr(profile, 'type_list', None):
        p.expect(*profile.type_list, "the XL Command Center's available types")
    for site, stock, handler in profile.hook_calls:
        p.own_call(site, stock, f'the Tap command hook at {site:#x}', m[handler])
