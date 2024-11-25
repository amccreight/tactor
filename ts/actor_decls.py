#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Representation of actor message types.

import sys
from copy import deepcopy

from ts import (
    AnyType,
    JSType,
    NeverType,
    TestOnlyType,
    identifierRe,
    messageNameRe,
    unionWith,
)


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

    def addMessage(self, loc, actorName, messageName, t, comment=""):
        assert actorName in self.actors
        actor = self.actors[actorName]
        if not actor.addMessage(loc, messageName, t, comment):
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

    # Add all message types in newDecls to self, replacing any
    # existing types. This is useful for hard coding message types
    # where log based inference does not do a good job. All of the
    # types in newDecls should have a comment explaining the
    # reason for the override.
    def override(self, overrides):
        for actorName, newDecl in overrides.actors.items():
            self.actors.setdefault(actorName, ActorDecl(Loc())).override(newDecl)

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
            if messages.comment:
                s.addLine(f"  // {messages.comment}")
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
            if messages.comment:
                s.addLine(f"// {messages.comment}")
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
                # We have a query reject type but not a query resolve type. The
                # C++ type representation relies on the presence of a query
                # resolve type to imply the query reject `any` type, so we
                # can't accurately represent this situation. However, the only
                # place we're likely going to do this is for test actors where
                # we override the type with `testOnly` anyways, so hack this
                # into the empty type if the actor is on the allow list of
                # test actors.
                if a not in set(["TestWindow", "TestProcessActor"]):
                    raise Exception(
                        f"Message {m} of actor {a} has a query reject type "
                        + "but not a query resolve type, which we can't "
                        + "really represent."
                    )
                newTypes[2] = NeverType()
            # Keep only the query and query resolve types.
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
    # The type of an actor can either be a map from message names to a
    # MessageTypes, or a single type, which will apply to all messages
    # and kinds.
    def __init__(self, loc, type=None, comment=""):
        self.loc = loc
        self.comment = comment
        if type is None:
            self.messages = {}
            self.type = None
        else:
            assert isinstance(type, JSType)
            self.messages = None
            self.type = type

    def addMessage(self, loc, messageName, t, comment=""):
        assert self.messages is not None
        if messageName in self.messages:
            return False
        assert messageNameRe.fullmatch(messageName)
        for kindType in t:
            assert kindType is None or isinstance(kindType, JSType)
        self.messages[messageName] = MessageTypes(loc, t, comment)
        return True

    # Helper method that is easier to use while parsing.
    def addMessageL(self, l):
        assert isinstance(l, list)
        assert len(l) == 3
        return self.addMessage(l[0], l[1], l[2])

    def existingMessageLoc(self, messageName):
        assert self.messages is not None
        assert messageName in self.messages
        return self.messages[messageName].loc

    def nameChars(self):
        messageNamesChars = set()
        if self.messages is not None:
            for messageName in self.messages.keys():
                messageNamesChars |= set(messageName)
        return messageNamesChars

    def override(self, newDecl):
        assert not self.comment
        self.comment = newDecl.comment
        if self.messages is not None and newDecl.messages is not None:
            for messageName, newType in newDecl.messages.items():
                if messageName in self.messages:
                    self.messages[messageName].override(newType)
                else:
                    self.messages[messageName] = deepcopy(newType)
            return
        if newDecl.messages is not None:
            self.type = None
            self.messages = deepcopy(newDecl.messages)
        else:
            if not newDecl.comment and newDecl.type != TestOnlyType():
                e = "Non-testOnly single actor override types for need a comment"
                raise Exception(e)
            self.messages = None
            self.type = deepcopy(newDecl.type)

    def serializeJSON(self, s, indent):
        if self.messages is not None:
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
        else:
            s.add(self.type.jsonStr())

    def toJSON(self):
        s = stringSerializer()
        self.serializeJSON(s, "")
        return s.string

    def serializeTS(self, s, indent):
        if self.messages is not None:
            s.addLine("{")
            for messageName in sorted(list(self.messages.keys())):
                self.messages[messageName].serializeTS(
                    s, indent + "  ", quoteNonIdentifier(messageName)
                )
            s.addLine(indent + "};")
        else:
            s.addLine(str(self.type) + ";")

    def toTS(self):
        s = stringSerializer()
        self.serializeTS(s, "")
        return s.string

    def serializeText(self, s, indent):
        if self.messages is not None:
            for messageName in sorted(list(self.messages.keys())):
                self.messages[messageName].serializeTS(
                    s, indent + "  ", messageName, False
                )
        else:
            s.addLine(indent + "  " + str(self.type))


class MessageTypes:
    # The comment, if present, will be added to the TypeScript output, before
    # the message declaration.
    def __init__(self, loc, types, comment=""):
        assert isinstance(types, list)
        assert 0 < len(types) <= 2
        self.loc = loc
        self.types = types
        if len(types) == 1:
            assert types[0] is not None
        elif len(types) == 2:
            assert types[0] is not None or types[1] is not None
        self.comment = comment

    def override(self, newType):
        assert isinstance(newType, MessageTypes)
        if len(self.types) != len(newType.types):
            m = (
                f"type {self.toJSON()} and override {newType.toJSON()} "
                + "must have the same length"
            )
            raise Exception(m)
        if not newType.comment:
            m = f"override type {newType.toJSON()} must have a comment"
            raise Exception(m)
        assert not self.comment
        self.comment = newType.comment
        # Probably not necessary to copy, but I expect the new type will
        # be small, and this will avoid weird things happening if we end
        # up somehow mutating this type later.
        if len(self.types) == 1:
            if newType.types[0] is None:
                raise Exception("Expected a type for sendAsyncMessage")
            self.types[0] = deepcopy(newType.types[0])
        else:
            if newType.types[0] is None and newType.types[1] is None:
                raise Exception("Expected a type in query override")
            if newType.types[0] is not None:
                self.types[0] = deepcopy(newType.types[0])
            if newType.types[1] is not None:
                self.types[1] = deepcopy(newType.types[1])

    def serializeJSON(self, s):
        tt = [t.jsonStr() if t is not None else '"never"' for t in self.types]
        s.add(f'[{", ".join(tt)}]')

    def toJSON(self):
        s = stringSerializer()
        self.serializeJSON(s)
        return s.string

    # The realTS is false case is an attempt to make a nicer
    # looking output that isn't TypeScript.
    def serializeTS(self, s, indent, messageName, realTS=True):
        if self.comment:
            s.addLine(f"{indent}// {self.comment}")
        if realTS:
            s.add(f"{indent}{messageName}: ")
        else:
            s.add(f"{indent}{messageName} : ")

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
        self.serializeTS(s, "", messageName)
        return s.string
