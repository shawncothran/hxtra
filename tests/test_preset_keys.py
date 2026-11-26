"""src/m4/preset_keys.s and tools/patch_menu.py's preset keys: the engine that owns the preset file's write, TOC count and section-10
read and hands each feature its own key, run in unicorn with two stand-in features; and the firmware it builds."""
import os
import struct

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
from firmware import branch_target, built, reader

MODS = features.load()
IDS = setting_ids.by_name()
ENGINE = 0x28e70000
STREAM, HEADER, WRITE_FN, SINK = 0x28700000, 0x28700100, 0x28700200, 0x28700300
SERIALIZE, TOC_WRITE, SECTION_READ, PRESET, PRESET_FLAG = 0x28deacf4, 0x28deabdc, 0x28def9a8, 0x28d92a98, 0x28e026f0
SECTION = 0x2821fcc8
WRITERS, FINDERS = (0x28710000, 0x28710010), (0x28710020, 0x28710030)
START = 0xffffffff


class Engine:
    """The engine with features A (key 0x40) and B (key 0x41): each writer writes its bytes (none: no key) and returns its count;
    each finder logs (feature, key, data)."""

    def __init__(self, m4emu, layout=pm.STOMP_MENU):
        keys = {0x40: ('a', WRITERS[0], FINDERS[0]), 0x41: ('b', WRITERS[1], FINDERS[1])}
        code, self.sym = m4emu.assemble('src/m4/preset_keys.s', MODS, IDS, inc={'preset_keys.inc': pm.preset_keys_inc(keys, layout)})
        self.m = m4emu.M4(code, ENGINE)
        self.writes, self.found, self.written, self.flag, self.section = {'a': b'', 'b': b''}, [], [], 0, b''
        self.m.u32(STREAM, SINK)
        self.m.u32(STREAM + 4, WRITE_FN | 1)
        self.m.stub(WRITE_FN, lambda m: self.written.append(m.read(m.reg('r1'), m.reg('r2'))))
        self.m.stub(layout.preset_calls[0][1], lambda m: (self.written.append(b'<map>'), m.reg('r0', 7)))
        self.m.stub(layout.preset_calls[1][1], lambda m: m.reg('r0', 3))
        self.m.stub(layout.preset_get, lambda m: m.reg('r0', 0x28720000))
        self.m.stub(layout.preset_flag, lambda m: m.reg('r0', self.flag))
        self.m.stub(layout.preset_calls[2][1], self._section)
        for name, at in zip('ab', WRITERS):
            self.m.stub(at, lambda m, name=name: self._write(m, name))
        for name, at in zip('ab', FINDERS):
            self.m.stub(at, lambda m, name=name: self.found.append(
                (name, m.reg('r0'), m.read(m.reg('r1'), m.reg('r2')) if m.reg('r0') != START else None)))

    def _write(self, m, name):
        data = self.writes[name]
        if data:
            self.written.append(data)
        m.reg('r0', int(bool(data)))

    def _section(self, m):
        assert (m.reg('r1'), m.reg('r3'), m.stack_args(1)[0]) == (10, SECTION, 0x5000)
        m.write(SECTION, self.section)
        m.reg('r0', len(self.section) or -0x2a)

    def save(self):
        """A save: the serializer then the TOC's second write; what reached the file."""
        self.written.clear()
        assert self.m.call(ENGINE + self.sym['pk_serialize'], STREAM, HEADER) == 7, "the serializer's result"
        assert self.m.call(ENGINE + self.sym['pk_toc'], STREAM, HEADER) == 3, "the TOC write's result"
        return self.written

    def load(self, section):
        self.section, self.found = section, []
        self.m.u32(0x28f00000, 0x5000)
        return self.m.call(ENGINE + self.sym['pk_section'], 0x28730000, 10, 0, SECTION)


@pytest.fixture
def engine(m4emu):
    return Engine(m4emu)


def key(k, data):
    return bytes([k, 0xc4, len(data)]) + data if len(data) < 0x100 else bytes([k, 0xc5]) + struct.pack('>H', len(data)) + data


def test_a_save_with_no_feature_data_is_a_stock_file(engine):
    assert engine.save() == [b'<map>'], 'no key, and the count left alone'


def test_xl_preset_key_engine_saves_and_loads(m4emu):
    engine = Engine(m4emu, pm.XL_MENU)
    engine.flag = 1
    engine.writes = {'a': key(0x40, b'aa'), 'b': key(0x41, b'bb')}
    assert engine.save() == [b'<map>', key(0x40, b'aa'), key(0x41, b'bb'), b'\x8c']
    data = b'\x0c\x90' + key(0x40, b'aa') + key(0x41, b'bb')
    assert engine.load(data) == len(data)
    assert engine.found == [('a', START, None), ('b', START, None), ('a', 0x40, b'aa'), ('b', 0x40, b'aa'),
                            ('a', 0x41, b'bb'), ('b', 0x41, b'bb')]


def test_serializer_callbacks_bracket_stock_serialization_and_feature_keys(m4emu):
    before, after = 0x28710040, 0x28710050
    keys = {0x40: ('snapshots', WRITERS[0], FINDERS[0])}
    callbacks = {'before': [('snapshots', before)], 'after': [('snapshots', after)]}
    code, symbols = m4emu.assemble('src/m4/preset_keys.s', MODS, IDS,
                                   inc={'preset_keys.inc': pm.preset_keys_inc(keys, pm.STOMP_MENU, callbacks)})
    machine = m4emu.M4(code, ENGINE)
    events = []
    machine.stub(before, lambda m: events.append('before'))
    machine.stub(after, lambda m: events.append('after'))
    machine.stub(SERIALIZE, lambda m: (events.append('stock'), m.reg('r0', 7)))
    machine.stub(WRITERS[0], lambda m: (events.append('key'), m.reg('r0', 1)))
    machine.call(ENGINE + symbols['pk_serialize'], STREAM, HEADER)
    assert events == ['before', 'stock', 'after', 'key']


@pytest.mark.firmware
def test_xl_preset_hooks_match_and_patch_stock(m4emu):
    path = os.environ.get('HX_STOMP_XL_HXF')
    if not path:
        pytest.skip('HX_STOMP_XL_HXF is not set')
    archive = pa.load_l6ia_from_any(path)[0]
    e0 = pa.get_entry_swapped(archive, 0)
    stock_read = reader(e0)
    for site, target, _ in pm.XL_MENU.preset_calls:
        assert stock_read(site, 4) == pm.bl(site, target)
    assert branch_target(0x28df0d3e, stock_read(0x28df0d3e, 4)) == pm.XL_MENU.preset_get
    assert branch_target(0x28df0d44, stock_read(0x28df0d44, 4)) == pm.XL_MENU.preset_flag
    patch = pm.Patch(e0, [], {}, layout=pm.XL_MENU)
    patch.preset_key(0x40, WRITERS[0], FINDERS[0])
    module = pm.add_preset_keys(patch)
    read = reader(patch.entry0())
    for site, _, handler in pm.XL_MENU.preset_calls:
        assert branch_target(site, read(site, 4)) == module[handler]


@pytest.mark.parametrize('flag, base', [(0, 0x89), (1, 0x8a)])
def test_each_feature_writes_its_key_after_the_map_in_order_and_the_count_counts_them(engine, flag, base):
    engine.flag = flag
    engine.writes = {'a': key(0x40, b'aa'), 'b': key(0x41, b'b' * 300)}
    assert engine.save() == [b'<map>', key(0x40, b'aa'), key(0x41, b'b' * 300), bytes([base + 2])]
    engine.writes = {'a': b'', 'b': key(0x41, b'bb')}
    assert engine.save() == [b'<map>', key(0x41, b'bb'), bytes([base + 1])], 'only the keys written are counted'


def test_the_count_is_written_once_a_save(engine):
    engine.writes['a'] = key(0x40, b'x')
    engine.save()
    engine.written.clear()
    engine.m.call(ENGINE + engine.sym['pk_toc'], STREAM, HEADER)
    assert engine.written == []


NAMES = (b'', b'\x0c\x90', b'\x0c\x92\xa3abc\xc0', b'\x0c\xdc\x00\x02\xd9\x02hi\xda\x00\x01z')


@pytest.mark.parametrize('names', NAMES)
def test_a_load_hands_every_key_to_every_finder_after_the_names(engine, names):
    section = names + key(0x41, b'b' * 300) + key(0x40, b'aa') + key(0x22, b'?')
    assert engine.load(section) == len(section), "the read's result"
    keys = [(0x41, b'b' * 300), (0x40, b'aa'), (0x22, b'?')]
    assert engine.found == [('a', START, None), ('b', START, None)] + [(f, k, d) for k, d in keys for f in 'ab']


@pytest.mark.parametrize('tail', [b'\x40\xc4\x05ab', b'\x40\xc5\x00', b'\x40\xd9\x01a', b'\x90', b'\x40'])
def test_a_load_stops_at_a_key_that_is_cut_short_or_not_ours(engine, tail):
    engine.load(b'\x0c\x90' + key(0x41, b'b') + tail)
    assert engine.found[2:] == [('a', 0x41, b'b'), ('b', 0x41, b'b')]


def test_a_failed_read_still_starts_each_finder(engine):
    assert engine.load(b'') == -0x2a & 0xffffffff
    assert engine.found == [('a', START, None), ('b', START, None)]


def test_a_feature_registers_a_key_once_and_only_a_free_one():
    p = pm.Patch.__new__(pm.Patch)
    p.owner = 'one'
    p.preset_key(0x50, 1, 2)
    p.owner = 'two'
    with pytest.raises(SystemExit, match='both take preset key 0x50'):
        p.preset_key(0x50, 3, 4)
    for k in (0, 12, 0x80):
        with pytest.raises(SystemExit, match='not a free positive fixint'):
            p.preset_key(k, 3, 4)


@pytest.mark.firmware
def test_without_a_key_the_preset_file_sites_stay_stock():
    read, _ = built({'HX_BPM': '1'})
    assert all(read(s, 4) == pm.bl(s, fn) for s, fn, _ in pm.PRESET_FILE_CALLS)


@pytest.mark.firmware
def test_a_build_with_a_key_sends_the_sites_to_the_engine(m4emu):
    _, sym = m4emu.assemble('src/m4/preset_keys.s', MODS, IDS, inc={'preset_keys.inc': pm.preset_keys_inc({0x64: ('', 0, 0)})})
    read, _ = built({'HX_MORE_SNAPSHOTS': '1'})
    site = pm.PRESET_FILE_CALLS[0][0]
    engine = branch_target(site, read(site, 4)) - sym['pk_serialize']
    assert [branch_target(s, read(s, 4)) for s, _, _ in pm.PRESET_FILE_CALLS] == [engine + sym[h] for _, _, h in pm.PRESET_FILE_CALLS]
