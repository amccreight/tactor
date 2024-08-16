#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parser for a subset of TypeScript.


from actor_decls import ActorDecl, ActorDecls, ActorError, Loc
from ply import lex, yacc
from ts import (
    AnyType,
    ArrayOrSetType,
    JSPropertyType,
    MapType,
    NeverType,
    ObjectType,
    PrimitiveType,
    TestOnlyType,
    UnionType,
    identifierRe,
    messageNameRe,
    primitiveTypes,
)


def _safeLinenoValue(t):
    lineno, value = 0, "???"
    if hasattr(t, "lineno"):
        lineno = t.lineno
    if hasattr(t, "value"):
        value = t.value
    return lineno, value


class Tokenizer(object):
    reserved = set(("any", "never", "testOnly", "Array", "Set", "Map")) | set(
        primitiveTypes
    )

    tokens = [
        "ID",
        "INTEGER",
        "STRING_SINGLE",
        "STRING_DOUBLE",
        "ARROW",
    ]
    tokens.extend([r.upper() for r in reserved])

    # The (?!\d) means that the first character can't be a number.
    def t_ID(self, t):
        r"(?!\d)[\w$]+"
        if t.value in self.reserved:
            t.type = t.value.upper()
        return t

    def t_INTEGER(self, t):
        r"-?\d+"
        i = int(t.value)
        if i < -2147483648:
            raise ActorError(t.lexpos, f"Integer {i} is too small")
        if i > 2147483647:
            raise ActorError(t.lexpos, f"Integer {i} is too large")
        t.value = i
        return t

    # XXX These probably need to escape everything, but I need to keep
    # this in sync with JSActorMessageType::ObjectType::ToString().
    # If I do that, it'll look more like
    # import codecs
    # t.value = codecs.decode(t.value[1:-1], "unicode-escape")

    def t_STRING_SINGLE(self, t):
        r"'(?:[^'\\\n]|\\.)*'"
        t.value = t.value[1:-1].replace("\\'", "'")
        return t

    def t_STRING_DOUBLE(self, t):
        r'"(?:[^"\\\n]|\\.)*"'
        t.value = t.value[1:-1].replace('\\"', '"')
        return t

    def t_ARROW(self, t):
        r"=>"
        return t

    def t_linecomment(self, t):
        r"//[^\n]*"

    def t_multilinecomment(self, t):
        r"/\*(\n|.)*?\*/"
        t.lexer.lineno += t.value.count("\n")

    def t_newline(self, t):
        r"\n+"
        t.lexer.lineno += len(t.value)

    literals = "(){},?:;<>|" + "="

    precedence = [["left", "|"]]

    t_ignore = " \t\r"

    def t_error(self, t):
        raise ActorError(t.lexpos, f"Bad character {t.value[0]}")

    def __init__(self, debug=False, lexer=None):
        if lexer:
            self.lexer = lexer
        else:
            self.lexer = lex.lex(object=self, debug=debug)
            self.debug = debug


class Parser(Tokenizer):
    def __init__(self, start, debug=False, lexer=None):
        Tokenizer.__init__(self, debug=debug, lexer=lexer)
        self.parser = yacc.yacc(
            module=self, start=start, debug=debug, write_tables=False
        )

    # Type declarations.

    def p_JSType(self, p):
        """JSType : PrimitiveType
        | AnyType
        | NeverType
        | TestOnlyType
        | ObjectType
        | ArrayOrSetType
        | MapType
        | '|' JSType
        | JSType '|' JSType
        | '(' JSType ')'"""
        if len(p) == 2:
            p[0] = p[1]
        elif len(p) == 3:
            p[0] = p[2]
        else:
            assert len(p) == 4
            if p[1] == "(":
                p[0] = p[2]
            else:
                tt = p[1].types if isinstance(p[1], UnionType) else [p[1]]
                tt.append(p[3])
                p[0] = UnionType(tt)

    def p_PrimitiveType(self, p):
        """PrimitiveType : UNDEFINED
        | STRING
        | NULL
        | BOOLEAN
        | NUMBER
        | STRUCTUREDCLONE
        | NSIPRINCIPAL
        | BROWSINGCONTEXT
        | DOMRECT"""
        p[0] = PrimitiveType(p[1])

    def p_AnyType(self, p):
        """AnyType : ANY"""
        p[0] = AnyType()

    def p_NeverType(self, p):
        """NeverType : NEVER"""
        p[0] = NeverType()

    def p_TestOnlyType(self, p):
        """TestOnlyType : TESTONLY"""
        p[0] = TestOnlyType()

    def p_ObjectType(self, p):
        """ObjectType : '{' ObjectTypeInner '}'
        | '{' ObjectTypeInner PropertySeparator '}'
        | '{' '}'"""
        if len(p) == 4:
            p[0] = ObjectType(p[2])
        elif len(p) == 5:
            p[0] = ObjectType(p[2])
        else:
            p[0] = ObjectType([])

    def p_PropertySeparator(self, p):
        """PropertySeparator : ','
        | ';'"""
        p[0] = p[1]

    def p_PropertyName(self, p):
        """PropertyName : ID
        | ReservedPropertyName
        | INTEGER
        | STRING_SINGLE
        | STRING_DOUBLE"""
        p[0] = p[1]

    # Our "reserved" words aren't reserved, so they can be used
    # as names. This is a big hack to try to revert that.
    def p_ReservedPropertyName(self, p):
        """ReservedPropertyName : UNDEFINED
        | STRING
        | NULL
        | BOOLEAN
        | NUMBER
        | STRUCTUREDCLONE
        | NSIPRINCIPAL
        | BROWSINGCONTEXT
        | DOMRECT
        | ANY
        | NEVER
        | TESTONLY
        | ARRAY
        | SET"""
        p[0] = p[1]

    def p_ObjectTypeInner(self, p):
        """ObjectTypeInner : ObjectTypeInner PropertySeparator PropertyName MaybeOptional JSType
        | PropertyName MaybeOptional JSType"""
        if len(p) == 6:
            tt = p[1]
            tt.append(JSPropertyType(p[3], p[5], p[4]))
            p[0] = tt
        else:
            assert len(p) == 4
            p[0] = [JSPropertyType(p[1], p[3], p[2])]

    def p_MaybeOptional(self, p):
        """MaybeOptional : '?' ':'
        | ':'"""
        if len(p) == 3:
            p[0] = True
        else:
            assert len(p) == 2
            p[0] = False

    def p_ArrayOrSetType(self, p):
        """ArrayOrSetType : ARRAY '<' JSType '>'
        | SET '<' JSType '>'"""
        assert p[1] == "Array" or p[1] == "Set"
        p[0] = ArrayOrSetType(p[1] == "Array", p[3])

    def p_MapType(self, p):
        """MapType : MAP '<' JSType ',' JSType '>'"""
        p[0] = MapType(p[3], p[5])

    # Top level actor message declarations.

    def p_TopLevelDecls(self, p):
        """TopLevelDecls : TopLevelActor
        | TopLevelActor ';'"""
        p[0] = p[1]

    def p_TopLevelActor(self, p):
        """TopLevelActor : ID ID '=' '{' ActorDecls '}' ';'"""
        if p[1] != "type":
            raise ActorError(
                self.locFromTok(p, 1),
                f'Expected actor declarations to start with "type", not "{p[1]}"',
            )
        if p[2] != "MessageTypes":
            raise ActorError(
                self.locFromTok(p, 2),
                f'Expected top level type name to be "MessageTypes", not "{p[2]}"',
            )
        p[0] = p[5]

    def p_ActorDecls(self, p):
        """ActorDecls : ActorDeclsInner
        | ActorDeclsInner PropertySeparator"""
        p[0] = p[1]

    def p_ActorDeclsInner(self, p):
        """ActorDeclsInner : ActorDeclsInner PropertySeparator ActorDecl
        | ActorDecl"""
        if len(p) == 4:
            actors = p[1]
            actors.addActorL(p[3])
            p[0] = actors
        else:
            assert len(p) == 2
            actors = ActorDecls()
            actors.addActorL(p[1])
            p[0] = actors

    def p_ActorDecl(self, p):
        """ActorDecl : ActorMessagesDecl
        | ActorSingleDecl"""
        p[0] = p[1]

    def p_ActorMessagesDecl(self, p):
        """ActorMessagesDecl : ActorOrMessageName ':' '{' MessageDecls '}'"""
        actorDecl = p[4]
        [loc, actorName] = p[1]

        # This is not a hard requirement, but it makes things easier if we
        # don't have to worry about escaping special characters in error
        # messages. This is actually a looser requirement than existing
        # practice, as all actor names (as of June 2024) consist entirely of
        # characters in [a-zA-Z0-9]. Check this before any other error messages
        # that use the actor name so we don't have to wrap the name in quotes
        # in those later error messages.
        if not identifierRe.fullmatch(actorName):
            raise ActorError(
                loc,
                f'Actor name "{actorName}" should be a valid identifier',
            )

        if isinstance(actorDecl, ActorDecl):
            actorDecl.loc = loc
            p[0] = [actorName, actorDecl]
        else:
            [loc, messageName, loc0] = actorDecl
            raise ActorError(
                loc,
                f"Multiple declarations of message {messageName} "
                + f"for actor {actorName}. Previous was at {loc0}",
            )

    def p_ActorSingleDecl(self, p):
        """ActorSingleDecl : ActorOrMessageName ':' ANY
        | ActorOrMessageName ':' TESTONLY"""
        type = AnyType() if p[3] == "any" else TestOnlyType()
        [loc, actorName] = p[1]
        actorDecl = ActorDecl(loc, type)
        p[0] = [actorName, actorDecl]

    def p_ActorOrMessageName(self, p):
        """ActorOrMessageName : ID
        | STRING_SINGLE
        | STRING_DOUBLE"""
        p[0] = [self.locFromTok(p, 1), p[1]]

    def p_MessageDecls(self, p):
        """MessageDecls : MessageDeclsInner
        | MessageDeclsInner PropertySeparator"""
        p[0] = p[1]

    def p_MessageDeclsInner(self, p):
        """MessageDeclsInner : MessageDeclsInner PropertySeparator MessageDecl
        | MessageDecl"""
        if len(p) == 4:
            if isinstance(p[1], list):
                # Parsing the MessageDeclsInner failed, so propagate the error.
                p[0] = p[1]
                return
            actorDecl = p[1]
            newDecl = p[3]
        else:
            assert len(p) == 2
            actorDecl = ActorDecl(Loc())
            newDecl = p[1]
        if actorDecl.addMessageL(newDecl):
            p[0] = actorDecl
        else:
            # Duplicate actor type declaration. Pass the data needed for an error
            # message back up to the point where we know what the actor is.
            [loc, messageName, _] = newDecl
            loc0 = actorDecl.existingMessageLoc(messageName)
            p[0] = [loc, messageName, loc0]

    def p_MessageDecl(self, p):
        """MessageDecl : ActorOrMessageName ':' MessageType"""
        [loc, messageName] = p[1]
        # This is not a hard requirement, but it makes things easier if we
        # don't have to worry about escaping special characters in error
        # messages. This is actually a looser requirement than existing
        # practice, as all message names (as of June 2024) consist entirely
        # of characters in [a-zA-Z0-9-:_]. Check this before any other error
        # messages that use the message name so we don't have to wrap the name
        # in quotes in those later error messages.
        if not messageNameRe.fullmatch(messageName):
            raise ActorError(
                loc,
                (
                    f'Message name "{messageName}" should be a valid identifier'
                    + ' (it can also contain "-" or ":" '
                    + "after the first character)"
                ),
            )
        p[0] = p[1] + [p[3]]

    def p_MessageType(self, p):
        """MessageType : JSType
        | '(' ID ':' JSType ')' ARROW JSType
        """
        if len(p) == 2:
            # sendAsyncMessage
            p[0] = [p[1]]
        else:
            assert len(p) == 8
            t1 = p[4]
            t2 = p[7]
            isNever1 = NeverType() == t1
            isNever2 = NeverType() == t2
            if isNever1:
                if isNever2:
                    # (_: never) => never;
                    # We could treat this as doing nothing, but that doesn't seem
                    # like it is worth the hassle.
                    raise ActorError(
                        self.locFromTok(p, 1),
                        'Message type must have a non-"never" type '
                        "to either the left or right of the arrow",
                    )
                # (_: never) => T
                # query resolve
                # It is not possible to specify QueryReject.
                p[0] = [None, t2]
                return
            if isNever2:
                # (_: T) => never
                # query
                p[0] = [t1, None]
                return
            # (_: T1) => T2
            # query and query resolve
            p[0] = [t1, t2]

    # Generic definitions.

    def p_error(self, p):
        lineno, value = _safeLinenoValue(p)
        raise ActorError(Loc(self.currFilename, lineno), f'Syntax error near "{value}"')

    def locFromTok(self, p, num):
        return Loc(self.currFilename, p.lineno(num))

    def parse(self, s, filename="???"):
        self.currFilename = filename
        self.lexer.lineno = 1
        return self.parser.parse(s, lexer=self.lexer, debug=self.debug)


class TypeParser(Parser):
    def __init__(self, debug=False):
        # This will generate a lot of warnings about the unused actor decls
        # rules, but that's okay.
        Parser.__init__(self, start="JSType", debug=debug)


class ActorDeclsParser(Parser):
    def __init__(self, debug=False):
        Parser.__init__(self, start="TopLevelDecls", debug=debug)
