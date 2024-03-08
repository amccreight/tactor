#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# The world's worst JS parser. The goal is to parse JSON-y JS produced
# by JS_ValueToSource. Some of the Ply tricks in here are taken from
# Firefox's IPDL parser.

class JSNull:
    def __str__(self):
        return "null"

class JSUndefined:
    def __str__(self):
        return "undefined"