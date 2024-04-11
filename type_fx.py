#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

class JSType:
    def __str__(self):
        return "JSTYPE"

class ObjectType(JSType):
    def __init__(self, m):
        self.map = m
        self.optional = set([])

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
        keys = list(self.map.keys())
        keys.sort()
        for p in keys:
            opt = "?" if p in self.optional else ""
            l.append(f"{str(p)}{opt}: {self.map[p]}")
        return "{" + ", ".join(l) + "}"

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return str(self) < str(o)

    def classOrd(self):
        return 1


class ArrayType(JSType):
    def __init__(self, elementType):
        # elementType can be None to represent the type of an empty array.
        self.elementType = elementType

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.elementType == o.elementType

    def __str__(self):
        if self.elementType:
            elementString = str(self.elementType)
        else:
            elementString = ""
        return f"Array({elementString})"

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.elementType < o.elementType

    def classOrd(self):
        return 2


class UnionType(JSType):
    def __init__(self, tt):
        assert len(tt) > 1
        self.types = sorted(tt)

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        return " | ".join(map(lambda t: str(t), self.types))

    def classOrd(self):
        return 3

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.types < o.types
