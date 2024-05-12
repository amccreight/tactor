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

# It would be nice to have information about which are the most frequent
# messages with "Any" in the type. Also I could collect information about
# the field names for "Any" types. eg if a field named lastModifiedDate
# has Any, it is probably a Type.

import argparse
import re
import sys
from ts_parse import parseType, ParseError
from ts import unifyMessageTypes, printMessageTypes, printJSONMessageTypes

typePatt = re.compile('JSIT (Send|Recv) ACTOR ([^ ]+) MESSAGE ([^ ]+) TYPE (.+)$')
# This can also be CONTENTS instead of TYPE, and then it will have the result
# of toSource(), but I'm not logging that right now so don't worry about it.

# Ideally, we'd report the file and test these warnings happened during.
fallbackWarningPatt = re.compile('WARNING: AnyToJSIPCValue fallback for (.+): file')
failedToSerializeWarningPatt = re.compile('WARNING: Failed to serialize')


def lookAtActors(args):
    sys.stdin.reconfigure(encoding='latin1')

    actors = {}

    fallbackWith = {}
    failedSerialize = 0

    # Parse the input.
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

        tp = typePatt.search(l)
        if not tp:
            continue

        isSend = tp.group(1) == "Send"
        actorName = tp.group(2)
        messageName = tp.group(3)

        # XXX In the previous version of this script, I was skipping
        # for messages with actorName == "DevToolsFrame" and
        # messageName == "DevToolsFrameChild:packet".

        typeRaw = tp.group(4)
        currActor = actors.setdefault(actorName, {})
        currMessage = currActor.setdefault(messageName, [])
        try:
            ty = parseType(typeRaw)
            if ty not in currMessage:
                currMessage.append(ty)
        except ParseError as p:
            print(p, file=sys.stderr)
            print(f'  while parsing: {typeRaw}', file=sys.stderr)
            return

    # Union together the types from different instances of each message.
    actors = unifyMessageTypes(actors, log=not args.json)

    if args.json:
        printJSONMessageTypes(actors)
        return

    print("=========================")
    print()
    printMessageTypes(actors)
    print("=========================")
    print()

    if len(fallbackWith) > 0:
        for t, c in fallbackWith.items():
            print(f"Fallback with {t}; count: {c}")
    else:
        print("Found no instances of AnyToJSIPCValue fallback.")
    print()
    print(f"Failed to serialize count: {failedSerialize}")

parser = argparse.ArgumentParser()
parser.add_argument("--json",
                    help="Print output as JSON.",
                    action="store_true")
args = parser.parse_args()

lookAtActors(args)
