"""Metronome: how the Metronome block (tools/patch_click.py, HX_CLICK=1) looks and assigns. Listed under Volume/Pan, it takes that
category's teal pictures in the signal flow, lit when on, dim when off, and its block category is Metronome, with Icon_Tempo. Added from
the browser, it stays off FS5, where a Volume/Pan block goes for an expression pedal's toe switch."""
import struct
import types

import image_store
import patch_menu as pm

FLAG = 'HX_CLICK'
WEB = 'dsp'
XL_PORTED = True

# A model without Entry 3 meta 'category' is block category 0x19, Unknown, otherwise only app, harness and mic models
CATEGORIES, METRONOME = 0x28e2815c, 0x19    # 0x2c-byte records {name[0x11], short[0xb], colour, dim colour, icon, icon off}
UNKNOWN_STOCK = bytes.fromhex('556e6b6f776e0000000000000000000000556e6b6f776e00000000008080800080808000de000000de000000')
NAME = b'Metronome'                 # tools/patch_click.py DISPLAY
COLOURS = (0x3cceb5, 0x21665d)      # Volume, Send, Return and FX Loop's
ICON_OFF_DIMMED = 0.39              # Icon_Tempo has no off picture: dimmed as the strip icons are

# A block added from the browser to a slot with no assignment: by its browser category, a Wah or Volume/Pan block goes on FS5, a toe
# switch's, Volume/Pan's on and Wah's off. The Metronome is no pedal's: the switch on the category reads it as a plain effect.
ADD_SWITCH, ADD_SWITCH_STOCK = 0x28d952d0, bytes.fromhex('9df8 2830')     # ldrb.w r3, [sp, #0x28]

# The footswitch assign (0x28dd8478) clears instead of assigning a block whose block category is None or Unknown: give it Volume's
ASSIGN_CATEGORY, BLOCK_CATEGORY = 0x28dd84d8, 0x28e0f064
# (block category, on) -> a footswitch's LED colour, for categories 4..0x16 only, so the Metronome's would be the default white
LED_COLOUR, LED_COLOUR_STOCK = 0x28db7e1c, bytes.fromhex('0438 1228')     # subs r0, #4; cmp r0, #0x12
STOMP = types.SimpleNamespace(add_switch=ADD_SWITCH, categories=CATEGORIES,
                              assign=ASSIGN_CATEGORY, block_category=BLOCK_CATEGORY, led_colour=LED_COLOUR)
XL = types.SimpleNamespace(
    add_switch=0x28d97da2, categories=0x28e2e5a8, assign=0x28de06c0,
    block_category=0x28e1548c, led_colour=0x28dbaf14)


def metronome_inc(profile=STOMP):
    return f'.equ BLOCK_CATEGORY, {profile.block_category | 1:#x}\n'


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    m = p.module('src/m4/metronome.s', inc={'metronome.inc': metronome_inc(profile)})
    p.expect(profile.add_switch, ADD_SWITCH_STOCK, "a block add's browser category load")
    p.put(profile.add_switch, pm.bl(profile.add_switch, m['metronome_add_cat']), "a block add's browser category load")
    p.own_call(profile.assign, profile.block_category, "the footswitch assign's block category", m['metronome_assign_cat'])
    hook = p.own_entry(profile.led_colour, LED_COLOUR_STOCK, "the footswitch LED's colour lookup")
    a = pm.Asm(p.next())
    a.movw_movt(12, hook.stock | 1)
    a.bw(m['metronome_led_colour'])
    hook.to(p.add(a.bytes()))

    e7, e8 = p.entry(7), p.entry(8)
    icon = pm.ICONS['Icon_Tempo']
    im = image_store.image_at(e7.data, e8.data, icon)
    off = p.add_image(icon, im.width, im.height, image_store.scaled(e8.read(im.offset, im.length), ICON_OFF_DIMMED))
    rec = profile.categories + 0x2c * METRONOME
    p.expect(rec, UNKNOWN_STOCK, 'the Unknown block category')
    p.put(rec, NAME.ljust(0x11, b'\0') + NAME.ljust(0xb, b'\0') + struct.pack('<4I', *COLOURS, icon, off),
          'the Unknown block category, as Metronome')
