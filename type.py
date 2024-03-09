#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Typing of JS in Python.
from enum import Enum
from jsast import JSNull, JSUndefined
import copy


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

    def union(self, o):
        if self != o:
            if self.__class__ != o.__class__:
                return None
            return OrType(self, o)
        return self


class MapType(JSType):
    def __init__(self, m, optional):
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

    def union(self, o):
        if self.__class__ != o.__class__:
            return None
        # TODO Do I want some kind of "anymap" when unioning gets too weird?
        # Some actors have this "data" field which has weird constraints I'm not sure I can merge.
        # Or maybe I need an actual "union" type that I'd have to decide when to use.
        newMap = {}
        newOptional = self.optional | o.optional
        for p, pt in self.map.items():
            if p in o.map:
                ptNew = pt.union(o.map[p])
                if not ptNew:
                    return None
                newMap[p] = ptNew
            else:
                newMap[p] = pt
                newOptional.add(p)
        for p, pt in o.map.items():
            if p in self.map:
                # We already handled this in the last loop.
                continue
            newMap[p] = pt
            newOptional.add(p)
        return MapType(newMap, newOptional)


class ArrayType(JSType):
    def __init__(self, tt):
        # TODO: for now, this is a list of possible types.
        self.types = tt
        # TODO: actually support this better?
        assert len(tt) == 1
        return

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        return f"Array({', '.join(map(lambda t: str(t), self.types))}"

    def union(self, o):
        if self.__class__ != o.__class__:
            return None

        if self == o:
            return copy.deepcopy(self)
        if len(self.types) == 1 and len(o.types) == 1:
            newType = self.types[0].union(o.types[0])
            if not newType:
                return None
            else:
                return ArrayType([newType])

        # TODO: Implement something for non-singleton array types.
        return None


class OrType(JSType):
    def __init__(self, t1, t2):
        self.type1 = t1
        self.type2 = t2

    def __eq__(self, o):
        self.type1 == o.type1 and self.type2 == o.type2

    def __str__(self):
        return f"{self.type1} | {self.type2}"

    def union(self, o):
        # TODO: I'm not sure what a good way to deal with this is.
        # eg union (int | bool) bool or union (int | bool) (bool | int)

        # Right now I'm only combining primitive types, so deal with the simple case there.
        if isinstance(o, PrimitiveType):
            if self.type1 == o or self.type2 == o:
                return self
        return None


# TODO: Probably need an "any" type.

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
        return MapType(tts, set([]))
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
