"""tools/features/metronome.py and src/m4/metronome.s: the Metronome block's stand-ins in unicorn, and its block category and hooks
in the firmware they build."""
import re
import struct

import pytest

import features
import patch_click
import patch_menu as pm
import setting_ids
from features import metronome as mt
from firmware import branch_target, built

MODS = features.load()
IDS = setting_ids.by_name()
CODE = 0x28e60000
PITCH, WAH, VOLUME_PAN, SEND_RETURN = 8, 0xa, 0x10, 0x11
OTHER_IDS = (patch_click.PRESET_ID + 0x100, 0x1b5 + 0x10000, 509, 0, -1)


def add_category(m4emu, preset_id, category):
    """metronome_add_cat in unicorn, called as the bl at the add switch is: the caller's block info where the site's load says (its
    category at +0xc); the r3 it returns."""
    code, sym = m4emu.assemble('src/m4/metronome.s', MODS, IDS)
    m = m4emu.M4(code, CODE)
    info = bytearray(0x34)
    struct.pack_into('<BI', info, 0, 1, preset_id & 0xffffffff)
    info[0xc] = category
    m.write(m4emu.STACK_TOP + mt.ADD_SWITCH_STOCK[2] - 0xc, info)
    m.call(CODE + sym['metronome_add_cat'])
    return m.reg('r3')


def test_the_metronome_added_falls_outside_the_add_switch(m4emu):
    assert patch_click.BROWSER == VOLUME_PAN
    assert not PITCH <= add_category(m4emu, patch_click.PRESET_ID, VOLUME_PAN) <= SEND_RETURN, 'the switch\'s default: no FS5'


@pytest.mark.parametrize('category', (PITCH, WAH, VOLUME_PAN, SEND_RETURN, 5))
@pytest.mark.parametrize('preset_id', OTHER_IDS)
def test_every_other_block_added_keeps_its_category(m4emu, preset_id, category):
    assert add_category(m4emu, preset_id, category) == category


def test_the_stand_in_reads_the_add_sites_frame():
    ldrb, off = mt.ADD_SWITCH_STOCK, mt.ADD_SWITCH_STOCK[2]          # ldrb.w r3, [sp, #off]: the block info's category
    assert ldrb[:2] == bytes.fromhex('9df8') and ldrb[3] >> 4 == 3
    asm = open(pm.ROOT + '/src/m4/metronome.s').read()
    body = asm[asm.index('metronome_add_cat:'):asm.index('bx lr', asm.index('metronome_add_cat:'))]
    assert f'ldrb.w r3, [sp, #{off:#x}]' in body and f'ldr.w r3, [sp, #{off - 0xb:#x}]' in body, 'the preset ID at info +1'


VOLUME, UNKNOWN = 0x0e, 0x19


def assign_category(m4emu, preset_id, result=0, category=UNKNOWN):
    """metronome_assign_cat in unicorn, the block category getter stubbed to store category and return result: (r0, the byte)."""
    code, sym = m4emu.assemble('src/m4/metronome.s', MODS, IDS)
    m = m4emu.M4(code, CODE)
    out = m4emu.STACK_TOP - 0x100
    m.stub(mt.BLOCK_CATEGORY, lambda m: (m.u8(m.reg('r2'), category), m.reg('r0', result)))
    r0 = m.call(CODE + sym['metronome_assign_cat'], 0x28a00000, preset_id & 0xffffffff, out)
    assert [regs[:3] for regs in m.calls(mt.BLOCK_CATEGORY)] == [(0x28a00000, preset_id & 0xffffffff, out)]
    return r0, m.read(out, 1)[0]


def test_the_footswitch_assign_sees_the_metronome_as_volume(m4emu):
    assert assign_category(m4emu, patch_click.PRESET_ID) == (0, VOLUME)
    assert assign_category(m4emu, patch_click.PRESET_ID, result=7)[0] == 7


@pytest.mark.parametrize('preset_id', OTHER_IDS)
def test_the_footswitch_assign_sees_every_other_block_as_it_is(m4emu, preset_id):
    assert assign_category(m4emu, preset_id) == (0, UNKNOWN)
    assert assign_category(m4emu, preset_id, category=5) == (0, 5)
    assert assign_category(m4emu, preset_id, result=-22 & 0xffffffff)[0] == -22 & 0xffffffff


STOCK_LED = 0x28e70000


def led_colour(m4emu, category, on=1):
    """metronome_led_colour in unicorn, r12 at a stub of the stock lookup: the category and on/off it passes on."""
    code, sym = m4emu.assemble('src/m4/metronome.s', MODS, IDS)
    m = m4emu.M4(code, CODE)
    m.stub(STOCK_LED)
    m.reg('r12', STOCK_LED | 1)
    m.call(CODE + sym['metronome_led_colour'], category, on)
    return m.calls(STOCK_LED)[0][:2]


def test_the_metronomes_led_takes_volumes_colour(m4emu):
    assert led_colour(m4emu, mt.METRONOME) == (VOLUME, 1)
    assert led_colour(m4emu, mt.METRONOME, on=0) == (VOLUME, 0)


@pytest.mark.parametrize('category', (0, 4, 7, VOLUME, 0x16, 0x17, 0x18, 0x1a, 0xff))
def test_every_other_leds_category_is_left_alone(m4emu, category):
    assert led_colour(m4emu, category) == (category, 1)


def test_its_constants_are_the_click_tools():
    asm = open(pm.ROOT + '/src/m4/metronome.s').read()
    assert int(re.search(r'\.equ PRESET_ID, (\d+)', asm).group(1)) == patch_click.PRESET_ID
    assert int(re.search(r'\.equ METRONOME, (0x[0-9a-f]+)', asm).group(1), 16) == mt.METRONOME
    assert int(re.search(r'\.equ PLAIN, (\d+)', asm).group(1)) == patch_click.CATEGORY
    assert mt.NAME == patch_click.DISPLAY.encode() and mt.FLAG == 'HX_CLICK' and not getattr(mt, 'SETTINGS', ())


@pytest.mark.firmware
def test_build_sends_the_add_switchs_category_load_to_the_module(m4emu):
    code, sym = m4emu.assemble('src/m4/metronome.s', MODS, IDS)
    read, on = built({'HX_CLICK': '1'})
    assert 'metronome' in on
    module = branch_target(mt.ADD_SWITCH, read(mt.ADD_SWITCH, 4)) - sym['metronome_add_cat']
    assert read(module, len(code)) == code
    assert read(mt.ADD_SWITCH + 4, 2) == bytes.fromhex('083b'), 'the stock subs r3, #8 follows'
    assert branch_target(mt.ASSIGN_CATEGORY, read(mt.ASSIGN_CATEGORY, 4)) == module + sym['metronome_assign_cat']
    tramp = branch_target(mt.LED_COLOUR, read(mt.LED_COLOUR, 4))
    assert branch_target(tramp + 8, read(tramp + 8, 4)) == module + sym['metronome_led_colour'], 'movw/movt r12, then b.w'


@pytest.mark.firmware
def test_build_makes_the_unknown_block_category_metronome_with_icon_tempo():
    read, _ = built({'HX_CLICK': '1'})
    rec = read(mt.CATEGORIES + 0x2c * mt.METRONOME, 0x2c)
    assert rec[:0x11].rstrip(b'\0') == rec[0x11:0x1c].rstrip(b'\0') == b'Metronome'
    colour, dim, icon, off = struct.unpack_from('<4I', rec, 0x1c)
    assert (colour, dim, icon) == (0x3cceb5, 0x21665d, pm.ICONS['Icon_Tempo']) and off not in (icon, 0xde)
    assert read(mt.CATEGORIES + 0x2c * 0x18, 0x2c)[:4] == b'None', 'the record before it is stock'


@pytest.mark.firmware
def test_without_the_flag_both_stay_stock():
    read, on = built({})
    assert 'metronome' not in on
    assert read(mt.ADD_SWITCH, 4) == mt.ADD_SWITCH_STOCK
    assert read(mt.CATEGORIES + 0x2c * mt.METRONOME, 0x2c) == mt.UNKNOWN_STOCK
    assert branch_target(mt.ASSIGN_CATEGORY, read(mt.ASSIGN_CATEGORY, 4)) == mt.BLOCK_CATEGORY
    assert read(mt.LED_COLOUR, 4) == mt.LED_COLOUR_STOCK
