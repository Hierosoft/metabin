# -*- coding: utf-8 -*-
"""
Translate Python struct packing characters (keys)
<https://docs.python.org/3/library/struct.html> (same for Python 2)
to ImHex Pattern Language (values) for generating ImHex project files.

License: [MIT License](https://github.com/Hierosoft/metabin#MIT-1-ov-file)

The most up-to-date version of this module can be obtained at:
<https://github.com/Hierosoft/metabin>.

The ImHex Pattern Language is documented at
<https://blog.xorhex.com/blog/quickimhexpatternyaratutorial/>.
"""
from __future__ import print_function

import inspect
import os
import struct
import sys

from pprint import pformat

imhex_keywords = {
    ">": "be",  # big endian (most significant byte is last) such as PIC-33
    "<": "le",  # little endian
    "B": "u8",
    "b": "s8",
    # "?": "u8",  # ? is actually bool
    "H": "u16",
    "h": "s16",
    "i": "i32",
    "I": "u32",
    "l": "i32",  # long is same as int in Python (and many modern platforms)
    "L": "u32",  # long is same as int in Python (and many modern platforms)
    "q": "s64",  # "long long" is 64-bit (8-byte) signed integer
    "Q": "u64",  # unsigned long long
    "s": "i32",  # actually ssize_t
    "S": "u32",  # actually size_t
    "e": "f16",  # 16-bit (2-byte) float
    "f": "f32",  # 32-bit (4-byte) float
    "d": "f64",  # 64-bit (8-byte) double (double precision float)
    # "s": None,  # char[] bytes; must be preceded by number (such as "10s")
    # where number is length (usually number is repeat but not for "s")
    # "p": None,  # char[] bytes Pascal-style (first byte is length, max 255)
    # "P": None,  # void* (integer-like)
}
# Arrays can be defined like char signature[2]; (2 bytes in this case)

NO_BYTES = ''
JOIN_BYTES = ''  # See also instances of checking Python version (''.join or "".join)
PAD_BYTES = '\x00\x00'
PAD_BYTE = '\x00'

if sys.version_info.major >= 3:
    NO_BYTES = b''
    JOIN_BYTES = b''
    PAD_BYTES = b'\x00\x00'
    PAD_BYTE = b'\x00'
else:
    # polyfill
    FileNotFoundError = IOError

BYTE_0 = bytes(bytearray([0x00]))


def echo0(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)


def chars_to_imhex(struct_pattern):
    """Convert a Python (2 or 3) struct template to ImHex Pattern Language.

    Examples:
    - Convert "H" to "u16"
    - Convert ">H" to "be u16" ("be" for big endian)
    """
    if len(struct_pattern) == 1:
        return imhex_keywords[struct_pattern]
    elif (len(struct_pattern) == 2) and (struct_pattern[0] in [">", "<"]):
        # Example: Convert ">H" to "be u16" ("be" for big endian)
        return (
            imhex_keywords[struct_pattern[:1]]
            + " "
            + imhex_keywords[struct_pattern[1:]]
        )
    raise NotImplementedError(
        "Converting multi-part chunks is not implemented (failed on %s)."
        "" % pformat(struct_pattern)
    )


class MetaBinFunction:
    """Describe how to portray a binary.

    Store metadata that can be converted to an ImHex Pattern Language
    function. An ImHex Pattern Language function describes how to
    represent dynamic data such as by deriving values or making
    decisions based on input parameters.

    Example:
    ```
    fn calculate_checksum(data: array<uint8>, length: uint32) -> uint32 {
        var checksum = 0;
        for (var i = 0; i < length; i++) {
            checksum += data[i];
        }
        return checksum;
    }
    ```

    Attributes:
        name (string): The name of the function.
        lines (list[string]): The lines that go inside of the function
            (not indented--indent will be added on export).
    """
    def __init__(self):
        self.name = None
        self.lines = []


class MetaBinStruct:
    """Describe the structure of a group of binary elements.

    Store metadata that can be converted to an ImHex Pattern Language
    struct. An ImHex Pattern Language struct describes how to represent
    a fixed layout of fields.

    Example:
    ```
    struct Header {
        uint32 magic;
        uint16 version;
        uint16 flags;
    };
    ```

    Attributes:
        name (string): The name of the struct.
        lines (list[string]): The lines that go inside of the structure
            (not indented--indent will be added on export).

    """
    def __init__(self):
        self.name = None
        self.lines = []


class Packable:
    def __init__(self):
        # self.data = NO_BYTES
        self.chunks = []
        self.lines = []

    def pack(self, pattern, value, name, count=None):
        """Pack literal or virtual data.

        Args:
            pattern (str): Python struct notation for the value.
            value (any): Any value to pack.
            name (str): The name of the variable being packed.
            count (int, optional): Skip the caching of data and instead
                only describe the structure. Defaults to None.
        """
        curframe = inspect.currentframe()
        calframe = inspect.getouterframes(curframe, 2)
        caller_name = calframe[1][3]
        if count is not None:
            line = "{} {}".format(chars_to_imhex(pattern), name)
        else:
            line = "{} {}[{}]".format(chars_to_imhex(pattern), name, count)
        echo0("packing {}  // = {}".format(line, value))  # FIXME: Use logging.debug
        # ^ "//" is the inline comment delimiter for ImHex Pattern Language.
        self.lines.append(line)
        # self.data += struct.pack(pattern, value)
        if count is not None:
            # Allow blank value to same RAM such as to only
            #   save the pattern in the case of a data array.
            return
        try:
            self.chunks.append(struct.pack(pattern, value))
        except struct.error:
            echo0("packing error in {}".format(caller_name))
            raise

    @property
    def data(self):
        return JOIN_BYTES.join(self.chunks)

    def append(self, packable):
        if hasattr(packable, "name"):
            raise TypeError(
                "A name prevents a packable from being appended:"
                " Keep the packable separate if it is a struct so it"
                " can be its own tier in the output metadata."
            )
        self.chunks += packable.chunks
        self.lines += packable.lines


class MetaBin:
    """Describe a binary file.

    Describe the structures in a binary file and how to represent them
    if the binary represents a string or other structure that isn't
    a number (See MetaBinFunction). Export to ImHex format.

    Attributes:
        structs (list[MetaBinStruct]): A list of multi-number structures
        functions (list[MetaBinFunction]): A list of functions that
            describe how to represent any non-numerical value.
        segments (list): A mixed list of MetaBinStruct, MetaBinFunction,
            or string objects, where string is a simple line in ImHex
            Pattern Language. A string should only be used for a type
            that can be represented by one line of ImHex Pattern
            Language code (usually a number).
    """
    def __init__(self):
        self.structs = []
        self.functions = []
        self.segments = []
