"""USB input: HX Edit's editor service takes one more command, whose parameter is UI events, and the HX Stomp queues them as its
own footswitches, knobs and buttons queue theirs (src/m4/usb_input.s). So a computer can press and turn the controls
(tools/hx_input.py), and the on-device tests drive the unit with them (tools/hx_devtest.py). Nothing changes on the unit itself."""

import types

import patch_menu as pm
import usb_commands

FLAG = 'HX_USB_INPUT'
XL_PORTED = True
MENU = False
WEB = False

CMD = usb_commands.by_feature()['usb_input']
REGISTER_ALL_CALL, REGISTER_ALL = 0x28d96adc, 0x28e1661c       # the boot's call of the editor's command registrations
PUT_QUEUE = 0x28db8a10                                          # the put's literal of its queue
QUEUE = 0x281f3db0
# The firmware functions src/m4/usb_input.s calls, by their first bytes
CALLED = (
    (0x28e165f0, '7b28 0dd8', 'the editor command table setter'),                   # cmp r0, #0x7b; bhi
    (0x28e19204, '0020 7047', 'the no-parameter check'),                            # movs r0, #0; bx lr
    (0x28e15b30, '2de9 f04f b0f8 0075', 'the reply sender'),                        # push.w; ldrh.w r7, [r0, #0x500]: the service
    (0x28db88fc, 'f0b5 0546 8bb0', "the key queue's put"),                          # push {r4-r7, lr}; mov r5, r0; sub sp, #0x2c
    (0x28db9a58, '4368 d0e9 0520', "a queue's free bytes"),                         # ldr r3, [r0, #4]; ldrd r2, r0, [r0, #20]
    (0x28e24c58, '5ff8 00f0 3108 0010', 'the task sleep'),
)
STOMP = types.SimpleNamespace(register_all_call=REGISTER_ALL_CALL, register_all=REGISTER_ALL, queue_literal=PUT_QUEUE,
                              queue=QUEUE, called=tuple(va for va, _, _ in CALLED))
XL = types.SimpleNamespace(register_all_call=0x28d99780, register_all=0x28e1ca44, queue_literal=0x28dbbb38,
                           queue=0x281f5e28, called=(0x28e1ca18, 0x28e1f62c, 0x28e1bf58, 0x28dbba24, 0x28dbcbd8, 0x28e2aee0))


def input_inc(profile):
    names = ('REGISTER', 'NO_PARAMS', 'SEND', 'PUT', 'ROOM', 'SLEEP')
    return usb_commands.inc('usb_input') + ''.join(f'.equ {name}, {address | 1:#x}\n' for name, address in zip(names, profile.called)) \
        + f'.equ QUEUE, {profile.queue:#x}\n'


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    for va, (_, stock, what) in zip(profile.called, CALLED):
        p.expect(va, bytes.fromhex(stock), what)
    p.expect(profile.queue_literal, profile.queue.to_bytes(4, 'little'), "the key queue's put's queue")
    m = p.module('src/m4/usb_input.s', inc={'usb.inc': input_inc(profile)})
    p.chain_bl(profile.register_all_call, profile.register_all, after=m['ui_register'])
