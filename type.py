#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Typing of JS in Python.
from enum import IntEnum
from jsast import *
import copy
import functools


class JSType:
    def __str__(self):
        return "JSTYPE"

    def classOrd(self):
        raise Exception("Implement in subclasses!")

class PrimitiveType(JSType):
    def __init__(self, name):
        self.name = name

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.name == o.name

    def __str__(self):
        return self.name

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.name < o.name

    def classOrd(self):
        return 0

    def union(self, o):
        if self == o:
            return self
        if isinstance(o, PrimitiveType) or isinstance(o, StructType):
            return OrType([self, o])
        if isinstance(o, OrType):
            return o.union(self)
        return None


class StructType(JSType):
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
            if isinstance(o, PrimitiveType):
                return OrType([self, o])
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
        return StructType(newMap, newOptional)


# This is the type for a JS object that is being used as a map.
# All keys have the keyType, and all values have the valType.
class ObjMapType(JSType):
    def __init__(self, keyType, valType):
        self.keyType = keyType
        self.valType = valType

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return (self.keyType == o.keyType and
                self.valType == o.valType)

    def __str__(self):
        return f"ObjMap({self.keyType}, {self.valType})"

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        if self.keyType < o.keyType:
            return True
        if self.keyType == o.keyType:
            return self.valType < o.valType
        return False

    def classOrd(self):
        return 2

    def union(self, o):
        if self == o:
            return copy.copy(self)
        return None


class ArrayType(JSType):
    def __init__(self, tt):
        self.types = sorted(tt)

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
        return 3

    def union(self, o):
        if self.__class__ != o.__class__:
            return None

        # An empty array can be any array type.
        if len(self.types) == 0:
            return copy.copy(o)
        if len(o.types) == 0:
            return copy.copy(self)

        # First, eliminate duplicates.
        newTypes = copy.copy(self.types)
        for x in o.types:
            if not x in self.types:
                newTypes.append(x)
        newTypes.sort()
        newTypes2 = functools.reduce(lambda x, y: None if x is None else x.union(y), newTypes)
        if newTypes2:
            if isinstance(newTypes2, OrType):
                return ArrayType(newTypes2.types)
            return ArrayType([newTypes2])
        else:
            return ArrayType(newTypes)


class OrType(JSType):
    def __init__(self, tt):
        self.types = sorted(tt)

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        self.types == o.types

    def __str__(self):
        return " | ".join(map(lambda t: str(t), self.types))

    def classOrd(self):
        return 4

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.types < o.types

    def union(self, o):
        # TODO: I'm not sure what a good way to deal with this is.
        # eg union (int | bool) bool or union (int | bool) (bool | int)

        # Right now I'm only dealing with primitive and map types, so only
        # worry about some simple cases.
        if isinstance(o, StructType):
            if o in self.types:
                return copy.copy(self)
        elif isinstance(o, PrimitiveType):
            if o in self.types:
                return copy.copy(self)
            tt = copy.copy(self.types)
            tt.append(o)
            return OrType(tt)
        return None


# TODO: Probably need an "any" type.

def FloatType(useNumberType):
    if useNumberType:
        pt = "number"
    else:
        pt = "float"
    return PrimitiveType(pt)

def IntegerType(useNumberType):
    if useNumberType:
        pt = "number"
    else:
        pt = "int"
    return PrimitiveType(pt)

def jsValToType(v):
    def mapKeyType(k):
        if isinstance(p, JSID):
            return None
        return jsValToType(k)

    useNumberType = True
    if isinstance(v, bool):
        return PrimitiveType("bool")
    elif isinstance(v, int):
        return IntegerType(useNumberType)
    elif (isinstance(v, float) or
          isinstance(v, JSInfinity) or
          isinstance(v, JSNaN)):
        return FloatType(useNumberType)
    elif isinstance(v, JSNull):
        return PrimitiveType("null")
    elif isinstance(v, str):
        return PrimitiveType("string")
    elif isinstance(v, JSUndefined):
        return PrimitiveType("undefined")
    elif isinstance(v, dict):
        objMapMaybe = True
        objMapKeyType = None
        objMapValType = None
        tts = {}
        for p, pv in v.items():
            pvType = jsValToType(pv)
            tts[p] = pvType
            if objMapMaybe:
                if objMapKeyType is None:
                    objMapKeyType = mapKeyType(p)
                if objMapKeyType is None:
                    objMapMaybe = False
                    continue
                if objMapValType is None:
                    objMapValType = pvType
                    assert not pvType is None
                else:
                    objMapMaybe = pvType == objMapValType
        if objMapMaybe and len(tts) > 0:
            return ObjMapType(objMapKeyType, objMapValType)
        return StructType(tts, set([]))
    elif isinstance(v, list):
        tts = []
        for val in v:
            t = jsValToType(val)
            if not t in tts:
               tts.append(t)
        return ArrayType(tts)
    elif isinstance(v, JSRegExp):
        return PrimitiveType("regexp")
    elif isinstance(v, JSBuiltin):
        return PrimitiveType(v.name)
    else:
        raise Exception(f"Untypeable value: {v}")
