#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parsing JS actor type logging.

# This takes the output of Firefox modified to log a subset of TypeScript for
# JS actor messages and tries to combine the types of different instances
# of the same message into a single type, and then outputs the types
# it found for all messages.
#
# It also tries to extract some information about the fallback serialization.

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
