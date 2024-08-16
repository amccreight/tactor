#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This is a helper file for logparse.py that gives actors and messages we should
# ignore, because their inferred types will be messy and/or wrong. This is in a
# separate file to make it easy to find, and because it will need to import
# various types.

from actor_decls import ActorDecl, ActorDecls, Loc


def defaultOverride(typeParser):
    newActors = ActorDecls()

    def addActor(a):
        newActors.addActor(a, ActorDecl(Loc()))

    def addMsg(a, m, typeStrings, comment):
        types = []
        for typeString in typeStrings:
            if typeString is None:
                types.append(None)
                continue
            types.append(typeParser.parse(typeString))
        newActors.addMessage(Loc(), a, m, types, comment)

    def addMsgAny(a, m, comment):
        newActors.addMessage(Loc(), a, m, ["any"], comment)

    def addMsgAnyComplex(a, m):
        addMsgAny(a, m, "This type is very complex.")

    def addActorWithType(a, typeString, comment):
        type = typeParser.parse(typeString)
        newActors.addActor(a, ActorDecl(Loc(), type, comment))

    def addActorTestOnly(a):
        # No need for a comment for testOnly, as it is self-explanatory.
        addActorWithType(a, "testOnly", "")

    def addActorAny(a, comment):
        addActorWithType(a, "any", comment)

    def addActorAboutAny(a):
        addActorAny(a, "actor with complex types for about: page")

    def addMsgAboutAny(a, m):
        addMsgAny(a, m, "message with complex type for about: page")

    def addQueryAboutAny(a, m):
        newActors.addMessage(
            Loc(), a, m, ["any", None], "message with complex type for about: page"
        )

    devToolsProcessActors = ["BrowserToolboxDevToolsProcess", "DevToolsProcess"]
    for a in devToolsProcessActors:
        addActor(a)
        for msg in [
            "DevToolsProcessChild:packet",
            "DevToolsProcessChild:targetAvailable",
            "DevToolsProcessChild:targetDestroyed",
        ]:
            addMsgAnyComplex(a, msg)

    actor = "Conduits"
    addActor(actor)
    addMsgAny(actor, "APICall", "This type is very complex, and we're not logging it.")
    addMsg(
        actor,
        "RunListener",
        [None, "undefined | structuredClone"],
        "This message is very frequent and boring, so we don't log it.",
    )
    # The Conduits messages CreateProxyContext and PortMessage have multiple kinds,
    # as seen in bug 1903128 and bug 1903134. Unfortunately, there's no way to allow
    # this at the level of individual messages, so for now anything that uses them
    # with the extra kind we're ignoring will fail to typecheck.

    actor = "ExtensionContent"
    addActor(actor)
    addMsg(
        actor, "Execute", [None, "Array<any>"], "Return values from extension scripts."
    )

    addActorAny(
        "AboutPocket",
        "Tests for this actor don't actually go through IPC, so we can't infer types.",
    )

    # Various about: pages use actors with one or more very complex messages.
    addActorAboutAny("ASRouter")

    actor = "AboutNewTab"
    addActor(actor)
    addMsgAboutAny(actor, "ActivityStream:ContentToMain")

    actor = "AboutPrivateBrowsing"
    addActor(actor)
    addQueryAboutAny(actor, "IsPromoBlocked")

    for a in ["AboutWelcome", "AboutWelcomeShopping"]:
        addActor(a)
        addQueryAboutAny(a, "AWPage:ADD_SCREEN_IMPRESSION")
        addQueryAboutAny(a, "AWPage:EVALUATE_SCREEN_TARGETING")

    # Test actors.
    testActors = [
        "AppTestDelegate",
        "BrowserTestUtils",
        "Bug1622420",
        "ReftestFission",
        "StartupContentSubframe",
        "TestProcessActor",
        "TestWindow",
        "SpecialPowers",
    ]
    for a in testActors:
        addActorTestOnly(a)

    return newActors
