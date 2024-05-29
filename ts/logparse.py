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

from actor_decls import ActorDecls, ActorError
from ts_parse import TypeParser

messageKindPatt = "Message|Query|QueryResolve|QueryReject"
typePatt = re.compile(
    f"JSIT (Send|Recv) ACTOR ([^ ]+) MESSAGE ([^ ]+) KIND ({messageKindPatt}) TYPE (.+)$"
)
# This can also be CONTENTS instead of TYPE, and then it will have the result
# of toSource(), but I'm not logging that right now so don't worry about it.

# Ideally, we'd report the file and test these warnings happened during.
fallbackWarningPatt = re.compile("WARNING: AnyToJSIPCValue fallback for (.+): file")
failedToSerializeWarningPatt = re.compile("WARNING: Failed to serialize")


def kindToEnum(k):
    if len(k) == 7:
        # Message
        return 0
    if len(k) == 5:
        # Query
        return 1
    if len(k) == 12:
        # QueryResolve
        return 2
    # QueryReject
    assert len(k) == 11
    return 3


def lookAtActors(args):
    sys.stdin.reconfigure(encoding="latin1")

    parser = TypeParser()

    actors = {}

    fallbackWith = {}
    failedSerialize = 0

    failedType = []

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

        actorName = tp.group(2)

        # XXX TEMPORARY workaround. This should be filtered while logging.
        if actorName == "DevToolsProcess":
            continue

        messageName = tp.group(3)
        kind = kindToEnum(tp.group(4))

        # XXX In the previous version of this script, I was skipping
        # for messages with actorName == "DevToolsFrame" and
        # messageName == "DevToolsFrameChild:packet".

        typeRaw = tp.group(5)
        currActor = actors.setdefault(actorName, {})
        currMessage = currActor.setdefault(messageName, [[], [], [], []])
        currTypes = currMessage[kind]

        if typeRaw == "NO VALUE":
            # The JS IPC value being passed in was None, so nothing to do.
            continue
        if typeRaw == "FAILED":
            failedType.append([actorName, messageName])
            continue

        try:
            ty = parser.parse(typeRaw)
            if ty not in currTypes:
                currTypes.append(ty)
        except ActorError as e:
            print(e, file=sys.stderr)
            print(f"  while parsing: {typeRaw}", file=sys.stderr)
            return

    # Union together the types from different instances of each message.
    actors = ActorDecls.unify(actors, log=not (args.json or args.ts))

    if args.json:
        actors.printJSON()
        return
    elif args.ts:
        actors.printTS()
        return

    print("=========================")
    print()
    actors.printText()
    print()

    if len(failedType) > 0:
        print("=========================")
        print()
        print("****FAILURES****")
        for [a, m] in failedType:
            print(f"Actor: {a}; Message: {m}")
        print()

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
parser.add_argument("--json", help="Print output as JSON.", action="store_true")
parser.add_argument("--ts", help="Print output as TypeScript.", action="store_true")
args = parser.parse_args()

lookAtActors(args)
