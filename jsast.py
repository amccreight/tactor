#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# AST helpers for representing JS in Python.

class JSNull:
    def __str__(self):
        return "null"

class JSUndefined:
    def __str__(self):
        return "undefined"

class JSInfinity:
    def __str__(self):
        return "Infinity"

class JSNaN:
    def __str__(self):
        return "NaN"

class JSID:
    def __init__(self, name):
        self.name = name

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.name == o.name

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return self.name

# I don't really care enough to store the argument.
class JSDate:
    def __str__(self):
        return "Date"

class JSRegExp:
    def __init__(self, regexp):
        assert isinstance(regexp, str)
        self.regexp = regexp

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.regexp == o.regexp

    def __hash__(self):
        return hash(self.regexp)

    def __str__(self):
        return f"/{self.regexp}/"

def jsToString(jsv):
    if isinstance(jsv, dict):
        s = "{"
        l = []
        for k, v in jsv.items():
            l.append(f'{jsToString(k)}: {jsToString(v)}')
        s += ", ".join(l) + "}"
        return s
    elif isinstance(jsv, list):
        s = "["
        l = []
        for x in jsv:
            l.append(f'{jsToString(x)}')
        s += ", ".join(l) + "]"
        return s
    elif isinstance(jsv, str):
        return f'"{jsv}"'
    else:
        return str(jsv)
