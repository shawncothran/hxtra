"""More snapshots: pressing the lit snapshot footswitch again flips between snapshots 1-3 and 4-6 (src/m4/more_snapshots.s); in
4-6 the snapshot icon at the top right and the footswitch labels show 4, 5 or 6. Once a preset has a bank B, the next and previous snapshot
footswitches and MIDI CC 69 run through all six: next on 3 goes to 4, next on 6 to 1, previous on 1 to 6, previous on 4 to 3.
MIDI CC 69's values 0..2 select snapshots 1..3 and 3..5 snapshots 4..6, from either bank."""

import struct
import types

import image_store
import patch_menu as pm

FLAG = 'HX_MORE_SNAPSHOTS'
XL_ORDER = 99                       # before Long Press, which reads its XL module data
XL_PORTED = True
STOMP = types.SimpleNamespace(record=0x260, native=3, extra=3, cur=0x743, prev=0x744, busy=0x9a9,
                                        manager_get=0, select=0x28de2f91, record_init=0x28de14b5,
                                                     redraw=0x28db8509, layout=pm.STOMP_MENU, select_sites=(),
                                                     next_cur=None, prev_cur=None)
XL = types.SimpleNamespace(record=0x278, native=4, extra=4, cur=0xa03, prev=0xa04, busy=0xc81,
                                    manager_get=0x28d98c35, select=0x28de8dcd, record_init=0x28de718d,
                                       redraw=0x28dbb631, layout=pm.XL_MENU,
                           cc_done=0x28d9e055, cc_direct=0x28d9e4e7, cc_remainder=0x28d9e397,
                           cc_range=0x28d9e390, cc_range_stock=bytes.fromhex('032940f2a880'),
                           select_sites=((0x28e2243a, 0x28de8dcc), (0x28dd5940, 0x28de8dcc),
                                         (0x28dc43be, 0x28de8dcc), (0x28dd2008, 0x28de8dcc),
                                         (0x28deb86c, 0x28de8dcc), (0x28deb890, 0x28de8dcc)),
                           snapshot_button=(0x28dd987c, 0x28de8dcc),
                           snapshot_mode_branch=(0x28dd988c, bytes.fromhex('7ff44fae'), 0x28dd952e, 0x28dd9890),
                                                    next_cur=(0x28dd992a, 0x28de958c), prev_cur=(0x28dd975a, 0x28de958c),
                                       load_finish_sites=((0x28df183e, bytes.fromhex('bde8f081')),
                                                          (0x28df1880, bytes.fromhex('bde8f081'))))
XL_PLAY_SET_CALLS = tuple((site, 0x28e2ade0) for site in (
    0x28dca844, 0x28dd5532, 0x28dca91c, 0x28dca93c, 0x28dca94c, 0x28dca95e,
    0x28dca96c, 0x28dca97a, 0x28dca986, 0x28dca992, 0x28dcf3d4, 0x28dcf3f4,
    0x28dcf404, 0x28dcf416, 0x28dcf424, 0x28dcf432, 0x28dcf43e, 0x28dcf44a))
XL_PLAY_LOOKUP = (0x28dcbae8, bytes.fromhex('53f82610'))


def snapshots_inc(profile=STOMP, play_originals=(), play_variants=()):
    values = {'SNAP_RECORD': profile.record, 'SNAP_NATIVE': profile.native, 'SNAP_EXTRA': profile.extra,
              'SNAP_CUR': profile.cur, 'SNAP_PREV': profile.prev, 'SNAP_BUSY': profile.busy,
              'SNAP_MANAGER_GET': profile.manager_get, 'SNAP_SELECT': profile.select,
              'SNAP_RECORD_INIT': profile.record_init, 'SNAP_REDRAW': profile.redraw,
              'SNAP_CC_DONE': getattr(profile, 'cc_done', 0), 'SNAP_CC_DIRECT': getattr(profile, 'cc_direct', 0),
              'SNAP_CC_REMAINDER': getattr(profile, 'cc_remainder', 0),
              'SNAP_XL': int(profile is XL)}
    text = ''.join(f'.equ {name}, {value:#x}\n' for name, value in values.items())
    if profile is XL:
        play_originals = play_originals or (0,) * 24
        play_variants = play_variants or (0,) * 24
        for name, indexes in (('XL_PLAY_ORIGINALS', play_originals), ('XL_PLAY_VARIANTS', play_variants)):
            words = '\n'.join('    .hword ' + ', '.join(f'{index:#x}' for index in indexes[i:i + 8])
                              for i in range(0, len(indexes), 8))
            text += f'.macro {name}\n{words}\n.endm\n'
    return text

SELECT = 0x28de2f90                 # (manager, index): recalls a snapshot
# The tail calls of select (b.w) a footswitch press reaches: the footswitch functions' (0x28dd14a0: 14 snapshot k for footswitch k,
# as Snapshot mode sets them [verified on unit], and 7, 8 next and previous) and the snapshot action's (0x28de59a8)
FS_SELECT_CALLS = (0x28dd1640, 0x28de59d8)
# Footswitch next and previous (the dispatch's cases 7 and 8) read the current snapshot at these calls of 0x28de3750, then wrap it in 0..2
NEXT_CUR, PREV_CUR, CUR_GET = 0x28dd1628, 0x28dd16dc, 0x28de3750
# MIDI CC 69 (0x28d9b120): its calls of the manager getter only where 8 (next) wraps 2 to 0 and 9 (previous) 0 to 2, and its select
CC_WRAP_CALLS, MANAGER_GET, CC_SELECT = (0x28d9b676, 0x28d9b6d8), 0x28d960a4, 0x28d9b5de
# CC 69's cmp r1, #2 before its select of the value: #5 sends 3..5 there too, which stock ignores; that path alone calls the manager
# getter at CC_VALUE_CALL, as next and previous within a bank select 0..2 through the same tail call
CC_RANGE, CC_RANGE_STOCK, CC_RANGE_SIX, CC_VALUE_CALL = 0x28d9b5a2, bytes.fromhex('0229'), bytes.fromhex('0529'), 0x28d9b63a
PARSE, PARSE_STOCK = 0x28de42c4, bytes.fromhex('2de9 f04f')     # the preset's snapshots into the manager; push.w {r4-r11,lr}
# The preset serializers: each copies the blocks, with their live values, then calls the snapshot writer 0x28de3c9c; a load takes the
# live values as its current snapshot's. 0x28dea8c4 (push.w {r4-r8,lr}) is the one a save on the unit took [verified on unit],
# 0x28deacf4 (push.w {r4-r11,lr}) the other save path's and HX Edit's (0x28e1c5b2). They are the writer's only callers.
SERIALIZERS = ((0x28dea8c4, bytes.fromhex('2de9 f041')), (0x28deacf4, bytes.fromhex('2de9 f04f')))
FILE_KEY = 0x64                     # bank B's key in the preset file, through tools/patch_menu.py's preset keys
XL_PLAY_STYLE_NAMES = (
    (b'Play_Snapshot1', b'Play_Snapshot2', b'Play_Snapshot3', b'Play_Snapshot4', 19017, 65535),
    (b'Play_Snapshot1Medium', b'Play_Snapshot2Medium', b'Play_Snapshot3Medium', b'Play_Snapshot4Medium', 19017, 65535),
    (b'Play_Snapshot1Sel', b'Play_Snapshot2Sel', b'Play_Snapshot3Sel', b'Play_Snapshot4Sel', 65535, 0),
    (b'Play_Snapshot1SelMedium', b'Play_Snapshot2SelMedium', b'Play_Snapshot3SelMedium', b'Play_Snapshot4SelMedium', 65535, 0),
    (b'Icon_Snapshot1', b'Icon_Snapshot2', b'Icon_Snapshot3', b'Icon_Snapshot4', 0, 65535),
    (b'Icon_Snapshot1Red', b'Icon_Snapshot2Red', b'Icon_Snapshot3Red', b'Icon_Snapshot4Red', 0, 65535),
)
TOP_PAINT_LIT, TOP_PAINT = 0x28d96d90, 0x28dca359              # the top view's paint (preset number, name, snapshot icon), as registered
HOME_PAINT_LIT, HOME_PAINT = 0x28d96e28, 0x28dc8d39            # the Home view's paint (footswitch labels), as registered


def xl_play_tiles(e7, e8):
    """Return 5–8 XL Play tile variants and their original-image to appended-image map."""
    names = image_store.names(e7)
    _, glyph_table = image_store.font(e7, b'hx28_boldFont')
    first_item = struct.unpack_from('<I', e8, 8)[0]
    first_record = struct.unpack_from('<I', e7, 0x18)[0]
    items, records, originals, variants = [], [], [], []

    def rows(image):
        words = struct.unpack_from(f'<{image.width * image.height}H', e8, image.offset)
        return [[words[x * image.height + image.height - 1 - y] for x in range(image.width)]
                for y in range(image.height)]

    for stock_names in XL_PLAY_STYLE_NAMES:
        background, ink = stock_names[-2:]
        indices = [names.index(name) for name in stock_names[:4]]
        source, compare = (image_store.image_at(e7, e8, index) for index in indices[:2])
        assert (source.width, source.height, source.bpp) == (compare.width, compare.height, 16)
        base_rows, compare_rows = rows(source), rows(compare)
        changed = [(x, y) for y in range(source.height) for x in range(source.width)
                   if base_rows[y][x] != compare_rows[y][x]]
        top, bottom = min(y for _, y in changed), max(y for _, y in changed) + 1
        left, right = min(x for x, _ in changed), max(x for x, _ in changed) + 1
        assert (bottom - top, right - left) == (21, 13)
        assert set(base_rows[y][x] for x, y in changed) == {background, ink}

        for digit, original in zip('5678', indices):
            height, width, glyph_item = image_store.glyph(e7, glyph_table, ord(digit))
            offset, length = image_store.item(e8, glyph_item)
            glyph_words = struct.unpack_from(f'<{width * height}H', e8, offset)
            glyph_rows = [[glyph_words[x * height + height - 1 - y] for x in range(width)] for y in range(height)]
            lit_pixels = [(x, y) for y in range(height) for x in range(width) if glyph_rows[y][x]]
            gy0, gy1 = min(y for _, y in lit_pixels), max(y for _, y in lit_pixels) + 1
            gx0, gx1 = min(x for x, _ in lit_pixels), max(x for x, _ in lit_pixels) + 1
            mask = [[bool(glyph_rows[y][x]) for x in range(gx0, gx1)] for y in range(gy0, gy1)]
            assert len(mask) <= 21 and len(mask[0]) <= 15
            picture = [row[:] for row in base_rows]
            for y in range(top, bottom):
                for x in range(left, right):
                    picture[y][x] = background
            y0 = top + (bottom - top - len(mask)) // 2
            x0 = left + (right - left - len(mask[0])) // 2
            for y, row in enumerate(mask):
                for x, active in enumerate(row):
                    if active:
                        picture[y0 + y][x0 + x] = ink
            pixels = b''.join(struct.pack('<H', picture[y][x])
                              for x in range(source.width) for y in range(source.height - 1, -1, -1))
            item_index = first_item + len(items)
            items.append(pixels)
            record_offset = image_store.record_at(e7, original)
            record = bytearray(e7[record_offset:record_offset + image_store.RECORD])
            for word in (2, 3, 9):
                struct.pack_into('<I', record, word * 4, item_index)
            variants.append(first_record + len(records))
            records.append(bytes(record))
            originals.append(original)
    return items, records, tuple(originals), tuple(variants)


def apply(p):
    profile = XL if getattr(p, 'layout', pm.STOMP_MENU).base == pm.XL_MENU.base else STOMP
    play_originals, play_variants = (), ()
    if profile is XL:
        e7, e8 = p.entry(7), p.entry(8)
        items, records, play_originals, _ = xl_play_tiles(e7.data, e8.data)
        item_indices = [e8.add_item(item) for item in items]
        play_variants = []
        for record, item_index in zip(records, item_indices):
            record = bytearray(record)
            for word in (2, 3, 9):
                struct.pack_into('<I', record, word * 4, item_index)
            play_variants.append(e7.add_record(record))
    if profile is XL:
        if profile is XL:
            m = p.module('src/m4/more_snapshots.s', inc={'snapshots.inc': snapshots_inc(profile, play_originals, play_variants)})
        else:
            m = p.module('src/m4/more_snapshots_stomp.s')
    else:
        m = p.module('src/m4/more_snapshots_stomp.s')
    if profile is XL:
        p.preset_key(FILE_KEY, m['snaps_key_write'], m['snaps_key_found'],
                     before=m['snaps_saving'], after=m['snaps_saved'])
        for site, stock in profile.load_finish_sites:
            p.own_entry(site, stock, 'the XL preset-load snapshot state', m['snaps_xl_load_finish'])
        for site, stock in profile.select_sites:
            p.own_call(site, stock, 'the XL native snapshot selection', m['snaps_select'])
        site, stock = profile.snapshot_button
        p.own_call(site, stock, 'the XL Snapshot-mode button selection', m['snaps_xl_button'])
        site, stock, _, _ = profile.snapshot_mode_branch
        p.expect(site, stock, 'the XL Snapshot-mode switch fallback')
        p.put(site, pm.thumb_bw(site, m['snaps_xl_mode_branch']), 'the XL Snapshot-mode switch fallback')
        p.own_call(profile.next_cur[0], profile.next_cur[1], 'XL footswitch next current snapshot', m['snaps_next_cur'])
        p.own_call(profile.prev_cur[0], profile.prev_cur[1], 'XL footswitch previous current snapshot', m['snaps_prev_cur'])
        p.expect(profile.cc_range, profile.cc_range_stock, 'the XL MIDI CC 69 snapshot range')
        p.put(profile.cc_range, pm.thumb_bw(profile.cc_range, m['snaps_xl_cc69']) + bytes.fromhex('00bf'),
              'the XL MIDI CC 69 snapshot range')
        for site, stock in XL_PLAY_SET_CALLS:
            p.own_call(site, stock, 'the XL Play snapshot tile image', m['snaps_xl_play_set'])
        site, stock = XL_PLAY_LOOKUP
        p.expect(site, stock, 'the XL Play snapshot tile lookup')
        p.put(site, pm.bl(site, m['snaps_xl_play_lookup']), 'the XL Play snapshot tile lookup')
        return
    for site in FS_SELECT_CALLS:
        p.own_call(site, SELECT, f"a footswitch's call of select at {site:#x}", m['snaps_select'])
    p.own_call(NEXT_CUR, CUR_GET, "footswitch next's read of the current snapshot", m['snaps_next_cur'])
    p.own_call(PREV_CUR, CUR_GET, "footswitch previous's read of the current snapshot", m['snaps_prev_cur'])
    for site in CC_WRAP_CALLS:
        p.own_call(site, MANAGER_GET, f"MIDI CC 69's call of the manager getter at {site:#x}, where it wraps", m['snaps_cc_wrap'])
    p.own_call(CC_SELECT, SELECT, "MIDI CC 69's call of select", m['snaps_cc_select'])
    p.own_call(CC_VALUE_CALL, MANAGER_GET, "MIDI CC 69's call of the manager getter before its select of the value", m['snaps_cc_value'])
    p.expect(CC_RANGE, CC_RANGE_STOCK, "MIDI CC 69's range of snapshot values")
    p.put(CC_RANGE, CC_RANGE_SIX, "MIDI CC 69's values 3..5, snapshots 4..6")
    p.chain_entry(PARSE, PARSE_STOCK, before=m['snaps_loaded'])
    p.preset_key(FILE_KEY, m['snaps_key_write'], m['snaps_key_found'])
    for fn, stock in SERIALIZERS:
        p.chain_entry(fn, stock, before=m['snaps_saving'], after=m['snaps_saved'])
    p.chain_ptr(TOP_PAINT_LIT, TOP_PAINT, after=m['snaps_paint'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, after=m['snaps_home_paint'])
