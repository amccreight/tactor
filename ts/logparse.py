#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parsing JS actor type logs.

# This takes the output of Firefox modified to log a subset of TypeScript for
# JS actor messages and tries to combine the types of different instances
# of the same message into a single type, and then outputs the types
# it found for all messages.
#
# It also tries to extract some information about the fallback serialization.

import argparse
import re
import sys
from copy import deepcopy

from actor_decls import ActorDecls, ActorError
from overrides import defaultOverride
from ts_parse import TypeParser

mozLogModules = [
    "JSIPCValSend",
    "JSIPCValRecv",
    "JSIPCTypeSend",
    "JSIPCTypeRecv",
    "JSIPCTypeChecking",
    "JSIPCTypeMemory",
    "JSIPCSerializer",
]
mozLogModulesPatt = re.compile(f"/({'|'.join(mozLogModules)}) (.*)$")

messageKindPatt = "Message|Query|QueryResolve|QueryReject"
typePatt = re.compile(
    f"JSIT (Send|Recv) ACTOR ([^ ]+) MESSAGE ([^ ]+) KIND ({messageKindPatt}) TYPE (.+)$"
)
# This can also be CONTENTS instead of TYPE, and then it will have the result
# of toSource(), but I'm not logging that right now so don't worry about it.

# Ideally, we'd report the file and test these messages happened during.
serializerMsgPatt = re.compile("JSIPCSerializer (.+)$")
fallbackMsg = re.compile("UntypedFromJSVal fallback: (.+)")


# This provides a way to skip specific actors, although in the long term it
# is better to ignore these messages in Firefox itself so we avoid using
# IPDL serialization.
actorsToIgnore = set([])


typeParser = TypeParser()


def lookAtActors(args):
    sys.stdin.reconfigure(encoding="latin1")

    kindToEnum = {
        len("Message"): 0,
        len("Query"): 1,
        len("QueryResolve"): 2,
        len("QueryReject"): 3,
    }

    # Raw type strings to actor names to message names to kinds.
    # Kinds is an integer or a set of integers.
    # The idea here is that more than 99.9% of the raw type strings
    # we see are duplicates, so the data structure is focused on
    # eliminating duplicates as efficiently as possible.
    typeActors = {}

    failedType = []

    fallbackFor = {}
    otherSerializerMsgs = {}
    otherMsgs = set([])

    ignoredActors = set([])

    # Parse the input.
    for l in sys.stdin:
        modulesMatch = mozLogModulesPatt.search(l)
        if not modulesMatch:
            continue
        module = modulesMatch.group(1)
        msg = modulesMatch.group(2)

        if module == "JSIPCTypeSend":
            tp = typePatt.match(msg)
            if not tp:
                print("Unknown JSIPCTypeSend: " + msg, file=sys.stderr)
                if args.ignore_errors:
                    continue
                assert tp

            actorName = tp.group(2)
            if actorName in actorsToIgnore:
                ignoredActors.add(actorName)
                continue
            messageName = tp.group(3)
            kind = kindToEnum[len(tp.group(4))]

            rawType = tp.group(5)
            if rawType == "NO VALUE":
                # The JS IPC value being passed in was None, so nothing to do.
                continue
            if rawType == "FAILED":
                failedType.append([actorName, messageName])
                continue

            if actorName == "Conduits":
                if messageName == "CreateProxyContext" and kind == 1:
                    # test_ext_subframes_privileges.html uses CreateProxyContext as a
                    # query, whereas everything else uses it as a message. This causes
                    # problems, so ignore it for now. See bug 1903128.
                    continue

            currType = typeActors.setdefault(rawType, {})
            currActor = currType.setdefault(actorName, {})
            existingKind = currActor.setdefault(messageName, kind)
            if existingKind == kind:
                continue

            if isinstance(existingKind, int):
                # Multiple kinds are very rare, so for efficiency don't create
                # a set unless we really need one.
                currActor[messageName] = set([existingKind])
            else:
                assert isinstance(existingKind, set)
                existingKind.add(kind)
            continue

        if module == "JSIPCSerializer":
            fallbackMatch = fallbackMsg.fullmatch(msg)
            if fallbackMatch:
                failCase = fallbackMatch.group(1)
                fallbackFor[failCase] = fallbackFor.setdefault(failCase, 0) + 1
                continue
            otherSerializerMsgs[msg] = otherSerializerMsgs.setdefault(msg, 0) + 1
            continue

        otherMsgs.add(f"{module}: {msg}")

    # Something like 94% of the total runtime of this script is up to this
    # point, so don't bother spending much time optimizing the rest of it.

    # Convert the dictionary to be actor-first for easier processing.
    # * Don't bother checking for duplicates. It is a few % slower, and we
    #   already know the initial type string isn't a duplicate, so it doesn't
    #   seem likely you'd end up with a duplicate type, given that the strings
    #   are automatically generated.
    # * ActorDecls.unify mutates the type, so multiple messages can't share
    #   the same type. On the other hand, copying large object types can be
    #   expensive. Therefore, we only do a copy if we actually need more than
    #   one, reusing the type created during parsing. This eliminates something
    #   like 70% of the type copying.
    actors = {}
    for rawType, actors0 in typeActors.items():
        try:
            ty = typeParser.parse(rawType)
            # The C++ logging does not use heuristics to combine object types,
            # so do that here before we get any further.
            ty = ty.simplify()
        except ActorError as e:
            print(e, file=sys.stderr)
            print(f"  while parsing: {rawType}", file=sys.stderr)
            if args.ignore_errors:
                continue
            return
        typeUsed = False
        for actorName, messages in actors0.items():
            currActor = actors.setdefault(actorName, {})
            for messageName, kinds0 in messages.items():
                currMessage = currActor.setdefault(messageName, [[], [], [], []])
                if isinstance(kinds0, int):
                    kinds = set([kinds0])
                else:
                    kinds = kinds0
                for kind in kinds:
                    currTypes = currMessage[kind]
                    if typeUsed:
                        currTypes.append(deepcopy(ty))
                    else:
                        currTypes.append(ty)
                        typeUsed = True

    typeActors = None

    # Union together the types from different instances of each message.
    actors = ActorDecls.unify(actors, log=not (args.json or args.ts))

    # Set any hard coded messages.
    if not args.no_overrides:
        actors.override(defaultOverride(typeParser))

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

    if len(otherMsgs) > 0:
        print("=========================")
        print()
        print("Other logged messages")
        for m in sorted(otherMsgs):
            print("  " + m)
        print()

    if len(ignoredActors) > 0:
        print("=========================")
        print()
        print(f"Ignored actors: {', '.join(ignoredActors)}")
        print()


parser = argparse.ArgumentParser()
parser.add_argument("--json", help="Print output as JSON.", action="store_true")
parser.add_argument("--ts", help="Print output as TypeScript.", action="store_true")
parser.add_argument("--no-overrides", help="Disable overrides", action="store_true")
parser.add_argument("--ignore-errors", help="Ignore parse errors", action="store_true")
args = parser.parse_args()

lookAtActors(args)
