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
    def __init__(self, m, optional=set([])):
        self.map = m
        self.optional = optional

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        if self.optional != o.optional:
            return False
        if self.map.keys() != o.map.keys():
            return False
        for p, pt in self.map.items():
            if pt != o.map[p]:
                return False
        return True

    def __str__(self):
        l = []
        for p, pt in self.map.items():
            opt = "?" if p in self.optional else ""
            l.append(f"{p}{opt}: {pt}")
        return "{" + ", ".join(l) + "}"


class ArrayType(JSType):
    def __init__(self, tt):
        # TODO: for now, this is a list of possible types.
        self.types = tt
        return

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        return f"Array({', '.join(map(lambda t: str(t), self.types))}"

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
        tts = {}
        for p, pv in v.items():
            tts[p] = jsValToType(pv)
        return MapType(tts)
    elif isinstance(v, list):
        tts = []
        for val in v:
            t = jsValToType(val)
            if not t in tts:
               tts.append(t)
        sorted(tts)
        return ArrayType(tts)
    else:
        raise Exception(f"Untypeable value: {v}")
