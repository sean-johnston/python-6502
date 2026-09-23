    org $8000

; Define a zero-page variable
flags = $10 

main:
    ; If bit 0 of 'flags' ($10) is set, branch to bit_is_one
    bbs0 flags, bit_is_one

bit_is_zero:
    ; Code continues here if bit 0 is 0
    nop
    rts

bit_is_one:
    ; Code jumps here if bit 0 is 1
    rts
