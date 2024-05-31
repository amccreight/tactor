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
valueUtilsWarning = re.compile(
    "WARNING: (.+): file .+dom/ipc/jsactor/JSIPCValueUtils\\.cpp:\\d+"
)
fallbackWarning = re.compile("UntypedFromJSVal fallback(?: with| for|:) (.+)")


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
    failedType = []

    fallbackFor = {}
    otherWarnings = {}

    # Parse the input.
    for l in sys.stdin:
        wp = valueUtilsWarning.search(l)
        if wp:
            warning = wp.group(1)
            fallbackMatch = fallbackWarning.fullmatch(warning)
            if fallbackMatch:
                failCase = fallbackMatch.group(1)
                fallbackFor[failCase] = fallbackFor.setdefault(failCase, 0) + 1
                continue
            otherWarnings[warning] = otherWarnings.setdefault(warning, 0) + 1
            continue

        tp = typePatt.search(l)
        if not tp:
            continue

        actorName = tp.group(2)
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
        for c, t in counts:
            print(f"\t{c}\t{t}")
    else:
        print("Found no UntypedFromJSVal fallbacks.")
    print()
    if len(otherWarnings) > 0:
        print("Other JSIPCValueUtils.cpp warnings:")
        counts = [(c, w) for [w, c] in otherWarnings.items()]
        counts.sort(reverse=True)
        for c, w in counts:
            print(f"\t{c}\t{w}")
    else:
        print("Found no other JSIPCValueUtils.cpp warnings.")


parser = argparse.ArgumentParser()
parser.add_argument("--json", help="Print output as JSON.", action="store_true")
parser.add_argument("--ts", help="Print output as TypeScript.", action="store_true")
args = parser.parse_args()

lookAtActors(args)
