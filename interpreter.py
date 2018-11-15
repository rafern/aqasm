#!/usr/bin/python3
import lex
from numpy import zeros, uint8

## Utilities used by instruction functions
def oputil_ldr(cpu, addr):
    # Loads a big endian word from memory and returns it
    if addr >= cpu.memWords:
        raise ValueError("Page fault: {:d} exceeds memory limit of {:d}".format(addr, cpu.memWords - 1))
    assert addr >= 0
    # Get real value by bit shifting
    fetchVal = 0
    for b in range(0, cpu.bytesPerWord):
        fetchVal += cpu.mem[addr * cpu.bytesPerWord + b] << ((cpu.bytesPerWord - b - 1) * 8)
    return fetchVal

def oputil_str(cpu, addr, val):
    # Stores a big endian word to memory
    if addr >= cpu.memWords:
        raise ValueError("Page fault: {:d} exceeds memory limit of {:d}".format(addr, cpu.memWords - 1))
    assert addr >= 0
    # Set big endian value by bit shifting
    for b in range(0, cpu.bytesPerWord):
        cpu.mem[addr * cpu.bytesPerWord + b] = (val >> ((cpu.bytesPerWord - b - 1) * 8)) & 0xff

## Instruction functions
def op_ldr(cpu):
    # LDR Rd, <memory ref>
    # Rd = <memory ref>
    # Since memory 
    cpu.reg[cpu.lex[cpu.pc][1]] = oputil_ldr(cpu, cpu.lex[cpu.pc][2])

def eop_ldr_r(cpu):
    # Language extension
    # LDR Rd, Rn
    # Rd = memory[Rn]
    cpu.reg[cpu.lex[cpu.pc][1]] = oputil_ldr(cpu, cpu.reg[cpu.lex[cpu.pc][2]])

def op_str(cpu):
    # STR Rd, <memory ref>
    # <memory ref> = Rd
    oputil_str(cpu, cpu.lex[cpu.pc][2], cpu.reg[cpu.lex[cpu.pc][1]])

def eop_str_da(cpu):
    # Language extension
    # STR #n, <memory ref>
    # <memory ref> = #n
    oputil_str(cpu, cpu.lex[cpu.pc][2], cpu.lex[cpu.pc][1])

def eop_str_rr(cpu):
    # Language extension
    # STR Rd, Rn
    # memory[Rn] = Rd
    oputil_str(cpu, cpu.reg[cpu.lex[cpu.pc][2]], cpu.reg[cpu.lex[cpu.pc][1]])

def eop_str_dr(cpu):
    # Language extension
    # STR #n, Rn
    # memory[Rn] = #n
    oputil_str(cpu, cpu.reg[cpu.lex[cpu.pc][2]], cpu.lex[cpu.pc][1])

def op_add_d(cpu):
    # ADD Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn + <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] + cpu.lex[cpu.pc][3]

def op_add_r(cpu):
    # ADD Rd, Rn, <operand2 [register overload]>
    # Rd = Rn + <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] + cpu.reg[cpu.lex[cpu.pc][3]]

def op_sub_d(cpu):
    # SUB Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn - <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] - cpu.lex[cpu.pc][3]

def op_sub_r(cpu):
    # SUB Rd, Rn, <operand2 [register overload]>
    # Rd = Rn - <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] - cpu.reg[cpu.lex[cpu.pc][3]]

def op_mov_d(cpu):
    # MOV Rd, <operand2 [decimal overload]>
    # Rd = <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.lex[cpu.pc][2]

def op_mov_r(cpu):
    # MOV Rd, <operand2 [register overload]>
    # Rd = <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]]

def op_cmp_d(cpu):
    # CMP Rn, <operand2 [decimal overload]>
    # temp = Rn - <operand2>
    # if temp is 0 then set zero flag
    # if temp is negative then set sign flag
    temp = cpu.reg[cpu.lex[cpu.pc][1]] - cpu.lex[cpu.pc][2]
    cpu.zero = (temp == 0)
    cpu.sign = (temp <  0)

def op_cmp_r(cpu):
    # CMP Rn, <operand2 [register overload]>
    # temp = Rn - <operand2>
    # if temp is 0 then set zero flag
    # if temp is negative then set sign flag
    temp = cpu.reg[cpu.lex[cpu.pc][1]] - cpu.reg[cpu.lex[cpu.pc][2]]
    cpu.zero = (temp == 0)
    cpu.sign = (temp <  0)

def op_b(cpu):
    # B <label>
    # pc = line number corresponding to label
    # set blast flag
    # (label line internally stored as line number)
    cpu.pc = cpu.lex[cpu.pc][1]
    cpu.blast = True

def op_beq(cpu):
    # BEQ <label>
    # if zero flag set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if cpu.zero:
        cpu.pc = cpu.lex[cpu.pc][1]
        cpu.blast = True

def op_bne(cpu):
    # BNE <label>
    # if zero flag not set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if not cpu.zero:
        cpu.pc = cpu.lex[cpu.pc][1]
        cpu.blast = True

def op_bgt(cpu):
    # BGT <label>
    # if sign flag not set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if not cpu.sign:
        cpu.pc = cpu.lex[cpu.pc][1]
        cpu.blast = True

def op_blt(cpu):
    # BLT <label>
    # if sign flag set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if cpu.sign:
        cpu.pc = cpu.lex[cpu.pc][1]
        cpu.blast = True

def op_and_d(cpu):
    # AND Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn & <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] & cpu.lex[cpu.pc][3]

def op_and_r(cpu):
    # AND Rd, Rn, <operand2 [register overload]>
    # Rd = Rn & <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] & cpu.reg[cpu.lex[cpu.pc][3]]

def op_orr_d(cpu):
    # ORR Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn | <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] | cpu.lex[cpu.pc][3]

def op_orr_r(cpu):
    # ORR Rd, Rn, <operand2 [register overload]>
    # Rd = Rn | <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] | cpu.reg[cpu.lex[cpu.pc][3]]

def op_eor_d(cpu):
    # EOR Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn ^ <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] ^ cpu.lex[cpu.pc][3]

def op_eor_r(cpu):
    # EOR Rd, Rn, <operand2 [register overload]>
    # Rd = Rn ^ <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] ^ cpu.reg[cpu.lex[cpu.pc][3]]

def op_mvn_d(cpu):
    # MVN Rd, <operand2 [decimal overload]>
    # Rd = ~<operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = ~cpu.lex[cpu.pc][3]

def op_mvn_r(cpu):
    # MVN Rd, <operand2 [register overload]>
    # Rd = ~<operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = ~cpu.reg[cpu.lex[cpu.pc][3]]

def op_lsl_d(cpu):
    # LSL Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn << <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] << cpu.lex[cpu.pc][3]

def op_lsl_r(cpu):
    # LSL Rd, Rn, <operand2 [register overload]>
    # Rd = Rn << <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] << cpu.reg[cpu.lex[cpu.pc][3]]

def op_lsr_d(cpu):
    # LSR Rd, Rn, <operand2 [decimal overload]>
    # Rd = Rn >> <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] >> cpu.lex[cpu.pc][3]

def op_lsr_r(cpu):
    # LSR Rd, Rn, <operand2 [register overload]>
    # Rd = Rn >> <operand2>
    cpu.reg[cpu.lex[cpu.pc][1]] = cpu.reg[cpu.lex[cpu.pc][2]] >> cpu.reg[cpu.lex[cpu.pc][3]]

def op_halt(cpu):
    # HALT
    # set halt flag
    cpu.halt = True

## Instruction definitions for lexer parser
# Each token match has a value to add to a sum. Each sum represents which
# alternative function to call for emulating an opcode. This is useful for
# emulating the <operand2> syntax in the AQA assembly spec and is flexible
# enough for creating complex overloading. However, instruction declaration
# becomes complex when it has no overloading

# Instruction function naming convention:
# [e]op_name[_rad]
# [e]    - Instruction is a language extension
# name   - Instruction name. E.g. mov
# [_rad} - Instruction overload. r = register, a = address, d = decimal
#          Can be stacked. E.g.: _ra suffix means that the instruction is an
#                                overload for the first operand as a register
#                                and the second operand as an address
#          If the instruction has no overloads, this is ommited so it is shorter

# Syntax:
# "opcode": ({sum1: (func1, is_extension), sum2: (func2, is_extension), ...},
#            ((addval, TOKEN_TYPE1), (addval, ALT_TOKEN_TYPE1), ...),
#            ((addval, TOKEN_TYPE2), (addval, ALT_TOKEN_TYPE2), ...),
#            ...),
# "opcode": ...

# Note: a common mistake is to forget to add a comma in the end of a 1D tuple.
# BE CAREFUL
opcodes = {
    "ldr": ({0: (op_ldr, False), 1: (eop_ldr_r, True)},
            ((0, lex.token.register),),
            ((0, lex.token.address), (1, lex.token.register))
           ),
    "str": (
            {0: (op_str, False), 1: (eop_str_da, True),
             2: (eop_str_rr, True), 3: (eop_str_dr, True)},
            ((0, lex.token.register), (1, lex.token.decimal)),
            ((0, lex.token.address), (2, lex.token.register))
           ),
    "add": (
            {0: (op_add_d, False), 1: (op_add_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "sub": (
            {0: (op_sub_d, False), 1: (op_sub_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "mov": (
            {0: (op_mov_d, False), 1: (op_mov_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "cmp": (
            {0: (op_cmp_d, False), 1: (op_cmp_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "b":   (
            {0: (op_b, False)},
            ((0, lex.token.labelid),)
           ),
    "beq": (
            {0: (op_beq, False)},
            ((0, lex.token.labelid),)
           ),
    "bne": (
            {0: (op_bne, False)},
            ((0, lex.token.labelid),)
           ),
    "bgt": (
            {0: (op_bgt, False)},
            ((0, lex.token.labelid),)
           ),
    "blt": (
            {0: (op_blt, False)},
            ((0, lex.token.labelid),)
           ),
    "and": (
            {0: (op_and_d, False), 1: (op_and_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "orr": (
            {0: (op_orr_d, False), 1: (op_orr_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "eor": (
            {0: (op_eor_d, False), 1: (op_eor_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "mvn": (
            {0: (op_mvn_d, False), 1: (op_mvn_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "lsl": (
            {0: (op_lsl_d, False), 1: (op_lsl_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "lsr": (
            {0: (op_lsr_d, False), 1: (op_lsr_r, False)},
            ((0, lex.token.register),),
            ((0, lex.token.register),),
            ((0, lex.token.decimal), (1, lex.token.register))
           ),
    "halt":(
            {0: (op_halt, False)},
           )
}

## Interpreter class for emulating a cpu running AQA assembly
class aqasm:
    def __init__(self, code = "", extensions = False, wordLength = 8, memWords = 256):
        self.compile_code(code, extensions, wordLength, memWords)

    def compile_code(self, code, extensions = False, wordLength = 8, memWords = 256):
        # If the word length is not a multiple of 8, error
        if wordLength % 8 != 0:
            raise ValueError("Attempt to use word length which is not a multiple of a byte")
        if memWords < 0:
            raise ValueError("Memory size cannot be negative")
        if memWords > 2 ** wordLength:
            raise ValueError("Memory size cannot be greater than 2 ^ wordLength, since it becomes unaddressable")
        # self.extensions has no effect, it is just so that outer code can check
        # whether the code was compiled with extensions or not
        self.extensions = extensions
        self.wordLength = wordLength
        self.bytesPerWord = wordLength // 8
        self.uintMax = 2 ** wordLength - 1
        self.memWords = memWords
        self.memBytes = memWords * 8
        self.code = code.splitlines()
        self.lex, times = lex.lex_process(self.code, extensions)
        self.reset()

        # Halt if no instructions or NOOPs
        if len(self.lex) == 0:
            self.halt = True
        return times

    def reset(self):
        # Memory
        self.mem = zeros(self.memBytes, dtype=uint8)
        # Registers
        self.reg = [0] * 13
        # Program counter
        self.pc = 0
        # Comparison flags. Called zero and sign flags to be similar to x86.
        # Note that they are only set in CMP instructions, _UNLIKE_ x86
        self.zero = False
        self.sign = False
        # Halted flag
        self.halt = False
        # Last was branch flag (for skipping PC increment on branch)
        self.blast = False

    def step(self):
        # Do nothing if CPU halted or if there are no instructions
        if self.halt or len(self.lex) == 0:
            return

        # Run instruction if not a NOOP (empty line)
        if self.lex[self.pc] != None:
            self.lex[self.pc][0](self)

            # "Short" CPU (just stop it... fancy terms are fancy) to preserve flags
            if self.halt:
                return

        # Increment program counter if branch last flag wasn't set
        if not self.blast:
            # Also check if at last instruction. Halt on last instruction
            if self.pc == len(self.lex) - 1:
                self.halt = True
                return

            self.pc += 1

        # Clear branch last flag
        self.blast = False
