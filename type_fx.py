#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

class JSType:
    def __str__(self):
        return "JSTYPE"

class JSPropertyType:
    def __init__(self, n, t, opt = False):
        # XXX Need to implement support for integer names.
        assert isinstance(n, str)
        self.name = n
        self.type = t
        self.optional = opt

    def __eq__(self, o):
        return (self.name == o.name and self.type == o.type and
                self.optional == o.optional)

class ObjectType(JSType):
    def __init__(self, tt):
        # types is an array of JSPropertyTypes
        self.types = tt
        # XXX Need to implement int fields for the order to match.

        # Field names must be in order, without duplicates.
        lastName = None
        for p in tt:
            if lastName:
                assert p.name > lastName
            lastName = p.name

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        l = []
        for p in self.types:
            opt = "?" if p.optional else ""
            l.append(f"{str(p.name)}{opt}: {p.type}")
        return "{" + ", ".join(l) + "}"

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        # XXX Do I still need to use strings?
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
