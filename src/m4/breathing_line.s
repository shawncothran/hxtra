@ breathing_line.s - the Home screen's divider (the line between the signal flow and the knobs) animated: Type's pattern in
@ Color's colours at Speed. After each Home paint the line is filled straight into the framebuffer in 4 px strips over the
@ stock segments, each strip as tall as the stock segment under it (the selected one is 2 px) and skipped where that one is hidden;
@ the LED task's 1 ms tick asks for a repaint every FRAME_MS while it runs. tools/features/breathing_line.py chains the handlers.
.syntax unified
.thumb
.include "hxtra.inc"
.include "gr.inc"                   @ GR_SHOWN: the gain-reduction meter's shown word, or 0 in a build without it
.include "breathing.inc"
.equ STRIP, 4                       @ px
.equ STRIPS, 80
.equ STRIPS_A_SEGMENT, 20
.equ FRAME_MS, 25
.equ HOME_GONE_MS, 1000             @ no Home paint for this long: another view is up, so no more repaint requests
.equ START_MS, 2000                 @ after the first Home paint: a second after bpm.s shows, as both at once glitch at boot
.equ CENTRE, 632                    @ the line's middle, strip 39.5, in 1/16 strips as every distance below
.equ EYE_CORE, 4 * 16               @ Cylon's eye: full on this far either side of its centre
.equ EYE_FRONT, 24                  @ and fading over this ahead of the core
.equ TRAIL_MIN, 32                  @ Cylon's trail at the ends, where the eye stops to turn
.equ GLOW, 16                       @ Comet's glow ahead of its head
.equ TAIL, 20 * 16                  @ Comet's tail
.equ SPARKS, 3                      @ Sparkle: strips that flash in a quarter cycle of each layer, in 16
.equ RAINBOW, 10                    @ the Color without a row in bl_schemes
.equ TEMPO, 10                      @ the Speed without a row in bl_rates

bl_tick:                            @ after the LED task's 1 ms sleep: a repaint every FRAME_MS while the line runs and its view is up
    adr.w r0, bl_data
    ldr r1, [r0, #24]
    cbz r1, bl_ticked
    movw r2, #START_MS
    cmp r1, r2
    bhi bl_started
    adds r1, #1
    str r1, [r0, #24]
    cmp r1, r2
    bhi bl_redraw                   @ START_MS since the first Home paint: a paint to start the line
    bx lr
bl_started:
    ldr r1, [r0]
    cbz r1, bl_ticked
    ldr r1, [r0, #4]
    movw r2, #HOME_GONE_MS
    cmp r1, r2
    bhs bl_ticked
    adds r1, #1
    str r1, [r0, #4]
    ldr r1, [r0, #8]
    adds r1, #1
    cmp r1, #FRAME_MS
    blo bl_frame
    movs r1, #0
    str r1, [r0, #8]
bl_redraw:
.if LINE_XL
    adr.w r2, bl_data
    ldr r2, [r2, #28]
    cbnz r2, bl_redraw_edit
    movs r0, #1
    movs r1, #1
    b bl_request_redraw
bl_redraw_edit:
    movs r0, #1
    movs r1, #0
bl_request_redraw:
    ldr r3, =LINE_REDRAW
    bx r3
.else
    movs r0, #0
    movs r1, #1
    ldr r3, =0x28db8509
    bx r3
.endif
bl_frame:
    str r1, [r0, #8]
bl_ticked:
    bx lr

bl_paint:                           @ default entry retained for the emulator: Home on Stomp, Edit on XL
.if LINE_XL
    movs r2, #1
    b bl_paint_view
bl_paint_play:
    movs r2, #0
    b bl_paint_view
bl_paint_edit:
    movs r2, #1
bl_paint_view:                      @ r2: Play/Home (0) or Edit (1)
.else
bl_paint_play:
.endif
    push {r4-r11, lr}
    sub sp, #20                     @ the fill's stack arguments: 0 height, 4 colour, 8 anchor
.if LINE_XL
    str r2, [sp, #16]
.endif
    mov r4, r0
    adr.w r9, bl_data
.if LINE_XL
    str r2, [r9, #28]
.endif
    movs r0, #0
    str r0, [r9, #4]
    ldr r0, [r9, #24]
    cbnz r0, bl_booting
    movs r0, #1
    str r0, [r9, #24]
bl_booting:
    movs r0, #SETTING_BREATHING_LINE_MOTION
    movs r1, #SETTING_BREATHING_LINE_MOTION_MAX
    movs r2, #SETTING_BREATHING_LINE_MOTION_DEFAULT
    bl hxtra_setting_get
    movs r6, r0
    ldr r1, [r9, #24]
    movw r2, #START_MS
    cmp r1, r2
    it ls
    movls r6, #0                    @ too soon after boot: the line holds still, as at Type Off
.if GR_SHOWN
    ldr r1, =GR_SHOWN               @ a compressor's meter shows: the line holds still, as at Type Off
    ldr r1, [r1]
    cmp r1, #0
    it ne
    movne r6, #0
.endif
    cmp r6, #0
    bne bl_animate
    ldr r5, [r9]
    cmp r5, #1
    bne bl_stopped
    mov r2, r4
.if LINE_XL
    ldr r0, =LINE_EDIT_SEGMENTS
    movs r1, #2
    bl bl_restore
.else
    bl bl_restore
.endif
    movs r6, #2                     @ the stock segments are dirty: one more paint draws them
bl_stopped:
    cmp r5, #0
    it ne
    strne r6, [r9]                  @ 1 -> 2 (restoring), 2 -> 0 (stock again)
    b bl_painted
bl_animate:
    movs r0, #1
    str r0, [r9]
    movs r0, #SETTING_BREATHING_LINE_THICKNESS
    movs r1, #SETTING_BREATHING_LINE_THICKNESS_MAX
    movs r2, #SETTING_BREATHING_LINE_THICKNESS_DEFAULT
    bl hxtra_setting_get
    str r0, [sp, #12]
    movs r0, #SETTING_BREATHING_LINE_COLOR
    movs r1, #SETTING_BREATHING_LINE_COLOR_MAX
    movs r2, #SETTING_BREATHING_LINE_COLOR_DEFAULT
    bl hxtra_setting_get
    mov r7, r0
    movs r0, #SETTING_BREATHING_LINE_SPEED
    movs r1, #SETTING_BREATHING_LINE_SPEED_MAX
    movs r2, #SETTING_BREATHING_LINE_SPEED_DEFAULT
    bl hxtra_setting_get
    cmp r0, #TEMPO
    bne bl_speed
    mov r0, r6
    bl bl_tempo_rate
    cmp r0, #0
    bne bl_rated
    movs r0, #SETTING_BREATHING_LINE_SPEED_DEFAULT  @ no tempo to follow
bl_speed:
    adr.w r1, bl_rates
    ldr.w r0, [r1, r0, lsl #2]
bl_rated:
    mov r10, r0
    ldr r3, =LINE_CLOCK              @ the µs clock
    blx r3
    ldr r1, [r9, #12]
    str r0, [r9, #12]
    subs r0, r0, r1
    ldr r1, [r9, #16]
    mla r2, r0, r10, r1             @ wraps a whole cycle at 2^32, so the clock's own wrap is harmless
    str r2, [r9, #16]
    cmp r2, r1
    bhs bl_same_cycle
    ldr r3, [r9, #20]
    adds r3, #1
    str r3, [r9, #20]
bl_same_cycle:
    lsr.w r8, r2, #16
    ldr r3, =LINE_LOCK              @ the widget lock, as the stock paint takes it
    blx r3
    mov r0, r4
    bl bl_clear_thick
.if LINE_XL
    ldr r0, [sp, #16]
    cbnz r0, bl_xl_edit_divider
    ldr.w r11, =LINE_PLAY_SEGMENTS
    bl bl_valid_divider
    cbnz r0, bl_xl_play_base_valid
    b.w bl_render_done
bl_xl_play_base_valid:
    ldr.w r11, =LINE_SELECTED
    bl bl_valid_overlay
    cbnz r0, bl_xl_play_overlay
    movs r10, #0
    b bl_xl_play_ready
bl_xl_play_overlay:
    mov r10, r11
bl_xl_play_ready:
    movs r5, #0
    b bl_strip
bl_xl_edit_divider:
    ldr.w r11, =LINE_SELECTED
    bl bl_valid_divider
    cbnz r0, bl_xl_edit_found
    ldr.w r11, =LINE_EDIT_SEGMENTS
    bl bl_valid_divider
    cbnz r0, bl_xl_edit_found
    b.w bl_render_done
bl_xl_edit_found:
    movs r5, #0
    b bl_strip
.else
    movs r5, #0
.endif
bl_strip:
.if LINE_XL
    ldr r0, [sp, #16]
    cbnz r0, bl_xl_widget_ready
    ldr.w r11, =LINE_PLAY_SEGMENTS
    cmp r10, #0
    beq bl_xl_widget_ready
    lsls r0, r5, #2
    ldr r1, [r10, #4]
    cmp r0, r1
    blo bl_xl_widget_ready
    ldr r1, [r10, #4]
    ldr r2, [r10, #0xc]
    adds r1, r1, r2
    cmp r0, r1
    bhs bl_xl_widget_ready
    mov r11, r10
bl_xl_widget_ready:
.else
    movs r0, #STRIPS_A_SEGMENT
    udiv r0, r5, r0
    movs r1, #0x1c
    ldr.w r11, =LINE_PLAY_SEGMENTS
    mla r11, r0, r1, r11
.endif
    ldrb.w r0, [r11, #0x15]         @ visible
    cmp r0, #0
    beq bl_next
    mov r0, r6
    mov r1, r5
    mov r2, r8
    bl bl_level
    mov r3, r0
    mov r0, r7
    mov r1, r5
    mov r2, r8
    bl bl_colour
    str r0, [sp, #4]
    ldr.w r0, [r11, #0x10]          @ height
    ldr r1, [sp, #12]
    adds r0, r0, r1
    str r0, [sp]
    cbz r1, bl_draw_strip
    mov r3, r0
    mov r1, r5
    ldr.w r2, [r11, #8]
.if LINE_XL
    ldr r0, [sp, #16]
    cbnz r0, bl_thick_y_ready
    adds r2, #LINE_PLAY_Y_OFFSET
bl_thick_y_ready:
.endif
    mov r0, r4
    ldr r12, [sp, #4]
    bl bl_save_thick
bl_draw_strip:
    movs r0, #6                     @ x at the left edge, y at the top, as the stock segments are placed
    str r0, [sp, #8]
.if LINE_XL
    lsls r1, r5, #2
    ldr.w r2, [r11, #8]
    ldr r0, [sp, #16]
    cbnz r0, bl_play_y_ready
    adds r2, #LINE_PLAY_Y_OFFSET
bl_play_y_ready:
    mov r0, r4
.else
    mov r0, r4
    lsls r1, r5, #2
    ldr.w r2, [r11, #8]
.endif
    movs r3, #STRIP
    ldr.w r12, =0x100017e9          @ the ROM rectangle fill (fb, x, y, w, h, colour, anchor)
    blx r12
bl_next:
    adds r5, #1
    cmp r5, #STRIPS
    bne bl_strip
.if LINE_XL
bl_render_done:
.endif
    ldr r3, =LINE_UNLOCK
    blx r3
bl_painted:
    add sp, #20
    pop {r4-r11, pc}

bl_restore:                         @ Type turned Off: the stock segments marked dirty, as setColor would mark them
.if LINE_XL
    push {r4-r6, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    ldr r3, =LINE_LOCK
    blx r3
    mov r0, r6
    bl bl_clear_thick
    movs r2, #1
bl_dirty:
    ldr r3, [r4, #0x18]             @ the node
    cbz r3, bl_next_node
    strb r2, [r3, #0x24]
bl_next_node:
    adds r4, #0x1c
    subs r5, #1
    bne bl_dirty
    ldr r3, =LINE_UNLOCK
    blx r3
    pop {r4-r6, pc}
.else
    push {r4, lr}
    mov r4, r2
    ldr r3, =0x28e24971
    blx r3
    mov r0, r4
    bl bl_clear_thick
    ldr r0, =LINE_PLAY_SEGMENTS
    movs r1, #4
    movs r2, #1
bl_dirty:
    ldr r3, [r0, #0x18]
    strb r2, [r3, #0x24]
    adds r0, #0x1c
    subs r1, #1
    bne bl_dirty
    ldr r3, =0x28e24ae9
    blx r3
    pop {r4, pc}
.endif

bl_clear_thick:
    push {r4-r11, lr}
    sub sp, #4
    mov r4, r0
    adr.w r5, bl_thick_frame
    ldr r11, [r5]
    movs r0, #0
    str r0, [r5]
    adr.w r5, bl_thick_data
    movs r6, #0
bl_clear_strip:
    ldrb r7, [r5, #2]
    cbz r7, bl_clear_next
    movs r0, #0
    strb r0, [r5, #2]
    cmp r4, r11
    bne bl_clear_next
    ldrh r8, [r5]
    ldrh r9, [r5, #4]
    movs r10, #0
bl_clear_column:
    lsls r0, r6, #2
    add r0, r10
    movs r1, #240
    mla r0, r1, r0, r9
    add.w r0, r4, r0, lsl #1
    movs r1, #12
    mla r1, r10, r1, r5
    adds r1, #8
    mov r2, r7
bl_clear_row:
    ldrh r3, [r0]
    cmp r3, r8
    itt eq
    ldrheq r3, [r1]
    strheq r3, [r0]
    subs r0, #2
    adds r1, #2
    subs r2, #1
    bne bl_clear_row
    adds r10, #1
    cmp r10, #4
    bne bl_clear_column
bl_clear_next:
    adds r5, #56
    adds r6, #1
    cmp r6, #STRIPS
    bne bl_clear_strip
    add sp, #4
    pop {r4-r11, pc}

bl_save_thick:
    push {r4-r11, lr}
    sub sp, #4
    mov r4, r0
    mov r5, r1
    mov r6, r2
    mov r7, r3
    adr.w r0, bl_thick_frame
    str r4, [r0]
    adr.w r8, bl_thick_data
    movs r0, #56
    mla r8, r5, r0, r8
    ubfx r0, r12, #3, #5
    lsls r0, #11
    ubfx r1, r12, #10, #6
    orr.w r0, r0, r1, lsl #5
    ubfx r1, r12, #19, #5
    orrs r0, r1
    strh r0, [r8]
    strb r7, [r8, #2]
    strh r6, [r8, #4]
    movs r9, #0
bl_save_column:
    lsls r0, r5, #2
    add r0, r9
    movs r1, #240
    mla r0, r1, r0, r6
    add.w r0, r4, r0, lsl #1
    movs r1, #12
    mla r1, r9, r1, r8
    adds r1, #8
    mov r2, r7
bl_save_row:
    ldrh r3, [r0]
    strh r3, [r1]
    subs r0, #2
    adds r1, #2
    subs r2, #1
    bne bl_save_row
    adds r9, #1
    cmp r9, #4
    bne bl_save_column
    add sp, #4
    pop {r4-r11, pc}

.if LINE_XL
bl_valid_divider:                   @ r11 a candidate XL divider widget -> r0 1 when it is visible and has stock divider geometry
    ldrb r0, [r11, #0x15]
    cbz r0, bl_not_divider
    ldrb r0, [r11, #0x14]
    cmp r0, #6
    bne bl_not_divider
    ldr r0, [r11, #4]
    cbnz r0, bl_not_divider
    ldr r0, [r11, #8]
    cmp r0, #120
    bne bl_not_divider
    ldr r0, [r11, #0xc]
    cmp r0, #320
    bne bl_not_divider
    ldr r0, [r11, #0x10]
    subs r0, #1
    cmp r0, #1
    ite ls
    movls r0, #1
    movhi r0, #0
    bx lr
bl_not_divider:
    movs r0, #0
    bx lr

bl_valid_overlay:                   @ r11 the selected Play rectangle -> r0 1 when it fits inside the 320 px divider
    ldrb r0, [r11, #0x15]
    cbz r0, bl_not_overlay
    ldrb r0, [r11, #0x14]
    cmp r0, #6
    bne bl_not_overlay
    ldr r0, [r11, #4]
    cmp r0, #320
    bhs bl_not_overlay
    ldr r1, [r11, #8]
    cmp r1, #119
    beq bl_overlay_y_ok
    cmp r1, #120
    bne bl_not_overlay
bl_overlay_y_ok:
    ldr r1, [r11, #0xc]
    cbz r1, bl_not_overlay
    cmp r1, #320
    bhi bl_not_overlay
    adds r0, r0, r1
    cmp r0, #320
    bhi bl_not_overlay
    ldr r0, [r11, #0x10]
    cmp r0, #2
    bne bl_not_overlay
    movs r0, #1
    bx lr
bl_not_overlay:
    movs r0, #0
    bx lr
.endif

bl_tempo_rate:                      @ r0 Type -> r0 the rate for bl_beats of its beats a cycle at the tempo, 0 if there is none
    push {r4, lr}
    adr.w r1, bl_beats
    ldrb r4, [r1, r0]
    movs r0, #14                    @ Tempo Select: Global BPM when Global, else Preset BPM, as bpm.s picks
    bl bl_get
    cmp r0, #2
    ite eq
    moveq r0, #15
    movne r0, #16
    bl bl_get
    ubfx r2, r0, #23, #8
    subs r2, #127
    cmp r2, #9
    bhi bl_untimed                  @ not 1..1023 BPM
    vmov s15, r0
    ldr r1, =0x476a6000             @ 60000.0f: the beat in whole ms, as the stock beat and bpm.s work it out
    vmov s14, r1
    vdiv.f32 s15, s14, s15
    vcvt.u32.f32 s15, s15
    vmov r0, s15
    cbz r0, bl_untimed
    movw r1, #1000
    muls r0, r1, r0
    muls r0, r4, r0                 @ the cycle in µs
    mov.w r1, #-1
    udiv r2, r1, r0
    mls r1, r2, r0, r1
    cmp.w r1, r0, lsr #1
    it hs
    addhs r2, #1                    @ 2^32 / the cycle, rounded
    mov r0, r2
    pop {r4, pc}
bl_untimed:
    movs r0, #0
    pop {r4, pc}

bl_get:                             @ r0 a stock setting ID -> r0 its value as stored (a float for the BPM), -1 if it has none
    push {r4, lr}
    sub sp, #8
    mov r1, sp
    ldr r3, =LINE_GET               @ GET_VALUE(id, out): the value at out + 4
    blx r3
    cmp r0, #0
    ldr r0, [sp, #4]
    it lt
    movlt r0, #-1
    add sp, #8
    pop {r4, pc}

bl_level:                           @ r0 Type, r1 a strip, r2 the phase (2^16 a cycle) -> r0 the strip's level 0..255
    push {r4-r6, lr}
    lsrs r3, r2, #8
    lsls r4, r1, #4
    adr.w r12, bl_sine
    tbb [pc, r0]
bl_levels:
    .byte (bl_steady - bl_levels) / 2, (bl_steady - bl_levels) / 2, (bl_breathe - bl_levels) / 2, (bl_cylon - bl_levels) / 2
    .byte (bl_comet - bl_levels) / 2, (bl_heart - bl_levels) / 2, (bl_sparkle - bl_levels) / 2
.balign 2
bl_steady:
    movs r0, #255
    pop {r4-r6, pc}
bl_breathe:                         @ a raised cosine from 0, squared to rest longer near the bottom
    adds r3, #192
    uxtb r3, r3
    ldrb r0, [r12, r3]
    muls r0, r0, r0
    adds r0, #255
    lsrs r0, #8
    pop {r4-r6, pc}
bl_cylon:                           @ an eye easing from end to end and back, its trail as long as it is fast
    adds r0, r3, #192
    uxtb r0, r0
    ldrb r0, [r12, r0]
    movw r5, #(STRIPS - 1) * 16
    muls r0, r5, r0
    movs r5, #255
    udiv r0, r0, r5
    ldrb r5, [r12, r3]              @ the speed is |sine(t) - 128|, as the position follows the raised cosine
    subs r5, #128
    it mi
    rsbmi r5, r5, #0
    lsls r5, #1
    adds r5, #TRAIL_MIN
    cmp r3, #128
    ite lo
    sublo r0, r0, r4
    subhs r0, r4, r0                @ behind the eye, whichever way it moves
    cmp r0, #0
    blt bl_cylon_ahead
    subs r0, #EYE_CORE
    it mi
    movmi r0, #0
    mov r1, r5
    bl bl_fall2
    pop {r4-r6, pc}
bl_cylon_ahead:
    rsbs r0, r0, #0
    subs r0, #EYE_CORE
    it mi
    movmi r0, #0
    movs r1, #EYE_FRONT
    bl bl_fall
    pop {r4-r6, pc}
bl_comet:                           @ a head moving right with a soft tail, off the end before it starts again
    movw r5, #STRIPS * 16 + TAIL
    mul r0, r2, r5
    lsrs r0, #16
    subs r0, r0, r4
    bmi bl_comet_ahead
    movw r1, #TAIL
    bl bl_fall2
    pop {r4-r6, pc}
bl_comet_ahead:
    rsbs r0, r0, #0
    movs r1, #GLOW
    bl bl_fall
    pop {r4-r6, pc}
bl_heart:                           @ lub-dub, then a rest, brightest in the middle
    mov r5, r3
    mov r0, r3
    bl bl_beat
    mov r6, r0
    subs r0, r5, #48
    bl bl_beat
    add.w r0, r0, r0, lsl #1
    lsrs r0, #2                     @ the dub at 3/4
    cmp r0, r6
    it lo
    movlo r0, r6
    movw r5, #CENTRE
    subs r1, r4, r5
    it mi
    rsbmi r1, r1, #0
    movs r2, #150
    muls r1, r2, r1
    udiv r1, r1, r5
    rsb r1, r1, #255                @ 255 in the middle, 105 at the ends
    muls r0, r1, r0
    lsrs r0, #8
    pop {r4-r6, pc}
bl_sparkle:                         @ strips flash at random, chosen afresh every cycle: two layers half a quarter apart, so it never goes dark
    mov r4, r3
    mov r6, r1
    adr.w r5, bl_data
    ldr r5, [r5, #20]
    lsls r5, #3                     @ eight quarters a cycle, four for each layer
    mov r0, r3
    mov r2, r5
    bl bl_spark
    mov r1, r6
    mov r6, r0
    adds r0, r4, #32
    uxtb r0, r0
    adds r2, r5, #4
    bl bl_spark
    cmp r0, r6
    it lo
    movlo r0, r6
    pop {r4-r6, pc}

bl_spark:                           @ r0 a phase 0..255, r1 a strip, r2 a seed -> r0 the strip's flash in that quarter of the phase
    push {r4, lr}
    mov r4, r0
    add.w r0, r2, r0, lsr #6
    movs r3, #STRIPS
    mla r0, r0, r3, r1
    ldr r3, =0x9e3779b1
    muls r0, r3, r0
    eor.w r0, r0, r0, lsr #15
    ldr r3, =0x85ebca6b
    muls r0, r3, r0
    eor.w r0, r0, r0, lsr #13
    lsrs r3, r0, #28
    cmp r3, #SPARKS
    bhs bl_unlit
    ubfx r3, r0, #8, #5             @ when in the quarter it flashes
    and r0, r4, #63
    subs r0, r0, r3
    bmi bl_unlit
    cmp r0, #2
    bhs bl_spark_fade
    movs r3, #127
    muls r0, r3, r0
    adds r0, #128
    pop {r4, pc}
bl_spark_fade:
    subs r0, #2
    movs r1, #30
    bl bl_fall2
    pop {r4, pc}
bl_unlit:
    movs r0, #0
    pop {r4, pc}

bl_beat:                            @ r0 a phase 0..255 (unsigned) -> r0 up in 6, a soft fall over 50, then 0
    cmp r0, #56
    bhs bl_beat_none
    cmp r0, #6
    bhs bl_beat_fall
    rsb.w r0, r0, r0, lsl #8
    movs r1, #6
    udiv r0, r0, r1
    bx lr
bl_beat_fall:
    subs r0, #6
    movs r1, #50
    b bl_fall2
bl_beat_none:
    movs r0, #0
    bx lr

bl_fall:                            @ r0 a distance (unsigned), r1 a width -> r0 255 at 0, straight down to 0 at the width and beyond
    cmp r0, r1
    bhs bl_fall_none
    rsb.w r0, r0, r0, lsl #8
    udiv r0, r0, r1
    rsb r0, r0, #255
    bx lr
bl_fall_none:
    movs r0, #0
    bx lr

bl_fall2:                           @ bl_fall squared: a softer tail
    push {r3, lr}
    bl bl_fall
    muls r0, r0, r0
    adds r0, #255
    lsrs r0, #8
    pop {r3, pc}

bl_colour:                          @ r0 Color, r1 a strip, r2 the phase, r3 a level -> r0 0xRRGGBB
    push {r4-r6, lr}
    mov r6, r3
    lsls r1, #4
    movs r3, #5
    udiv r1, r1, r3
    add.w r1, r1, r2, lsr #8
    uxtb r4, r1                     @ the colours run once across the line, moving left a cycle
    cmp r0, #RAINBOW
    bne bl_palette
    mov r0, r4
    bl bl_hue
    b bl_shade
bl_palette:                         @ around three stops: back from the third to the first, so the line has no seam
    adr.w r5, bl_schemes
    add.w r0, r0, r0, lsl #1
    add.w r5, r5, r0, lsl #2
    add.w r4, r4, r4, lsl #1
    lsrs r3, r4, #8
    uxtb r2, r4
    ldr.w r0, [r5, r3, lsl #2]
    adds r3, #1
    cmp r3, #3
    it eq
    moveq r3, #0
    ldr.w r1, [r5, r3, lsl #2]
    bl bl_mix
bl_shade:                           @ the level eased out, from a quarter of the colour: 3/16 and a straight level were too dim on the unit
    mov r1, r0
    ldr r3, =0x3f3f3f
    and.w r0, r3, r1, lsr #2
    rsb r2, r6, #255
    muls r2, r2, r2
    adds r2, #255
    lsrs r2, #8
    rsb r2, r2, #255
    bl bl_mix
    pop {r4-r6, pc}

bl_mix:                             @ r0, r1 two colours, r2 0..255 -> r0 each channel from r0's at 0 to r1's at 255
    push {r4, r5, lr}
    add.w r2, r2, r2, lsr #7
    mov r3, r0
    movs r0, #0
    movs r4, #16
bl_channel:
    lsr.w r5, r3, r4
    uxtb r5, r5
    lsr.w r12, r1, r4
    uxtb r12, r12
    sub.w r12, r12, r5
    mul r12, r12, r2
    add.w r5, r5, r12, asr #8
    lsl.w r5, r5, r4
    orrs r0, r5
    subs r4, #8
    bpl bl_channel
    pop {r4, r5, pc}

bl_hue:                             @ r0 a hue 0..255 -> r0 0xRRGGBB at full saturation and value; uses r1-r3
    movs r1, #43
    udiv r2, r0, r1
    mls r0, r2, r1, r0
    add.w r0, r0, r0, lsl #1
    lsls r0, #1                     @ rising, 0..252
    rsb r1, r0, #255                @ falling
    tbb [pc, r2]
bl_hues:
    .byte (bl_hue0 - bl_hues) / 2, (bl_hue1 - bl_hues) / 2, (bl_hue2 - bl_hues) / 2
    .byte (bl_hue3 - bl_hues) / 2, (bl_hue4 - bl_hues) / 2, (bl_hue5 - bl_hues) / 2
.balign 2
bl_hue0:                            @ red, green rising
    lsls r0, #8
    orr r0, r0, #0xff0000
    bx lr
bl_hue1:                            @ green, red falling
    lsls r0, r1, #16
    orr r0, r0, #0xff00
    bx lr
bl_hue2:                            @ green, blue rising
    orr r0, r0, #0xff00
    bx lr
bl_hue3:                            @ blue, green falling
    lsls r0, r1, #8
    orr r0, r0, #0xff
    bx lr
bl_hue4:                            @ blue, red rising
    lsls r0, #16
    orr r0, r0, #0xff
    bx lr
bl_hue5:                            @ red, blue falling
    orr r0, r1, #0xff0000
    bx lr

HXTRA_SETTING_GET
.ltorg
.balign 4
bl_rates:                           @ Speed 1..10: 2^32 / the cycle in µs, for cycles of 8, 6, 4.8, 4, 3.2, 2.5, 2, 1.5, 1.1 and 0.8 s
    .word 537, 716, 895, 1074, 1342, 1718, 2147, 2863, 3905, 5369
bl_beats:                           @ Speed Tempo: beats a cycle for each Type (Off, Steady, Breathe, Cylon, Comet, Heart, Sparkle)
    .byte 1, 4, 2, 2, 2, 1, 8
.balign 4
bl_schemes:                         @ Color's three stops but Rainbow's; a plain colour repeats its one
    .word 0xffffff, 0xffffff, 0xffffff  @ White
    .word 0xff0000, 0xff0000, 0xff0000  @ Red
    .word 0x00ff00, 0x00ff00, 0x00ff00  @ Green
    .word 0x0060ff, 0x0060ff, 0x0060ff  @ Blue
    .word 0xff1800, 0xff7000, 0xffc800  @ Fire: red, orange, yellow
    .word 0x0050ff, 0x00d0ff, 0xd0f8ff  @ Ice: blue, cyan, white
    .word 0x9000ff, 0xff2a7a, 0xff8a00  @ Sunset: purple, pink, orange
    .word 0x0018ff, 0x0090ff, 0x00ffd0  @ Ocean: deep blue, blue, aqua
    .word 0x00ff70, 0x00b0ff, 0x9a00ff  @ Aurora: green, sky blue, violet
    .word 0xff00d0, 0x5000ff, 0x00f0ff  @ Neon: magenta, indigo, cyan
bl_data:                            @ 0 running (0 no, 1 yes, 2 one more paint for the stock line), 4 ms since the last Home paint,
    .word 0, 0, 0, 0, 0, 0, 0      @ 8 ms into the frame, 12 the clock at the last paint (µs), 16 the phase (2^32 a cycle), 20 cycles,
                                    @ 24 1 + ms since the first Home paint, up to START_MS + 1 (0 before it)
.if LINE_XL
    .word 0                        @ 28 the last view painter (Play/Home 0, Edit 1)
.endif
bl_sine:                            @ 128 + 127.5 sin(2 pi i / 256), rounded
    .byte 128, 131, 134, 137, 140, 143, 146, 149, 152, 155, 158, 162, 165, 167, 170, 173
    .byte 176, 179, 182, 185, 188, 190, 193, 196, 198, 201, 203, 206, 208, 211, 213, 215
    .byte 218, 220, 222, 224, 226, 228, 230, 232, 234, 235, 237, 238, 240, 241, 243, 244
    .byte 245, 246, 248, 249, 250, 250, 251, 252, 253, 253, 254, 254, 254, 255, 255, 255
    .byte 255, 255, 255, 255, 254, 254, 254, 253, 253, 252, 251, 250, 250, 249, 248, 246
    .byte 245, 244, 243, 241, 240, 238, 237, 235, 234, 232, 230, 228, 226, 224, 222, 220
    .byte 218, 215, 213, 211, 208, 206, 203, 201, 198, 196, 193, 190, 188, 185, 182, 179
    .byte 176, 173, 170, 167, 165, 162, 158, 155, 152, 149, 146, 143, 140, 137, 134, 131
    .byte 128, 124, 121, 118, 115, 112, 109, 106, 103, 100, 97, 93, 90, 88, 85, 82
    .byte 79, 76, 73, 70, 67, 65, 62, 59, 57, 54, 52, 49, 47, 44, 42, 40
    .byte 37, 35, 33, 31, 29, 27, 25, 23, 21, 20, 18, 17, 15, 14, 12, 11
    .byte 10, 9, 7, 6, 5, 5, 4, 3, 2, 2, 1, 1, 1, 0, 0, 0
    .byte 0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 9
    .byte 10, 11, 12, 14, 15, 17, 18, 20, 21, 23, 25, 27, 29, 31, 33, 35
    .byte 37, 40, 42, 44, 47, 49, 52, 54, 57, 59, 62, 65, 67, 70, 73, 76
    .byte 79, 82, 85, 88, 90, 93, 97, 100, 103, 106, 109, 112, 115, 118, 121, 124
.balign 4
bl_thick_frame:
    .word 0
bl_thick_data:
    .space STRIPS * 56
