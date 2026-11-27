@ metronome.s - the Metronome block, listed under Volume/Pan: kept off the toe switch's FS5 that a Volume/Pan block gets when added,
@ and Volume's teal for its footswitch, whose block category, Metronome, has none.
.syntax unified
.thumb
.equ PRESET_ID, 181                 @ tools/patch_click.py PRESET_ID
.equ PLAIN, 5                       @ Modulation, the Tremolo it is copied from: outside the add switch's 8..0x11
.equ BLOCK_CATEGORY, 0x28e0f065     @ (model, preset ID, &category) -> <0 on error; 0x19 for a model without Entry 3's category
.equ VOLUME, 0x0e                   @ Volume's block category, teal like the Metronome's
.equ METRONOME, 0x19                @ the Metronome's block category: tools/features/metronome.py METRONOME

metronome_add_cat:                  @ at 0x28d952d0, for ldrb.w r3, [sp, #0x28]: the block info at sp+0x1c has its preset ID at +1
    ldr.w r3, [sp, #0x1d]
    cmp r3, #PRESET_ID              @ the site's next instruction, subs r3, #8, sets the flags again
    ldrb.w r3, [sp, #0x28]
    it eq
    moveq r3, #PLAIN
    bx lr

@ The footswitch assign clears a block of category None or Unknown (0x18, 0x19) instead, and the Metronome's block category is 0x19.
metronome_assign_cat:               @ in place of its call of BLOCK_CATEGORY at 0x28dd84d8
    push {r1, r2, r4, lr}
    ldr r4, =BLOCK_CATEGORY
    blx r4
    pop {r1, r2}
    cmp r1, #PRESET_ID
    itt eq
    moveq r1, #VOLUME
    strbeq r1, [r2]
    pop {r4, pc}

@ Its footswitch's LED would be white at every other call, preset load among them: the colour lookup has no colour for 0x19.
metronome_led_colour:               @ owns the colour lookup (r0 block category, r1 on); r12 its stock code
    cmp r0, #METRONOME
    it eq
    moveq r0, #VOLUME
    bx r12
