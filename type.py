#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Typing of JS in Python.
from enum import IntEnum
from jsast import JSNull, JSUndefined, JSRegExp, jsToString
import copy
import functools


class JSType:
    def __str__(self):
        return "JSTYPE"

    def classOrd(self):
        raise Exception("Implement in subclasses!")

class JSPrimitiveType(IntEnum):
    BOOL = 0
    INTEGER = 1
    FLOAT = 2
    NULL = 3
    STRING = 4
    UNDEFINED = 5
    REGEXP = 6

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
            JSPrimitiveType.FLOAT: "float",
            JSPrimitiveType.NULL: "null",
            JSPrimitiveType.STRING: "string",
            JSPrimitiveType.UNDEFINED: "undefined",
            JSPrimitiveType.REGEXP: "regexp",
        }[self.prim]

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.prim < o.prim

    def classOrd(self):
        return 0

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
            l.append(f"{jsToString(p)}{opt}: {pt}")
        return "{" + ", ".join(l) + "}"

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return str(self) < str(o)

    def classOrd(self):
        return 1

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
        self.types = tt

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        return f"Array({', '.join(map(lambda t: str(t), self.types))})"

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.types < o.types

    def classOrd(self):
        return 2

    def union(self, o):
        if self.__class__ != o.__class__:
            return None

        # An empty array can be any array type.
        if len(self.types) == 0:
            return copy.copy(o)
        if len(o.types) == 0:
            return copy.copy(self)

        # Try to union everything together.
        t1 = functools.reduce(lambda x, y: None if x is None else x.union(y), self.types)
        if not t1 is None:
            t2 = functools.reduce(lambda x, y: None if x is None else x.union(y), o.types)
            if not t2 is None:
                t3 = t1.union(t2)
                if not t3 is None:
                    return ArrayType([t3])

        # If that doesn't work, try eliminating duplicates at least.
        t2 = copy.copy(self.types)
        for x in o.types:
            if not x in self.types:
                t2.append(x)
        return ArrayType(t2)


class OrType(JSType):
    def __init__(self, t1, t2):
        self.type1 = t1
        self.type2 = t2

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        self.type1 == o.type1 and self.type2 == o.type2

    def __str__(self):
        return f"{self.type1} | {self.type2}"

    def classOrd(self):
        return 3

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
    elif isinstance(v, float):
        return PrimitiveType(JSPrimitiveType.FLOAT)
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
    elif isinstance(v, JSRegExp):
        return PrimitiveType(JSPrimitiveType.REGEXP)
    else:
        raise Exception(f"Untypeable value: {v}")
