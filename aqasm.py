#!/usr/bin/python3
import interpreter

## Unit-test
if __name__ == "__main__":
    print("Type in code. Ctrl+D or EOF to stop multi-line input")
    code = ""
    while True:
        try:
            line = input("")
        except EOFError:
            break
        code = code + line + '\n'

    print("Compiling code...")
    cpu = interpreter.aqasm(code, True)

    if len(cpu.lex) == 0:
        print("No code to execute...")
        exit()

    print("Code execution [Ctrl+D or EOF to stop, enter to step]:")
    while True:
        print(cpu.code[cpu.pc])
        print("Registers:")
        print(cpu.reg)
        print("Memory:")
        print(cpu.mem)
        print("States:")
        print(" Zero: " + str(cpu.zero) + "; Sign: " + str(cpu.sign)
              + "; PC: " + str(cpu.pc))

        if cpu.halt:
            break

        try:
            line = input("")
        except EOFError:
            break

        cpu.step()
    print("CPU halted")
