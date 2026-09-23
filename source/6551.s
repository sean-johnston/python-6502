; set the 6551 register addresses
 
A_RXD           = $F000 ; ACIA receive data port
A_TXD           = $F000 ; ACIA transmit data port
A_STS           = $F001 ; ACIA status port
A_RES           = $F001 ; ACIA reset port
A_CMD           = $F002 ; ACIA command port
A_CTL           = $F003 ; ACIA control port

    *= $ff00

START       JSR INIT_6551
            LDX #$00
LOOP1       LDA BANNER, X
            BEQ LOOP
            JSR CHROUT
            INX
            JMP LOOP1
LOOP        JSR CHRIN
            JSR CHROUT
            JMP LOOP
 
; initialise 6551 ACIA
 
INIT_6551   STA A_RES       ; soft reset (value not important)
            LDA #$0B        ; set specific modes and functions
                            ; no parity, no echo, no Tx interrupt
                            ; no Rx interrupt, enable Tx/Rx
            STA A_CMD       ; save to command register
                            ; all the following 8-N-1 with the baud rate
                            ; generator selected. uncomment the line with
                            ; the required baud rate.
;           LDA #$1A        ; 8-N-1, 2400 baud
;           LDA #$1C        ; 8-N-1, 4800 baud
            LDA #$1E        ; 8-N-1, 9600 baud
;           LDA #$1F        ; 8-N-1, 19200 baud
            STA A_CTL       ; set control register
            RTS

CHROUT      CMP #13
            BNE CHROUT1
            JSR PUTCHR
            LDA #10
CHROUT1     JSR PUTCHR
            RTS

; wait for ACIA and Tx byte
 
PUTCHR      PHA         ; save A
WAIT_TX
            LDA A_STS       ; get status byte
            AND #$10        ; mask transmit buffer status flag
            BEQ WAIT_TX     ; loop if tx buffer full
 
            PLA             ; restore A
            STA A_TXD       ; save byte to ACIA data port
            RTS

; wait for ACIA and Rx byte

CHRIN 
WAIT_RX
            LDA A_STS       ; get ACIA status
            AND #$08        ; mask rx buffer status flag
            BEQ WAIT_RX     ; loop if rx buffer empty
 
            LDA A_RXD       ; get byte from ACIA data port
            RTS

BANNER		.byte	"6551 Echo - Type and it will be echoed"
            .byte   0x0d, 0x00

    .org $fffc  ; Specify that the following code will go at the position
                ; that appears to the CPU to be at $fffc. $fffc is the
                ; location of the reset vector. The value at this vector
                ; is loaded into the program counter after a CPU reset.

    .word START ; Place the value of the label reset, ie $8000, at this
                ; position

    .word $0000 ; Pad out the last couple bytes
