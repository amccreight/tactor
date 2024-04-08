#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Analyze JS actor logging.

# This is intended to work with the C++-based type logging from the
# prototype version of bug 1885221 as of April 8, 2024.
#
# The two main goals:
# 1) Extract the types for individual messages and combine them
#   together into types we can use as specifications for the messages/
# 2) Figure out which cases for fallback serialization (represented
#   by the "Any" type should be implemented. These will show up as
#   "AnyToJSIPCValue fallback with" warnings.

NS_WARNING("AnyToJSIPCValue fallback with ESClass::Number");

NS_WARNING("Failed to serialize");

import argparse
import re
import sys
import json
from jsparse import parseJS, ParseError
from type import jsValToType

messagePatt = re.compile('QQQ ACTOR ([^ ]+) MESSAGE ([^ ]+) CONTENTS (.+)$')

def lookAtActors(args):
    sys.stdin.reconfigure(encoding='latin1')

    actors = {}

    for l in sys.stdin:
        mp = messagePatt.search(l)
        if not mp:
            continue
        actorName = mp.group(1)
        messageName = mp.group(2)

        if (actorName == "DevToolsFrame" and
            messageName == "DevToolsFrameChild:packet"):
            # These messages are very large and complicated, so ignore them.
            # I should probably ignore them while logging.
            continue

        contentsRaw = mp.group(3)
        contents = "???"
        try:
            contents = parseJS(contentsRaw)
        except ParseError as p:
            print(p, file=sys.stderr)
            print(f'  while parsing: {contentsRaw}', file=sys.stderr)
            return

        # TODO Catch the exception.
        t = jsValToType(contents)

        currMessages = actors.setdefault(actorName, {})
        currTypes = currMessages.setdefault(messageName, [])
        if args.strict:
            found = False
            for currType in currTypes:
                if currType == t:
                    found = True
                    break
            if not found:
                currTypes.append(t)
        else:
            foundAt = -1
            for i, currType in enumerate(currTypes):
                currType2 = currType.union(t)
                if currType2:
                    foundAt = i
                    t = currType2
                    break
            if foundAt != -1:
                currTypes[foundAt] = t
            else:
                currTypes.append(t)

    for a, mm in actors.items():
        print(a)
        for m, tt in mm.items():
            if len(tt) == 1:
                print(f"  {m} {tt[0]}")
            else:
                print(f"  {m}")
                tts = [str(t) for t in tt]
                for t in sorted(tts):
                    print(f"    {t}")
        print()

parser = argparse.ArgumentParser()
parser.add_argument("--strict",
                    help="Use strict matching for types, instead of unioning.",
                    action="store_true")
args = parser.parse_args()

lookAtActors(args)
