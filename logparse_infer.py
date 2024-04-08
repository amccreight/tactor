#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Analyze JS actor logging.

# This is intended to work with the C++-based type logging from the
# prototype version of bug 1885221 as of April 8, 2024.
#
# Goals:
# 1) Extract the types for individual messages and combine them
#   together into types we can use as specifications for the messages/
# 2) Figure out which cases for fallback serialization (represented
#   by the "Any" type should be implemented. These will show up as
#   "AnyToJSIPCValue fallback with" warnings.
# 3) Tracking "Failed to serialize" warnings might be useful, too.


import argparse
import re
import sys
import json
from jsparse import parseJS, ParseError
from type import jsValToType


typePatt = re.compile('JSIT (Send|Recv) ACTOR ([^ ]+) MESSAGE ([^ ]+) TYPE (.+)$')
# This can also be CONTENTS instead of TYPE, and then it will have the result
# of toSource(), but I'm not logging that right now so don't worry about it.

# Ideally, we'd report the file and test these warnings happened during.
fallbackWarningPatt = re.compile('WARNING: AnyToJSIPCValue fallback with (.+): file')
failedToSerializeWarningPatt = re.compile('WARNING: Failed to serialize')


def lookAtActors(args):
    sys.stdin.reconfigure(encoding='latin1')

    actors = {}

    fallbackWith = {}
    failedSerialize = 0

    for l in sys.stdin:
        fwp = fallbackWarningPatt.search(l)
        if fwp:
            failCase = fwp.group(1)
            if failCase in fallbackWith:
                fallbackWith[failCase] += 1
            else:
                fallbackWith[failCase] = 1
            continue
        ftswp = failedToSerializeWarningPatt.search(l)
        if ftswp:
            failedSerialize += 1
        continue
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

    for t, c in fallbackWith.items():
        print(f"Fallback with {t}; count: {c}")
    # I disabled the warning for ESClass::Other because it was spammy in one
    # log I looked at, so this is so I don't forget.
    print(f"Fallback with ESClass::Other; count: ???")
    print()
    print(f"Failed to serialize count: {failedSerialize}")
    return

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