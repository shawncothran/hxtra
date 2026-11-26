# HX Stomp XL 3.80.0 measurements

**Status: verified offline from the stock 3.80.0 images.** Stock image MD5s: HX Stomp `a2cd8f4ae56f49415380270ebc484bf1`; HX Stomp XL `329e3a26d60d3de1988b6785fa833ee1`.

## Entry payloads

Payload sizes are read from each stock `.hxf`'s L6IA entries (`tools/hxf_ram.py load`). The partition map is the shared 3.80.0 map in `tools/hxf_ram.py`; payload capacity excludes the 512-byte entry sub-header sector.

| Entry | XL payload bytes | Stomp payload bytes | Partition start (sector) | Partition sectors |      Payload capacity (bytes) |
| ----: | ---------------: | ------------------: | -----------------------: | ----------------: | ----------------------------: |
|     0 |          911,756 |             895,120 |                    `0x0` |            32,769 |                    16,777,216 |
|     1 |          181,516 |             181,516 |                 `0x8001` |             2,049 |                     1,048,576 |
|     2 |          490,648 |             490,648 |                 `0x8802` |             1,025 |                       524,288 |
|     3 |          830,900 |             830,900 |                 `0x8c03` |             2,057 |                     1,052,672 |
|     4 |       12,575,736 |          12,575,736 |                 `0x940c` |            31,737 |                    16,248,832 |
|     5 |           17,108 |              17,108 |                `0x11005` |             1,025 |                       524,288 |
|     6 |           26,372 |              26,372 |                `0x11406` |            32,769 |                    16,777,216 |
|     7 |           52,032 |              52,032 |                `0x19407` |             2,049 |                     1,048,576 |
|     8 |        4,822,676 |           4,822,676 |                `0x19c08` |         1,071,947 |                   548,836,352 |
|     9 |              132 |                 132 |               `0x11f753` |             4,611 |                     2,360,320 |
|    10 |              764 |                 764 |               `0x120956` |               161 |                        81,920 |
|    11 |            4,080 |               4,020 |               `0x1209f7` |               161 |                        81,920 |
|    12 |          444,196 |             350,028 |               `0x120a98` |           526,914 |                   269,779,456 |
|    13 |        1,046,388 |             952,612 |               `0x1a14da` |           529,276 |                   270,988,800 |
|    14 |       54,264,320 |          54,264,320 |               `0x222856` |         remainder | not bounded by the static map |

Entries 1–10 except Entry 0, and Entry 14, have equal Stomp and XL payload sizes. Entries 0, 11, 12 and 13 differ. The Stomp and XL fixed partition starts and sizes are identical in the stock 3.80.0 layout. Entry 14 is the final partition; its end depends on the physical eMMC size.

The physical XL eMMC sector count was not queried: the XL was in normal application mode, not the RAM loader's info mode. These numbers describe the stock firmware's partition map, not a live capacity read from the unit.

## Preset DSP limit

The Stomp stock app's limit function at `0x28e01e88` and the XL stock app's corresponding function at `0x28e07fa8` contain the same 16 bytes:

`42f2283081428cbf00200120704700bf`

Unicorn calls against both stock code images return `[1, 1, 0]` for preset totals `[8999, 9000, 9001]`. Thus the preset total limit is 9,000 cost units (90%); the fixed 1,500-unit overhead leaves 7,500 units (75%) for blocks, matching the Stomp limit.
