#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Representation of actor message types.

import json
import unittest
import re
import sys
from ts import identifierRe, AnyType, unionWith


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
        assert "\"" not in actorName
        if actorName in self.actors:
            loc0 = self.actors[actorName].loc
            raise ActorError(actorDecl.loc,
                             f'Multiple declarations of actor "{actorName}".' +
                             f' Previous was at {loc0}')
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

    def addMessage(self, loc, actorName, messageName, t, kind):
        assert actorName in self.actors
        actor = self.actors[actorName]
        if not actor.addMessage(loc, messageName, t, kind):
            loc0 = actor.existingMessageKindLoc(messageName, kind)
            raise ActorError(loc,
                             f'Multiple declarations of actor "{actorName}"\'s ' +
                             f'{kindToStr(kind)} message "{messageName}".' +
                             f' Previous was at {loc0}')

    def serializeJSON(self, s):
        s.addLine("{")
        firstActor = True
        for actorName in sorted(list(self.actors.keys())):
            messages = self.actors[actorName]
            if firstActor:
                firstActor = False
            else:
                s.addLine(",")
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
            s.add(f'  {quoteNonIdentifier(actorName)}: ')
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
            s.addLine(f'{actorName}')
            messages.serializeText(s, "")
            s.addLine('')

    def printText(self):
        self.serializeText(printSerializer())

    # This takes a map from actor names to message names to a list of list of
    # types and combines the list of types together to produce an ActorDecl.
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
                haveQueryResolve = False
                for kind in range(len(kindTypes)):
                    types = kindTypes[kind]
                    if len(types) == 0:
                        if kind == 3 and haveQueryResolve:
                            # If no reject type was specified, but a resolve type
                            # was, allow any type for the reject.
                            newActors.addMessage(Loc(), a, m, AnyType(), kind)
                        continue
                    if kind == 2:
                        haveQueryResolve = True
                    if len(types) == 1:
                        newActors.addMessage(Loc(), a, m, types[0], kind)
                        continue
                    if log:
                        if not loggedCurrentActor:
                            loggedCurrentActor = True
                            print(a)
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
                    newActors.addMessage(Loc(), a, m, tCombined, kind)
                    if log:
                        print(f"  {kindToStr(kind)} message COMBINED: {tCombined}")
            if log and loggedCurrentActor:
                print()

        return newActors


# For now, only allow actor declarations in a single location. Hopefully
# that is sufficient.
class ActorDecl:
    def __init__(self, loc):
        self.loc = loc
        self.messages = {}

    def addMessage(self, loc, messageName, t, kind):
        assert "\"" not in messageName
        if messageName not in self.messages:
            self.messages[messageName] = MessageTypes(loc, t, kind)
            return True
        return self.messages[messageName].addType(loc, t, kind)

    # Helper method that is easier to use while parsing.
    def addMessageL(self, l):
        assert isinstance(l, list)
        assert len(l) == 4
        return self.addMessage(l[0], l[1], l[2], l[3])

    def existingMessageKindLoc(self, messageName, kind):
        assert messageName in self.messages
        return self.messages[messageName].existingMessageKindLoc(kind)

    def serializeJSON(self, s, indent):
        s.addLine("{")
        firstMessage = True
        for messageName in sorted(list(self.messages.keys())):
            if firstMessage:
                firstMessage = False
            else:
                s.addLine(",")
            assert "\"" not in messageName
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
            assert "\"" not in messageName
            name = indent + "  " + quoteNonIdentifier(messageName)
            self.messages[messageName].serializeTS(s, name)
        s.addLine(indent + "};")

    def toTS(self):
        s = stringSerializer()
        self.serializeTS(s, "")
        return s.string

    def serializeText(self, s, indent):
        for messageName in sorted(list(self.messages.keys())):
            assert "\"" not in messageName
            name = indent + "  " + messageName
            self.messages[messageName].serializeTS(s, name, False)


class MessageTypes:
    def __init__(self, loc, t, kind):
        self.types = []
        ok = self.addType(loc, t, kind)
        assert ok

    def addType(self, loc, t, kind):
        assert kind >= 0
        assert kind < 4
        if kind >= len(self.types):
            for _ in range(kind - len(self.types) + 1):
                self.types.append(None)
        if self.types[kind] is not None:
            return False
        self.types[kind] = [loc, t]
        return True

    def existingMessageKindLoc(self, kind):
        assert kind >= 0
        assert kind < len(self.types)
        return self.types[kind][0]

    def rawTypes(self):
        tt = []
        for t in self.types:
            if t is None:
                tt.append(None)
            else:
                tt.append(t[1])
        return tt

    def serializeJSON(self, s):
        assert len(self.types) <= 4
        tt = [t[1].jsonStr() if t is not None else '"never"' for t in self.types]
        # For the JSON output, never include the QueryReject type. Instead,
        # let the checker implicitly treat that as "any".
        if len(tt) == 4:
            tt = tt[:3]
        s.add(f'[{", ".join(tt)}]')

    def toJSON(self):
        s = stringSerializer()
        self.serializeJSON(s)
        return s.string

    # messageName must include any indentation.
    def serializeTS(self, s, messageName, realTS = True):
        assert len(self.types) <= 4
        for [i, t] in enumerate(self.types):
            if t is None:
                continue
            t = t[1]
            if i == 3:
                # For the TS output, never include the QueryReject type.
                # Instead, make it implicitly treated as "any", if a
                # QueryResolve type is defined.
                if realTS or t == AnyType():
                    continue
            if realTS:
                s.add(f'{messageName}: ')
            else:
                s.add(f'{messageName} : ')
            if i == 0:
                # Message
                s.add(f'{t}')
            elif i == 1:
                # Query
                s.add(f'(_: {t}) => never')
            elif i == 2:
                # QueryResolve
                s.add(f'(_: never) => {t}')
            else:
                assert i == 3
                assert not realTS
                # QueryReject
                s.add(f'(reject: never) => {t}')

            if realTS:
                s.addLine(';')
            else:
                s.addLine('')

    def toTS(self, messageName):
        s = stringSerializer()
        self.serializeTS(s, messageName)
        return s.string


class MessageTests(unittest.TestCase):
    def test_messageTypes(self):
        mt = MessageTypes(Loc(), AnyType(), 0)
        self.assertEqual(mt.rawTypes(), [AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["any"])
        self.assertEqual(mt.toTS("x"), 'x: any;\n')
        self.assertEqual(mt.addType(Loc(), AnyType(), 2), True)
        self.assertEqual(mt.rawTypes(), [AnyType(), None, AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["any", "never", "any"])
        self.assertEqual(mt.toTS("x"), 'x: any;\nx: (_: never) => any;\n')
        self.assertEqual(mt.addType(Loc(), AnyType(), 2), False)
        self.assertEqual(mt.addType(Loc(), AnyType(), 1), True)
        self.assertEqual(mt.rawTypes(), [AnyType(), AnyType(), AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["any", "any", "any"])
        self.assertEqual(mt.toTS("x"),
                         'x: any;\nx: (_: any) => never;\nx: (_: never) => any;\n')

        mt = MessageTypes(Loc(), AnyType(), 2)
        self.assertEqual(mt.rawTypes(), [None, None, AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["never", "never", "any"])
        self.assertEqual(mt.toTS("x"), 'x: (_: never) => any;\n')
        # You can add a QueryReject kind, but we don't print it as JSON or TS.
        self.assertEqual(mt.addType(Loc(), AnyType(), 3), True)
        self.assertEqual(mt.rawTypes(), [None, None, AnyType(), AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["never", "never", "any"])
        self.assertEqual(mt.toTS("x"), 'x: (_: never) => any;\n')

    def test_messageDecls(self):
        ad = ActorDecl(Loc())
        self.assertEqual(ad.addMessage(Loc(), "M2", AnyType(), 0), True)
        self.assertEqual(json.loads(ad.toJSON()), {"M2": ["any"]})
        self.assertEqual(ad.toTS(), '{\n  M2: any;\n};\n')
        self.assertEqual(ad.addMessage(Loc(), "M1", AnyType(), 2), True)
        self.assertEqual(json.loads(ad.toJSON()),
                         {"M1": ["never", "never", "any"], "M2": ["any"]})
        self.assertEqual(ad.toTS(), '{\n  M1: (_: never) => any;\n  M2: any;\n};\n')
        # Adding a message kind twice fails.
        self.assertEqual(ad.addMessage(Loc(), "M2", AnyType(), 0), False)
        self.assertEqual(ad.addMessage(Loc(), "M1", AnyType(), 1), True)
        self.assertEqual(json.loads(ad.toJSON()),
                         {"M1": ["never", "any", "any"], "M2": ["any"]})
        self.assertEqual(ad.toTS(), '{\n  M1: (_: any) => never;\n  M1: (_: never) => any;\n  M2: any;\n};\n')

        # Name that needs quotes.
        ad = ActorDecl(Loc())
        self.assertEqual(ad.addMessage(Loc(), "A1:M1", AnyType(), 0), True)
        self.assertEqual(json.loads(ad.toJSON()), {"A1:M1": ["any"]})
        self.assertEqual(ad.toTS(), '{\n  "A1:M1": any;\n};\n')

    def test_actorDecls(self):
        ads = ActorDecls()
        self.assertEqual(json.loads(ads.toJSON()), {})
        ads.addActor("B", ActorDecl(Loc()))
        self.assertEqual(json.loads(ads.toJSON()), {"B": {}})
        with self.assertRaisesRegex(ActorError, 'Multiple declarations of actor "B".'):
            ads.addActor("B", ActorDecl(Loc()))
        ads.addMessage(Loc(), "B", "M", AnyType(), 0)
        self.assertEqual(json.loads(ads.toJSON()), {"B": {"M": ["any"]}})
        e = 'Multiple declarations of actor "B"\'s sendAsyncMessage() message "M"'
        with self.assertRaisesRegex(ActorError,
                                    re.escape(e)):
            ads.addMessage(Loc(), "B", "M", AnyType(), 0)
        ads.addActor("A", ActorDecl(Loc()))
        ads.addMessage(Loc(), "A", "M", AnyType(), 0)
        self.assertEqual(json.loads(ads.toJSON()),
                         {"A": {"M": ["any"]}, "B": {"M": ["any"]}})
        self.assertEqual(ads.toTS(),
                         "type MessageTypes = {\n" +
                         "  A: {\n    M: any;\n  };\n" +
                         "  B: {\n    M: any;\n  };\n" +
                         "};\n")

        # Basic tests for addActors
        ads = ActorDecls()
        ads.addActor("B", ActorDecl(Loc()))
        ads.addMessage(Loc(), "B", "M", AnyType(), 0)
        ads2 = ActorDecls()
        ads.addActor("A", ActorDecl(Loc()))
        ads.addMessage(Loc(), "A", "M", AnyType(), 0)
        ads.addActor("C", ActorDecl(Loc()))
        ads.addMessage(Loc(), "C", "M", AnyType(), 0)
        ads.addActors(ads2)
        self.assertEqual(json.loads(ads.toJSON()),
                         {"A": {"M": ["any"]},
                          "B": {"M": ["any"]},
                          "C": {"M": ["any"]}})

        ads = ActorDecls()
        ads.addActor("A", ActorDecl(Loc()))
        ads2 = ActorDecls()
        ads2.addActor("A", ActorDecl(Loc()))
        with self.assertRaisesRegex(ActorError, 'Multiple declarations of actor "A".'):
            ads.addActors(ads2)


if __name__ == "__main__":
    unittest.main()
