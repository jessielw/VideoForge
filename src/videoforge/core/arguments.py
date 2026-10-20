"""Extra tool arguments, using Windows double-quote/backslash rules on every platform.

The fields are argv fragments, not shell programs. Double quotes group spaces; apostrophes and shell
operators are literal. Backslashes stay literal except immediately before a double quote. Keeping one
syntax makes templates portable and Windows paths usable in Linux/Wine. Unclosed quotes are rejected.
"""


def split_args(text: str) -> list[str]:
    args: list[str] = []
    word: list[str] = []
    quoted = active = False
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace() and not quoted:
            if active:
                args.append("".join(word))
                word, active = [], False
            i += 1
            continue
        active = True
        if c == "\\":
            start = i
            while i < len(text) and text[i] == "\\":
                i += 1
            count = i - start
            if i == len(text) or text[i] != '"':
                word.append("\\" * count)
                continue
            word.append("\\" * (count // 2))
            if count % 2:
                word.append('"')
                i += 1
                continue
            c = '"'
        if c == '"':
            if quoted and i + 1 < len(text) and text[i + 1] == '"':
                word.append('"')
                i += 2
                continue
            quoted = not quoted
        else:
            word.append(c)
        i += 1
    if quoted:
        raise ValueError("Unclosed double quote in extra arguments")
    if active:
        args.append("".join(word))
    return args
