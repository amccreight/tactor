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
from ts import TestOnlyType
from ts_parse import TypeParser

messageKindPatt = "Message|Query|QueryResolve|QueryReject"
typePatt = re.compile(
    f"JSIT (Send|Recv) ACTOR ([^ ]+) MESSAGE ([^ ]+) KIND ({messageKindPatt}) TYPE (.+)$"
)
# This can also be CONTENTS instead of TYPE, and then it will have the result
# of toSource(), but I'm not logging that right now so don't worry about it.

# Ideally, we'd report the file and test these messages happened during.
serializerMsgPatt = re.compile("/JSIPCSerializer (.+)$")
fallbackMsg = re.compile("UntypedFromJSVal fallback: (.+)")


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


# This provides a way to skip specific actors, although in the long term it
# is better to ignore these messages in Firefox itself so we avoid using
# IPDL serialization.
actorsToIgnore = set(["BrowserToolboxDevToolsProcess", "MarionetteCommands"])

# XXX Ideally, we'd support going from actor names directly to types, instead
# of having to list all of the messages we found.
testActors = set(
    [
        "BrowserTestUtils",
        "Bug1622420",
        "ReftestFission",
        "StartupContentSubframe",
        "TestProcessActor",
        "TestWindow",
        "SpecialPowers",
    ]
)


def specialType(actorName):
    if actorName in testActors:
        return TestOnlyType()
    return None


def lookAtActors(args):
    sys.stdin.reconfigure(encoding="latin1")

    parser = TypeParser()

    actors = {}
    failedType = []

    fallbackFor = {}
    otherSerializerMsgs = {}

    # Parse the input.
    for l in sys.stdin:
        serializerMsgMatch = serializerMsgPatt.search(l)
        if serializerMsgMatch:
            serializerMsg = serializerMsgMatch.group(1)
            fallbackMatch = fallbackMsg.fullmatch(serializerMsg)
            if fallbackMatch:
                failCase = fallbackMatch.group(1)
                fallbackFor[failCase] = fallbackFor.setdefault(failCase, 0) + 1
                continue
            otherSerializerMsgs[serializerMsg] = (
                otherSerializerMsgs.setdefault(serializerMsg, 0) + 1
            )
            continue

        tp = typePatt.search(l)
        if not tp:
            continue

        actorName = tp.group(2)
        if actorName in actorsToIgnore:
            continue
        messageName = tp.group(3)
        kind = kindToEnum(tp.group(4))

        # XXX In the previous version of this script, I was skipping
        # for messages with actorName == "DevToolsFrame" and
        # messageName == "DevToolsFrameChild:packet".

        typeRaw = tp.group(5)
        if typeRaw == "NO VALUE":
            # The JS IPC value being passed in was None, so nothing to do.
            continue
        if typeRaw == "FAILED":
            failedType.append([actorName, messageName])
            continue

        currActor = actors.setdefault(actorName, {})
        currMessage = currActor.setdefault(messageName, [[], [], [], []])
        currTypes = currMessage[kind]

        ty = specialType(actorName)
        if ty is None:
            try:
                ty = parser.parse(typeRaw)
            except ActorError as e:
                print(e, file=sys.stderr)
                print(f"  while parsing: {typeRaw}", file=sys.stderr)
                return
        if ty not in currTypes:
            currTypes.append(ty)

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
    nameChars = actors.nameChars()

    def filterChars(cc1):
        patt = re.compile("[a-zA-Z0-9]")
        cc2 = []
        for c in sorted(list(cc1)):
            if patt.fullmatch(c):
                continue
            cc2.append(c)
        if len(cc2) == 0:
            return "none"
        return "".join(cc2)

    print("Actor name non-alphanumeric characters: " + filterChars(nameChars[0]))
    print("Message name non-alphanumeric characters: " + filterChars(nameChars[1]))
    print()

    print("=========================")
    print()

    if len(fallbackFor) > 0:
        print("UntypedFromJSVal fallbacks:")
        counts = [(c, t) for [t, c] in fallbackFor.items()]
        counts.sort(reverse=True)
        maxCountLen = len(str(counts[0][0]))
        for c, t in counts:
            print(f"  {str(c).rjust(maxCountLen)} {t}")
    else:
        print("Found no UntypedFromJSVal fallbacks.")
    print()
    if len(otherSerializerMsgs) > 0:
        print("Other JSIPCSerializer messages:")
        counts = [(c, w) for [w, c] in otherSerializerMsgs.items()]
        counts.sort(reverse=True)
        maxCountLen = len(str(counts[0][0]))
        for c, w in counts:
            print(f"  {str(c).rjust(maxCountLen)} {w}")
    else:
        print("Found no other JSIPCSerializer messages.")


parser = argparse.ArgumentParser()
parser.add_argument("--json", help="Print output as JSON.", action="store_true")
parser.add_argument("--ts", help="Print output as TypeScript.", action="store_true")
args = parser.parse_args()

lookAtActors(args)
