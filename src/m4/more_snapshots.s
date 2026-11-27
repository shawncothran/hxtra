@ more_snapshots.s - snapshots 4 to 6: pressing the lit snapshot footswitch again flips between bank A (snapshots 1-3) and bank B
@ (4-6). The snapshot manager holds three 0x260-byte records; the other bank waits in snaps_shadow, and a flip swaps the two and
@ recalls the same footswitch's snapshot through the stock select. tools/features/more_snapshots.py places the hooks.
.syntax unified
.thumb
.include "snapshots.inc"
.equ SELECT, SNAP_SELECT            @ (manager, index): recalls a snapshot
.equ RECORD_INIT, SNAP_RECORD_INIT  @ (manager, record, name): a record's defaults; takes the manager's lock itself
.equ LOCK, 0x28e24c01
.equ UNLOCK, 0x28e24bb1
.equ REC, SNAP_RECORD               @ a snapshot record
.equ NATIVE, SNAP_NATIVE
.equ EXTRA, SNAP_EXTRA
.equ RECS, 0xc                      @ record 0, in the manager
.equ CUR, SNAP_CUR                  @ the current snapshot
.equ PREV, SNAP_PREV                @ the one before it
.equ BUSY, SNAP_BUSY                @ set while select must not run; select returns 0 then
.equ MANAGER, 0x2812c630
.equ ICON, 0x2812ade8               @ the top view's snapshot icon (image widget): a camera, its number in a circle
.equ LABELS, 0x2812a4bc             @ the Home view's footswitch labels in Snapshot mode: the same cameras, 0x24 bytes apart
.equ FS_FUNCTIONS, 0x28128a74       @ each footswitch's function, two bytes apart
.equ FN_SNAPSHOT, 14                @ snapshot k for footswitch k: Snapshot mode; other modes keep stale cameras in LABELS
.equ WIDGET_LOCK, 0x28e24971
.equ WIDGET_UNLOCK, 0x28e24ae9
.equ REDRAW, SNAP_REDRAW            @ (full, partial): the UI repaints; the layout code ends with (0, 1)
.equ FILL, 0x100017e9               @ (fb, x, y, w, h, colour, anchor)
.equ TEXT, 0x28db7aa5               @ (fb, text, length, x, y, font, colour, anchor, mode): mode 1 draws only the glyphs' pixels
.equ CONTROLLERS, 0x741             @ snapshot controllers: 7-byte entries at a record's +0x28, keyed by their first byte
.equ SWITCHES, 0x742                @ footswitch entries: 9 bytes at +0x1e8, keyed by their first byte
.equ FILE_KEY, 0x64                 @ bank B's key in the preset file (src/m4/preset_keys.s); stock uses 0..12
.equ FILE_LEN, 8 + EXTRA * REC      @ its bin16: extension header plus extra records
.equ DARK, 0x101010                 @ the digit on a lit camera's white circle; black would be the renderer's transparent
.equ WRAP, 5                        @ in snaps_data: the select on its way is a next or previous past the bank's end
.equ VALUE, 2                       @ in WRAP instead: the select on its way is CC 69's value, 0..5

snaps_select:                       @ a footswitch press's call of select (manager, index)
    adr.w r2, snaps_data
    ldrb r3, [r2, #WRAP]
    cbz r3, snaps_select_normal
    b.w snaps_wrap
snaps_select_normal:
    cmp r1, #NATIVE - 1
    bhi snaps_stock
    ldrb.w r2, [r0, #CUR]
    cmp r2, r1
    bne snaps_stock
    ldrb.w r2, [r0, #BUSY]
    cbnz r2, snaps_stock
    b.w snaps_flip
snaps_stock:
    ldr r12, =SELECT
    bx r12

.thumb_func
snaps_xl_button:                    @ XL Snapshot-mode button (manager, physical index): keep the mode handler's frame intact
    push {r4-r7, lr}
    sub sp, #4
    mov r4, r0
    mov r5, r1
    cmp r5, #NATIVE - 1
    bhi snaps_xl_button_stock
    adr.w r2, snaps_data
    ldrb r6, [r2]
    mov r0, r4
    mov r1, r5
    bl snaps_select
    adr.w r2, snaps_data
    ldrb r3, [r2]
    cmp r3, r6
    beq snaps_xl_button_done
    movs r3, #1
    strb r3, [r2, #4]
    b snaps_xl_button_done
snaps_xl_button_stock:
    mov r0, r4
    mov r1, r5
    ldr r3, =SELECT
    blx r3
snaps_xl_button_done:
    add sp, #4
    pop {r4-r7, pc}

.thumb_func
snaps_xl_mode_branch:              @ setting 67's stock fallback would leave Snapshot mode after a bank-flip button press
    adr.w r1, snaps_data
    ldrb.w r12, [r1, #4]
    movs r2, #0
    strb r2, [r1, #4]
    cmp r3, #0
    bne snaps_xl_mode_return
    cmp r12, r2
    bne snaps_xl_mode_return
    ldr r12, =0x28dd9891
    bx r12
snaps_xl_mode_return:
    ldr r12, =0x28dd952f
    bx r12

snaps_cc_select:                    @ MIDI CC 69's call of select (manager, index): stock, bar a value 0..5 or a next or previous past the bank's end
    adr.w r2, snaps_data
    ldrb r3, [r2, #WRAP]
    cmp r3, #VALUE
    beq snaps_value
    cmp r3, #0
    beq snaps_stock

snaps_wrap:                        @ (manager, index, snaps_data): the other bank's first or last, if this preset has a bank B
    movs r3, #0
    strb r3, [r2, #WRAP]
    ldrb r3, [r2, #1]
    cmp r3, #0
    beq snaps_stock
    cmp r1, #NATIVE - 1
    bhi snaps_stock
snaps_cc_cross:
    ldrb.w r3, [r0, #BUSY]
    cmp r3, #0
    bne snaps_stock
    ldrb.w r2, [r0, #CUR]
    b snaps_cross

snaps_value:                        @ (manager, value, snaps_data): 0..2 snapshots 1..3 and 3..5 snapshots 4..6, from either bank
    movs r3, #0
    strb r3, [r2, #WRAP]
    ldrb r3, [r2]
    cmp r1, #NATIVE
    itt hs
    subhs r1, #NATIVE
    eorhs r3, r3, #1                @ r3 set: the value's bank is not the live one
    cmp r3, #0
    beq snaps_stock
    b snaps_cc_cross

snaps_next_cur:                    @ in place of footswitch next's read of the current snapshot (manager): marks a wrap past 3 or 6
    ldrb.w r0, [r0, #CUR]
    cmp r0, #NATIVE - 1
    beq snaps_mark
    bx lr

snaps_prev_cur:                     @ in place of footswitch previous's read: marks a wrap past 1 or 4
    ldrb.w r0, [r0, #CUR]
    cbz r0, snaps_mark
    bx lr

snaps_cc_value:                     @ in place of CC 69's manager getter before its select of the value: marks it
.if SNAP_XL
    movs r2, #VALUE
    b snaps_manager_mark
.else
    ldr r0, =MANAGER
    movs r2, #VALUE
    b snaps_mark_as
.endif

snaps_cc_wrap:                      @ in place of CC 69's manager getter where next leaves 3 or previous leaves 1: marks the wrap
.if SNAP_XL
    movs r2, #1
    b snaps_manager_mark
.else
    ldr r0, =MANAGER
    movs r2, #1
    b snaps_mark_as
.endif
.if SNAP_XL
snaps_manager_mark:
    adr.w r1, snaps_data
    strb r2, [r1, #WRAP]
    ldr r3, =SNAP_MANAGER_GET
    bx r3
.endif
snaps_mark:
    movs r2, #1
snaps_mark_as:
    adr.w r1, snaps_data
    strb r2, [r1, #WRAP]
    bx lr

snaps_flip:                         @ the lit one again: the other bank, then select(index) from the record the sound came from
    mov r2, r1
snaps_cross:                        @ (manager, index, the index being left)
    push {r3-r11, lr}
    mov r4, r0
    mov r5, r1
    mov r11, r2
    adr.w r6, snaps_data
    ldrb r0, [r6, #1]
    cbnz r0, snaps_ready
    adr.w r0, snaps_shadow          @ bank B since the preset loaded: three default records, which select fills from the sound
    movs r1, #0
    movw r2, #EXTRA * REC
    bl snaps_zero_n
    movs r7, #0
snaps_init:
    adr.w r1, snaps_shadow
    mov.w r2, #REC
    mla r1, r2, r7, r1
    adr.w r2, snaps_names
    add.w r2, r2, r7, lsl #4
    mov r0, r4
    ldr r3, =RECORD_INIT
    blx r3
    adds r7, #1
    cmp r7, #EXTRA
    bne snaps_init
    movs r0, #1
    strb r0, [r6, #1]
snaps_ready:
.if !SNAP_XL
    add.w r0, r4, #4
    ldr r3, =LOCK
    blx r3
.endif
    bl snaps_swap
.if !SNAP_XL
    bl snaps_match
.endif
    cmp r5, #0                      @ j, another index: its record stands in for the old one while select runs
    ite eq
    moveq r7, #1
    movne r7, #0
    mov r0, r7
    bl snaps_record
    mov r9, r0
    adr.w r0, snaps_temp
    mov r1, r9
    bl snaps_copy
    adr.w r1, snaps_shadow          @ the record just swapped out holds the sound being left, with its edits
    mov.w r2, #REC
    mla r1, r2, r11, r1
    mov r0, r9
    bl snaps_copy
    ldrb.w r8, [r4, #PREV]
    strb.w r7, [r4, #CUR]           @ so select sees a change from j: it diffs, or copies into an unused record, from there
.if !SNAP_XL
    add.w r0, r4, #4
    ldr r3, =UNLOCK
    blx r3
.endif
.if SNAP_XL
    ldrb r0, [r6]
    eor r0, r0, #1
    strb r0, [r6]
.endif
    mov r0, r4
    mov r1, r5
    ldr r3, =SELECT
    blx r3
    mov r10, r0
.if !SNAP_XL
    add.w r0, r4, #4
    ldr r3, =LOCK
    blx r3
.endif
    mov r0, r9
    adr.w r1, snaps_temp
    bl snaps_copy
    strb.w r8, [r4, #PREV]
    ldrb r0, [r6]
.if !SNAP_XL
    eor r0, r0, #1
    strb r0, [r6]
.endif
    cbnz r0, snaps_flipped
    movs r1, #3
    strb r1, [r6, #3]               @ back in bank A: the top icon (bit 0) and the labels (bit 1) drawn again over bank B's numbers
snaps_flipped:
.if !SNAP_XL
    add.w r0, r4, #4
    ldr r3, =UNLOCK
    blx r3
.endif
    movs r0, #0
    movs r1, #1
    ldr r3, =REDRAW
    blx r3
    mov r0, r10
    pop {r3-r11, pc}

snaps_loaded:                       @ before the preset parser fills the records: bank A, and bank B from the file or anew
    adr.w r0, snaps_data
.if SNAP_XL
    movs r1, #0
    strb r1, [r0]
    strb r1, [r0, #1]
.else
    ldrb r1, [r0]
    add.w r1, r1, r1, lsl #1
    lsls r1, r1, #24                @ bank B was live: the cameras must be drawn again (byte 3)
    str r1, [r0]
.endif
    ldrb r1, [r0, #6]
    cbnz r1, snaps_loaded_b
    bx lr
snaps_loaded_b:                     @ the file's bank B, read with its section 10
    movs r2, #0
    strb r2, [r0, #6]
    movs r2, #1
    strb r2, [r0, #1]
    adr.w r0, snaps_shadow
    add.w r1, r0, #EXTRA * REC
    movw r2, #EXTRA * REC
    b snaps_copy_n

snaps_match:                        @ (r4 the manager) after a swap: the incoming bank's controller and footswitch entries as the
    push {r4-r8, lr}                @ outgoing bank's, which were live, wherever their keys differ (an assignment made meanwhile)
    add.w r4, r4, #RECS
    ldrb.w r7, [r4, #CONTROLLERS - RECS]
    cmp r7, #64
    it hi
    movhi r7, #64
    ldrb.w r8, [r4, #SWITCHES - RECS]
    cmp.w r8, #11
    it hi
    movhi.w r8, #11
    adr.w r5, snaps_shadow
    movs r6, #EXTRA
snaps_match_record:
    add.w r0, r4, #0x28
    add.w r1, r5, #0x28
    mov r2, r7
    movs r3, #7
    bl snaps_match_entries
    add.w r0, r4, #0x1e8
    add.w r1, r5, #0x1e8
    mov r2, r8
    movs r3, #9
    bl snaps_match_entries
    add.w r4, r4, #REC
    add.w r5, r5, #REC
    subs r6, #1
    bne snaps_match_record
    pop {r4-r8, pc}

snaps_match_entries:                @ (to, from, count, size): entry i from from where its first byte differs
    cbz r2, snaps_matched
    push {r4, r5}
snaps_match_entry:
    ldrb r4, [r0]
    ldrb r5, [r1]
    cmp r4, r5
    beq snaps_match_next
    movs r4, #0
snaps_match_byte:
    ldrb r5, [r1, r4]
    strb r5, [r0, r4]
    adds r4, #1
    cmp r4, r3
    bne snaps_match_byte
snaps_match_next:
    add r0, r3
    add r1, r3
    subs r2, #1
    bne snaps_match_entry
    pop {r4, r5}
snaps_matched:
    bx lr

.thumb_func
.global snaps_key_write
snaps_key_write:                    @ preset_keys.s's writer (stream): bank B after the map, as key 0x64; -> the keys written
    push {r4, r5, r6, lr}
    mov r4, r0
.if SNAP_XL
    ldr r3, =SNAP_MANAGER_GET
    blx r3
    add.w r5, r0, #RECS
.else
    ldr r5, =MANAGER + RECS         @ bank B live: the manager's records
.endif
    adr.w r6, snaps_data
    ldrb r0, [r6]
    cbnz r0, snaps_key_put
    ldrb r0, [r6, #1]
    cbz r0, snaps_key_written       @ no bank B for this preset: a stock file
    adr.w r5, snaps_shadow
snaps_key_put:
    adr.w r1, snaps_file_head
    movs r2, #12
    bl snaps_file_put
    mov r1, r5
    movw r2, #EXTRA * REC
    bl snaps_file_put
    movs r0, #1
snaps_key_written:
    pop {r4, r5, r6, pc}

snaps_file_put:                     @ (r4 the stream, r1 bytes, r2 length): the stream's write(context, bytes, length)
    ldr r0, [r4]
    ldr r3, [r4, #4]
    bx r3

.thumb_func
.global snaps_key_found
snaps_key_found:                    @ preset_keys.s's finder (key, data, length): key 0x64, "HX6B", version 1, into snaps_staged
    adr.w r3, snaps_data
    cmp r0, #FILE_KEY
    beq snaps_key_ours
    cmn r0, #1                      @ START: a file is being read
    itt eq
    moveq r0, #0
    strbeq r0, [r3, #6]
    bx lr
snaps_key_ours:
    movw r0, #FILE_LEN
    cmp r2, r0
    it ne
    bxne lr
    push {r4, r5, r6, lr}
    mov r6, r3
    adr.w r4, snaps_file_head + 4
    movs r3, #0
snaps_key_head_byte:
    ldrb r2, [r1, r3]
    ldrb r5, [r4, r3]
    cmp r2, r5
    bne snaps_key_none
    adds r3, #1
    cmp r3, #5
    bne snaps_key_head_byte
    adds r1, #8
    adr.w r0, snaps_shadow
    add.w r0, r0, #EXTRA * REC
    movw r2, #EXTRA * REC
    bl snaps_copy_n
    movs r1, #1
    strb r1, [r6, #6]
snaps_key_none:
    pop {r4, r5, r6, pc}

snaps_paint:                        @ after the top view's paint (framebuffer, view): bank B's number over its snapshot icon's
    movs r1, #1
    adr.w r2, snaps_top
    b snaps_cameras_paint

snaps_home_paint:                   @ after the Home view's paint (framebuffer, view): over its footswitch labels'
    ldr r3, =FS_FUNCTIONS
    ldrb r3, [r3]
    cmp r3, #FN_SNAPSHOT
    it ne
    bxne lr
    movs r1, #2
    adr.w r2, snaps_labels

snaps_cameras_paint:                @ r0 the framebuffer, r1 this paint's bit in byte 3, r2 its cameras, a list ending in 0
    push {r4-r8, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    adr.w r7, snaps_data
    ldrb r0, [r7]
    ldrb r1, [r7, #3]
    tst r1, r5
    it eq
    cmpeq r0, #0
    beq snaps_cameras_done
    ldr r3, =WIDGET_LOCK
    blx r3
    movs r8, #0
    ldrb r0, [r7, #3]
    tst r0, r5
    beq snaps_cameras_draw
    bic r0, r0, r5
    strb r0, [r7, #3]
    movs r8, #1
    mov r0, r6
snaps_cameras_dirty:
    ldr r1, [r0], #4
    cbz r1, snaps_cameras_draw
    ldrb r2, [r1, #0x1d]            @ a hidden one is a renamed snapshot's: its erase would black out the name over it
    cmp r2, #0
    beq snaps_cameras_dirty
    ldr r1, [r1, #0x20]             @ its node: the paint draws it only while the node's byte 0x24 is set
    movs r2, #1
    strb.w r2, [r1, #0x24]
    b snaps_cameras_dirty
snaps_cameras_draw:
    ldrb r0, [r7]
    cbz r0, snaps_cameras_unlock
snaps_cameras_each:
    ldr r0, [r6], #4
    cbz r0, snaps_cameras_unlock
    bl snaps_camera
    b snaps_cameras_each
snaps_cameras_unlock:
    ldr r3, =WIDGET_UNLOCK
    blx r3
    cmp.w r8, #0
    beq snaps_cameras_done
    movs r0, #0                     @ the stock cameras are drawn on the next paint
    movs r1, #1
    ldr r3, =REDRAW
    blx r3
snaps_cameras_done:
    pop {r4-r8, pc}

snaps_camera:                       @ (camera, r4 the framebuffer): 4..6 over a visible stock camera's 1..3, where its image puts it
    push {r4-r7, lr}
    sub sp, #28                     @ 0..16 the stack arguments, 20 the digit
    mov r5, r0
    ldrb r0, [r5, #0x1d]            @ visible
    cmp r0, #0
    beq snaps_camera_done
    ldr r0, [r5]                    @ its image
    adr.w r1, snaps_images
    movs r6, #0
snaps_camera_find:
    ldrh.w r2, [r1, r6, lsl #1]
    cmp r2, r0
    beq snaps_camera_found
    adds r6, #1
    cmp r6, #9
    bne snaps_camera_find
    b snaps_camera_done
snaps_camera_found:
    movs r1, #3
    udiv r7, r6, r1                 @ its style: 0 white, 1 red, 2 lit
    mls r6, r7, r1, r6
    adds r6, #'4'
    strh r6, [sp, #20]              @ with its NUL: the renderer draws to the NUL, using the length only to spot 0 or 1
    ldrb r0, [r5, #0x1c]            @ the anchor: column (x at the left, centre, right) and row (y at the bottom, middle, top)
    udiv r2, r0, r1
    mls r1, r2, r1, r0
    ldr r3, [r5, #0x14]
    mul r1, r1, r3
    ldr r0, [r5, #0xc]
    sub.w r6, r0, r1, lsr #1        @ the camera's left
    ldr r3, [r5, #0x18]
    mul r2, r2, r3
    ldr r0, [r5, #0x10]
    sub.w r5, r0, r2, lsr #1        @ and bottom; its digit's rows are 6..26, inside the circle at 16..42 across [verified offline]
    movs r0, #22
    str r0, [sp]
    movs r0, #0
    cmp r7, #2
    it eq
    mvneq r0, #0xff000000           @ a lit camera's circle is white
    str r0, [sp, #4]
    movs r0, #0
    str r0, [sp, #8]                @ anchor 0: x, y the bottom left corner
    mov r0, r4
    add.w r1, r6, #22
    add.w r2, r5, #6
    movs r3, #16
    ldr r12, =FILL
    blx r12
    adds r0, r5, #1                 @ hx28_boldFont's digits ink rows 5..25 of the cell
    str r0, [sp]
    movs r0, #2
    str r0, [sp, #4]
    ldr r0, =DARK
    cmp r7, #2
    it ne
    mvnne r0, #0xff000000
    str r0, [sp, #8]
    movs r0, #1                     @ anchor 1: x the centre, y the bottom; mode 1: the glyphs' pixels only
    str r0, [sp, #12]
    str r0, [sp, #16]
    mov r0, r4
    add r1, sp, #20
    movs r2, #1
    add.w r3, r6, #29
    ldr r12, =TEXT
    blx r12
snaps_camera_done:
    add sp, #28
    pop {r4-r7, pc}

snaps_saving:                       @ before a preset serializer: bank A live, as a load takes the blocks' live values for its snapshot
.if SNAP_XL
    push {r3, lr}
    ldr r3, =SNAP_MANAGER_GET
    blx r3
    pop {r3, lr}
.else
    ldr r0, =MANAGER
.endif
    adr.w r1, snaps_data
    ldrb r2, [r1]
    cbz r2, snaps_none
    movs r2, #1
    strb r2, [r1, #2]
    b snaps_flip_now
snaps_none:
    bx lr

snaps_saved:                        @ after it: bank B again
.if SNAP_XL
    push {r3, lr}
    ldr r3, =SNAP_MANAGER_GET
    blx r3
    pop {r3, lr}
.else
    ldr r0, =MANAGER
.endif
    adr.w r1, snaps_data
    ldrb r2, [r1, #2]
    cmp r2, #0
    it eq
    bxeq lr
    movs r2, #0
    strb r2, [r1, #2]

snaps_flip_now:                     @ (manager): a flip on the current snapshot; select allowed for it, as the load path allows its own
    push {r4-r6, lr}
    mov r4, r0
    ldrb.w r6, [r4, #BUSY]
    movs r1, #0
    strb.w r1, [r4, #BUSY]
    ldrb.w r1, [r4, #CUR]
    bl snaps_flip
    strb.w r6, [r4, #BUSY]
    pop {r4-r6, pc}

.if SNAP_XL
.thumb_func
snaps_xl_load_finish:               @ XL preset-load epilogue: commit a staged extra bank only on success
    cmp r0, #0
    blt snaps_xl_load_return
    push {r0, lr}
    bl snaps_loaded
    pop {r0, lr}
snaps_xl_load_return:
    pop.w {r4-r8, pc}

.thumb_func
snaps_xl_cc69:                      @ the XL CC handler: values 0..7 select, 8/9 step, other values stay stock
    push {r0-r7, lr}
    sub sp, #12
    mov r4, r1
    cmp r4, #9
    bhi snaps_xl_cc_stock
    ldr r3, =SNAP_MANAGER_GET
    blx r3
    mov r5, r0
    cmp r4, #8
    blo snaps_xl_cc_value
    ldrb r6, [r5, #CUR]
    adr.w r3, snaps_data
    ldrb r7, [r3]
    cmp r7, #0
    it ne
    addne r6, #NATIVE
    cmp r4, #8
    bne snaps_xl_cc_previous
    adds r6, #1
    cmp r6, #2 * NATIVE
    it hs
    movhs r6, #0
    b snaps_xl_cc_step
snaps_xl_cc_previous:
    cbnz r6, snaps_xl_cc_previous_nonzero
    movs r6, #2 * NATIVE - 1
    b snaps_xl_cc_step
snaps_xl_cc_previous_nonzero:
    subs r6, #1
snaps_xl_cc_step:
    lsrs r2, r6, #2
    cmp r2, r7
    ite ne
    movne r2, #1
    moveq r2, #0
    adr.w r3, snaps_data
    strb r2, [r3, #WRAP]
    and r1, r6, #NATIVE - 1
    mov r0, r5
    bl snaps_cc_select
    b snaps_xl_cc_done
snaps_xl_cc_value:
    adr.w r3, snaps_data
    ldrb r2, [r3, #1]
    cmp r4, #NATIVE
    blo snaps_xl_cc_value_ready
    cbnz r2, snaps_xl_cc_value_ready
    ldrb r1, [r5, #CUR]
    mov r0, r5
    bl snaps_select
snaps_xl_cc_value_ready:
    adr.w r3, snaps_data
    movs r2, #VALUE
    strb r2, [r3, #WRAP]
    mov r0, r5
    mov r1, r4
    bl snaps_cc_select
snaps_xl_cc_done:
    add sp, #12
    pop {r0-r7, lr}
    ldr r12, =SNAP_CC_DONE
    bx r12
snaps_xl_cc_stock:
    add sp, #12
    pop {r0-r7, lr}
    cmp r1, #3
    ite ls
    ldrls r12, =SNAP_CC_DIRECT
    ldrhi r12, =SNAP_CC_REMAINDER
    bx r12

.thumb_func
snaps_xl_play_set:                  @ (widget, original image): substitute the matching 5..8 tile while bank B is live
    push {r2, lr}
    bl snaps_xl_play_image
    pop {r2, lr}
    ldr r12, =0x28e2ade1
    bx r12

.thumb_func
snaps_xl_play_lookup:              @ the stock indexed image lookup, then the same bank-B substitution
    ldr.w r1, [r3, r6, lsl #2]
    push {r0, r2, r3, r12, lr}
    sub sp, #4
    bl snaps_xl_play_image
    add sp, #4
    pop {r0, r2, r3, r12, pc}

snaps_xl_play_image:
    adr.w r2, snaps_data
    ldrb r2, [r2]
    cbz r2, snaps_xl_play_done
    adr.w r2, snaps_xl_play_originals
    movs r3, #0
snaps_xl_play_find:
    ldrh.w r12, [r2, r3, lsl #1]
    cmp r1, r12
    beq snaps_xl_play_match
    adds r3, #1
    cmp r3, #24
    bne snaps_xl_play_find
snaps_xl_play_done:
    bx lr
snaps_xl_play_match:
    adr.w r2, snaps_xl_play_variants
    ldrh.w r1, [r2, r3, lsl #1]
    bx lr
.balign 4
snaps_xl_play_originals:
    XL_PLAY_ORIGINALS
snaps_xl_play_variants:
    XL_PLAY_VARIANTS
.endif

snaps_swap:                         @ the manager's three records and snaps_shadow trade places (r4 the manager)
    push {r4-r6, lr}
    add.w r4, r4, #RECS
    adr.w r5, snaps_shadow
    movs r6, #EXTRA
snaps_swap1:
    adr.w r0, snaps_temp
    mov r1, r4
    bl snaps_copy
    mov r0, r4
    mov r1, r5
    bl snaps_copy
    mov r0, r5
    adr.w r1, snaps_temp
    bl snaps_copy
    add.w r4, r4, #REC
    add.w r5, r5, #REC
    subs r6, #1
    bne snaps_swap1
    pop {r4-r6, pc}

snaps_record:                       @ (index) -> its record in the manager (r4)
    mov.w r1, #REC
    mla r0, r0, r1, r4
    adds r0, #RECS
    bx lr

snaps_copy:                         @ (to, from): a record
    mov.w r2, #REC
snaps_copy_n:                       @ (to, from, byte length), aligned to words
    lsrs r2, #2
    cbz r2, snaps_copy_done
snaps_copy_word:
    ldr r3, [r1], #4
    str r3, [r0], #4
    subs r2, #1
    bne snaps_copy_word
snaps_copy_done:
    bx lr

snaps_zero_n:                       @ (address, value, byte length), used for the zeroed bank shadow
    lsrs r2, #2
    movs r3, #0
snaps_zero_word:
    str r3, [r0], #4
    subs r2, #1
    bne snaps_zero_word
    bx lr

.ltorg
.balign 4
snaps_top:
    .word ICON, 0
snaps_labels:
    .word LABELS, LABELS + 0x24, LABELS + 0x48, 0
snaps_images:                       @ the stock cameras by style, then number: Icon_Snapshot1..3, 1Red..3Red, 1Sel..3Sel
    .hword 0x1a0, 0x71, 0x10f, 0x156, 0x105, 0x4f, 0x13, 0x202, 0x12a
.balign 4
snaps_names:                        @ bank B's default names, 16 bytes apart
.if SNAP_XL
    .ascii "SNAPSHOT 5"
    .space 6
    .ascii "SNAPSHOT 6"
    .space 6
    .ascii "SNAPSHOT 7"
    .space 6
    .ascii "SNAPSHOT 8"
    .space 6
.else
    .ascii "SNAPSHOT 4"
    .space 6
    .ascii "SNAPSHOT 5"
    .space 6
    .ascii "SNAPSHOT 6"
    .space 6
.endif
snaps_file_head:                    @ key 0x64, bin16 of FILE_LEN (big-endian), "HX6B", version 1, 3 spare
.if SNAP_XL
    .byte FILE_KEY, 0xc5, FILE_LEN >> 8, FILE_LEN & 0xff, 'H', 'X', '8', 'B', 1, 0, 0, 0
.else
    .byte FILE_KEY, 0xc5, FILE_LEN >> 8, FILE_LEN & 0xff, 'H', 'X', '6', 'B', 1, 0, 0, 0
.endif
snaps_data:                         @ 0 bank B live, 1 snaps_shadow holds bank B, 2 flipped to bank A for a save, 3 cameras to redraw,
    .word 0, 0                      @ 4 XL mode guard, 5 WRAP, 6 bank B read from a file, 7 spare
snaps_temp:
    .space REC
snaps_shadow:                       @ the bank not live: three records as the manager's
    .space EXTRA * REC
snaps_staged:                       @ bank B as read from a preset file, until the preset's snapshots are parsed
    .space EXTRA * REC
