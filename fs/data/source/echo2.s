  .org $ff00    ; Though written to the first address in the ROM, $0,
                ; this code will appear to the CPU to be at $8000

CIN             = $d104
COUT            = $d101

reset:          ; This label marks the first position in the ROM for
                ; the CPU is $8000

    lda #'/'
    jsr CHROUT
    lda #$0D
    jsr CHROUT
    lda #$0A
    jsr CHROUT

getkey:
    jsr CHRIN
    cmp #$00
    beq getkey
    cmp #$0d
    bne getkey
    lda #$0a
    jsr CHROUT
    jmp getkey

; Input a character from the serial interface.
; On return, carry flag indicates whether a key was pressed
; If a key was pressed, the key value will be in the A register
;
; Modifies: flags, A
MONRDKEY:
CHRIN:
                phx
                LDA CIN
                beq     no_keypressed
                jsr     CHROUT                  ; echo
                pha
mostly_full:
                pla
                plx
                rts
no_keypressed:
                plx
                rts


; Output a character (from the A register) to the serial interface.
;
; Modifies: flags
MONCOUT:
CHROUT:
                pha
                sta COUT
                pla
                rts

WRITE_BUFFER:
                rts

; Read a character from the circular input buffer and put it in the A register
; Modifies: flags, A, X
READ_BUFFER:
                rts

; Return (in A) the number of unread bytes in the circular input buffer
; Modifies: flags, A
BUFFER_SIZE:
                rts


; Interrupt request handler
IRQ_HANDLER:
                rti

    .org $fffc   ; Specify that the following code will go at the position
               ; that appears to the CPU to be at $fffc. $fffc is the
               ; location of the reset vector. The value at this vector
               ; is loaded into the program counter after a CPU reset.

    .word reset  ; Place the value of the label reset, ie $8000, at this
               ; position

    .word $0000  ; Pad out the last couple bytes
