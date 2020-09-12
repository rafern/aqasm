from enum import Enum
import interpreter
import time
import re

## Lexical analysis tokens
class token(Enum):
    separator  = 0
    decimal    = 1
    floating   = 2
    register   = 3
    address    = 4
    label      = 5
    identifier = 6
    # Special identifier. Matches with the identifier token but in the parsing
    # stage it converts the identifier to its numerical value (line number)
    labelid    = 7
    # Syntax highlighter exclusive tokens. Not used during compilation
    comment    = 8
    whitespace = 9
    error      = 10

## Validation regexes
# Valid code line regex
valid_regex = re.compile("^([a-zA-Z_-]+:)?(\t+[a-zA-Z]+(\s+(#(-?[0-9]+(\.[0-9]+)?|-?inf|nan)|[rR][0-9]+|[0-9]+|[a-zA-Z_-]+)(\s*,\s*(#(-?[0-9]+(\.[0-9]+)?|-?inf|nan)|[rR][0-9]+|[0-9]+|[a-zA-Z_-]+))*)?)?\s*(;.*)?$")
# Error regexes
symbol_regex = re.compile("^[ \ta-zA-Z0-9#,\.:_-]*(;.*)?$")
spaces_regex = re.compile("^ ")
tabs_regex   = re.compile("^([a-zA-Z_-]+:)?\t")
labelc_regex = re.compile("^[a-zA-Z_-]*[\s0-9#,\.][\s0-9#,\.a-zA-Z_-]*:")
labeli_regex = re.compile("^:")
## Lexical analysis regexes
# Regex for splitting lines into fields
split_regex = re.compile("(,)|(\s+)|(;.*$)")
# Regex for each token type. Note that separators (commas) dont need regexes
decimal_regex    = re.compile("^#-?[0-9]+$")
floating_regex   = re.compile("^#(-?[0-9]+\.[0-9]+|nan|-?inf)$")
# Registers can be more than 12 here. Handle registers higher than 12 later
register_regex   = re.compile("^[rR][0-9]+$")
address_regex    = re.compile("^[0-9]+$")
label_regex      = re.compile("^[a-zA-Z_-]+:$")
# Identifiers can represent both opcodes and label identifiers for B opcode
identifier_regex = re.compile("^[a-zA-Z_-]+$")
# Comment token. Does nothing
comment_regex    = re.compile("^;")
# Whitespace token. Does nothing
whitespace_regex = re.compile("^\s+$")

# Validate line
def compiler_validation(line):
    # Check if the line is valid code.
    # Syntax meaning:
    # (group)<optional group>{optional repeatable group}
    # Valid code
    # <label><<tabs><(opcode)<(whitespaces)(operand){<whitespaces>(comma)<whitespaces>(operand)}>><whitespaces><comment>
    if not valid_regex.match(line):
        # Check if code contains invalid characters
        if not symbol_regex.match(line):
            raise ValueError("Syntax error: Unknown symbol")
        # Check if code contains more than 1 labels
        elif line.count(':') > 1:
            raise ValueError("Syntax error: More than 1 label")
        # Check if code contains preceding whitespaces
        elif spaces_regex.match(line):
            raise ValueError("Syntax error: Preceding whitespaces")
        # Check if code is code without labels but contains no tabs
        elif not tabs_regex.match(line):
            raise ValueError("Syntax error: No tab before code")
        # Check if code contains a label with no identifier
        elif labeli_regex.match(line):
            raise ValueError("Syntax error: Label with no identifier")
        # Check if code contains a label with disallowed characters for
        # label identifiers
        elif labelc_regex.match(line):
            raise ValueError("Syntax error: Disallowed characters in label identifier")
        # If match failed but because of none of the previous syntax errors,
        # raise a generic syntax error exception
        else:
            raise ValueError("Generic syntax error: Invalid syntax")

# Lexically analyse line
def compiler_lexical_analysis(line, wordMin, wordMax, addrMax, bytesPerWord, extensionsEnabled):
    # Calculate floating point bits
    exponentLen = 3 * bytesPerWord
    fractionLen = 5 * bytesPerWord - 1

    # Split into fields
    line = list(filter(None, split_regex.split(line)))

    # Classify fields into specific tokens and save their positions for
    # highlighting
    tokens = list()
    positions = list()
    errors = list()
    offset = 0
    for field in line:
        if field == ',':
            tokens.append([token.separator])
            positions.append((offset, token.separator))
        elif decimal_regex.match(field):
            try:
                decVal = int(field[1:])
                if wordMin != None and decVal < wordMin:
                    errors.append("Architecture error: Constant " + str(decVal)
                                  + " below word minimum of " + str(wordMin))
                    positions.append((offset, token.error))
                elif wordMax != None and decVal > wordMax:
                    errors.append("Architecture error: Constant " + str(decVal)
                                  + " above word maximum of " + str(wordMax))
                    positions.append((offset, token.error))
                else:
                    tokens.append([token.decimal, interpreter.aqasmutil_num2int(decVal, bytesPerWord * 8)])
                    positions.append((offset, token.decimal))
            except:
                errors.append("Syntax error: Invalid decimal. Not a number")
                positions.append((offset, token.error))
        elif floating_regex.match(field):
            if extensionsEnabled:
                floatVal = float(field[1:])
                # Special case if input is negative zero, since python treats
                # zero and negative zero as the same (thankfully)
                if floatVal == 0 and field[1] == '-':
                    tokens.append([token.floating, 1 << (exponentLen + fractionLen)])
                else:
                    tokens.append([token.floating, interpreter.aqasmutil_num2float(floatVal, exponentLen, fractionLen)])
                positions.append((offset, token.floating))
            else:
                errors.append("Architecture error: Floating point numbers need extensions enabled")
                positions.append((offset, token.error))
        elif register_regex.match(field):
            try:
                regVal = int(field[1:])
                if not regVal in range(0, 13):
                    errors.append("Semantic error: Invalid register number "
                                  + str(regVal))
                    positions.append((offset, token.error))
                else:
                    tokens.append([token.register, regVal])
                    positions.append((offset, token.register))
            except:
                errors.append("Syntax error: Invalid register number. Not a number")
                positions.append((offset, token.error))
        elif address_regex.match(field):
            try:
                addrVal = int(field)
                if addrVal < 0:
                    errors.append("Architecture error: Constant address "
                                  + str(addrVal) + " below address minimum of 0")
                    positions.append((offset, token.error))
                elif addrMax != None and addrVal > addrMax:
                    errors.append("Architecture error: Constant address "
                                  + str(addrVal) + " above address maximum of "
                                  + str(addrMax))
                    positions.append((offset, token.error))
                else:
                    tokens.append([token.address, addrVal])
                    positions.append((offset, token.address))
            except:
                errors.append("Syntax error: Invalid address. Not a number")
                positions.append((offset, token.error))
        elif label_regex.match(field):
            tokens.append([token.label, field[:-1]])
            positions.append((offset, token.label))
        elif identifier_regex.match(field):
            tokens.append([token.identifier, field])
            positions.append((offset, token.identifier))
        elif whitespace_regex.match(field):
            # Whitespaces don't do anything, so don't append token
            positions.append((offset, token.whitespace))
        elif comment_regex.match(field):
            # Comments also don't do anything
            positions.append((offset, token.comment))
        else:
            errors.append("Syntax error: Cannot classify field " + str(field)
                    + " as any of the known tokens")
            positions.append((offset, token.error))

        # Increment offset for determining next token's position
        offset += len(field)

    # If there is an error, don't return the tokens
    if errors:
        return None, positions, errors
    else:
        return tokens, positions, errors

# Parse tokens into list of functions and operands
def compiler_parsing(tokenized_lines, extensions):
    # First stage, store all label lines
    labels = dict()

    for l in range(len(tokenized_lines)):
        # Skip empty lines
        if len(tokenized_lines[l]) == 0:
            continue

        # Check for label
        if tokenized_lines[l][0][0] == token.label:
            labelName = tokenized_lines[l][0][1]
            # Throw error when label already exists
            if labelName in labels:
                raise ValueError("Semantic error at line {:d}:\nLabel '{:s}' already exists".format(l + 1, labelName))
            # Store label in dictionary
            labels[labelName] = l
            # Remove label token
            tokenized_lines[l].pop(0)

    # Second stage, remove separators and raise error if operands aren't
    # separated, and check if everything is in opcode and operand pairs
    for l in range(len(tokenized_lines)):
        # Skip empty lines
        if len(tokenized_lines[l]) == 0:
            continue

        # Check if first token is an opcode
        if tokenized_lines[l][0][0] != token.identifier:
            raise ValueError("Syntax error at line {:d}:\nExpected opcode identifier".format(l + 1))

        # Check if the rest are valid separated operands
        for t in range(1, len(tokenized_lines[l])):
            # Odd, operand expected
            if t % 2 == 1:
                if tokenized_lines[l][t][0] in [token.separator, token.label]:
                    raise ValueError("Syntax error at line {:d}:\nExpected operand".format(l + 1))
            # Even, separator expected
            else:
                if tokenized_lines[l][t][0] != token.separator:
                    raise ValueError("Syntax error at line {:d}:\nExpected separator".format(l + 1))

        # Pop separators (every even index, except 0)
        for t in reversed(range(2, len(tokenized_lines[l]), 2)):
            tokenized_lines[l].pop(t)

    # Third stage, parse token chains (opcode and operand pairs) into function
    # reference and arguments lists
    ops = list()

    def checkOperands(tokens, l):
        def tokenStr(ttype):
            # Converts a token enumerator into a string
            if ttype == token.separator:
                return "separator"
            elif ttype == token.decimal:
                return "decimal"
            elif ttype == token.floating:
                return "floating"
            elif ttype == token.register:
                return "register"
            elif ttype == token.address:
                return "address"
            elif ttype == token.label:
                return "label"
            elif ttype == token.identifier:
                return "identifier"
            elif ttype == token.labelid:
                return "label identifier"
            else:
                return "unknown"

        def tokenListStr(tlist):
            # Converts a token list in the opcodes format into a string
            tstr = ""
            for ttype in tlist:
                if tstr != "":
                    tstr += " or "

                tstr += tokenStr(ttype[1])

            return tstr

        # Get line's opcode
        op = tokens[0][1].lower()

        # Throw error if opcode isn't declared
        if op not in interpreter.opcodes:
            raise ValueError("Semantic error at line {:d}:\nAttempt to parse undeclared opcode '{:s}'".format(l + 1, op))

        # Check operand count
        if len(tokens) != len(interpreter.opcodes[op]):
            raise ValueError("Semantic error at line {:d}:\nExpected {:d} operand(s), got {:d}".format(l + 1, len(interpreter.opcodes[op]) - 1, len(tokens) - 1))

        # Parse overload
        overload = 0
        for t in range(1, len(tokens)):
            for match in interpreter.opcodes[op][t]:
                match_token = match[1]
                if match_token == token.labelid:
                    match_token = token.identifier
                if tokens[t][0] == match_token:
                    overload += match[0]

                    # If a label identifier, turn it into a line number
                    if match[1] == token.labelid:
                        try:
                            tokens[t][1] = labels[tokens[t][1]]
                        except:
                            raise ValueError("Semantic error at line {:d}:\nAttempt to parse undeclared label '{:s}'".format(l + 1, tokens[t][1]))

                    break
            else:
                raise ValueError("Semantic error at line {:d}:\nExpected a {:s}, got a {:s} in operand number {:d}".format(l + 1, tokenListStr(interpreter.opcodes[op][t]), tokenStr(tokens[t][0]), t))

        return overload

    for l in range(len(tokenized_lines)):
        # Skip empty lines
        if len(tokenized_lines[l]) == 0:
            ops.append(None)
            continue

        # Check opcode operands and get overload
        overload = checkOperands(tokenized_lines[l], l)
        op_name = tokenized_lines[l][0][1].lower()
        if interpreter.opcodes[op_name][0][overload][1] and not extensions:
            raise ValueError("Architecture error at line {:d}: Attempt to use extension without language extensions enabled".format(l + 1))
        thisop = [interpreter.opcodes[op_name][0][overload][0]]

        # Generate operands
        for operand in range(1, len(tokenized_lines[l])):
            thisop.append(tokenized_lines[l][operand][1])

        # Append to opcode list
        ops.append(thisop)

    return ops

# Process all code
def compile_asm(code, extensions, wordMin, wordMax, addrMax, bytesPerWord):
    # Times dictionary. For monitoring performance. Is returned alongside code
    times = {"validation": 0, "lexical_analysis": 0, "parsing": 0}

    # Validate and tokenize each line
    for l in range(0, len(code)):
        # Validate
        start_time = time.time()
        try:
            compiler_validation(code[l])
        except Exception as e:
            raise ValueError("Error at line {:d}:\n{}".format(l + 1, e))
        times["validation"] += time.time() - start_time

        # Analyse lexically
        start_time = time.time()
        code[l], _, errors = compiler_lexical_analysis(code[l], wordMin, wordMax, addrMax, bytesPerWord, extensions)
        if errors:
            error_str = "{:s} at line {:d}:\n".format("Multiple errors" if len(errors) > 1 else "Error", l + 1)
            for e in errors:
                error_str += e + '\n'
            raise ValueError(error_str)
        times["lexical_analysis"] += time.time() - start_time

    # Parse
    start_time = time.time()
    code = compiler_parsing(code, extensions)
    times["parsing"] = time.time() - start_time

    return code, times
