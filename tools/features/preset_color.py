"""Preset LED Color: in Preset footswitch mode each preset's footswitch in its own colour, for its ring and its switch icon on the
Home screen (src/m4/preset_color.s). Global Settings > Displays > This Preset gives the current preset one, kept in its file, lit
while it is selected and dimmed while it is not; a preset without one is lit in Preset LED Color's colour and off while not selected,
as stock lights it red. The colours are Tap LED Color's, the stock footswitch palette."""
import struct

import image_store
import patch_menu as pm
from features import Setting, tap_color

FLAG = 'HX_PRESET_COLOR'
MENU = 'Displays'
XL_PORTED = True
ORDER = 110                         # after more_snapshots: its preset key is the file's last, so another preset's tail holds it
MODULE = 'src/m4/preset_color.s'
XL_MODULE = 'src/m4/preset_color_xl.s'
SETTINGS = (     # a label's last line shows on top: Preset over LED, This over Preset
    Setting('color', b'LED\nPreset', tap_color.SETTINGS[0].values[:10]),
    Setting('this', b'Preset\nThis', (b'None',) + tap_color.SETTINGS[0].values[:10]),
)
PRESET_KEY = 0x65                   # this preset's colour in its file: bin8 of "HXPC" and This Preset's value
LEDS, ICONS = tap_color.LEDS, (0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115)  # Icon_SwitchRed .. White
DIMS = (0x02000c, 0x000410, 0x000608, 0x000c08, 0x000901, 0x060d00, 0x0d0400, 0x0b0003, 0x07000b, 0x0c1007)    # 0x28dd8030(_, i, 0)
DIM_ICONS = (0x9c, 0x1e0, 0x214, 0xb7, 0x1fb, 0x8, 0x184, 0xc0, 0x117, 0x76)                    # Icon_SwitchRedOff .. WhiteOff
XL_SELECTED_TILES = (0x196, 0x221)
XL_DIM_TILES = (0x1ae, 0x152)

LED_COLOUR, SET_IMAGE, LED_MODE = tap_color.LED_COLOUR, tap_color.SET_IMAGE, 0x28db8260
# The LED refresh 0x28dd0b3c's Preset case (function 13): mode on, then the red word below through r10, its only literal
PRESET_RED, PRESET_RED_LIT = 0x28e3c4a0, 0x28dd0f40
LED_CALL, LED_LOAD = 0x28dd0c44, (0x28dd0c3e, bytes.fromhex('daf80010'))     # ldr.w r1,[r10]
# Its call that turns a ring off, which the Preset case reaches for a preset that is not the current one
OFF_CALL, OFF_ZERO = 0x28dd0b96, (0x28dd0b94, bytes.fromhex('0021'))          # movs r1,#0
# The Preset-mode Home builder 0x28dc712c: Icon_SwitchRed for the current preset, Icon_SwitchDark (0x112) for the others, r4 the preset
ICON_CALL, ICON_PICK = 0x28dc71a0, (0x28dc7194, bytes.fromhex('4ff48971'))   # mov.w r1,#0x112, then moveq r1,#0x78
HOME_PAINT_LIT, HOME_PAINT = tap_color.HOME_PAINT_LIT, tap_color.HOME_PAINT
XL = {
    'ring': (0x28dd8c02, 0x28dbb308),
    'icons': (0x28dcb93a, 0x28dcba24),
    'dim_ring': 0x28dd8bf2,
    'dim_icons': (0x28dcb7ca, 0x28dcb90c),
    'paint_pointer': (0x28d99a44, 0x28dcc98d),
}


def xl_tile_records(e7, e8):
    """Return XL's appended selected/dim tile records, pixels, and per-style index maps."""
    items, records = [], []
    first_record = struct.unpack_from('<I', e7, 0x18)[0]
    first_item = struct.unpack_from('<I', e8, 8)[0]

    def variants(source_index, colors, include_original):
        source = image_store.image_at(e7, e8, source_index)
        if source.bpp != 16 or source.length != 2 * source.width * source.height:
            raise SystemExit('patch-menu: an XL Preset Play tile is not RGB565')
        pixels = struct.unpack_from(f'<{source.width * source.height}H', e8, source.offset)
        indices = [source_index] if include_original else []
        for color in colors:
            red, green, blue = (color >> 16) & 255, (color >> 8) & 255, color & 255
            palette = {shade: ((shade & 31) * red // 255)
                       | ((((shade >> 5) & 63) * green // 255) << 5)
                       | ((((shade >> 11) & 31) * blue // 255) << 11) for shade in set(pixels)}
            item_index = first_item + len(items)
            items.append(struct.pack(f'<{len(pixels)}H', *(palette[shade] for shade in pixels)))
            record_offset = image_store.record_at(e7, source_index)
            record = bytearray(e7[record_offset:record_offset + image_store.RECORD])
            for word in (2, 3, 9):
                struct.pack_into('<I', record, word * 4, item_index)
            indices.append(first_record + len(records))
            records.append(bytes(record))
        return indices

    selected = [index for source in XL_SELECTED_TILES for index in variants(source, tap_color.TEXTS[1:], True)]
    dimmed = [index for source in XL_DIM_TILES for index in variants(source, (*tap_color.TEXTS[:9], 0xffffff), False)]
    return items, records, tuple(selected), tuple(dimmed)


def xl_include(preset_lit, selected, dimmed):
    selected_words = ', '.join(f'{value:#x}' for value in selected)
    dim_words = ', '.join(f'{value:#x}' for value in dimmed)
    return (f'.equ PRESET_LIT, {preset_lit | 1:#x}\n'
            f'.macro XL_SELECTED_IDS\n    .hword {selected_words}\n.endm\n'
            f'.macro XL_DIM_IDS\n    .hword {dim_words}\n.endm\n')


def apply(p):
    m = p.module(MODULE)
    if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base:
        e7, e8 = p.entry(7), p.entry(8)
        items, records, selected, dimmed = xl_tile_records(e7.data, e8.data)
        for item in items:
            e8.add_item(item)
        for record in records:
            e7.add_record(record)
        xl = p.module(XL_MODULE, inc={
            'xl_preset_color.inc': xl_include(m['preset_lit'], selected, dimmed)})
        p.own_call(XL['ring'][0], XL['ring'][1], 'the XL Preset ring colour', xl['preset_ring_xl'])
        for site in XL['icons']:
            p.own_call(site, 0x28e2ade0, 'the XL selected preset tile', xl['preset_icon_xl'])
        p.expect(XL['dim_ring'], bytes.fromhex('7ff42eaf'), 'the XL dim preset ring branch')
        p.put(XL['dim_ring'], pm.bl(XL['dim_ring'], xl['preset_ring_dim_xl']), 'the XL dim preset ring')
        for site in XL['dim_icons']:
            p.own_call(site, 0x28e2ade0, 'the XL dim preset tile', xl['preset_icon_dim_xl'])
        p.expect(0x28dcb7b2, bytes.fromhex('00f02d81'), 'the XL dim tile branch')
        p.put(0x28dcb7b2, bytes.fromhex('00bf00bf'), 'the XL dim tile branch')
        p.chain_ptr(*XL['paint_pointer'], after=xl['preset_paint_xl'])
        p.preset_key(PRESET_KEY, m['preset_key_write'], m['preset_key_found'])
        return
    if p.u32(PRESET_RED_LIT) != PRESET_RED or p.u32(PRESET_RED) != LEDS[0]:
        raise SystemExit('patch-menu: the Preset case of the LED refresh does not load the stock red')
    p.expect(*LED_LOAD, 'the Preset ring colour load')
    p.own_call(LED_CALL, LED_COLOUR, 'the Preset ring colour', m['preset_led'])
    p.expect(*OFF_ZERO, 'the LED refresh turning a ring off')
    p.own_call(OFF_CALL, LED_MODE, 'the LED refresh turning a ring off', m['preset_off'])
    p.expect(*ICON_PICK, 'the Preset switch icon')
    p.own_call(ICON_CALL, SET_IMAGE, 'the Preset switch icon', m['preset_icon'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, before=m['preset_paint'])
    p.preset_key(PRESET_KEY, m['preset_key_write'], m['preset_key_found'])
