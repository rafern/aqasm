#!/usr/bin/python3
from enum import Enum
import interpreter
import time
import re

## Lexical analysis
class token(Enum):
    separator  = 0
    decimal    = 1
    register   = 2
    address    = 3
    label      = 4
    identifier = 5
    # Special identifier. Matches with the identifier token but in the lex parse
    # stage it converts the identifier to its numerical value (line number)
    labelid    = 6
    # Sytax highlighter exclusive tokens. Not used during compilation
    comment    = 7
    whitespace = 8
    error      = 9

# Return tokenised line for syntax highlighting. Line is a bytestring or array
def lex_highlight(line):
    tokens = list()
    lastToken = token.whitespace

    # Parse line into highlight tokens
    foundOpcode = False
    foundArgument = False
    wasR = False
    for i in range(len(line)):
        c = line[i]
        if c == 9 or c == 32: # Tab or space
            # Ignore if token is already a whitespace or separator
            if lastToken != token.whitespace and lastToken != token.separator:
                if lastToken == token.identifier:
                    foundOpcode = True
                lastToken = token.whitespace
                tokens.append((i, token.whitespace))
        elif c == 59: # Semi-colon
            # Comment out rest of line if semi-colon found
            tokens.append((i, token.comment))
            break
        elif c == 35: # Hash
            if (lastToken != token.separator and lastToken != token.whitespace) or (lastToken == token.separator and not foundArgument) or (lastToken == token.whitespace and foundArgument):
                lastToken = token.error
                tokens.append((i, token.error))
            else:
                foundArgument = True
                lastToken = token.decimal
                tokens.append((i, token.decimal))
        elif c >= 48 and c <= 57: # Digit
            if lastToken != token.decimal and lastToken != token.register and lastToken != token.address:
                foundArgument = True
                if wasR and lastToken == token.labelid:
                    lastToken = token.register
                    tokens[-1] = (tokens[-1][0], token.register)
                elif (lastToken != token.separator and lastToken != token.whitespace) or (lastToken == token.separator and not foundArgument) or (lastToken == token.whitespace and foundArgument):
                    lastToken = token.error
                    tokens.append((i, token.error))
                else:
                    lastToken = token.address
                    tokens.append((i, token.address))
        elif (c >= 65 and c <= 90) or (c >= 97 and c <= 122): # a-z and A-Z
            if (lastToken == token.separator and foundArgument) or (lastToken == token.whitespace and not foundArgument):
                if foundOpcode:
                    foundArgument = True
                    lastToken = token.labelid
                    tokens.append((i, token.labelid))
                    if c == 82 or c == 114:
                        wasR = True
                        # Continue so that wasR is not set to false again
                        continue
                else:
                    lastToken = token.identifier
                    tokens.append((i, token.identifier))
            elif lastToken != token.identifier and lastToken != token.labelid:
                lastToken = token.error
                tokens.append((i, token.error))
        elif c == 45 or c == 95: # Underscore or minus/hyphen
            if lastToken == token.whitespace:
                lastToken = token.labelid
                tokens.append((i, token.labelid))
            elif lastToken == token.identifier:
                lastToken = token.labelid
                tokens[-1] = (tokens[-1][0], token.labelid)
            elif lastToken != token.labelid:
                lastToken = token.error
                tokens.append((i, token.error))
        elif c == 58: # Colon
            if not foundOpcode and (lastToken == token.labelid or lastToken == token.identifier):
                lastToken = token.label
                tokens[-1] = (tokens[-1][0], token.label)
            else:
                lastToken = token.error
                tokens.append((i, token.error))
        elif c == 44: # Comma
            if lastToken == token.whitespace and foundArgument:
                lastToken = token.separator
                tokens[-1] = (tokens[-1][0], token.separator)
            elif foundArgument and (lastToken == token.labelid or lastToken == token.decimal or lastToken == token.register or lastToken == token.address):
                lastToken = token.separator
                tokens.append((i, token.separator))
            else:
                lastToken = token.error
                tokens.append((i, token.error))
        else:
            lastToken = token.error
            tokens.append((i, token.error))
        wasR = False

    return tokens

# Remove comments, whitespace characters, and check for lone symbols which are
# not part of the language or invalid line starters, raising an exception
def lex_clean(lines):
    # Valid code line regex
    starter_regex = re.compile("(^\t[a-zA-Z][ \ta-zA-Z0-9#,_-]+$)|(^[a-zA-Z_-]+:[ \t]*$)|(^[a-zA-Z_-]+:\t[a-zA-Z][ \ta-zA-Z0-9#,_-]+$)|(^[ \t]+$)")
    # Error regexes
    symbol_regex = re.compile("^[ \ta-zA-Z0-9#,:_-]*$")
    spaces_regex = re.compile("^( *\t* +)|([ \t]+[ \ta-zA-Z0-9#,_-]+:)")
    notabs_regex = re.compile("^(([a-zA-Z_-]+:){0} *[ \ta-zA-Z0-9#,_-]+)|([a-zA-Z_-]+: +[ \ta-zA-Z0-9#,_-]+)$")
    labelc_regex = re.compile("^[a-zA-Z_-]*[ \t0-9#,][ \ta-zA-Z0-9#,_-]*:")
    labeli_regex = re.compile("^:")
    for l in range(0, len(lines)):
        # Strip out comments
        lines[l] = lines[l].split(';', 1)[0]

        # Abort error and gray area checking if line is empty
        if lines[l] == "":
            continue

        # Check if the line is valid code. Valid code includes:
        # <tab>code<whitespaces>
        # label:<whitespaces>
        # label:<tab>code<whitespaces>
        # <whitespaces>
        if not starter_regex.match(lines[l]):
            # Check if code contains invalid characters
            if not symbol_regex.match(lines[l]):
                raise ValueError("Syntax error: Unknown symbol found at line\n"
                                 + lines[l])
            # Check if code contains more than 1 labels
            elif lines[l].count(':') > 1:
                raise ValueError("Syntax error: More than 1 label at line "
                                 + str(l + 1))
            # Check if code contains preceding whitespaces
            elif spaces_regex.match(lines[l]):
                raise ValueError("Syntax error: Preceding whitespaces at line "
                                 + str(l + 1))
            # Check if code is code without labels but contains no tabs
            elif notabs_regex.match(lines[l]):
                raise ValueError("Syntax error: No tab before code at line "
                                 + str(l + 1))
            # Check if code contains a label with no identifier
            elif labeli_regex.match(lines[l]):
                raise ValueError("Syntax error: Label with no identifier at line "
                                 + str(l + 1))
            # Check if code contains a label with disallowed characters for
            # label identifiers
            elif labelc_regex.match(lines[l]):
                raise ValueError("Syntax error: Disallowed characters in label identifier at line "
                                 + str(l + 1))
            # If match failed but because of none of the previous syntax errors,
            # raise a generic syntax error exception
            else:
                raise ValueError("Syntax error: Expected valid label, tabbed code, both or an empty line at line "
                                 + str(l + 1))

    return lines

# Split everything into keywords
def lex_split(lines):
    # Regex for splitting on separators
    split_regex = re.compile("(,)")
    for l in range(0, len(lines)):
        # Split into keywords
        lines[l] = lines[l].split()

        line_new = list()
        # Split separators (commas) into their own keyword.
        for keyword in lines[l]:
            # Use extend so that members are appended to line_new, instead of
            # the list itself, as filter returns a new list
            line_new.extend(filter(None, split_regex.split(keyword)))
        lines[l] = line_new

    return lines

# Tokenize code
def lex_tokenize(lines):
    tokenized_lines = list()
    # Regex for each token type. Note that separators (commas) dont need regexes
    decimal_regex    = re.compile("^#-?[0-9]+$")
    # Registers can be more than 12 here. Handle registers higher than 12 later
    register_regex   = re.compile("^R|r[0-9]+$")
    address_regex    = re.compile("^[0-9]+$")
    label_regex      = re.compile("^[a-zA-Z_-]+:$")
    # Identifiers can represent both opcodes and label indentifiers for B opcode
    identifier_regex = re.compile("^[a-zA-Z_-]+$")
    for l in range(0, len(lines)):
        tokens = list()
        for keyword in lines[l]:
            if keyword == ',':
                tokens.append([token.separator])
            elif decimal_regex.match(keyword):
                tokens.append([token.decimal, int(keyword[1:])])
            elif register_regex.match(keyword):
                if not int(keyword[1:]) in range(0, 13):
                    raise ValueError("Syntax error: Invalid register number "
                                     + str(int(keyword[1:])) + " at line "
                                     + str(l))
                tokens.append([token.register, int(keyword[1:])])
            elif address_regex.match(keyword):
                tokens.append([token.address, int(keyword)])
            elif label_regex.match(keyword):
                tokens.append([token.label, keyword[:-1]])
            elif identifier_regex.match(keyword):
                tokens.append([token.identifier, keyword])
            else:
                raise ValueError("Syntax error: Cannot classify keyword "
                                 + str(keyword) + " at line " + str(l + 1) + 
                                 " as any of the known tokens")
        tokenized_lines.append(tokens)
    return tokenized_lines

# Parse tokens into list of lambdas representing each instruction
def lex_parse(tokenized_lines, extensions):
    # First stage, store all label lines
    labels = dict()

    for l in range(0, len(tokenized_lines)):
        # Skip empty lines
        if len(tokenized_lines[l]) == 0:
            continue

        # Check for label
        if tokenized_lines[l][0][0] == token.label:
            labelName = tokenized_lines[l][0][1]
            # Throw error when label already exists
            if labelName in labels:
                raise ValueError("Syntax error: Label '" + labelName
                                 + "' already exists")
            # Store label in dictionary
            labels[labelName] = l
            # Remove label token
            tokenized_lines[l].pop(0)

    # Second stage, remove separators and raise error if operands aren't
    # separated, and check if everything is in opcode and operand pairs
    for l in range(0, len(tokenized_lines)):
        # Skip empty lines
        if len(tokenized_lines[l]) == 0:
            continue

        # Check if first token is an opcode
        if tokenized_lines[l][0][0] != token.identifier:
            raise ValueError("Syntax error: Expected opcode identifier at line "
                             + str(l + 1))

        # Check if the rest are valid separated operands
        for t in range(1, len(tokenized_lines[l])):
            # Odd, operand expected
            if t % 2 == 1:
                if tokenized_lines[l][t][0] in [token.separator, token.label]:
                    raise ValueError("Syntax error: Expected operand at line "
                                     + str(l + 1))
            # Even, separator expected
            else:
                if tokenized_lines[l][t][0] != token.separator:
                    raise ValueError("Syntax error: Expected separator at line "
                                     + str(l + 1))

        # Pop separators (every even index, except 0)
        for t in reversed(range(2, len(tokenized_lines[l]), 2)):
            tokenized_lines[l].pop(t)

    # Third stage, parse token chains (opcode and operand pairs) into function
    # reference and arguments lists
    ops = list()

    def checkOperands(tokens):
        def tokensStr(ttype):
            tstr = ""
            for tinit in ttype:
                if tstr != "":
                    tstr += " or "

                # If using token definitions from instruction definitions,
                # use the second element of tuple, as it also contains the add
                # value for overloading
                t = tinit
                if isinstance(t, tuple):
                    t = tinit[1]

                if t == token.separator:
                    tstr += "separator"
                elif t == token.decimal:
                    tstr += "decimal"
                elif t == token.register:
                    tstr += "register"
                elif t == token.address:
                    tstr += "address"
                elif t == token.label:
                    tstr += "label"
                elif t == token.identifier or t == token.labelid:
                    tstr += "identifier"
                else:
                    tstr += "unknown"
            return tstr

        op = tokens[0][1].lower()

        # Throw error if opcode isn't declared
        if op not in interpreter.opcodes:
            raise ValueError("Error: Attempt to parse undeclared opcode " + op)

        # Check operand count
        if len(tokens) != len(interpreter.opcodes[op]):
            raise ValueError("Syntax error: Expected "
                             + str(len(interpreter.opcodes[op]) - 1)
                             + " operands, got " + str(len(tokens) - 1))

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
                            raise ValueError("Error: Attempt to parse undeclared label "
                                             + tokens[t][1])

                    break
            else:
                raise ValueError("Syntax error: Expected "
                                 + tokensStr([interpreter.opcodes[op][t][1]])
                                 + ", got " + tokensStr([tokens[t][0]])
                                 + " in operand number " + str(t))

        return overload

    for tokens in tokenized_lines:
        # Skip empty lines
        if len(tokens) == 0:
            ops.append(None)
            continue

        # Check opcode operands and get overload
        overload = checkOperands(tokens)
        op_name = tokens[0][1].lower()
        if interpreter.opcodes[op_name][0][overload][1] and not extensions:
            raise ValueError("Error: Attempt to use extension without language extensions enabled")
        thisop = [interpreter.opcodes[op_name][0][overload][0]]

        # Generate operands
        for operand in range(1, len(tokens)):
            thisop.append(tokens[operand][1])

        # Append to opcode list
        ops.append(thisop)

    return ops

# Process all code
def lex_process(code, extensions = False):
    # Times dictionary. For monitoring performance. Is returned alongside code
    times = dict()

    # Clean (lex)
    start_time = time.time()
    code = lex_clean(code)
    times["lex_clean"] = time.time() - start_time

    # Split (lex)
    start_time = time.time()
    pipeline = lex_split(code)
    times["lex_split"] = time.time() - start_time

    # Tokenize (lex)
    start_time = time.time()
    pipeline = lex_tokenize(pipeline)
    times["lex_tokenize"] = time.time() - start_time

    # Parse (lex)
    start_time = time.time()
    pipeline = lex_parse(pipeline, extensions)
    times["lex_parse"] = time.time() - start_time

    return pipeline, times
