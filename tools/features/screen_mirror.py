"""Screen mirror: HX Edit's editor service answers one more command with the frame on the LCD and the UI events posted since the
last frame, so tools/hx_mirror.py can show the screen on a computer and record it with the controls being used
(src/m4/screen_mirror.s). Nothing changes on the HX Stomp itself."""

import types

import patch_menu as pm
import usb_commands

FLAG = 'HX_SCREEN_MIRROR'
XL_PORTED = True
MENU = False
WEB = False

CMD = usb_commands.by_feature()['screen_mirror']
REGISTER_ALL_CALL, REGISTER_ALL = 0x28d96adc, 0x28e1661c       # the boot's call of the editor's command registrations
POST, POST_STOCK = 0x28db8830, bytes.fromhex('f8b5 0446')       # (event): every UI event to its listeners; push {r3-r7,lr}; mov r4,r0
# The firmware functions src/m4/screen_mirror.s calls, by their first bytes
CALLED = (
    (0x28e165f0, '7b28 0dd8', 'the editor command table setter'),                   # cmp r0, #0x7b; bhi
    (0x28e19204, '0020 7047', 'the no-parameter check'),                            # movs r0, #0; bx lr
    (0x28e157c8, '0228 07d0 054b a3f1 0802', 'the reply writer getter'),            # cmp r0, #2; beq; ...; sub.w r2, r3, #8
    (0x28e157ec, '0228 07d0 054b a3f1 0c02', 'the reply prefix length getter'),     # ...; sub.w r2, r3, #0xc
    (0x28e15810, '0228 07d0 054b a3f1 6402', 'the reply prefix getter'),            # ...; sub.w r2, r3, #0x64
    (0x28e15834, '0228 0c4b 4ff0 0002', 'the reply prefix reset'),
    (0x28e15878, '70b5 82b0 8323', "the reply map's head"),                         # push; sub sp; movs r3, #0x83
    (0x28e24c00, '5ff8 00f0 bd34 0010', 'the lock'),
    (0x28e24bb0, '5ff8 00f0 d134 0010', 'the unlock'),
    (0x28da6458, '0120 fdf7 a7b9', 'the microsecond clock'),                       # movs r0, #1; b.w the timer read
    (0x28e24c58, '5ff8 00f0 3108 0010', 'the task sleep'),                          # ldr.w pc, =0x10000831: the boot ROM's
    (0x28d9f9a0, '034b 1861', "the framebuffer setter's write of the LCD's frame address"),   # ldr r3, =0x40008000; str r0, [r3, #0x10]
    (0x28d9f9b0, '0080 0040', 'the LCD controller'),
)
STOMP = types.SimpleNamespace(register_all_call=REGISTER_ALL_CALL, register_all=REGISTER_ALL, post=POST,
                              called=CALLED, framebuffer=0x28d1ce98, led_colours=0x281f35e0, led_modes=0x281f35f8)
XL_ADDRESSES = (0x28e1ca18, 0x28e1f62c, 0x28e1bbf0, 0x28e1bc14, 0x28e1bc38, 0x28e1bc5c, 0x28e1bca0,
                0x28e2ae80, 0x28e2aef8, 0x28da93ac, 0x28e2aee0, 0x28da291c, 0x28da292c)
XL_STOCK = {7: '5ff800f075350010', 8: '5ff800f089350010', 9: '0120fdf7bdb9'}
XL = types.SimpleNamespace(
    register_all_call=0x28d99780, register_all=0x28e1ca44, post=0x28dbb958,
    called=tuple((address, XL_STOCK.get(index, stock), what)
                 for index, (address, (_, stock, what)) in enumerate(zip(XL_ADDRESSES, CALLED))),
    framebuffer=0x28d1f650, led_colours=0x281f55f8, led_modes=0x281f561c)


def mirror_inc(profile):
    names = ('REGISTER', 'NO_PARAMS', 'WRITER', 'PREFIX_LEN', 'PREFIX', 'PREFIX_RESET', 'REPLY_HEAD', 'LOCK', 'UNLOCK', 'CLOCK', 'SLEEP')
    addresses = {name: address | 1 for name, (address, _, _) in zip(names, profile.called)}
    addresses.update(FB0=profile.framebuffer, LED_COLOURS=profile.led_colours, LED_MODES=profile.led_modes)
    return usb_commands.inc('screen_mirror') + ''.join(f'.equ {name}, {address:#x}\n' for name, address in addresses.items())


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    for va, stock, what in profile.called:
        p.expect(va, bytes.fromhex(stock), what)
    if profile is XL:
        for site, value in ((0x28dbb5fc, profile.framebuffer), (0x28dbb620, profile.framebuffer),
                            (0x28dbb304, profile.led_colours), (0x28dbb2f8, profile.led_modes)):
            p.expect(site, value.to_bytes(4, 'little'), 'the XL screen or LED buffer')
    m = p.module('src/m4/screen_mirror.s', inc={'usb.inc': mirror_inc(profile)})
    p.chain_bl(profile.register_all_call, profile.register_all, after=m['sm_register'])
    p.chain_entry(profile.post, POST_STOCK, before=m['sm_event'])
