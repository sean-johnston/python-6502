import math

class Memory:
    def __init__(self, pc=0):
        self.mem = []

    #def add_registers(start_address, length, func):

    #def add_memory(start, length):
    #   mem.append(bytearray(65536) # 64K of memory)

    def read(self, address):
        return self.mem[address]

    def write(self, address, value):
        self.mem[address] = value

    def readWord(self, addr):
        return (self.read(addr+1) << 8) + self.read(addr)

class Registers:
    """ An object to hold the CPU registers. """
    def __init__(self, pc=0):
        self.reset(pc)

    def reset(self, pc=0):
        self.a = 0          # Accumulator
        self.x = 0          # General Purpose X
        self.y = 0          # General Purpose Y
        self.s = 0xff       # Stack Pointer
        self.pc = pc        # Program Counter

        self.flagBit = {
            'N': 128,   # N - Negative
            'V': 64,    # V - Overflow
            'B': 16,    # B - Break Command
            'D': 8,     # D - Decimal Mode
            'I': 4,     # I - IRQ Disable
            'Z': 2,     # Z - Zero
            'C': 1      # C - Carry
        }
        self.p = 0b00100100  # Flag Pointer - N|V|1|B|D|I|Z|C

    def getFlag(self, flag):
        return bool(self.p & self.flagBit[flag])

    def setFlag(self, flag, v=True):
        if v:
            self.p = self.p | self.flagBit[flag]
        else:
            self.clearFlag(flag)

    def clearFlag(self, flag):
        self.p = self.p & (255 - self.flagBit[flag])

    def clearFlags(self):
        self.p = 0

    def ZN(self, v):
        """
        The criteria for Z and N flags are standard.  Z gets set if the
        value is zero and N gets set to the same value as bit 7 of the value.
        """
        self.setFlag('Z', v == 0)
        self.setFlag('N', v & 0x80)

    def __repr__(self):
        return "A: %02x X: %02x Y: %02x S: %02x PC: %04x P: %s" % (
            self.a, self.x, self.y, self.s, self.pc, bin(self.p)[2:].zfill(8)
        )

class CPU:
    def __init__(self, mmu=None, pc=None, stack_page=0x1, magic=0xee):
        """
        Parameters
        ----------
        mmu: An instance of MMU
        pc: The starting address of the pc (program counter)
        stack_page: The index of the page which contains the stack.  The default for
            a 6502 is page 1 (the stack from 0x0100-0x1ff) but in some varients the
            stack page may be elsewhere.
        magic: A value needed for the illegal opcodes, XAA.  This value differs
            between different versions, even of the same CPU.  The default is 0xee.
        """
        self.mmu = mmu
        self.r = Registers()
        # Hold the number of CPU cycles used during the last call to `self.step()`
        self.cc = 0
        # Which page the stack is in.  0x1 means that the stack is from
        # 0x100-0x1ff.  In the 6502 this is always true but it's different
        # for other 65* varients.
        self.stack_page = stack_page
        self.magic = magic

        self.P6502 = 0
        self.P65c02 = 1
        self.processor_type = self.P65c02

        if pc:
            self.r.pc = pc
        else:
            # if pc is none get the address from $FFFD,$FFFC
            self.reset()
            pass

        #self._create_ops()
        self.assign_opcodes()
        pass

    def reset(self):
        pc = (self.mmu.read(0xfffd) << 8) + self.mmu.read(0xfffc)
        self.r.reset(pc)
        self.mmu.reset()

        self.running = True

    def step(self):
        self.cc = 0
        opcode = self.nextByte()
        fn = self.opcodes_setup[opcode][self.device[self.processor_type][opcode]]
        v = fn[2]()
        if fn[5] is None:
            fn[3](v)
        elif isinstance(fn[5], str) and fn[5][0] == "*":
            fn[3](v, fn[5])
        else:
            fn[3](fn[5])

    def nextByte(self):
        v = self.mmu.read(self.r.pc)
        self.r.pc += 1
        return v

    def nextWord(self):
        low = self.nextByte()
        high = self.nextByte()
        return (high << 8) + low

    def stackPush(self, v):
        self.mmu.write(self.stack_page*0x100 + self.r.s, v)
        self.r.s = (self.r.s - 1) & 0xff

    def stackPushWord(self, v):
        self.stackPush(v >> 8)
        self.stackPush(v & 0xff)

    def stackPop(self):
        v = self.mmu.read(self.stack_page*0x100 + ((self.r.s + 1) & 0xff))
        self.r.s = (self.r.s + 1) & 0xff
        return v

    def stackPopWord(self):
        return self.stackPop() + (self.stackPop() << 8)

    def fromBCD(self, v):
        return (((v & 0xf0) // 0x10) * 10) + (v & 0xf)

    def toBCD(self, v):
        return int(math.floor(v/10))*16 + (v % 10)

    def fromTwosCom(self, v):
        return (v & 0x7f) - (v & 0x80)

    interrupts = {
        "ABORT":    0xfff8,
        "COP":      0xfff4,
        "IRQ":      0xfffe,
        "BRK":      0xfffe,
        "NMI":      0xfffa,
        "RESET":    0xfffc
    }

    def interruptAddress(self, i):
        return self.mmu.readWord(self.interrupts[i])

    # Addressing modes
    def z_a(self):
        return self.nextByte()

    def zx_a(self):
        return (self.nextByte() + self.r.x) & 0xff

    def zy_a(self):
        return (self.nextByte() + self.r.y) & 0xff

    def a_a(self):
        return self.nextWord()

    def ax_a(self):
        o = self.nextWord()
        a = o + self.r.x
        if math.floor(o/0xff) != math.floor(a/0xff):
            self.cc += 1

        return a & 0xffff

    def ay_a(self):
        o = self.nextWord()
        a = o + self.r.y
        if math.floor(o/0xff) != math.floor(a/0xff):
            self.cc += 1

        return a & 0xffff

    def i_a(self):
        """Only used by indirect JMP"""
        i = self.nextWord()
        # Doesn't carry, so if the low byte is in the XXFF position
        # Then the high byte will be XX00 rather than XY00
        if i & 0xff == 0xff:
            j = i - 0xff
        else:
            j = i + 1

        return ((self.mmu.read(j) << 8) + self.mmu.read(i)) & 0xffff

    def ix_a(self):
        i = (self.nextByte() + self.r.x) & 0xff
        return ((self.mmu.read((i + 1) & 0xff) << 8) + self.mmu.read(i)) & 0xffff

    def iy_a(self):
        i = self.nextByte()
        o = (self.mmu.read((i + 1) & 0xff) << 8) + self.mmu.read(i)
        a = o + self.r.y

        if math.floor(o/0xff) != math.floor(a/0xff):
            self.cc += 1

        return a & 0xffff

    def iz_a(self):
        i = self.nextByte()
        o = (self.mmu.read((i + 1) & 0xff) << 8) + self.mmu.read(i)
        a = o # + self.r.y

        if math.floor(o/0xff) != math.floor(a/0xff):
            self.cc += 1

        return a & 0xffff

    # Return values based on the addressing mode
    def imp(self): # Implied
        return self.nextByte()

    def imm(self): # Immediate
        return 0

    def z(self): # Zero Page
        return self.mmu.read(self.z_a())

    def zx(self): # Zero Page X
        return self.mmu.read(self.zx_a())

    def zy(self): # Zero Page Y
        return self.mmu.read(self.zy_a())

    def a(self): # Absolute
        return self.mmu.read(self.a_a())

    def ax(self): # Absolute X
        return self.mmu.read(self.ax_a())

    def ay(self): # Absolute Y
        return self.mmu.read(self.ay_a())

    def i(self): # Indexed
        return self.mmu.read(self.i_a())

    def ix(self): # Indexed X
        return self.mmu.read(self.ix_a())

    def iy(self): # Indexed Y
        return self.mmu.read(self.iy_a())

    def iz(self): # Indexed Zero
        return self.mmu.read(self.iz_a())

    def rl(self): # Relative
        return 0

    def AAC(self, v):
        pass

    def AAX(self, a):
        pass

    def ADC(self, v2):
        v1 = self.r.a

        if self.r.getFlag('D'):  # decimal mode
            d1 = self.fromBCD(v1)
            d2 = self.fromBCD(v2)
            r = d1 + d2 + self.r.getFlag('C')
            self.r.a = self.toBCD(r % 100)

            self.r.setFlag('C', r > 99)
        else:
            r = v1 + v2 + self.r.getFlag('C')
            self.r.a = r & 0xff

            self.r.setFlag('C', r > 0xff)

        self.r.ZN(self.r.a)
        self.r.setFlag('V', ((~(v1 ^ v2)) & (v1 ^ r) & 0x80))

    def AND(self, v):
        self.r.a = (self.r.a & v) & 0xff
        self.r.ZN(self.r.a)

    def ARR(self, v):
        pass

    def ASL(self, a):
        if a == 'a':
            v = self.r.a << 1
            self.r.a = v & 0xff
        else:
            v = self.mmu.read(a) << 1
            self.mmu.write(a, v)

        self.r.setFlag('C', v > 0xff)
        self.r.ZN(v & 0xff)

    def ASR(self, v):
        self.AND(v)
        self.LSR('a')

    def ATX(self, v):
        self.AND(v)
        self.T(('a', 'x'))

    def AXA(self, a):
        """
        There are a few illegal opcodes which and the high
        bit of the address with registers and write the values
        back into that address.  These operations are
        particularly screwy.  These posts are used as reference
        but I am unsure whether they are correct.
        - forums.nesdev.com/viewtopic.php?f=3&t=3831&start=30#p113343
        - forums.nesdev.com/viewtopic.php?f=3&t=10698
        """
        o = (a - self.r.y) & 0xffff
        low = o & 0xff
        high = o >> 8
        if low + self.r.y > 0xff:  # crossed page
            a = ((high & self.r.x) << 8) + low + self.r.y
        else:
            a = (high << 8) + low + self.r.y

        v = self.r.a & self.r.x & (high + 1)
        self.mmu.write(a, v)

    def AXS(self, v):
        o = self.r.a & self.r.x
        self.r.x = (o - v) & 0xff

        self.r.setFlag('C', v <= o)
        self.r.ZN(self.r.x)

    def BIT(self, v):
        self.r.setFlag('Z', self.r.a & v == 0)
        self.r.setFlag('N', v & 0x80)
        self.r.setFlag('V', v & 0x40)

    def br(self, v): # branch
        """
        v is a tuple of (flag, boolean).  For instance, BCC (Branch Carry Clear)
        will call B(('C', False)).
        """

        # Todo: Implement BRA (Branch always) instruction
        d = self.imp()
        if v[0] == "A": # Branch always
            o = self.r.pc
            self.r.pc += self.fromTwosCom(d)
            if math.floor(o/0xff) == math.floor(self.r.pc/0xff):
                self.cc += 1
            else:
                self.cc += 2
        else:
            if self.r.getFlag(v[0]) is v[1]:
                o = self.r.pc
                self.r.pc += self.fromTwosCom(d)
                if math.floor(o/0xff) == math.floor(self.r.pc/0xff):
                    self.cc += 1
                else:
                    self.cc += 2

    def BRK(self, _):
        self.r.setFlag('B')
        self.stackPushWord(self.r.pc+1)
        self.stackPush(self.r.p)
        self.r.setFlag('I')
        self.r.pc = self.interruptAddress('BRK')

    def BBR(self, a, v):
        d = self.imp()
        if self.mmu.read(a) & (2 ** int(v[1])) == 0:
                o = self.r.pc
                self.r.pc += self.fromTwosCom(d)
                if math.floor(o/0xff) == math.floor(self.r.pc/0xff):
                    self.cc += 1
                else:
                    self.cc += 2

    def BBS(self, a, v):
        d = self.imp()
        if self.mmu.read(a) & (2 ** int(v[1])) != 0:
            o = self.r.pc
            self.r.pc += self.fromTwosCom(d)
            if math.floor(o/0xff) == math.floor(self.r.pc/0xff):
                self.cc += 1
            else:
                self.cc += 2

    def clr(self, v):
        """Clear the flag to False."""
        self.r.clearFlag(v)

    def CP(self, r, v):
        o = (r-v) & 0xff
        self.r.setFlag('Z', o == 0)
        self.r.setFlag('C', v <= r)
        self.r.setFlag('N', o & 0x80)

    def CMP(self, v):
        self.CP(self.r.a, v)

    def CPX(self, v):
        self.CP(self.r.x, v)

    def CPY(self, v):
        self.CP(self.r.y, v)

    def DCP(self, a):
        self.DEC(a)
        self.CMP(self.mmu.read(a))

    def DEA(self, _):
        self.r.a = (self.r.a-1) & 0xff
        self.r.ZN(self.r.a)

    def DEC(self, a):
        v = (self.mmu.read(a)-1) & 0xff
        self.mmu.write(a, v)
        self.r.ZN(v)

    def DEX(self, _):
        self.r.x = (self.r.x-1) & 0xff
        self.r.ZN(self.r.x)

    def DEY(self, _):
        self.r.y = (self.r.y-1) & 0xff
        self.r.ZN(self.r.y)

    def EOR(self, v):
        self.r.a = self.r.a ^ v
        self.r.ZN(self.r.a)

    def INC(self, a):
        v = (self.mmu.read(a)+1) & 0xff
        self.mmu.write(a, v)
        self.r.ZN(v)

    def INX(self, _):
        self.r.x = (self.r.x+1) & 0xff
        self.r.ZN(self.r.x)

    def INY(self, _):
        self.r.y = (self.r.y+1) & 0xff
        self.r.ZN(self.r.y)

    def INA(self, _):
        self.r.a = (self.r.a+1) & 0xff
        self.r.ZN(self.r.a)

    def ISC(self, a):
        self.INC(a)
        self.SBC(self.mmu.read(a))

    def JMP(self, a):
        self.r.pc = a

    def JSR(self, a):
        self.stackPushWord(self.r.pc-1)
        self.r.pc = a

    def KIL(self, v):
        self.running = False

    def LAX(self, v):
        self.r.a = self.r.x = v
        self.r.ZN(self.r.a)

    def LAR(self, v):
        self.r.a = self.r.x = self.r.s = self.r.s & v
        self.r.ZN(self.r.a)

    def LDA(self, v):
        self.r.a = v
        self.r.ZN(self.r.a)

    def LDX(self, v):
        self.r.x = v
        self.r.ZN(self.r.x)

    def LDY(self, v):
        self.r.y = v
        self.r.ZN(self.r.y)

    def LSR(self, a):
        if a == 'a':
            self.r.setFlag('C', self.r.a & 0x01)
            self.r.a = v = self.r.a >> 1
        else:
            v = self.mmu.read(a)
            self.r.setFlag('C', v & 0x01)
            v = v >> 1
            self.mmu.write(a, v)

        self.r.ZN(v)

    def NOP(self, _):
        pass

    def ORA(self, v):
        self.r.a = self.r.a | v
        self.r.ZN(self.r.a)

    def RMB(self, a, v):
        # Unset bit in memory value
        self.mmu.write(a, self.mmu.read(a) & (255-(2 ** int(v[1]))))

    def SMB(self, a, v):
        # Set bit in memory value
        self.mmu.write(a, self.mmu.read(a) | (2 ** int(v[1])))

    def ROL(self, a):
        if a == "a":
            v_old = self.r.a
            self.r.a = v_new = ((v_old << 1) + self.r.getFlag('C')) & 0xff
        else:
            v_old = self.mmu.read(a)
            v_new = ((v_old << 1) + self.r.getFlag('C')) & 0xff
            self.mmu.write(a, v_new)

        self.r.setFlag('C', v_old & 0x80)
        self.r.ZN(v_new)

    def ROR(self, a):
        if a == "a":
            v_old = self.r.a
            self.r.a = v_new = ((v_old >> 1) + self.r.getFlag('C')*0x80) & 0xff
        else:
            v_old = self.mmu.read(a)
            v_new = ((v_old >> 1) + self.r.getFlag('C')*0x80) & 0xff
            self.mmu.write(a, v_new)

        self.r.setFlag('C', v_old & 0x01)
        self.r.ZN(v_new)

    def RLA(self, a):
        self.ROL(a)
        self.AND(self.mmu.read(a))

    def RRA(self, a):
        self.ROR(a)
        self.ADC(self.mmu.read(a))

    def RTI(self, _):
        self.r.p = self.stackPop()
        self.r.pc = self.stackPopWord()

    def RTS(self, _):
        self.r.pc = (self.stackPopWord() + 1) & 0xffff

    def set(self, v):
        """Set the flag to True."""
        self.r.setFlag(v)

    def stk(self, v): #stack
        """
        Stack operations, PusH and PulL.  v is a tuple where the
        first value is either PH or PL, specifying the action and
        the second is the source or target register, either A or P,
        meaning the Accumulator or the Processor status flag.
        """
        a, r = v

        if a == "H":
            self.stackPush(getattr(self.r, r))
        else:
            setattr(self.r, r, self.stackPop())

            if r == "a":
                self.r.ZN(self.r.a)
            if r == "y":
                self.r.ZN(self.r.y)
            elif r == "x":
                self.r.ZN(self.r.x)
            elif r == "p":
                self.r.p = self.r.p | 0b00100000

    def SBC(self, v2):
        v1 = self.r.a
        if self.r.getFlag('D'):
            d1 = self.fromBCD(v1)
            d2 = self.fromBCD(v2)
            r = d1 - d2 - (not self.r.getFlag('C'))
            self.r.a = self.toBCD(r % 100)
        else:
            r = v1 - v2 - (not self.r.getFlag('C'))
            self.r.a = r & 0xff

        self.r.setFlag('C', r >= 0)
        self.r.setFlag('V', ((v1 ^ v2) & (v1 ^ r) & 0x80))
        self.r.ZN(self.r.a)

    def SLO(self, a):
        self.ASL(a)
        self.ORA(self.mmu.read(a))

    def STA(self, a):
        self.mmu.write(a, self.r.a)

    def STX(self, a):
        self.mmu.write(a, self.r.x)

    def STY(self, a):
        self.mmu.write(a, self.r.y)

    def STZ(self, a):
        self.mmu.write(a, 0)

    def tfr(self, a):
        """
        Transfer registers
        a is a tuple with (source, destination) so TAX
        would be T(('a', 'x'))self.
        """
        s, d = a
        setattr(self.r, d, getattr(self.r, s))
        if d != 's':
            self.r.ZN(getattr(self.r, d))

    def TRB(self, a):
        value = self.mmu.read(a)
        self.r.clearFlags()
        self.r.setFlag('Z', True)
        t = ~self.r.a & value 
        self.mmu.write(a,t)
        self.r.setFlag('Z', self.r.a & value == 0)

    def TSB(self, a):
        value = self.mmu.read(a)
        self.r.clearFlags()
        self.r.setFlag('Z', True)
        self.mmu.write(a, self.r.a | value)
        self.r.setFlag('Z', self.r.a & value == 0)

    def SRE(self, a):
        self.LSR(a)
        self.EOR(self.mmu.read(a))
    
    def XAA(self, v):  # ANE
        """
        Another very wonky operation.  It's fully described here:
        http://visual6502.org/wiki/index.php?title=6502_Opcode_8B_%28XAA,_ANE%29
        "magic" varies by version of the processor.  0xee seems to be common.
        The formula is: A = (A | magic) & X & imm
        """
        self.r.a = (self.r.a | self.magic) & self.r.x & v
        self.r.ZN(self.r.a)

    def XAS(self, a):  # SHS, TAS
        # First set the stack pointer's value
        self.r.s = self.r.a & self.r.x

        # Then write to memory using the new value of the stack pointer
        o = (a - self.r.y) & 0xffff
        low = o & 0xff
        high = o >> 8
        if low + self.r.y > 0xff:  # crossed page
            a = ((high & self.r.s) << 8) + low + self.r.y
        else:
            a = (high << 8) + low + self.r.y

        v = self.r.s & (high + 1)
        self.mmu.write(a, v)

    def assign_opcodes(self):

        # Column 1 = Opcode
        # Column 2 = Type of Value
        # Column 3 = Address Mode Function
        # Column 4 = Opcode Function
        # Column 5 = Number of Cycles
        # Column 6 = Extra Data

        self.opcodes_setup = (
            (("BRK", "v", self.imm,  self.BRK, 7, 1),None),            # 0x00
            (("ORA", "v", self.ix,   self.ORA, 6, None),None),         # 0x01
            (("KIL", "v", self.imp,  self.KIL, 0, 1),None),            # 0x02
            (("SLO", "a", self.ix_a, self.SLO, 8, None),None),         # 0x03
            (
                ("TSB", "a", self.z_a,  self.TSB, 5, None),
                ("TSB", "a", self.z_a,  self.TSB, 5, None)
            ),                                                         # 0x04 65C02 (NOP z)
            (("ORA", "v", self.z,    self.ORA, 3, None),None),         # 0x05
            (("ASL", "a", self.z_a,  self.ASL, 5, None),None),         # 0x06
            (
                ("SLO", "a", self.z_a,  self.SLO, 5, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*0")
            ),                                                         # 0x07 RMB0 65C02
            (("PHP", "a", self.imm,  self.stk, 3, ("H", "p")),None),   # 0x08
            (("ORA", "v", self.imp,  self.ORA, 2, None),None),         # 0x09
            (("ASL", "a", self.imm,  self.ASL, 2, "a"),None),          # 0x0a
            (("AAC", "v", self.imp,  self.AAC, 2, None),None),         # 0x0b
            (
                ("TSB", "a", self.a_a,  self.TSB, 6, None),
                ("TSB", "a", self.a_a,  self.TSB, 6, None)
            ),                                                         # 0x0c 65C02 (6502 NOP a)
            (("ORA", "v", self.a,    self.ORA, 4, None),None),         # 0x0d
            (("ASL", "a", self.a_a,  self.ASL, 6, None),None),         # 0x0e
            (
                ("SLO", "a", self.a_a,  self.SLO, 6, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*0"))
            ),                                                         # 0x0f BBR0 65C02

            (("BPL", "v", self.rl,   self.br,  2, ("N", False)),None), # 0x10
            (("ORA", "v", self.iy,   self.ORA, 5, None),None),         # 0x11
            (
                ("ORA", "v", self.iz,   self.ORA, 5, None),
                ("ORA", "v", self.iz,   self.ORA, 5, None)
            ),                                                         # 0x12 65C02 (KIL)
            (("SLO", "a", self.iy_a, self.SLO, 8, None),None),         # 0x13
            (
                ("TRB", "a", self.z_a,  self.TRB, 5, None),
                ("TRB", "a", self.z_a,  self.TRB, 5, None)
            ),                                                         # 0x14 65C02 (NOP zx)
            (("ORA", "v", self.zx,   self.ORA, 4, None),None),         # 0x15
            (("ASL", "a", self.zx_a, self.ASL, 6, None),None),         # 0x16
            (
                ("SLO", "a", self.zx_a, self.SLO, 6, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*1")
            ),                                                         # 0x17 RMB1 65C02
            (("CLC", "v", self.imm,  self.clr, 2, "C"),None),          # 0x18
            (("ORA", "v", self.ay,   self.ORA, 4, None),None),         # 0x19
            (
                ("INA", "a", self.imm,  self.INA, 2, 1),
                ("INA", "a", self.imm,  self.INA, 2, 1)
            ),                                                         # 0x1a 65C02 (NOP imp)
            (("SLO", "a", self.ay_a, self.SLO, 7, None),None),         # 0x1b
            (
                ("TRB", "a", self.a_a,  self.TRB, 6, None),
                ("TRB", "a", self.a_a,  self.TRB, 6, None)
            ),                                                         # 0x1c 65C02 (NOP ax)
            (("ORA", "v", self.ax,   self.ORA, 4, None),None),         # 0x1d
            (("ASL", "a", self.ax_a, self.ASL, 7, None),None),         # 0x1e
            (
                ("SLO", "a", self.ax_a, self.SLO, 7, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*1"))
            ),                                                         # 0x1f BBR1 65C02

            (("JSR", "a", self.a_a,  self.JSR, 6, None),None),         # 0x20
            (("AND", "v", self.ix,   self.AND, 6, None),None),         # 0x21
            (("KIL", "v", self.imp,  self.KIL, 0, 1),None),            # 0x22
            (("RLA", "a", self.ix_a, self.RLA, 8, None),None),         # 0x23
            (("BIT", "v", self.z,    self.BIT, 3, None),None),         # 0x24
            (("AND", "v", self.z,    self.AND, 3, None),None),         # 0x25
            (("ROL", "a", self.z_a,  self.ROL, 5, None),None),         # 0x26
            (
                ("RLA", "a", self.z_a,  self.RLA, 5, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*2")
            ),                                                         # 0x27 RMB2 65C02
            (("PLP", "a", self.imm,  self.stk, 4, ("L", "p")),None),   # 0x28
            (("AND", "v", self.imp,  self.AND, 2, None),None),         # 0x29
            (("ROL", "a", self.imm,  self.ROL, 2, "a"),None),          # 0x2a
            (("AAC", "v", self.imp,  self.AAC, 2, None),None),         # 0x2b
            (("BIT", "v", self.a,    self.BIT, 4, None),None),         # 0x2c
            (("AND", "v", self.a,    self.AND, 4, None),None),         # 0x2d
            (("ROL", "a", self.a_a,  self.ROL, 6, None),None),         # 0x2e
            (
                ("RLA", "a", self.a_a,  self.RLA, 6, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*2"))
            ),                                                         # 0x2f BBR2 65C02

            (("BMI", "v", self.rl,   self.br,  2, ("N", True)),None),  # 0x30
            (("AND", "v", self.iy,   self.AND, 5, None),None),         # 0x31
            (
                ("AND", "v", self.iz,   self.AND, 5, None),
                ("AND", "v", self.iz,   self.AND, 5, None)
            ),                                                         # 0x32 65C02 (KIL)
            (("RLA", "a", self.iy_a, self.RLA, 8, None),None),         # 0x33
            (
                ("BIT", "v", self.zx,   self.BIT, 4, None),
                ("BIT", "v", self.zx,   self.BIT, 4, None)
            ),                                                         # 0x34 65C02 (NOP zx)
            (("AND", "v", self.zx,   self.AND, 4, None),None),         # 0x35
            (("ROL", "a", self.zx_a, self.ROL, 6, None),None),         # 0x36
            (
                ("RLA", "a", self.zx_a, self.RLA, 6, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*3")
            ),                                                         # 0x37 RMB3 65C02
            (("SEC", "v", self.imm,  self.set, 2, "C"),None),          # 0x38
            (("AND", "v", self.ay,   self.AND, 4, None),None),         # 0x39
            (
                ("DEA", "a", self.imm,  self.DEA, 2, 1),
                ("DEA", "a", self.imm,  self.DEA, 2, 1)
            ),                                                         # 0x3a 65C02 (NOP imp)
            (("RLA", "a", self.ay_a, self.RLA, 7, None),None),         # 0x3b
            (
                ("BIT", "v", self.ax,   self.BIT, 4, None),
                ("BIT", "v", self.ax,   self.BIT, 4, None)
            ),                                                         # 0x3c 65C02 (NOP ax)
            (("AND", "v", self.ax,   self.AND, 4, None),None),         # 0x3d
            (("ROL", "a", self.ax_a, self.ROL, 7, None),None),         # 0x3e
            (
                ("RLA", "a", self.ax_a, self.RLA, 7, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*3"))
            ),                                                         # 0x3f BBR3 65C02

            (("RTI", "a", self.imm,  self.RTI, 6, 1),None),            # 0x40
            (("EOR", "v", self.ix,   self.EOR, 6, None),None),         # 0x41
            (("KIL", "v", self.imp,  self.KIL, 0, 1),None),            # 0x42
            (("SRE", "a", self.ix_a, self.SRE, 8, None),None),         # 0x43
            (("NOP", "v", self.z,    self.NOP, 3, None),None),         # 0x44
            (("EOR", "v", self.z,    self.EOR, 3, None),None),         # 0x45
            (("LSR", "a", self.z_a,  self.LSR, 5, None),None),         # 0x46
            (
                ("SRE", "a", self.z_a,  self.SRE, 5, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*4")
            ),                                                         # 0x47 RMB4 65C02
            (("PHA", "a", self.imm,  self.stk, 3, ("H", "a")),None),   # 0x48
            (("EOR", "v", self.imp,  self.EOR, 2, None),None),         # 0x49
            (("LSR", "a", self.imm,  self.LSR, 2, "a"),None),          # 0x4a
            (("ASR", "v", self.imp,  self.ASR, 2, None),None),         # 0x4b
            (("JMP", "a", self.a_a , self.JMP, 3, None),None),         # 0x4c
            (("EOR", "v", self.a,    self.EOR, 4, None),None),         # 0x4d
            (("LSR", "a", self.a_a,  self.LSR, 6, None),None),         # 0x4e
            (
                ("SRE", "a", self.a_a,  self.SRE, 6, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*4"))
            ),                                                         # 0x4f BBR4 65C02

            (("BVC", "v", self.rl,   self.br,  2, ("V", False)),None), # 0x50
            (("EOR", "v", self.iy,   self.EOR, 5, None),None),         # 0x51
            (
                ("EOR", "v", self.iz,   self.EOR, 5, None),
                ("EOR", "v", self.iz,   self.EOR, 5, None)
            ),                                                         # 0x52 65C02 (KIL)
            (("SRE", "a", self.iy_a, self.SRE, 8, None),None),         # 0x53
            (("NOP", "v", self.zx,   self.NOP, 4, None),None),         # 0x54
            (("EOR", "v", self.zx,   self.EOR, 4, None),None),         # 0x55
            (("LSR", "a", self.zx_a, self.LSR, 6, None),None),         # 0x56
            (
                ("SRE", "a", self.zx_a, self.SRE, 6, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*5")
            ),                                                         # 0x57 RMB5 65C02
            (("CLI", "v", self.imm,  self.clr, 2, "I"),None),          # 0x58
            (("EOR", "v", self.ay,   self.EOR, 4, None),None),         # 0x59
            (
                ("PHY", "a", self.imm,  self.stk, 3, ("H", "y")),
                ("PHY", "a", self.imm,  self.stk, 3, ("H", "y"))
            ),                                                         # 0x5a 65C02 (NOP imp)
            (("SRE", "a", self.ay_a, self.SRE, 7, None),None),         # 0x5b
            (("NOP", "v", self.ax,   self.NOP, 4, None),None),         # 0x5c
            (("EOR", "v", self.ax,   self.EOR, 4, None),None),         # 0x5d
            (("LSR", "a", self.ax_a, self.LSR, 7, None),None),         # 0x5e
            (
                ("SRE", "a", self.ax_a, self.SRE, 7, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*5"))
            ),                                                         # 0x5f BBR5 65C02

            (("RTS", "a", self.imm,  self.RTS, 6, 1),None),            # 0x60
            (("ADC", "v", self.ix,   self.ADC, 6, None),None),         # 0x61
            (("KIL", "v", self.imp,  self.KIL, 0, 1),None),            # 0x62
            (("RRA", "a", self.ix_a, self.RRA, 8, None),None),         # 0x63
            (
                ("STZ", "a", self.z_a,  self.STZ, 3, None),
                ("STZ", "a", self.z_a,  self.STZ, 3, None)
            ),                                                         # 0x64 65C02 (NOP zp)
            (("ADC", "v", self.z,    self.ADC, 3, None),None),         # 0x65
            (("ROR", "a", self.z_a,  self.ROR, 5, None),None),         # 0x66
            (
                ("RRA", "a", self.z_a,  self.RRA, 5, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*6")
            ),                                                         # 0x67 RMB6 65C02
            (("PLA", "a", self.imm,  self.stk, 4, ("L", "a")),None),   # 0x68
            (("ADC", "v", self.imp,  self.ADC, 2, None),None),         # 0x69
            (("ROR", "a", self.imm,  self.ROR, 2, "a"),None),          # 0x6a
            (("ARR", "v", self.imp,  self.ARR, 2, None),None),         # 0x6b
            (("JMP", "a", self.i_a , self.JMP, 5, None),None),         # 0x6c
            (("ADC", "v", self.a,    self.ADC, 4, None),None),         # 0x6d
            (("ROR", "a", self.a_a,  self.ROR, 6, None),None),         # 0x6e
            (
                ("RRA", "a", self.a_a,  self.RRA, 6, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*6"))
            ),                                                         # 0x6f BBR6 65C02

            (("BVS", "v", self.rl,   self.br,  2, ("V", True)),None),  # 0x70
            (("ADC", "v", self.iy,   self.ADC, 5, None),None),         # 0x71
            (
                ("ADC", "v", self.iz,   self.ADC, 5, None),
                ("ADC", "v", self.iz,   self.ADC, 5, None)
            ),                                                         # 0x72 65C02 (KIL)
            (("RRA", "a", self.iy_a, self.RRA, 8, None),None),         # 0x73
            (
                ("STZ", "a", self.zx_a, self.STZ, 4, None),
                ("STZ", "a", self.zx_a, self.STZ, 4, None)
            ),                                                         # 0x74 65C02 (NOP zx)
            (("ADC", "v", self.zx,   self.ADC, 4, None),None),         # 0x75
            (("ROR", "a", self.zx_a, self.ROR, 6, None),None),         # 0x76
            (
                ("RRA", "a", self.zx_a, self.RRA, 6, None),
                ("RMB","a", self.z_a,  self.RMB, 5, "*7")
            ),                                                         # 0x77 RMB7 65C02
            (("SEI", "v", self.imm,  self.set, 2, "I"),None),          # 0x78
            (("ADC", "v", self.ay,   self.ADC, 4, None),None),         # 0x79
            (
                ("PLY", "a", self.imm,  self.stk, 4, ("L", "y")),
                ("PLY", "a", self.imm,  self.stk, 4, ("L", "y"))
            ),                                                         # 0x7a 65C02 (NOP imp)
            (("RRA", "a", self.ay_a, self.RRA, 7, None),None),         # 0x7b
            (("JMP", "a", self.ax_a, self.JMP, 4, None),None),         # 0x7c
            (("ADC", "v", self.ax,   self.ADC, 4, None),None),         # 0x7d
            (("ROR", "a", self.ax_a, self.ROR, 7, None),None),         # 0x7e
            (
                ("RRA", "a", self.ax_a, self.RRA, 7, None),
                ("BBR", "a", self.z,  self.BBR, 6, ("*7"))
            ),                                                         # 0x7f BBR7 65C02

            (
                ("BRA", "v", self.rl,   self.br,  3, ("A", False)),
                ("BRA", "v", self.rl,   self.br,  3, ("A", False))
            ),                                                         # 0x80 65C02 (NOP imm)
            (("STA", "a", self.ix_a, self.STA, 6, None),None),         # 0x81
            (("NOP", "v", self.imm,  self.NOP, 2, None),None),         # 0x82
            (("AAX", "a", self.ix_a, self.AAX, 6, None),None),         # 0x83
            (("STY", "a", self.z_a,  self.STY, 3, None),None),         # 0x84
            (("STA", "a", self.z_a,  self.STA, 3, None),None),         # 0x85
            (("STX", "a", self.z_a,  self.STX, 3, None),None),         # 0x86
            (
                ("AAX", "a", self.z_a,  self.AAX, 3, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*0")
            ),                                                         # 0x87 SMB0 65C02
            (("DEY", "a", self.imm,  self.DEY, 2, 1),None),            # 0x88
            (
                ("BIT", "v", self.imm,  self.BIT, 2, None),
                ("BIT", "v", self.imm,  self.BIT, 2, None)
            ),                                                         # 0x89 65C02 (NOP imm)
            (("TXA", "a", self.imm,  self.tfr, 2, ('x', 'a')),None),   # 0x8a
            (("XAA", "v", self.imp,  self.XAA, 2, None),None),         # 0x8b
            (("STY", "a", self.a_a,  self.STY, 4, None),None),         # 0x8c
            (("STA", "a", self.a_a,  self.STA, 4, None),None),         # 0x8d
            (("STX", "a", self.a_a,  self.STX, 4, None),None),         # 0x8e
            (
                ("AAX", "a", self.a_a,  self.AAX, 4, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*0"))
            ),                                                         # 0x8f BBS0 65C02

            (("BCC", "v", self.rl,   self.br,  2, ("C", False)),None), # 0x90
            (("STA", "a", self.iy_a, self.STA, 6, None),None),         # 0x91
            (
                ("STA", "a", self.iz_a, self.STA, 6, None),
                ("STA", "a", self.iz_a, self.STA, 6, None)
            ),                                                         # 0x92 65C02 (KIL)
            (("AXA", "a", self.iy_a, self.AXA, 6, None),None),         # 0x93
            (("STY", "a", self.zx_a, self.STY, 4, None),None),         # 0x94
            (("STA", "a", self.zx_a, self.STA, 4, None),None),         # 0x95
            (("STX", "a", self.zy_a, self.STX, 4, None),None),         # 0x96
            (
                ("AAX", "a", self.zy_a, self.AAX, 4, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*1")
            ),                                                         # 0x97 SMB1 65C02
            (("TYA", "a", self.imm,  self.tfr, 2, ('y', 'a')),None),   # 0x98
            (("STA", "a", self.ay_a, self.STA, 5, None),None),         # 0x99
            (("TXS", "a", self.imm,  self.tfr, 2, ('x', 's')),None),   # 0x9a
            (("XAS", "a", self.ay_a, self.XAS, 5, None),None),         # 0x9b
            (
                ("STZ", "a", self.a_a,  self.STZ, 5, None),
                ("STZ", "a", self.a_a,  self.STZ, 5, None)
            ),                                                         # 0x9c 65C02  (SHY ax)   fix in other
            (("STA", "a", self.ax_a, self.STA, 3, None),None),         # 0x9d                   fix in other
            (
                ("STZ", "a", self.ax_a, self.STZ, 5, None),
                ("STZ", "a", self.ax_a, self.STZ, 5, None)
            ),                                                         # 0x9e 65C02  (SHX ay)
            (
                ("AXA", "a", self.ay_a, self.AXA, 5, None),
                ("BBS", "a", self.z,  self.BBS, 6, "*1")
            ),                                                         # 0x9f BBS1 65C02


            (("LDY", "v", self.imp,  self.LDY, 2, None),None),         # 0xa0
            (("LDA", "v", self.ix,   self.LDA, 6, None),None),         # 0xa1
            (("LDX", "v", self.imp,  self.LDX, 2, None),None),         # 0xa2
            (("LAX", "v", self.ix,   self.LAX, 6, None),None),         # 0xa3
            (("LDY", "v", self.z,    self.LDY, 3, None),None),         # 0xa4
            (("LDA", "v", self.z,    self.LDA, 3, None),None),         # 0xa5
            (("LDX", "v", self.z,    self.LDX, 3, None),None),         # 0xa6
            (
                ("LAX", "v", self.z,    self.LAX, 3, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*2")
            ),                                                         # 0xa7 SMB2 65C02
            (("TAY", "a", self.imm,  self.tfr, 2, ('a', 'y')),None),   # 0xa8
            (("LDA", "v", self.imp,  self.LDA, 2, None),None),         # 0xa9
            (("TAX", "a", self.imm,  self.tfr, 2, ('a', 'x')),None),   # 0xaa
            (("ATX", "v", self.imp,  self.ATX, 2, None),None),         # 0xab
            (("LDY", "v", self.a,    self.LDY, 4, None),None),         # 0xac
            (("LDA", "v", self.a,    self.LDA, 4, None),None),         # 0xad
            (("LDX", "v", self.a,    self.LDX, 4, None),None),         # 0xae
            (
                ("LAX", "v", self.a,    self.LAX, 4, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*1"))
            ),                                                         # 0xaf BBS2 65C02

            (("BCS", "v", self.rl,   self.br,  2, ("C", True)),None),  # 0xb0
            (("LDA", "v", self.iy,   self.LDA, 5, None),None),         # 0xb1
            (
                ("LDA", "v", self.iz,   self.LDA, 5, None),
                ("LDA", "v", self.iz,   self.LDA, 5, None)
            ),                                                         # 0xb2 65C02 (KIL)
            (("LAX", "v", self.iy,   self.LAX, 5, None),None),         # 0xb3
            (("LDY", "v", self.zx,   self.LDY, 4, None),None),         # 0xb4
            (("LDA", "v", self.zx,   self.LDA, 4, None),None),         # 0xb5
            (("LDX", "v", self.zy,   self.LDX, 4, None),None),         # 0xb6
            (
                ("LAX", "v", self.zy,   self.LAX, 4, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*3")
            ),                                                         # 0xb7 SMB3 65C02
            (("CLV", "v", self.imm,  self.clr, 2, "V"),None),          # 0xb8
            (("LDA", "v", self.ay,   self.LDA, 4, None),None),         # 0xb9
            (("TSX", "a", self.imm,  self.tfr, 2, ('s', 'x')),None),   # 0xba
            (("LAR", "v", self.ay,   self.LAR, 4, None),None),         # 0xbb
            (("LDY", "v", self.ax,   self.LDY, 4, None),None),         # 0xbc
            (("LDA", "v", self.ax,   self.LDA, 4, None),None),         # 0xbd
            (("LDX", "v", self.ay,   self.LDX, 4, None),None),         # 0xbe
            (
                ("LAX", "v", self.ay,   self.LAX, 4, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*3"))
            ),                                                         # 0xbf BBS3 65C02

            (("CPY", "v", self.imp,  self.CPY, 2, None),None),         # 0xc0
            (("CMP", "v", self.ix,   self.CMP, 6, None),None),         # 0xc1
            (("NOP", "v", self.imp,  self.NOP, 2, None),None),         # 0xc2
            (("DCP", "a", self.ix_a, self.DCP, 8, None),None),         # 0xc3
            (("CPY", "v", self.z,    self.CPY, 3, None),None),         # 0xc4
            (("CMP", "v", self.z,    self.CMP, 3, None),None),         # 0xc5
            (("DEC", "a", self.z_a,  self.DEC, 5, None),None),         # 0xc6
            (
                ("DCP", "a", self.z_a,  self.DCP, 5, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*4")
            ),                                                         # 0xc7 SMB4 65C02
            (("INY", "a", self.imm,  self.INY, 2, 1),None),            # 0xc8
            (("CMP", "v", self.imp,  self.CMP, 2, None),None),         # 0xc9
            (("DEX", "a", self.imm,  self.DEX, 2, 1),None),            # 0xca
            (("AXS", "v", self.imp,  self.AXS, 2, None),None),         # 0xcb
            (("CPY", "v", self.a,    self.CPY, 4, None),None),         # 0xcc
            (("CMP", "v", self.a,    self.CMP, 4, None),None),         # 0xcd
            (("DEC", "a", self.a_a,  self.DEC, 6, None),None),         # 0xce
            (
                ("DCP", "a", self.a_a,  self.DCP, 6, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*4"))
            ),                                                         # 0xcf BBS4 65C02

            (("BNE", "v", self.rl,   self.br,  2, ("Z", False)),None), # 0xd0
            (("CMP", "v", self.iy,   self.CMP, 5, None),None),         # 0xd1
            (
                ("CMP", "v", self.iz,   self.CMP, 5, None),
                ("CMP", "v", self.iz,   self.CMP, 5, None)
            ),                                                         # 0xd2 65C02 (KIL)
            (("DCP", "a", self.iy_a, self.DCP, 8, None),None),         # 0xd3
            (("NOP", "v", self.zx,   self.NOP, 4, None),None),         # 0xd4
            (("CMP", "v", self.zx,   self.CMP, 4, None),None),         # 0xd5
            (("DEC", "a", self.zx_a, self.DEC, 6, None),None),         # 0xd6
            (
                ("DCP", "a", self.zx_a, self.DCP, 6, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*5")
            ),                                                         # 0xd7 SMB5 65C02
            (("CLD", "v", self.imm,  self.clr, 2, "D"),None),          # 0xd8
            (("CMP", "v", self.ay,   self.CMP, 4, None),None),         # 0xd9
            (
                ("PHX", "a", self.imm,  self.stk, 3, ("H", "x")),
                ("PHX", "a", self.imm,  self.stk, 3, ("H", "x"))
            ),                                                         # 0xda 65C02 (NOP imp)
            (("DCP", "a", self.ay_a, self.DCP, 7, None),None),         # 0xdb
            (("CMP", "v", self.ax,   self.CMP, 4, None),None),         # 0xdc
            (("NOP", "v", self.ax,   self.NOP, 4, None),None),         # 0xdd
            (("DEC", "a", self.ax_a, self.DEC, 7, None),None),         # 0xde
            (
                ("DCP", "a", self.ax_a, self.DCP, 7, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*5"))
            ),                                                         # 0xdf BBS5 65C02

            (("CPX", "v", self.imp,  self.CPX, 2, None),None),         # 0xe0
            (("SBC", "v", self.ix,   self.SBC, 6, None),None),         # 0xe1
            (("NOP", "v", self.imm,  self.NOP, 2, None),None),         # 0xe2
            (("ISC", "a", self.ix_a, self.ISC, 8, None),None),         # 0xe3
            (("CPX", "v", self.z,    self.CPX, 3, None),None),         # 0xe4
            (("SBC", "v", self.z,    self.SBC, 3, None),None),         # 0xe5
            (("INC", "a", self.z_a,  self.INC, 5, None),None),         # 0xe6
            (
                ("ISC", "a", self.z_a,  self.ISC, 5, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*6")
            ),                                                         # 0xe7 SMB6 65C02
            (("INX", "a", self.imm,  self.INX, 2, 1),None),            # 0xe8
            (("SBC", "v", self.imp,  self.SBC, 2, None),None), # Dup   # 0xe9
            (("NOP", "v", self.imm,  self.NOP, 2, 1),None),            # 0xea
            (("SBC", "v", self.imp,  self.SBC, 2, None),None), # Dup   # 0xeb
            (("CPX", "v", self.a,    self.CPX, 4, None),None),         # 0xec
            (("SBC", "v", self.a,    self.SBC, 4, None),None),         # 0xed
            (("INC", "a", self.a_a,  self.INC, 6, None),None),         # 0xee
            (
                ("ISC", "a", self.a_a,  self.ISC, 6, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*6"))
            ),                                                         # 0xef BBS6 65C02

            (("BEQ", "v", self.rl,   self.br,  2, ("Z", True)),None),  # 0xf0
            (("SBC", "v", self.iy,   self.SBC, 5, None),None),         # 0xf1
            (
                ("SBC", "v", self.iz,   self.SBC, 5, None),
                ("SBC", "v", self.iz,   self.SBC, 5, None)
            ),                                                         # 0xf2 65C02 (KIL)
            (("ISC", "a", self.iy_a, self.ISC, 8, None),None),         # 0xf3
            (("NOP", "v", self.zx,   self.NOP, 4, None),None),         # 0xf4
            (("SBC", "v", self.zx,   self.SBC, 4, None),None),         # 0xf5
            (("INC", "a", self.zx_a, self.INC, 6, None),None),         # 0xf6
            (
                ("ISC", "a", self.zx_a, self.ISC, 6, None),
                ("SMB","a", self.z_a,  self.SMB, 5, "*7")
            ),                                                         # 0xf7 SMB7 65C02
            (("SED", "v", self.imm,  self.set, 2, "D"),None),          # 0xf8
            (("SBC", "v", self.ay,   self.SBC, 4, None),None),         # 0xf9
            (
                ("PLX", "a", self.imm,  self.stk, 4, ("L", "x")),
                ("PLX", "a", self.imm,  self.stk, 4, ("L", "x"))
            ),                                                         # 0xfa 65C02 (NOP imp)
            (("ISC", "a", self.ay_a, self.ISC, 7, None),None),         # 0xfb
            (("NOP", "v", self.ax,   self.NOP, 4, None),None),         # 0xfc
            (("SBC", "v", self.ax,   self.SBC, 4, None),None),         # 0xfd
            (("INC", "a", self.ax_a, self.INC, 7, None),None),         # 0xfe
            (
                ("ISC", "a", self.ax_a, self.ISC, 7, None),
                ("BBS", "a", self.z,  self.BBS, 6, ("*7"))
            )                                                          # 0xff BBS7 65C02
        )

        self.device = (
            (
            #   6502
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 0
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 1
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 2
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 3
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 4
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 5
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 6
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 7
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 8
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # 9
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # a
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # b
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # c
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # d
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, # e
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0  # f
            ),
            (
            # 65C02
            #   0 1 2 3 4 5 6 7 8 9 A B C D E F
                0,0,0,0,1,0,0,1,0,0,0,0,1,0,0,1, # 0
                0,0,1,0,1,0,0,1,0,0,1,0,1,0,0,1, # 1
                0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1, # 2
                0,0,1,0,0,0,0,1,0,0,0,0,1,0,0,1, # 3
                0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1, # 4
                0,0,1,0,0,0,0,1,0,0,1,0,0,0,0,1, # 5
                0,0,0,0,1,0,0,1,0,0,0,0,0,0,0,1, # 6
                0,0,1,0,1,0,0,1,0,0,1,0,0,0,0,1, # 7
                1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1, # 8
                0,0,1,0,0,0,0,1,0,0,0,0,1,0,1,1, # 9
                0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1, # a
                0,0,1,0,0,0,0,1,0,0,0,0,0,0,0,1, # b
                0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1, # c
                0,0,1,0,0,0,0,1,0,0,1,0,0,0,0,1, # d
                0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1, # e
                0,0,1,0,0,0,0,1,0,0,1,0,0,0,0,1  # f
            )
        )
