#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Representation of actor message types.

import json
import re
import sys
import unittest

from ts import AnyType, PrimitiveType, identifierRe, messageNameRe, unionWith


# Representation of a source file location. This is needed so we can report
# useful errors for things like duplicate definitions
class Loc:
    def __init__(self, filename="<??>", lineno=0):
        assert filename
        self.filename = filename
        self.lineno = lineno

    def __repr__(self):
        return "%r:%r" % (self.filename, self.lineno)

    def __str__(self):
        return "%s:%s" % (self.filename, self.lineno)

    def __eq__(self, o):
        return self.filename == o.filename and self.lineno == o.lineno


class ActorError(Exception):
    def __init__(self, loc, msg):
        self.loc = loc
        self.error = f"{str(loc)}: {msg}"

    def __str__(self):
        return self.error


def quoteNonIdentifier(name):
    if identifierRe.fullmatch(name):
        return name
    else:
        return '"' + name + '"'


def kindToStr(kind):
    if kind == 0:
        return "sendAsyncMessage()"
    if kind == 1:
        return "sendQuery()"
    if kind == 2:
        return "query reply"
    assert kind == 3
    return "query reject"


class printSerializer:
    def add(self, s):
        sys.stdout.write(s)

    def addLine(self, s):
        print(s)


class stringSerializer:
    def __init__(self):
        self.string = ""

    def add(self, s):
        self.string += s

    def addLine(self, s):
        self.string += s + "\n"


class fileSerializer:
    def __init__(self, file):
        self.file = file

    def add(self, s):
        self.file.write(s)

    def addLine(self, s):
        self.file.write(s)
        self.file.write("\n")


class ActorDecls:
    def __init__(self):
        self.actors = {}

    def addActor(self, actorName, actorDecl):
        if actorName in self.actors:
            loc0 = self.actors[actorName].loc
            raise ActorError(
                actorDecl.loc,
                f"Multiple declarations of actor {actorName}."
                + f" Previous was at {loc0}",
            )
        else:
            # The parser guarantees this.
            assert identifierRe.fullmatch(actorName)
        self.actors[actorName] = actorDecl

    # Helper for use by the parser.
    def addActorL(self, l):
        assert isinstance(l, list)
        assert len(l) == 2
        self.addActor(l[0], l[1])

    def addActors(self, decls):
        assert isinstance(decls, ActorDecls)
        for a, d in decls.actors.items():
            self.addActor(a, d)

    def addMessage(self, loc, actorName, messageName, t):
        assert actorName in self.actors
        actor = self.actors[actorName]
        if not actor.addMessage(loc, messageName, t):
            loc0 = actor.existingMessageLoc(messageName)
            raise ActorError(
                loc,
                f"Multiple declarations of message {messageName} "
                + f"for actor {actorName}. Previous was at {loc0}",
            )

    # Return a pair of sets of characters. One for those from the
    # actor names and one for the message names.
    def nameChars(self):
        actorNamesChars = set()
        messageNamesChars = set()
        for actorName, messages in self.actors.items():
            actorNamesChars |= set(actorName)
            messageNamesChars |= messages.nameChars()
        return [actorNamesChars, messageNamesChars]

    def serializeJSON(self, s):
        s.addLine("{")
        firstActor = True
        for actorName in sorted(list(self.actors.keys())):
            messages = self.actors[actorName]
            if firstActor:
                firstActor = False
            else:
                s.addLine(",")
            # I'm not sure if we need quotes given that the
            # actor name is a valid identifier.
            s.add(f'  "{actorName}": ')
            messages.serializeJSON(s, "  ")
        s.addLine("")
        s.addLine("}")

    def toJSON(self):
        s = stringSerializer()
        self.serializeJSON(s)
        return s.string

    def printJSON(self):
        self.serializeJSON(printSerializer())

    def writeJSONToFile(self, f):
        s = fileSerializer(f)
        self.serializeJSON(s)

    def serializeTS(self, s):
        s.addLine("type MessageTypes = {")
        for actorName in sorted(list(self.actors.keys())):
            messages = self.actors[actorName]
            s.add(f"  {actorName}: ")
            messages.serializeTS(s, "  ")
        s.addLine("};")

    def toTS(self):
        s = stringSerializer()
        self.serializeTS(s)
        return s.string

    def printTS(self):
        self.serializeTS(printSerializer())

    # Very similar to the TS format, except the actor decls part isn't a
    # dictionary.
    def serializeText(self, s):
        for actorName in sorted(list(self.actors.keys())):
            messages = self.actors[actorName]
            s.addLine(f"{actorName}")
            messages.serializeText(s, "")
            s.addLine("")

    def printText(self):
        self.serializeText(printSerializer())

    def unify1(a, m, kindTypes, loggedCurrentActor, log=False):
        haveQueryResolve = False
        newTypes = []
        lastNonNone = -1
        for kind in range(len(kindTypes)):
            types = kindTypes[kind]
            if len(types) == 0:
                if kind == 3 and haveQueryResolve:
                    # If no reject type was specified, but a resolve type
                    # was, allow any type for the reject.
                    newTypes.append(AnyType())
                    lastNonNone = kind
                else:
                    newTypes.append(None)
                continue
            if kind == 2:
                haveQueryResolve = True
            if len(types) == 1:
                assert types[0] is not None
                newTypes.append(types[0])
                lastNonNone = kind
                continue
            if log:
                if not loggedCurrentActor:
                    print(a)
                    loggedCurrentActor = True
                print(f"  {m}")
                for t in sorted([str(t) for t in types]):
                    print(f"    {t}")
            tCombined = None
            for t in types:
                if tCombined is None:
                    tCombined = t
                    continue
                tCombined = unionWith(tCombined, t)
                assert tCombined is not None
            assert tCombined is not None
            newTypes.append(tCombined)
            lastNonNone = kind
            if log:
                print(f"  {kindToStr(kind)} message COMBINED: {tCombined}")
        newTypes = newTypes[: lastNonNone + 1]
        assert len(newTypes) <= 4
        if len(newTypes) == 0:
            raise Exception(f"Message {m} of actor {a} has no types.")
        if len(newTypes) > 1:
            if newTypes[0] is not None:
                raise Exception(
                    f"Message {m} of actor {a} " + "has both message and query types."
                )
            if len(newTypes) == 4 and newTypes[2] is None:
                # XXX Not sure what we should do for this.
                raise Exception(
                    f"Message {m} of actor {a} has "
                    + "query reject, but not query "
                    + "resolve type."
                )
            newTypes = newTypes[1:3]
            if len(newTypes) == 1:
                newTypes.append(None)
            assert len(newTypes) == 2
        return [newTypes, loggedCurrentActor]

    # This takes a map from actor names to message names to a list of list of
    # types and combines the list of types together to produce an ActorDecls.
    def unify(actors, log=False):
        newActors = ActorDecls()

        if log:
            print("Logging information about type combining")
            print()

        for a in sorted(list(actors.keys())):
            newActors.addActor(a, ActorDecl(Loc()))
            loggedCurrentActor = False
            messages = actors[a]
            for m in sorted(list(messages.keys())):
                kindTypes = messages[m]
                [newTypes, logged] = ActorDecls.unify1(
                    a, m, kindTypes, loggedCurrentActor, log
                )
                loggedCurrentActor = logged
                newActors.addMessage(Loc(), a, m, newTypes)
            if log and loggedCurrentActor:
                print()

        return newActors


# For now, only allow actor declarations in a single location. Hopefully
# that is sufficient.
class ActorDecl:
    def __init__(self, loc):
        self.loc = loc
        self.messages = {}

    def addMessage(self, loc, messageName, t):
        if messageName in self.messages:
            return False
        assert messageNameRe.fullmatch(messageName)
        self.messages[messageName] = MessageTypes(loc, t)
        return True

    # Helper method that is easier to use while parsing.
    def addMessageL(self, l):
        assert isinstance(l, list)
        assert len(l) == 3
        return self.addMessage(l[0], l[1], l[2])

    def existingMessageLoc(self, messageName):
        assert messageName in self.messages
        return self.messages[messageName].loc

    def nameChars(self):
        messageNamesChars = set()
        for messageName in self.messages.keys():
            messageNamesChars |= set(messageName)
        return messageNamesChars

    def serializeJSON(self, s, indent):
        s.addLine("{")
        firstMessage = True
        for messageName in sorted(list(self.messages.keys())):
            if firstMessage:
                firstMessage = False
            else:
                s.addLine(",")
            s.add(indent + f'  "{messageName}": ')
            self.messages[messageName].serializeJSON(s)
        s.addLine("")
        s.add(indent + "}")

    def toJSON(self):
        s = stringSerializer()
        self.serializeJSON(s, "")
        return s.string

    def serializeTS(self, s, indent):
        s.addLine("{")
        for messageName in sorted(list(self.messages.keys())):
            name = indent + "  " + quoteNonIdentifier(messageName)
            self.messages[messageName].serializeTS(s, name)
        s.addLine(indent + "};")

    def toTS(self):
        s = stringSerializer()
        self.serializeTS(s, "")
        return s.string

    def serializeText(self, s, indent):
        for messageName in sorted(list(self.messages.keys())):
            name = indent + "  " + messageName
            self.messages[messageName].serializeTS(s, name, False)


class MessageTypes:
    def __init__(self, loc, types):
        assert isinstance(types, list)
        assert 0 < len(types) <= 2
        self.loc = loc
        self.types = types
        if len(types) == 1:
            assert types[0] is not None
        elif len(types) == 2:
            assert types[0] is not None or types[1] is not None

    def serializeJSON(self, s):
        tt = [t.jsonStr() if t is not None else '"never"' for t in self.types]
        s.add(f'[{", ".join(tt)}]')

    def toJSON(self):
        s = stringSerializer()
        self.serializeJSON(s)
        return s.string

    # messageName must include any indentation.
    # The realTS is false case is an attempt to make a nicer
    # looking output that isn't TypeScript.
    def serializeTS(self, s, messageName, realTS=True):
        if realTS:
            s.add(f"{messageName}: ")
        else:
            s.add(f"{messageName} : ")

        if len(self.types) == 1:
            s.add(f"{self.types[0]}")
        else:
            assert len(self.types) == 2

            def typeString(i):
                if i < len(self.types) and self.types[i] is not None:
                    return str(self.types[i])
                return "never"

            s.add(f"(_: {typeString(0)}) => {typeString(1)}")

        if realTS:
            s.addLine(";")
        else:
            s.addLine("")

    def toTS(self, messageName):
        s = stringSerializer()
        self.serializeTS(s, messageName)
        return s.string


class MessageTests(unittest.TestCase):
    def test_messageTypes(self):
        # sendAsyncMessage
        mt = MessageTypes(Loc(), [AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["any"])
        self.assertEqual(mt.toTS("x"), "x: any;\n")

        # query
        mt = MessageTypes(Loc(), [AnyType(), None])
        self.assertEqual(json.loads(mt.toJSON()), ["any", "never"])
        self.assertEqual(mt.toTS("x"), "x: (_: any) => never;\n")

        # query resolve
        mt = MessageTypes(Loc(), [None, AnyType()])
        self.assertEqual(
            json.loads(mt.toJSON()),
            [
                "never",
                "any",
            ],
        )
        self.assertEqual(mt.toTS("x"), "x: (_: never) => any;\n")

        # query and query resolve
        mt = MessageTypes(Loc(), [PrimitiveType("undefined"), AnyType()])
        self.assertEqual(
            json.loads(mt.toJSON()),
            [
                "undefined",
                "any",
            ],
        )
        self.assertEqual(mt.toTS("x"), "x: (_: undefined) => any;\n")

    def test_messageDecls(self):
        ad = ActorDecl(Loc())
        self.assertEqual(ad.addMessage(Loc(), "M2", [AnyType()]), True)
        self.assertEqual(json.loads(ad.toJSON()), {"M2": ["any"]})
        self.assertEqual(ad.toTS(), "{\n  M2: any;\n};\n")
        self.assertEqual(ad.addMessage(Loc(), "M1", [None, AnyType()]), True)
        self.assertEqual(
            json.loads(ad.toJSON()), {"M1": ["never", "any"], "M2": ["any"]}
        )
        self.assertEqual(ad.toTS(), "{\n  M1: (_: never) => any;\n  M2: any;\n};\n")
        # Adding a message twice fails.
        self.assertEqual(ad.addMessage(Loc(), "M2", [AnyType()]), False)
        self.assertEqual(ad.addMessage(Loc(), "M2", [AnyType(), None]), False)

        # Name that needs quotes.
        ad = ActorDecl(Loc())
        self.assertEqual(ad.addMessage(Loc(), "A1:M1", [AnyType()]), True)
        self.assertEqual(json.loads(ad.toJSON()), {"A1:M1": ["any"]})
        self.assertEqual(ad.toTS(), '{\n  "A1:M1": any;\n};\n')

    def test_actorDecls(self):
        ads = ActorDecls()
        self.assertEqual(json.loads(ads.toJSON()), {})
        ads.addActor("B", ActorDecl(Loc()))
        self.assertEqual(json.loads(ads.toJSON()), {"B": {}})
        with self.assertRaisesRegex(ActorError, "Multiple declarations of actor B."):
            ads.addActor("B", ActorDecl(Loc()))
        ads.addMessage(Loc(), "B", "M", [AnyType()])
        self.assertEqual(json.loads(ads.toJSON()), {"B": {"M": ["any"]}})
        e = "Multiple declarations of message M for actor B."
        with self.assertRaisesRegex(ActorError, re.escape(e)):
            ads.addMessage(Loc(), "B", "M", [AnyType(), None])
        ads.addActor("A", ActorDecl(Loc()))
        ads.addMessage(Loc(), "A", "M", [AnyType()])
        self.assertEqual(
            json.loads(ads.toJSON()), {"A": {"M": ["any"]}, "B": {"M": ["any"]}}
        )
        self.assertEqual(
            ads.toTS(),
            "type MessageTypes = {\n"
            + "  A: {\n    M: any;\n  };\n"
            + "  B: {\n    M: any;\n  };\n"
            + "};\n",
        )

        # Basic tests for addActors
        ads = ActorDecls()
        ads.addActor("B", ActorDecl(Loc()))
        ads.addMessage(Loc(), "B", "M", [AnyType()])
        ads2 = ActorDecls()
        ads.addActor("A", ActorDecl(Loc()))
        ads.addMessage(Loc(), "A", "M", [AnyType()])
        ads.addActor("C", ActorDecl(Loc()))
        ads.addMessage(Loc(), "C", "M", [AnyType()])
        ads.addActors(ads2)
        self.assertEqual(
            json.loads(ads.toJSON()),
            {"A": {"M": ["any"]}, "B": {"M": ["any"]}, "C": {"M": ["any"]}},
        )

        ads = ActorDecls()
        ads.addActor("A", ActorDecl(Loc()))
        ads2 = ActorDecls()
        ads2.addActor("A", ActorDecl(Loc()))
        with self.assertRaisesRegex(ActorError, "Multiple declarations of actor A."):
            ads.addActors(ads2)

    def assertUnify(self, types1, j):
        [types2, _] = ActorDecls.unify1("A", "M", types1, False)
        self.assertEqual([str(t) for t in types2], j)

    def test_unify(self):
        # Basic single types.
        t = [[AnyType()], [], [], []]
        self.assertUnify(t, ["any"])

        t = [[], [AnyType()], [], []]
        self.assertUnify(t, ["any", "None"])

        t = [[], [], [AnyType()], []]
        self.assertUnify(t, ["None", "any"])

        t = [[], [AnyType()], [AnyType()], []]
        self.assertUnify(t, ["any", "any"])

        t = [[], [AnyType()], [AnyType()], [AnyType()]]
        self.assertUnify(t, ["any", "any"])

        t = [[], [], [AnyType()], [AnyType()]]
        self.assertUnify(t, ["None", "any"])

        # message and various query types
        m = "Message M of actor A has both message and query types."
        t = [[AnyType()], [AnyType()], [], []]
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)
        t = [[AnyType()], [], [AnyType()], []]
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)
        t = [[AnyType()], [], [], [AnyType()]]
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)

        # query reject only
        t = [[], [], [], [AnyType()]]
        m = "Message M of actor A has query reject, but not query resolve type."
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)


if __name__ == "__main__":
    unittest.main()
