#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This is a helper file for logparse.py that gives actors and messages we should
# ignore, because their inferred types will be messy and/or wrong. This is in a
# separate file to make it easy to find, and because it will need to import
# various types.

from actor_decls import ActorDecl, ActorDecls, Loc
from ts import (
    AnyType,
    ArrayOrSetType,
    TestOnlyType,
)


def defaultOverride():
    newActors = ActorDecls()
    newActors.addActor("ExtensionContent", ActorDecl(Loc()))
    newActors.addMessage(
        Loc(),
        "ExtensionContent",
        "Execute",
        [None, ArrayOrSetType(True, AnyType())],
        "Return values from extension scripts.",
    )
    testActors = [
        "BrowserTestUtils",
        "Bug1622420",
        "ReftestFission",
        "StartupContentSubframe",
        "TestProcessActor",
        "TestWindow",
        "SpecialPowers",
    ]
    for a in testActors:
        newActors.addActor(a, ActorDecl(Loc(), TestOnlyType()))
    return newActors
