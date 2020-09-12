import compiler
from collections import deque
from numpy import zeros, uint8
from math import inf, nan, floor, isnan

## Reserved IRQ numbers
IRQ_DIVISION_BY_ZERO         = 0
IRQ_PAGE_FAULT               = 1
IRQ_GENERAL_PROTECTION_FAULT = 2
IRQ_BREAKPOINT               = 3
IRQ_OVERFLOW                 = 4
IRQ_IO_EXCEPTION             = 5
IRQ_INVALID_ARITHMETIC       = 6

## Utilities used for interpreting CPU data
def aqasmutil_num2int(val, n):
    # Parses a python number into an n-bit twos complement number.
    # Note that this utility throws an exception if the number is not within the
    # representable range with the given bit count

    # Check if number in representable range
    if val > 2 ** (n - 1) - 1 or val < -(2 ** (n - 1)):
        raise ValueError("Architecture error: Cannot represent number as twos complement")

    accum = 0

    # Determine sign bit's value
    if val < 0:
        val += 2 ** (n - 1)
        accum |= 0x1 << (n - 1)

    # Determine which bits are set
    for b in reversed(range(0, n - 1)):
        bitVal = 2 ** b
        if val >= bitVal:
            val -= bitVal
            accum |= 0x1 << b

    return accum

def aqasmutil_num2float(val, en, fn):
    # Parses a python decimal number into a twos complement float with an en-bit
    # exponent and an fn-bit fraction.
    # Note that this does not throw exceptions, giving approximations of the
    # number to be converted. Numbers too big will become infinity, etc...

    # Special cases for zero, infinities, not a number and tiny numbers
    if isnan(val):
        return 1 | ((2 ** en - 1) << fn) # Not a number
    elif abs(val) > ((2 ** (fn + 1) - 1) * (2 ** (2 ** (en - 1) - fn - 1))) or val == inf or val == -inf:
        if val > 0:
            return (2 ** en - 1) << fn # Positive infinity
        else:
            return (1 << (en + fn)) | ((2 ** en - 1) << fn) # Negative infinity
    elif val == 0 or abs(val) < 2 ** (2 - fn -(2 ** (en - 1))):
        return 0 # Zero

    # Determine sign bit
    signBit = (val < 0)
    if signBit:
        val = -val

    # Separate value into whole and fraction parts
    wholeRaw = floor(val)
    fractionRaw = val - wholeRaw

    # Convert value's whole part
    # i is the length of the whole part
    whole = 0
    i = 0
    while wholeRaw != 0:
        whole |= (wholeRaw % 2) << i
        wholeRaw //= 2
        i += 1

    # Convert value's fractional part
    # j is the length of the fractional part and, therefore, the initial binary
    # point's location
    # k is the distance from 0 to the first set bit in the fractional part
    fraction = 0
    j = 0
    k = -i
    while fractionRaw != 0:
        fraction <<= 1
        fractionRaw *= 2
        j += 1
        if fractionRaw >= 1:
            fractionRaw -= 1
            fraction |= 1
            if k == 0:
                k = j
        if k != 0 and j - k == fn:
            break

    # Marge fraction and whole part into mantissa
    mantissa = (whole << j) | fraction

    # Normalize mantissa
    tempExponentZero = 2 ** (en - 1) - 1
    tempExponentMax  = 2 ** en - 1
    tempFractionMask = 2 ** fn - 1
    finalFraction, exponent = oputil_float_normalize(mantissa, tempExponentZero, i, j, fn, tempExponentMax, tempFractionMask)

    # Done, construct float
    return oputil_float_construct(signBit, finalFraction, exponent, fn, en)

def aqasmutil_parse_bin(val, n):
    # Parses an n-bit unsigned number into a python number
    accum = 0
    for b in range(0, n):
        if (val >> b) & 0x1 == 0x1:
            accum += 2 ** b

    return accum

def aqasmutil_parse_twos(val, n):
    # Parses an n-bit twos complement number into a python number
    accum = 0

    # Get negative part
    if (val >> (n - 1)) & 0x1 == 0x1:
        accum -= 2 ** (n - 1)

    # Get positive part
    accum += aqasmutil_parse_bin(val, n - 1)

    return accum

def aqasmutil_parse_int(cpu, val):
    return aqasmutil_parse_twos(val, cpu.bytesPerWord * 8)

def aqasmutil_parse_float(cpu, val):
    # Extract raw sign, fraction and exponent
    fraction = val & cpu.fractionMask
    negate = (val & cpu.signBitMask) != 0
    exponent = (val & cpu.exponentMask) >> cpu.fractionLen

    # Check if it is a special value
    if val == cpu.posZero:
        return 0.0
    elif val == cpu.negZero:
        return -0.0
    elif val == cpu.posInf:
        return inf
    elif val == cpu.negInf:
        return -inf
    elif exponent == cpu.exponentMax:
        return nan

    # Parse the fraction
    accum = 0
    for b in range(0, cpu.fractionLen):
        if (fraction >> b) & 0x1 == 0x1:
            accum += 2 ** (b - cpu.fractionLen)

    # Multiply by exponent
    if oputil_is_float_denormal(cpu,val):
        accum *= 2 ** (1 - cpu.exponentBias)
    else:
        # Parse exponent
        parsedExponent = aqasmutil_parse_bin(exponent, cpu.exponentLen) - cpu.exponentBias

        accum += 1
        accum *= 2 ** parsedExponent

    # Return final value
    if negate:
        return -accum
    else:
        return accum

def aqasmutil_int2str(cpu, val):
    # Convert to string
    return str(aqasmutil_parse_int(cpu, val))

def aqasmutil_float2str(cpu, val):
    # Convert to string. Also show if denormal or negative zero
    if val == cpu.negZero:
        return '-0'
    s = '{:g}'.format(aqasmutil_parse_float(cpu, val))
    if oputil_is_float_denormal(cpu, val):
        s += ' (denormal)'
    return s

## Utilities used by instruction functions
def oputil_ldr(cpu, addr):
    # Loads a big endian word from memory and returns it
    # Convert the number to its unsigned bitwise equivalent
    if addr < 0:
        addr += 2 ** cpu.wordLength
    if addr >= cpu.memWords:
        cpu.irq.append(IRQ_PAGE_FAULT)
        return 0
    assert addr >= 0
    # Get real value by bit shifting
    fetchVal = 0
    for b in range(0, cpu.bytesPerWord):
        fetchVal += cpu.mem[addr * cpu.bytesPerWord + b] << ((cpu.bytesPerWord - b - 1) * 8)
    return fetchVal

def oputil_str(cpu, addr, val):
    # Stores a big endian word to memory
    # Convert the number to its unsigned bitwise equivalent
    if addr < 0:
        addr += 2 ** cpu.wordLength
    if addr >= cpu.memWords:
        cpu.irq.append(IRQ_PAGE_FAULT)
        return 0
    assert addr >= 0
    # Set big endian value by bit shifting
    for b in range(0, cpu.bytesPerWord):
        cpu.mem[addr * cpu.bytesPerWord + b] = (val >> ((cpu.bytesPerWord - b - 1) * 8)) & 0xff

def oputil_truncate(cpu, a, n):
    # Truncates a number a to n bits
    return a & (2 ** n - 1)

def oputil_shift_left(cpu, a, t, n):
    # Shifts an n-bit number a left, t times
    return oputil_truncate(cpu, a << t, n)

def oputil_shift_right(cpu, a, t, n):
    # Shifts an n-bit number a right, t times
    return oputil_truncate(cpu, a >> t, n)

def oputil_negate_twos(cpu, a, n):
    # Negates an n-bit number a, twos complement style
    a = ~a
    return oputil_add_twos(cpu, a, 1, n)

def oputil_add_twos(cpu, a, b, n):
    # Adds the n-bit numbers a and b
    carry = 0
    result = 0
    for i in range(0, n):
        # Get bit of a and b
        abit = (a >> i) & 1
        bbit = (b >> i) & 1
        # Get resulting bit
        result |= (abit ^ bbit ^ carry) << i
        # Update carry
        carry = (bbit & carry) | (abit & carry) | (abit & bbit)
    return result

def oputil_sub_twos(cpu, a, b, n):
    # Subtracts the n-bit numbers a and b
    return oputil_add_twos(cpu, a, oputil_negate_twos(cpu, b, n), n)

def oputil_mul_twos(cpu, a, b, n):
    # Multiplies the n-bit numbers a and b
    result = 0
    for i in range(0, n):
        # Check if bit in position i is set
        if ((b >> i) & 1) == 1:
            # Shift and add number
            result = oputil_add_twos(cpu, result, oputil_shift_left(cpu, a, i, n), n)
    return result

def oputil_div_twos(cpu, a, b, n):
    # Divides the n-bit numbers a by b and returns the quotient and remainder
    if b == 0:
        cpu.irq.append(IRQ_DIVISION_BY_ZERO)
        return (0, 0)

    # Handle negative values
    aNegative = ((a >> (n - 1)) & 1) == 1
    bNegative = ((b >> (n - 1)) & 1) == 1
    if aNegative:
        a = oputil_negate_twos(cpu, a, n)
    if bNegative:
        b = oputil_negate_twos(cpu, b, n)
    # Quotient and remainder
    q = r = 0
    for i in reversed(range(0, n)):
        # Left-shift remainder by 1
        r = oputil_shift_left(cpu, r, 1, n)
        # Set the remainder's LSB equal to the ith bit of the numerator
        r |= (a >> i) & 1
        # Update quotient if the remainder is greater or equal to the divisor
        if r >= b:
            r = oputil_sub_twos(cpu, r, b, n)
            q |= 1 << i
    # Final negative handling
    if (aNegative and not bNegative) or (not aNegative and bNegative):
        q = oputil_negate_twos(cpu, q, n)
    if aNegative:
        r = oputil_negate_twos(cpu, r, n)
    return (q, r)

def oputil_is_float_nan(cpu, a):
    return ((a & cpu.exponentMask) == cpu.exponentMask) and ((a & cpu.fractionMask) != 0)

def oputil_is_float_denormal(cpu, val):
    exponent = (val & cpu.exponentMask) >> cpu.fractionLen
    return exponent == 0 and val != cpu.posZero and val != cpu.negZero

def oputil_float_split(cpu, a):
    # Splits a float into an intermediary float, which is a sign boolean, a
    # mantissa and a biased exponent

    # Split parts
    sign = (a >> (cpu.exponentLen + cpu.fractionLen)) == 1
    exponent = (a & cpu.exponentMask) >> cpu.fractionLen
    mantissa = a & cpu.fractionMask

    # Unpack mantissa from fraction
    if exponent == 0:
        # Denormal; correct shift
        mantissa <<= 1
    else:
        # Normal; add hidden most significant one
        mantissa |= 1 << cpu.fractionLen

    return sign, exponent, mantissa

def oputil_float_construct(s, f, e, tfs, tes):
    # Constructs a float from an intermediary float with sign boolean (s),
    # fraction (f), exponent (e), target fraction size (tfs) and target
    # exponent size (tes)
    if s:
        return (e << tfs) | f | (1 << (tfs + tes))
    else:
        return (e << tfs) | f

def oputil_float_normalize(m, e, ws, fs, tfs, em, fm):
    # Normalizes an intermediary float with mantissa (m), biased exponent (e),
    # whole size (ws), fraction size (fs), target fraction size (tfs), exponent
    # max (em) and fraction mask (fm, for optimising)

    # Seek target binary point
    t = 0
    for i in reversed(range(0, ws + fs)):
        if (m >> i) == 1:
            t = i
            break

    # Calculate mantissa shift and new exponent
    shift = fs - t
    e -= shift
    if e <= 0:
        shift += e - 1
        e = 0
    shift -= fs - tfs

    # If the new exponent is too big, return infinity
    if e >= em:
        return 0, em

    # Shift mantissa
    if shift > 0:
        m <<= shift
    else:
        m >>= -shift

    # Truncate mantissa
    m &= fm

    return m, e

def oputil_float_add(cpu, a, b):
    # Special cases
    if oputil_is_float_nan(cpu, a) or oputil_is_float_nan(cpu, b) or (a == cpu.posInf and b == cpu.negInf) or (a == cpu.negInf and b == cpu.posInf):
        return cpu.defaultNan
    elif a == cpu.posInf or a == cpu.negInf:
        return a
    elif b == cpu.posInf or b == cpu.negInf:
        return b

    # Get float parts
    aNegative, aExponent, aMantissa = oputil_float_split(cpu, a)
    bNegative, bExponent, bMantissa = oputil_float_split(cpu, b)

    # Match exponents
    eDiff = abs(aExponent - bExponent)
    l = cpu.fractionLen + 3 + eDiff
    minExponent = 0
    if aExponent > bExponent:
        minExponent = bExponent
        aMantissa <<= eDiff
    else:
        minExponent = aExponent
        bMantissa <<= eDiff

    # If signed, two's complement
    if aNegative:
        aMantissa = oputil_negate_twos(cpu, aMantissa, l)
    if bNegative:
        bMantissa = oputil_negate_twos(cpu, bMantissa, l)

    # Add fractions
    cMantissa = oputil_add_twos(cpu, aMantissa, bMantissa, l)

    # If result is negative, two's complement the fraction
    cNegative = ((cMantissa >> (l - 1)) == 1)
    if cNegative:
        cMantissa = oputil_negate_twos(cpu, cMantissa, l)

    # If the resulting fraction is zero, then return 0
    if cMantissa == 0:
        return cpu.posZero

    # Normalize the result
    cFraction, cExponent = oputil_float_normalize(cMantissa, minExponent, 3 + eDiff, cpu.fractionLen, cpu.fractionLen, cpu.exponentMax, cpu.fractionMask)

    # Done
    return oputil_float_construct(cNegative, cFraction, cExponent, cpu.fractionLen, cpu.exponentLen)

def oputil_float_mul(cpu, a, b):
    # Special cases
    aIsZero = (a == cpu.posZero or a == cpu.negZero)
    bIsZero = (b == cpu.posZero or b == cpu.negZero)
    aIsInf = (a == cpu.posInf or a == cpu.negInf)
    bIsInf = (b == cpu.posInf or b == cpu.negInf)
    if oputil_is_float_nan(cpu, a) or oputil_is_float_nan(cpu, b) or (aIsZero and bIsInf) or (aIsInf and bIsZero):
        return cpu.defaultNan
    elif aIsInf and bIsInf:
        return cpu.posInf | ((a & cpu.signBitMask) ^ (b & cpu.signBitMask))

    # Get float parts
    aNegative, aExponent, aMantissa = oputil_float_split(cpu, a)
    bNegative, bExponent, bMantissa = oputil_float_split(cpu, b)

    # Multiply fractions
    l = (cpu.fractionLen + 1) * 2
    cMantissa = oputil_mul_twos(cpu, aMantissa, bMantissa, l)

    # Add exponents
    cExponent = aExponent + bExponent - cpu.exponentBias

    # Normalize the result
    cFraction, cExponent = oputil_float_normalize(cMantissa, cExponent, 2, cpu.fractionLen * 2, cpu.fractionLen, cpu.exponentMax, cpu.fractionMask)

    # Done
    return oputil_float_construct(aNegative != bNegative, cFraction, cExponent, cpu.fractionLen, cpu.exponentLen)

def oputil_float_truncate(cpu, a):
    # Don't round if nan
    if oputil_is_float_nan(cpu, a):
        return a

    # Get unbiased exponent
    exponent = ((a & cpu.exponentMask) >> cpu.fractionLen) - cpu.exponentBias

    # If the unbiased exponent is less than zero, then the result is zero
    if exponent < 0:
        return a & cpu.signBitMask

    # Remove part of mantissa less than zero
    maskLen = cpu.fractionLen - exponent
    if maskLen <= 0:
        # If the mask length is too small, then there is no part smaller than
        # zero, so do nothing
        return a
    mask = ~(2 ** maskLen - 1)

    # Done, return truncated float (by masking it)
    return a & mask

def oputil_float_round_away(cpu, a):
    # If the value is zero or nan, don't round
    if a == cpu.posZero or a == cpu.negZero or oputil_is_float_nan(cpu, a):
        return a

    # Get unbiased exponent
    exponent = ((a & cpu.exponentMask) >> cpu.fractionLen) - cpu.exponentBias

    # If the unbiased exponent is less than zero, then the result is one
    if exponent < 0:
        return (a & cpu.signBitMask) | (cpu.exponentBias << cpu.fractionLen)

    # Generate mask
    maskLen = cpu.fractionLen - exponent
    if maskLen <= 0:
        # If the mask length is too small, then there is no part smaller than
        # zero, so do nothing
        return a
    mask = 2 ** maskLen - 1

    # If there is a part less than zero, add one after mask
    if a & mask > 0:
        a = oputil_add_twos(cpu, a, 1 << maskLen, cpu.fractionLen + cpu.exponentLen + 1)

    # Done, return rounded float (by masking it)
    return a & ~mask

def oputil_float_floor(cpu, a):
    # If positive, round to zero, else, round to negative infinity (away)
    if a & cpu.signBitMask == 0:
        return oputil_float_truncate(cpu, a)
    else:
        return oputil_float_round_away(cpu, a)

def oputil_float_ceil(cpu, a):
    # If positive, round to infinity (away), else, round to zero
    if a & cpu.signBitMask == 0:
        return oputil_float_round_away(cpu, a)
    else:
        return oputil_float_truncate(cpu, a)

def oputil_float_round(cpu, a):
    # Don't round if nan or infinity
    if oputil_is_float_nan(cpu, a) or a == cpu.posInf or a == cpu.negInf:
        return a

    # Split float and remove bias from exponent
    sign, exponent, mantissa = oputil_float_split(cpu, a)
    exponent -= cpu.exponentBias

    # If the bit for 0.5 is set then ceil, else, floor
    halfPos = cpu.fractionLen - exponent - 1

    # If the half position is less than zero, then the result is already rounded
    if halfPos < 0:
        return a

    # If the half is set, round away from zero, else, truncate
    if ((mantissa >> halfPos) & 1) == 1:
        return oputil_float_round_away(cpu, a)
    else:
        return oputil_float_truncate(cpu, a)

def oputil_float_div(cpu, a, b):
    # Special cases
    aIsZero = (a == cpu.posZero or a == cpu.negZero)
    bIsZero = (b == cpu.posZero or b == cpu.negZero)
    aIsInf = (a == cpu.posInf or a == cpu.negInf)
    bIsInf = (b == cpu.posInf or b == cpu.negInf)
    if oputil_is_float_nan(cpu, a) or oputil_is_float_nan(cpu, b) or (aIsInf and bIsInf) or (aIsZero and bIsZero):
        return cpu.defaultNan
    elif aIsZero or bIsInf:
        return (a & cpu.signBitMask) ^ (b & cpu.signBitMask)
    elif aIsInf or bIsZero:
        return cpu.posInf | ((a & cpu.signBitMask) ^ (b & cpu.signBitMask))

    # Get float parts
    aNegative, aExponent, aMantissa = oputil_float_split(cpu, a)
    bNegative, bExponent, bMantissa = oputil_float_split(cpu, b)

    # Left shift A's mantissa to avoid precision loss and late right shifting
    aMantissa <<= cpu.fractionLen

    # Divide fractions
    l = (cpu.fractionLen + 1) * 2
    cMantissa = oputil_div_twos(cpu, aMantissa, bMantissa, l)[0]

    # Subtract exponents
    cExponent = aExponent - bExponent + cpu.exponentBias

    # Normalize the result
    cFraction, cExponent = oputil_float_normalize(cMantissa, cExponent, 2 + cpu.fractionLen, cpu.fractionLen, cpu.fractionLen, cpu.exponentMax, cpu.fractionMask)

    # Done
    return oputil_float_construct(aNegative != bNegative, cFraction, cExponent, cpu.fractionLen, cpu.exponentLen)

def oputil_float_ln1px(cpu, x, n):
    # Calculate ln(1 + x) with n iterations of a maclaurin series
    # ln(1 + x) = sigma[r=1 to n]((-1)^(n + 1)*(x^r)/r)
    result = cpu.posZero
    # Starting at x^0 which is 1
    xpown = cpu.exponentBias << cpu.fractionLen
    for r in range(1, n + 1):
        # Increase power of x
        xpown = oputil_float_mul(cpu, xpown, x)
        # Get r as a parsed float
        rfloat = aqasmutil_num2float(float(r), cpu.exponentLen, cpu.fractionLen)
        # Handle division
        increment = oputil_float_div(cpu, xpown, rfloat)
        # Make sign negative if iteration is even
        if r % 2 == 0:
            increment |= cpu.signBitMask
        # Add iteration increment to result
        result = oputil_float_add(cpu, result, increment)

    # Return result
    return result

def oputil_float_exp(cpu, a, n):
    # Handle nans
    if oputil_is_float_nan(cpu, a):
        return cpu.defaultNan

    # Get float parts
    negative, exponent, mantissa = oputil_float_split(cpu, a)

    # Get fully unpacked value of float
    value = mantissa * (2 ** (exponent - cpu.exponentBias - cpu.fractionLen))

    # Special cases for big exponents
    if value > cpu.unbiasedExponentMax:
        if negative:
            return cpu.posZero
        else:
            return cpu.posInf

    # Separate value into whole part and fraction
    whole = int(floor(value))
    fraction = value - whole

    # Calculate result
    # exp = 2^e = 2^whole_e * 2^fraction_e
    result = (whole + cpu.exponentBias) << cpu.fractionLen
    if fraction > 0:
        # Use maclaurin series for 2^x {0 < x < 1}
        # 2^x = 1 + xln2 + ((x^2)(ln2)^2)/(2!) + ... + ((x^n)(ln2)^n)/(n!)
        # Fractional part is initially 1, and so is x^0, (ln2)^0 and the divisor
        fracPart = xpown = lntwopown = divisor = cpu.exponentBias << cpu.fractionLen
        x = aqasmutil_num2float(fraction, cpu.exponentLen, cpu.fractionLen)

        # Doing n iterations
        for r in range(1, n + 1):
            # Calculate r
            rfloat = aqasmutil_num2float(r, cpu.exponentLen, cpu.fractionLen)
            # Calculate divisor
            divisor = oputil_float_mul(cpu, rfloat, divisor)
            # Calculate ln2 power
            lntwopown = oputil_float_mul(cpu, lntwopown, cpu.lntwo)
            # Calculate x power
            xpown = oputil_float_mul(cpu, xpown, x)
            # Calculate iteration result
            iterResult = oputil_float_mul(cpu, xpown, lntwopown)
            iterResult = oputil_float_div(cpu, iterResult, divisor)
            # Add iteration result to fractional part of result
            fracPart = oputil_float_add(cpu, fracPart, iterResult)

        # Multiply fractional part of result with result for final power
        result = oputil_float_mul(cpu, result, fracPart)

    # Calculate reciprocal if exponent is negative
    if negative:
        result = oputil_float_div(cpu, cpu.exponentBias << cpu.fractionLen, result)

    # Return final result
    return result

def oputil_float_log(cpu, a, n):
    # Special cases
    if oputil_is_float_nan(cpu, a) or ((a & cpu.signBitMask) > 0):
        return cpu.defaultNan
    elif a == cpu.posZero:
        return cpu.negInf
    elif a == cpu.posInf:
        return cpu.posInf

    # Get float parts
    negative, exponent, mantissa = oputil_float_split(cpu, a)

    # Get fraction part of mantissa
    mantissaFrac = mantissa & cpu.fractionMask

    # Calculate result
    # log2(1.f * 2^e) = e + sigma[r=1 to n]((0.f^r) * ((-1)^(r + 1))/r)
    result = aqasmutil_num2float(exponent - cpu.exponentBias, cpu.exponentLen, cpu.fractionLen)
    if mantissaFrac != 0:
        # Note that this is the sigma part of the above formula. This part is
        # slow and is therefore avoided when not needed
        mantissaFracVal = mantissaFrac * (2 ** -cpu.fractionLen)
        fractionFloat = aqasmutil_num2float(mantissaFracVal, cpu.exponentLen, cpu.fractionLen)
        fractionExponent = oputil_float_ln1px(cpu, fractionFloat, n)
        fractionExponent = oputil_float_mul(cpu, fractionExponent, cpu.lntwo_rec)
        result = oputil_float_add(cpu, result, fractionExponent)

    # Return final result
    return result

## Instruction functions
def op_ldr(cpu):
    # LDR Rd, <memory ref>
    # Rd = <memory ref>
    # Since memory 
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_ldr(cpu, cpu.compiled[cpu.pc][2])

def eop_ldr_r(cpu):
    # Language extension
    # LDR Rd, Rn
    # Rd = memory[Rn]
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_ldr(cpu, cpu.reg[cpu.compiled[cpu.pc][2]])

def op_str(cpu):
    # STR Rd, <memory ref>
    # <memory ref> = Rd
    oputil_str(cpu, cpu.compiled[cpu.pc][2], cpu.reg[cpu.compiled[cpu.pc][1]])

def eop_str_da(cpu):
    # Language extension
    # STR #n, <memory ref>
    # <memory ref> = #n
    oputil_str(cpu, cpu.compiled[cpu.pc][2], cpu.compiled[cpu.pc][1])

def eop_str_rr(cpu):
    # Language extension
    # STR Rd, Rn
    # memory[Rn] = Rd
    oputil_str(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][1]])

def eop_str_dr(cpu):
    # Language extension
    # STR #n, Rn
    # memory[Rn] = #n
    oputil_str(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][1])

def op_add_d(cpu):
    # ADD Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn + <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_add_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)

def op_add_r(cpu):
    # ADD Rd, Rn, <operand3 [register overload]>
    # Rd = Rn + <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_add_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)

def op_sub_d(cpu):
    # SUB Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn - <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_sub_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)

def op_sub_r(cpu):
    # SUB Rd, Rn, <operand3 [register overload]>
    # Rd = Rn - <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_sub_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)

def eop_mul_d(cpu):
    # MUL Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn * <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_mul_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)

def eop_mul_r(cpu):
    # MUL Rd, Rn, <operand3 [register overload]>
    # Rd = Rn * <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_mul_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)

def eop_div_d(cpu):
    # DIV Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn // <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_div_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)[0]

def eop_div_r(cpu):
    # DIV Rd, Rn, <operand3 [register overload]>
    # Rd = Rn // <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_div_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)[0]

def eop_rem_d(cpu):
    # REM Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn % <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_div_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)[1]

def eop_rem_r(cpu):
    # REM Rd, Rn, <operand3 [register overload]>
    # Rd = Rn % <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_div_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)[1]

def op_mov_d(cpu):
    # MOV Rd, <operand2 [decimal overload]>
    # Rd = <operand2>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.compiled[cpu.pc][2]

def op_mov_r(cpu):
    # MOV Rd, <operand2 [register overload]>
    # Rd = <operand2>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]]

def eop_mov_f(cpu):
    # MOV Rd, <operand2 [floating overload]>
    # Rd = <operand2>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.compiled[cpu.pc][2]

def op_cmp_d(cpu):
    # CMP Rn, <operand2 [decimal overload]>
    # temp = Rn - <operand2>
    # if temp is 0 then set zero flag
    # if temp is negative then set sign flag
    temp = oputil_sub_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][1]], cpu.compiled[cpu.pc][2], cpu.wordLength)
    cpu.zero = (temp == 0)
    # If MSB is set, then the result is negative, therefore, if the result is
    # greater than the signed integer max, then the MSB is set and the result
    # is negative. Same is done in op_cmp_r
    cpu.sign = (temp > cpu.intMax)

def op_cmp_r(cpu):
    # CMP Rn, <operand2 [register overload]>
    # temp = Rn - <operand2>
    # if temp is 0 then set zero flag
    # if temp is negative then set sign flag
    temp = oputil_sub_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][1]], cpu.reg[cpu.compiled[cpu.pc][2]], cpu.wordLength)
    cpu.zero = (temp == 0)
    cpu.sign = (temp > cpu.intMax)

def op_b_l(cpu):
    # B <label>
    # pc = line number corresponding to label
    # set blast flag
    # (label line internally stored as line number)
    cpu.pc = cpu.compiled[cpu.pc][1]
    cpu.blast = True

def eop_b_r(cpu):
    # B Rn
    # if Rn < 0 or Rn > PCmax:
    #   push GP to IRQ
    # else:
    #   pc = Rn
    #   set blast flag
    newpc = cpu.reg[cpu.compiled[cpu.pc][1]]
    if newpc > cpu.intMax or newpc > (len(cpu.compiled) - 1):
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.pc = newpc
        cpu.blast = True

def op_beq_l(cpu):
    # BEQ <label>
    # if zero flag set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if cpu.zero:
        cpu.pc = cpu.compiled[cpu.pc][1]
        cpu.blast = True

def eop_beq_r(cpu):
    # BEQ Rn
    # if Rn < 0 or Rn > PCmax:
    #   push GP to IRQ
    # else if zero flag set:
    #   pc = Rn
    #   set blast flag
    newpc = cpu.reg[cpu.compiled[cpu.pc][1]]
    if newpc > cpu.intMax or newpc > (len(cpu.compiled) - 1):
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    elif cpu.zero:
        cpu.pc = newpc
        cpu.blast = True

def op_bne_l(cpu):
    # BNE <label>
    # if zero flag not set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if not cpu.zero:
        cpu.pc = cpu.compiled[cpu.pc][1]
        cpu.blast = True

def eop_bne_r(cpu):
    # BNE Rn
    # if Rn < 0 or Rn > PCmax:
    #   push GP to IRQ
    # else if zero flag not set:
    #   pc = Rn
    #   set blast flag
    newpc = cpu.reg[cpu.compiled[cpu.pc][1]]
    if newpc > cpu.intMax or newpc > (len(cpu.compiled) - 1):
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    elif not cpu.zero:
        cpu.pc = newpc
        cpu.blast = True

def op_bgt_l(cpu):
    # BGT <label>
    # if sign flag not set and zero flag not set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if not cpu.sign and not cpu.zero:
        cpu.pc = cpu.compiled[cpu.pc][1]
        cpu.blast = True

def eop_bgt_r(cpu):
    # BGT Rn
    # if Rn < 0 or Rn > PCmax:
    #   push GP to IRQ
    # else if sign flag not set and zero flag not set:
    #   pc = Rn
    #   set blast flag
    newpc = cpu.reg[cpu.compiled[cpu.pc][1]]
    if newpc > cpu.intMax or newpc > (len(cpu.compiled) - 1):
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    elif not cpu.sign and not cpu.zero:
        cpu.pc = newpc
        cpu.blast = True

def op_blt_l(cpu):
    # BLT <label>
    # if sign flag set
    #   pc = line number corresponding to label
    #   set blast flag
    # (label line internally stored as line number)
    if cpu.sign:
        cpu.pc = cpu.compiled[cpu.pc][1]
        cpu.blast = True

def eop_blt_r(cpu):
    # BLT Rn
    # if Rn < 0 or Rn > PCmax:
    #   push GP to IRQ
    # else if sign flag set:
    #   pc = Rn
    #   set blast flag
    newpc = cpu.reg[cpu.compiled[cpu.pc][1]]
    if newpc > cpu.intMax or newpc > (len(cpu.compiled) - 1):
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    elif cpu.sign:
        cpu.pc = newpc
        cpu.blast = True

def op_and_d(cpu):
    # AND Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn & <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]] & cpu.compiled[cpu.pc][3]

def op_and_r(cpu):
    # AND Rd, Rn, <operand3 [register overload]>
    # Rd = Rn & <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]] & cpu.reg[cpu.compiled[cpu.pc][3]]

def op_orr_d(cpu):
    # ORR Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn | <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]] | cpu.compiled[cpu.pc][3]

def op_orr_r(cpu):
    # ORR Rd, Rn, <operand3 [register overload]>
    # Rd = Rn | <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]] | cpu.reg[cpu.compiled[cpu.pc][3]]

def op_eor_d(cpu):
    # EOR Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn ^ <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]] ^ cpu.compiled[cpu.pc][3]

def op_eor_r(cpu):
    # EOR Rd, Rn, <operand3 [register overload]>
    # Rd = Rn ^ <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.reg[cpu.compiled[cpu.pc][2]] ^ cpu.reg[cpu.compiled[cpu.pc][3]]

def op_mvn_d(cpu):
    # MVN Rd, <operand2 [decimal overload]>
    # Rd = ~<operand2>
    cpu.reg[cpu.compiled[cpu.pc][1]] = ~cpu.compiled[cpu.pc][3]

def op_mvn_r(cpu):
    # MVN Rd, <operand2 [register overload]>
    # Rd = ~<operand2>
    cpu.reg[cpu.compiled[cpu.pc][1]] = ~cpu.reg[cpu.compiled[cpu.pc][3]]

def op_lsl_d(cpu):
    # LSL Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn << <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_shift_left(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)

def op_lsl_r(cpu):
    # LSL Rd, Rn, <operand3 [register overload]>
    # Rd = Rn << <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_shift_left(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)

def op_lsr_d(cpu):
    # LSR Rd, Rn, <operand3 [decimal overload]>
    # Rd = Rn >> <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_shift_right(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3], cpu.wordLength)

def op_lsr_r(cpu):
    # LSR Rd, Rn, <operand3 [register overload]>
    # Rd = Rn >> <operand3>
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_shift_right(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]], cpu.wordLength)

def op_halt(cpu):
    # HALT
    # set halt flag
    cpu.halt = True

def eop_int(cpu):
    # INT <operand1 [register overload only]>
    # if <operand1> > 127 or <operand1> < 0 then push GP fault to IRQ
    # else push IRQ number to IRQ
    irq = cpu.compiled[cpu.pc][1]
    if irq > 127 or irq < 0:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.irq.append(irq)

def eop_iret(cpu):
    # IRET
    # if int flag set
    #   pc = intpc
    #   unset interrupt cycle flag
    #   set branch last flag
    # else push GP fault to IRQ
    if cpu.intc:
        cpu.pc = cpu.intpc
        cpu.intc = False
        cpu.blast = True
        cpu.zero = cpu.intzero
        cpu.sign = cpu.intsign
    else:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)

def eop_mivt(cpu):
    # MIVT <operand1 [register overload only]>, <label>
    # if <operand1> > 127 or <operand1> < 0 then push GP fault to IRQ
    # else IVT[<operand1>] = line number corresponding to label
    irq = cpu.compiled[cpu.pc][1]
    if irq > 127 or irq < 0:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.ivt[cpu.compiled[cpu.pc][1]] = cpu.compiled[cpu.pc][2]

def eop_in_d(cpu):
    # IN Rd, <operand2 [decimal overload]>
    # if <operand2> > 127 or <operand2> < 0 or ioConfig[<operand2>] invalid
    #   push GP fault to IRQ
    # elif ioInput[<operand2>] empty
    #   push IO exception to IRQ
    # else
    #   Rd = dequeue ioInput[<operand2>]
    port = cpu.compiled[cpu.pc][2]
    if port > 127 or port < 0 or cpu.ioConfig[port][1] == False:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    elif len(cpu.ioInput[port]) == 0:
        cpu.irq.append(IRQ_IO_EXCEPTION)
    else:
        cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.ioInput[port].pop(0)

def eop_in_r(cpu):
    # IN Rd, <operand2 [register overload]>
    # if <operand2> > 127 or <operand2> < 0 or ioConfig[<operand2>] invalid
    #   push GP fault to IRQ
    # elif ioInput[<operand2>] empty
    #   push IO exception to IRQ
    # else
    #   Rd = dequeue ioInput[<operand2>]
    port = cpu.reg[cpu.compiled[cpu.pc][2]]
    if port > 127 or port < 0 or cpu.ioConfig[port][1] == False:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    elif len(cpu.ioInput[port]) == 0:
        cpu.irq.append(IRQ_IO_EXCEPTION)
    else:
        cpu.reg[cpu.compiled[cpu.pc][1]] = cpu.ioInput[port].pop(0)

def eop_out_rd(cpu):
    # OUT <operand1 [register overload]>, <operand2 [decimal overload]>
    # if <operand2> > 127 or <operand2> < 0 or ioConfig[<operand2>] invalid
    #   push GP fault to IRQ
    # else
    #   send <operand1> to I/O port <operand2>
    port = cpu.compiled[cpu.pc][2]
    if port > 127 or port < 0 or cpu.ioConfig[port][1] == False:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.ioOutput(port, cpu.reg[cpu.compiled[cpu.pc][1]])

def eop_out_rr(cpu):
    # OUT <operand1 [register overload]>, <operand2 [register overload]>
    # if <operand2> > 127 or <operand2> < 0 or ioConfig[<operand2>] invalid
    #   push GP fault to IRQ
    # else
    #   send <operand1> to I/O port <operand2>
    port = cpu.reg[cpu.compiled[cpu.pc][2]]
    if port > 127 or port < 0 or cpu.ioConfig[port][1] == False:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.ioOutput(port, cpu.reg[cpu.compiled[cpu.pc][1]])

def eop_out_dd(cpu):
    # OUT <operand1 [decimal overload]>, <operand2 [decimal overload]>
    # if <operand2> > 127 or <operand2> < 0 or ioConfig[<operand2>] invalid
    #   push GP fault to IRQ
    # else
    #   send <operand1> to I/O port <operand2>
    port = cpu.compiled[cpu.pc][2]
    if port > 127 or port < 0 or cpu.ioConfig[port][1] == False:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.ioOutput(port, cpu.compiled[cpu.pc][1])

def eop_out_dr(cpu):
    # OUT <operand1 [decimal overload]>, <operand2 [register overload]>
    # if <operand2> > 127 or <operand2> < 0 or ioConfig[<operand2>] invalid
    #   push GP fault to IRQ
    # else
    #   send <operand1> to I/O port <operand2>
    port = cpu.reg[cpu.compiled[cpu.pc][2]]
    if port > 127 or port < 0 or cpu.ioConfig[port][1] == False:
        cpu.irq.append(IRQ_GENERAL_PROTECTION_FAULT)
    else:
        cpu.ioOutput(port, cpu.compiled[cpu.pc][1])

def eop_fadd_f(cpu):
    # FADD Rd, Rn, <operand3 [floating overload]>
    # Rdf = Rnf + <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_add(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3])

def eop_fadd_r(cpu):
    # FADD Rd, Rn, <operand3 [register overload]>
    # Rdf = Rnf + <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_add(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]])

def eop_fsub_f(cpu):
    # FSUB Rd, Rn, <operand3 [floating overload]>
    # Rdf = Rnf - <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_add(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3] ^ cpu.signBitMask)

def eop_fsub_r(cpu):
    # FSUB Rd, Rn, <operand3 [register overload]>
    # Rdf = Rnf - <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_add(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]] ^ cpu.signBitMask)

def eop_fcmp_f(cpu):
    # FCMP Rn, <operand2 [floating overload]>
    # if isnan(Rnf) or isnan(<operand2>):
    #   push IA fault to IRQ
    # else:
    #   if Rnf == -0:
    #     Rn = 0
    #   if <operand2> == -0:
    #     <operand2> = 0
    #   save operands' sign bits
    #   if Rnf's sign set and <operand2>f's sign not set:
    #     unset zero flag
    #     set sign flag
    #   elif Rnf's sign not set and <operand2>f's sign set:
    #     unset zero flag
    #     unset sign flag
    #   else:
    #     unset both operands' sign bits
    #     temp = Rn - <operand2>
    #     if temp is 0 then set zero flag
    #     if Rnf's saved sign bit is set:
    #       if temp is positive then set sign flag
    #     else:
    #       if temp is negative then set sign flag
    a = cpu.reg[cpu.compiled[cpu.pc][1]]
    b = cpu.compiled[cpu.pc][2]
    if oputil_is_float_nan(cpu, a) or oputil_is_float_nan(cpu, b):
        cpu.irq.append(IRQ_INVALID_ARITHMETIC)
    else:
        if a == cpu.negZero:
            a = 0
        if b == cpu.negZero:
            b = 0
        aSign = (a & cpu.signBitMask > 0)
        bSign = (b & cpu.signBitMask > 0)
        if aSign and not bSign:
            cpu.zero = False
            cpu.sign = True
        elif not aSign and bSign:
            cpu.zero = False
            cpu.sign = False
        else:
            a &= cpu.signBitMask - 1
            b &= cpu.signBitMask - 1
            temp = oputil_sub_twos(cpu, a, b, cpu.wordLength)
            cpu.zero = (temp == 0)
            if aSign:
                cpu.sign = ((temp >> (cpu.exponentLen + cpu.fractionLen)) == 0)
            else:
                cpu.sign = ((temp >> (cpu.exponentLen + cpu.fractionLen)) == 1)

def eop_fcmp_r(cpu):
    # FCMP Rn, <operand2 [register overload]>
    # if isnan(Rnf) or isnan(<operand2>):
    #   push IA fault to IRQ
    # else:
    #   if Rnf == -0:
    #     Rn = 0
    #   if <operand2> == -0:
    #     <operand2> = 0
    #   save operands' sign bits
    #   if Rnf's sign set and <operand2>f's sign not set:
    #     unset zero flag
    #     set sign flag
    #   elif Rnf's sign not set and <operand2>f's sign set:
    #     unset zero flag
    #     unset sign flag
    #   else:
    #     unset both operands' sign bits
    #     temp = Rn - <operand2>
    #     if temp is 0 then set zero flag
    #     if Rnf's saved sign bit is set:
    #       if temp is positive then set sign flag
    #     else:
    #       if temp is negative then set sign flag
    a = cpu.reg[cpu.compiled[cpu.pc][1]]
    b = cpu.reg[cpu.compiled[cpu.pc][2]]
    if oputil_is_float_nan(cpu, a) or oputil_is_float_nan(cpu, b):
        cpu.irq.append(IRQ_INVALID_ARITHMETIC)
    else:
        if a == cpu.negZero:
            a = 0
        if b == cpu.negZero:
            b = 0
        aSign = (a & cpu.signBitMask > 0)
        bSign = (b & cpu.signBitMask > 0)
        if aSign and not bSign:
            cpu.zero = False
            cpu.sign = True
        elif not aSign and bSign:
            cpu.zero = False
            cpu.sign = False
        else:
            a &= cpu.signBitMask - 1
            b &= cpu.signBitMask - 1
            temp = oputil_sub_twos(cpu, a, b, cpu.wordLength)
            cpu.zero = (temp == 0)
            if aSign:
                cpu.sign = ((temp >> (cpu.exponentLen + cpu.fractionLen)) == 0)
            else:
                cpu.sign = ((temp >> (cpu.exponentLen + cpu.fractionLen)) == 1)

def eop_fmul_f(cpu):
    # FMUL Rd, Rn, <operand3 [floating overload]>
    # Rdf = Rnf * <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_mul(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3])

def eop_fmul_r(cpu):
    # FMUL Rd, Rn, <operand3 [register overload]>
    # Rdf = Rnf * <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_mul(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]])

def eop_ftrunc(cpu):
    # FTRUNC Rd, Rn
    # Rdf = truncate(Rnf)
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_truncate(cpu, cpu.reg[cpu.compiled[cpu.pc][2]])

def eop_fraway(cpu):
    # FRAWAY Rd, Rn
    # Rdf = round_away_from_zero(Rnf)
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_round_away(cpu, cpu.reg[cpu.compiled[cpu.pc][2]])

def eop_ffloor(cpu):
    # FFLOOR Rd, Rn
    # Rdf = floor(Rnf)
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_floor(cpu, cpu.reg[cpu.compiled[cpu.pc][2]])

def eop_fceil(cpu):
    # FCEIL Rd, Rn
    # Rdf = floor(Rnf)
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_ceil(cpu, cpu.reg[cpu.compiled[cpu.pc][2]])

def eop_fround(cpu):
    # FROUND Rd, Rn
    # Rdf = round(Rnf)
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_round(cpu, cpu.reg[cpu.compiled[cpu.pc][2]])

def eop_fdiv_f(cpu):
    # FDIV Rd, Rn, <operand3 [floating overload]>
    # Rdf = Rnf / <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_div(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.compiled[cpu.pc][3])

def eop_fdiv_r(cpu):
    # FDIV Rd, Rn, <operand3 [register overload]>
    # Rdf = Rnf / <operand3>f
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_div(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], cpu.reg[cpu.compiled[cpu.pc][3]])

def eop_fexp(cpu):
    # FEXP Rd, Rn
    # Rdf = 2f ^ Rnf
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_exp(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], 25)

def eop_flog(cpu):
    # FLOG Rd, Rn
    # Rdf = log2(Rnf)
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_float_log(cpu, cpu.reg[cpu.compiled[cpu.pc][2]], 50)

def eop_ftoi(cpu):
    # FTOI Rd, Rn
    # if Rnf can't be represented as an integer:
    #   push IA fault to IRQ
    # else:
    #   Rd = Rnf
    a = cpu.reg[cpu.compiled[cpu.pc][2]]

    # Handle nan and infinities
    if oputil_is_float_nan(cpu, a) or a == cpu.posInf or a == cpu.negInf:
        cpu.irq.append(IRQ_INVALID_ARITHMETIC)
        return

    # Parse float and truncate it
    fval = aqasmutil_parse_float(cpu, oputil_float_truncate(cpu, a))

    # Handle overflow
    if fval > cpu.intMax or fval < cpu.intMin:
        cpu.irq.append(IRQ_INVALID_ARITHMETIC)
        return

    # Convert
    cpu.reg[cpu.compiled[cpu.pc][1]] = aqasmutil_num2int(fval, cpu.wordLength)

def eop_itof(cpu):
    # ITOF Rd, Rn
    # Rdf = Rn
    cpu.reg[cpu.compiled[cpu.pc][1]] = aqasmutil_num2float(aqasmutil_parse_int(cpu, cpu.reg[cpu.compiled[cpu.pc][2]]), cpu.exponentLen, cpu.fractionLen)

def eop_inc(cpu):
    # INC Rd
    # Rd = Rd + 1
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_add_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][1]], 1, cpu.wordLength)

def eop_dec(cpu):
    # DEC Rd
    # Rd = Rd - 1
    cpu.reg[cpu.compiled[cpu.pc][1]] = oputil_sub_twos(cpu, cpu.reg[cpu.compiled[cpu.pc][1]], 1, cpu.wordLength)

def eop_ldpc(cpu):
    # LDPC Rd
    # Rd = PC
    cpu.reg[cpu.compiled[cpu.pc][1]] = aqasmutil_num2int(cpu.pc, cpu.wordLength)

## Instruction definitions for compiler
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
            ((0, compiler.token.register),),
            ((0, compiler.token.address), (1, compiler.token.register))
           ),
    "str": (
            {0: (op_str, False), 1: (eop_str_da, True),
             2: (eop_str_rr, True), 3: (eop_str_dr, True)},
            ((0, compiler.token.register), (1, compiler.token.decimal)),
            ((0, compiler.token.address), (2, compiler.token.register))
           ),
    "add": (
            {0: (op_add_d, False), 1: (op_add_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "sub": (
            {0: (op_sub_d, False), 1: (op_sub_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "mov": (
            {0: (op_mov_d, False), 1: (op_mov_r, False), 2: (eop_mov_f, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register), (2, compiler.token.floating))
           ),
    "cmp": (
            {0: (op_cmp_d, False), 1: (op_cmp_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "b":   (
            {0: (op_b_l, False), 1: (eop_b_r, True)},
            ((0, compiler.token.labelid), (1, compiler.token.register))
           ),
    "beq": (
            {0: (op_beq_l, False), 1: (eop_beq_r, True)},
            ((0, compiler.token.labelid), (1, compiler.token.register))
           ),
    "bne": (
            {0: (op_bne_l, False), 1: (eop_bne_r, True)},
            ((0, compiler.token.labelid), (1, compiler.token.register))
           ),
    "bgt": (
            {0: (op_bgt_l, False), 1: (eop_bgt_r, True)},
            ((0, compiler.token.labelid), (1, compiler.token.register))
           ),
    "blt": (
            {0: (op_blt_l, False), 1: (eop_blt_r, True)},
            ((0, compiler.token.labelid), (1, compiler.token.register))
           ),
    "and": (
            {0: (op_and_d, False), 1: (op_and_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "orr": (
            {0: (op_orr_d, False), 1: (op_orr_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "eor": (
            {0: (op_eor_d, False), 1: (op_eor_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "mvn": (
            {0: (op_mvn_d, False), 1: (op_mvn_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "lsl": (
            {0: (op_lsl_d, False), 1: (op_lsl_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "lsr": (
            {0: (op_lsr_d, False), 1: (op_lsr_r, False)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "halt":(
            {0: (op_halt, False)},
           ),
    "mul": (
            {0: (eop_mul_d, True), 1: (eop_mul_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "div": (
            {0: (eop_div_d, True), 1: (eop_div_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "rem": (
            {0: (eop_rem_d, True), 1: (eop_rem_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "int": (
            {0: (eop_int, True)},
            ((0, compiler.token.decimal),)
           ),
    "iret":(
            {0: (eop_iret, True)},
           ),
    "mivt":(
            {0: (eop_mivt, True)},
            ((0, compiler.token.decimal),),
            ((0, compiler.token.labelid),)
           ),
    "in":  (
            {0: (eop_in_d, True), 1: (eop_in_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.decimal), (1, compiler.token.register))
           ),
    "out": (
            {0: (eop_out_rd, True), 1: (eop_out_dd, True),
             2: (eop_out_rr, True), 3: (eop_out_dr, True)},
            ((0, compiler.token.register), (1, compiler.token.decimal)),
            ((0, compiler.token.decimal), (2, compiler.token.register))
           ),
    "fadd":(
            {0: (eop_fadd_f, True), 1: (eop_fadd_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.floating), (1, compiler.token.register))
           ),
    "fsub":(
            {0: (eop_fsub_f, True), 1: (eop_fsub_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.floating), (1, compiler.token.register))
           ),
    "fcmp":(
            {0: (eop_fcmp_f, True), 1: (eop_fcmp_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.floating), (1, compiler.token.register))
           ),
    "fmul":(
            {0: (eop_fmul_f, True), 1: (eop_fmul_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.floating), (1, compiler.token.register))
           ),
    "fdiv":(
            {0: (eop_fdiv_f, True), 1: (eop_fdiv_r, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),),
            ((0, compiler.token.floating), (1, compiler.token.register))
           ),
    "ftrunc":(
            {0: (eop_ftrunc, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "fraway":(
            {0: (eop_fraway, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "ffloor":(
            {0: (eop_ffloor, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "fceil":(
            {0: (eop_fceil, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "fround":(
            {0: (eop_fround, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "fexp":(
            {0: (eop_fexp, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "flog":(
            {0: (eop_flog, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "ftoi":(
            {0: (eop_ftoi, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "itof":(
            {0: (eop_itof, True)},
            ((0, compiler.token.register),),
            ((0, compiler.token.register),)
           ),
    "inc": (
            {0: (eop_inc, True)},
            ((0, compiler.token.register),)
           ),
    "dec": (
            {0: (eop_dec, True)},
            ((0, compiler.token.register),)
           ),
    "ldpc":(
            {0: (eop_ldpc, True)},
            ((0, compiler.token.register),)
           )
}

## Interpreter class for emulating a cpu running AQA assembly
class aqasm:
    def __init__(self, code = "", extensions = False, bytesPerWord = 1, memWords = None):
        self.ioReset()
        self.compile_code(code, extensions, bytesPerWord, memWords)

    def compile_code(self, code, extensions = False, bytesPerWord = 1, memWords = None):
        if memWords == None:
            memWords = 2 ** (bytesPerWord * 8)
        else:
            if memWords < 0:
                raise ValueError("Memory size cannot be negative")
            if memWords > 2 ** (bytesPerWord * 8):
                raise ValueError("Memory size cannot be greater than 2 ^ wordLength, since it becomes unaddressable")
        # self.extensions has no effect, it is just so that outer code can check
        # whether the code was compiled with extensions or not
        self.extensions = extensions
        # Number of bytes and bits per word
        self.bytesPerWord = bytesPerWord
        self.wordLength = bytesPerWord * 8
        # Integer ranges
        self.uintMax = 2 ** self.wordLength - 1
        self.intMin = -(2 ** (self.wordLength - 1))
        self.intMax = 2 ** (self.wordLength - 1) - 1
        # Floating point helper values
        self.exponentLen = 3 * bytesPerWord
        self.fractionLen = 5 * bytesPerWord - 1
        self.exponentMax = 2 ** self.exponentLen - 1
        self.exponentBias = 2 ** (self.exponentLen - 1) - 1
        self.unbiasedExponentMax = self.exponentMax - self.exponentBias - 1
        self.signBitMask = 2 ** (self.fractionLen + self.exponentLen)
        self.fractionMask = 2 ** self.fractionLen - 1
        self.exponentMask = self.exponentMax << self.fractionLen
        self.posZero = 0
        self.negZero = self.signBitMask
        self.posInf = self.exponentMask
        self.negInf = self.posInf | self.signBitMask
        self.defaultNan = 2 ** (self.exponentLen + self.fractionLen) - 1
        self.lntwo = aqasmutil_num2float(0.6931471806, self.exponentLen, self.fractionLen)
        self.lntwo_rec = aqasmutil_num2float(1.442695041, self.exponentLen, self.fractionLen)
        # Number of words and bytes available for memory
        self.memWords = memWords
        self.memBytes = memWords * bytesPerWord
        # Passed source code split into lines
        self.code = code.splitlines()
        # Code passed to compiler
        self.compiled, times = compiler.compile_asm(self.code, extensions, self.intMin, self.intMax, self.memWords - 1, self.bytesPerWord)
        # Reset all flags and memory
        self.reset()
        # Halt if no instructions or NOOPs
        if len(self.compiled) == 0:
            self.halt = True
        return times

    def reset(self):
        # Memory
        self.mem = zeros(self.memBytes, dtype=uint8)
        # Registers
        self.reg = [0] * 13
        # IRQ
        self.irq = deque()
        # IVT. Reset to default interrupt vector table. A none value represents
        # the default action for that IRQ number. For division by 0 and faults,
        # the CPU halts and throws an exception, and for all other IRQ numbers,
        # nothing is done
        self.ivt = [None] * 128
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
        # Interrupt cycle flag. If currently running an interrupt, this is true
        self.intc = False
        # Interrupt cycle saved flags
        self.intpc = 0
        self.intzero = False
        self.intsign = False

    def step(self):
        # Do nothing if CPU halted or if there are no instructions
        if self.halt or len(self.compiled) == 0:
            return

        # Run instruction if not a NOOP (empty line)
        if self.compiled[self.pc] != None:
            self.compiled[self.pc][0](self)

            # "Short" CPU to preserve flags
            if self.halt:
                return

        # Increment program counter if branch last flag wasn't set
        if not self.blast:
            self.pc += 1

        # Clear branch last flag
        self.blast = False
        
        # If there are interrupts available, start the interrupt service routine
        # by preparing all flags for the next cycle, if there is a handler.
        # Don't do this if already in an ISR cycle
        if not self.intc and len(self.irq) > 0:
            # Pop IRQ
            irq = self.irq.popleft()
            isr_pc = self.ivt[irq]

            # Check if the default handler should be run
            if isr_pc == None:
                # If the IRQ is a fault, then throw the corresponding exception
                # and halt, else, NOP
                if irq == IRQ_DIVISION_BY_ZERO:
                    self.halt = True
                    raise ValueError("Division by 0: Default handler for IRQ {:d} called. Halting".format(IRQ_DIVISION_BY_ZERO))
                elif irq == IRQ_PAGE_FAULT:
                    self.halt = True
                    raise ValueError("Page fault: Default handler for IRQ {:d} called. Halting".format(IRQ_PAGE_FAULT))
                elif irq == IRQ_GENERAL_PROTECTION_FAULT:
                    self.halt = True
                    raise ValueError("General protection fault: Default handler for IRQ {:d} called. Halting".format(IRQ_GENERAL_PROTECTION_FAULT))
                elif irq == IRQ_INVALID_ARITHMETIC:
                    self.halt = True
                    raise ValueError("Invalid arithmetic operand: Default handler for IRQ {:d} called. Halting".format(IRQ_INVALID_ARITHMETIC))
            else:
                self.intc = True
                self.intpc = self.pc
                self.pc = isr_pc
                self.intzero = self.zero
                self.intsign = self.sign

        # If past all code, halt CPU
        if self.pc >= len(self.compiled):
            self.halt = True

    def ioReset(self):
        # Reset I/O configuration table
        self.ioConfig = [None] * 128
        self.ioInput = [None] * 128

        for i in range(0, 128):
            self.ioConfig[i] = (None, False)
            self.ioInput[i] = []

    def ioRegister(self, port, callback):
        # Add callback to I/O output at port, unless port already taken
        if port < 0 or port > 127 or self.ioConfig[port][1] == True:
            raise ValueError("Hardware error: Invalid port number or already taken")
        self.ioConfig[port] = (callback, True)

    def ioInputPush(self, port, data):
        # Add input data at port
        if port < 0 or port > 127 or self.ioConfig[port][1] == False:
            raise ValueError("Hardware error: Invalid port number or not registered")
        self.ioInput[port].append(data)

    def ioOutput(self, port, data):
        # Call callback with output data, unless I/O is registered but doesn't
        # have a callback
        if port < 0 or port > 127 or self.ioConfig[port][1] == False:
            raise ValueError("Hardware error: Invalid port number or not registered")
        if self.ioConfig[port][0] != None:
            self.ioConfig[port][0](data)
