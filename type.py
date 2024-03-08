#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Typing of JS in Python.
from enum import Enum
from jsast import JSNull, JSUndefined


class JSType:
    def __str__(self):
        return "JSTYPE"

JSPrimitiveType = Enum("JSPrimitiveType", [
    "BOOL",
    "INTEGER",
    "NULL",
    "STRING",
    "UNDEFINED",
    ])

class PrimitiveType(JSType):
    def __init__(self, prim):
        self.prim = prim

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.prim == o.prim

    def __str__(self):
        return {
            JSPrimitiveType.BOOL: "bool",
            JSPrimitiveType.INTEGER: "int",
            JSPrimitiveType.NULL: "null",
            JSPrimitiveType.STRING: "string",
            JSPrimitiveType.UNDEFINED: "undefined",
        }[self.prim]

class MapType(JSType):
    def __init__(self, m):
        self.map = m

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        # TODO: Implement actual checking.
        return True

    def __str__(self):
        return "MAP"

class ArrayType(JSType):
    def __init__(self):
        # Not sure what to do with this. Probably a single type, but is that
        # enough?
        return

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        # TODO: Implement actual checking.
        return True

    def __str__(self):
        return "ARRAY"

# TODO: Probably need an "any" type and maybe an "or" type.

def jsValToType(v):
    if isinstance(v, bool):
        return PrimitiveType(JSPrimitiveType.BOOL)
    elif isinstance(v, int):
        return PrimitiveType(JSPrimitiveType.INTEGER)
    elif isinstance(v, JSNull):
        return PrimitiveType(JSPrimitiveType.NULL)
    elif isinstance(v, str):
        return PrimitiveType(JSPrimitiveType.STRING)
    elif isinstance(v, JSUndefined):
        return PrimitiveType(JSPrimitiveType.UNDEFINED)
    elif isinstance(v, dict):
        # TODO Deal with all of the fields.
        return MapType({})
    elif isinstance(v, list):
        # TODO Deal with joining the types of the elements
        return ArrayType()
    else:
        raise Exception(f"Untypeable value: {v}")
