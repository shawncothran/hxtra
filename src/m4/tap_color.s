@ tap_color.s - the TAP footswitch in the colour Tap LED Color picks: its ring as the stock beat lights it, and on the Home screen its
@ switch icon and the two lines of its label. Rainbow moves the ring a small step round the colour wheel at each beat, Random lights it a random colour;
@ both leave the label White. tap_now is the colour shown, for BPM's Tempo. tools/features/tap_color.py places the hooks.
.syntax unified
.thumb
.include "hxtra.inc"
.include "rainbow.inc"              @ STEPS; RAINBOW_LEDS, RAINBOW_TEXTS: its colours, as tap_color.py blends them
.include "tap.inc"
.equ SET_COLOR, 0x28e24a29          @ (text widget, 0xRRGGBB)
.equ SET_IMAGE, 0x28e24c19          @ (image widget, image index)
.equ FS_FUNCTIONS, 0x28128a74       @ each footswitch's function, two bytes apart: 1 is TAP
.equ LABEL_TOP, 0x64                @ in the Home view: footswitch k's label lines, text widgets 0x30 bytes apart
.equ LABEL_BOTTOM, 0xf4
.equ ICON, 0x3f4                    @ footswitch k's switch icon, image widgets 0x24 bytes apart
.equ ON_SCREEN, 3                   @ footswitches 4 and 5 are the external pair, with no label
.equ COLOURS, 10
.equ RAINBOW, 10                    @ then Random: the values that change colour at each beat
.equ RANDOM, 11
.equ OFF, 12                        @ no blink: the stock Tap Tempo LED Off; the labels keep the stock red
.equ TAP_TEMPO_LED, 26              @ a bool: record type 1, as the stock knob writes it (source 1)
.equ UNSEEN, 0xff

.thumb_func
.global tap_led
tap_led:                            @ the stock beat's colour call (led, its red): the TAP ring in our colour, Rainbow and Random's next
    push {r4, lr}
    mov r4, r0
    bl tap_setting
.if TAP_OFF_BLACK
    cmp r0, #OFF
    beq tap_led_off
.endif
    cmp r0, #RAINBOW
    beq tap_led_rainbow
    cmp r0, #RANDOM
    it eq
    bleq tap_random
tap_led_palette:
    adr.w r1, tap_texts
    ldr.w r2, [r1, r0, lsl #2]
    adr.w r1, tap_leds
    ldr.w r1, [r1, r0, lsl #2]
tap_led_send:                       @ r1 the ring's colour, r2 the same as the label's palette has it
    adr.w r3, tap_now
    str r2, [r3]
    adr.w r3, tap_ring
    str r1, [r3]
    mov r0, r4
    pop {r4, lr}
    ldr r3, =LED_COLOUR
    bx r3
tap_led_rainbow:
    adr.w r3, tap_step
    ldr r0, [r3]
    adds r0, #1
    cmp r0, #STEPS
    it hs
    movhs r0, #0
    str r0, [r3]
    adr.w r1, tap_rainbow_texts
    ldr.w r2, [r1, r0, lsl #2]
    adr.w r1, tap_rainbow_leds
    ldr.w r1, [r1, r0, lsl #2]
    b tap_led_send

.thumb_func
.global tap_led_again
tap_led_again:                      @ the other stock call that lights the TAP ring, outside the beat: Rainbow and Random keep their colour
    push {r4, lr}
    mov r4, r0
    bl tap_setting
.if TAP_OFF_BLACK
    cmp r0, #OFF
    beq tap_led_off
.endif
    cmp r0, #RAINBOW
    blo tap_led_palette
    adr.w r1, tap_ring
    ldr r1, [r1]
    adr.w r2, tap_now
    ldr r2, [r2]
    b tap_led_send

.if TAP_OFF_BLACK
tap_led_off:
    movs r1, #0
    ldr r2, =0xff0000
    b tap_led_send
.endif

tap_random:                         @ -> r0 a colour of the palette, never the last one: xorshift32, seeded from the µs clock
    push {r4, lr}
    adr.w r4, tap_seed
    ldr r0, [r4]
    cbnz r0, 1f
    ldr r3, =CLOCK
    blx r3
    orr r0, r0, #1                  @ xorshift sticks at 0
1:  eor r0, r0, r0, lsl #13
    eor r0, r0, r0, lsr #17
    eor r0, r0, r0, lsl #5
    str r0, [r4]
    movs r1, #COLOURS - 1
    udiv r2, r0, r1
    mls r0, r2, r1, r0              @ 0..8, then past the last one: each other colour as likely
    ldrb r1, [r4, #4]
    cmp r0, r1
    it hs
    addhs r0, #1
    strb r0, [r4, #4]
    pop {r4, pc}

.thumb_func
.global tap_text
tap_text:                           @ the Home label's TAP case, setColor (widget, red) of either line
    push {r0, lr}
    adr.w r0, tap_texts
    bl tap_pick
    mov r1, r0
    pop {r0, lr}
    ldr r3, =SET_COLOR
    bx r3

.thumb_func
.global tap_icon
tap_icon:                           @ the Home label's TAP case, setImage (widget, Icon_SwitchRed)
    push {r0, lr}
    adr.w r0, tap_icons
    bl tap_pick
    mov r1, r0
    pop {r0, lr}
    ldr r3, =SET_IMAGE
    bx r3

.thumb_func
.global tap_paint
tap_paint:                          @ before the Home paint (framebuffer, Home view): a changed setting recolours the TAP labels shown
    push {r4-r8, lr}
    mov r4, r1
    bl tap_sync
    bl tap_setting
    cmp r0, #RAINBOW                @ Rainbow's and Random's tap_now follows the ring
    bhs 1f
    adr.w r1, tap_texts
    ldr.w r1, [r1, r0, lsl #2]
    adr.w r2, tap_now
    str r1, [r2]
1:  adr.w r1, tap_shown
    ldrb r2, [r1]
    cmp r2, r0
    beq tap_paint_done
    strb r0, [r1]                   @ a rebuild already takes the setting; this catches a change made in Global Settings
    adr.w r1, tap_texts
    ldr.w r6, [r1, r0, lsl #2]
    adr.w r1, tap_icons
    ldr.w r7, [r1, r0, lsl #2]
    movs r5, #0
tap_paint_each:
    ldr r0, =FS_FUNCTIONS
    ldrb.w r0, [r0, r5, lsl #1]
    cmp r0, #1
    bne tap_paint_next
    movs r0, #0x30
    mul r8, r5, r0
    add r8, r4
    add.w r0, r8, #LABEL_TOP
    mov r1, r6
    ldr r3, =SET_COLOR
    blx r3
    add.w r0, r8, #LABEL_BOTTOM
    mov r1, r6
    ldr r3, =SET_COLOR
    blx r3
    movs r0, #0x24
    mul r0, r5, r0
    add r0, r4
    add.w r0, r0, #ICON
    mov r1, r7
    ldr r3, =SET_IMAGE
    blx r3
tap_paint_next:
    adds r5, #1
    cmp r5, #ON_SCREEN
    bne tap_paint_each
tap_paint_done:
    pop {r4-r8, pc}

tap_pick:                           @ (r0 a table) -> r0 its word for the setting's colour
    push {r4, lr}
    mov r4, r0
    bl tap_setting
    ldr.w r0, [r4, r0, lsl #2]
    pop {r4, pc}

tap_setting:                        @ -> r0 Tap LED Color; Stomp labels and stray ring turns treat Off as Red
    push {r4, lr}
    bl tap_raw
.if !TAP_OFF_BLACK
    cmp r0, #OFF
    it eq
    moveq r0, #0
.endif
    pop {r4, pc}

tap_raw:                            @ -> r0 Tap LED Color as stored, Off included
    movs r0, #SETTING_TAP_COLOR_COLOR
    movs r1, #SETTING_TAP_COLOR_COLOR_MAX
    movs r2, #SETTING_TAP_COLOR_COLOR_DEFAULT
    b hxtra_setting_get

.thumb_func
.global tap_changed
tap_changed:                        @ after Global Settings' repaint of a changed slot (view, ID): a turn of Tap LED Color, at once
    cmp r1, #SETTING_TAP_COLOR_COLOR
    it ne
    bxne lr
    b tap_sync

.thumb_func
.global tap_sync_page
tap_sync_page:                      @ after Global Settings' page repaint (view), as after a click's reset to the default
    b tap_sync

tap_sync:                           @ the stock Tap Tempo LED, hidden, kept in step: Off when Tap LED Color is Off, else On. A change of
    push {r4, r5, r6, lr}           @ Tap LED Color sets it; otherwise it sets Tap LED Color (the first paint, and a change from HX Edit)
    sub sp, #8
    bl tap_raw
    mov r4, r0
    movs r0, #TAP_TEMPO_LED
    mov r1, sp
    ldr r3, =GET_VALUE
    blx r3
    cmp r0, #0
    blt tap_sync_done               @ no value: nothing to keep in step
    ldr r5, [sp, #4]
    cmp r5, #0
    it ne
    movne r5, #1
    adr.w r6, tap_seen
    ldrb r0, [r6]
    cmp r0, r4
    beq tap_sync_led
    cmp r0, #UNSEEN
    beq tap_sync_led
    subs r1, r4, #OFF               @ Tap LED Color changed: Tap Tempo LED follows it
    it ne
    movne r1, #1
    cmp r1, r5
    beq tap_sync_seen
    bl tap_set_led
    b tap_sync_seen
tap_sync_led:                       @ Tap Tempo LED decides: Off is Off, On with Off picks the default colour
    cmp r5, #0
    bne 1f
    cmp r4, #OFF
    beq tap_sync_seen
    movs r4, #OFF
    b 2f
1:  cmp r4, #OFF
    bne tap_sync_seen
    movs r4, #SETTING_TAP_COLOR_COLOR_DEFAULT
2:  movs r0, #SETTING_TAP_COLOR_COLOR
    mov r1, r4
    bl hxtra_setting_set
tap_sync_seen:
    strb r4, [r6]
tap_sync_done:
    add sp, #8
    pop {r4, r5, r6, pc}

tap_set_led:                        @ (-, r1 0 or 1): the stock Tap Tempo LED, written as its knob writes it
    push {r4, lr}
    sub sp, #8
    movs r2, #1
    strd r2, r1, [sp]
    ldr r3, =SETTER_CONTEXT
    blx r3
    movs r1, #TAP_TEMPO_LED
    mov r2, sp
    movs r3, #1
    ldr r12, =SETTER
    blx r12
    add sp, #8
    pop {r4, pc}

HXTRA_SETTING_GET
HXTRA_SETTING_SET
.ltorg
.balign 4
@ The stock palette, by Color: Red, Dk Orange, Lt Orange, Yellow, Green, Turquoise, Blue, Violet, Pink, White; Rainbow's and Random's labels are White's
tap_leds:                           @ the LED driver's lit colours (0x28dd8030)
    .word 0x0300ff, 0x002dff, 0x00afd0, 0x00ff84, 0x00ff06, 0x80ff00, 0xff3200, 0xff0032, 0x2800ff, 0xceff6b
tap_texts:                          @ the block categories' label colours (0x28e2815c), White their gray
    .word 0xff0000, 0xff5a18, 0xf5911e, 0xead82f, 0x43ff40, 0x3cceb5, 0x0097e4, 0xb049db, 0xf12f91, 0xb1b1b1, 0xb1b1b1, 0xb1b1b1
tap_icons:                          @ Icon_SwitchRed .. Icon_SwitchWhite, as 0x28dc6e9c picks them for those colours
    .word 0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115, 0x115, 0x115
tap_rainbow_leds:
    RAINBOW_LEDS
tap_rainbow_texts:
    RAINBOW_TEXTS
tap_now:                            @ the colour shown (0xRRGGBB), as the label's palette has it
    .word 0xff0000
tap_ring:                           @ the ring's colour Rainbow or Random last lit
    .word 0x0300ff
tap_step:                           @ Rainbow's colour last lit: the first beat lights red
    .word STEPS - 1
tap_seed:                           @ the random state, then the last colour Random lit
    .word 0, 0
tap_shown:                          @ the setting the labels were last recoloured for; none yet
    .word 0xff
tap_seen:                           @ Tap LED Color as tap_sync last kept it in step; none yet
    .word UNSEEN
