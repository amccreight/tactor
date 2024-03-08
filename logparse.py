#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Analyze JS actor logging.

import re
import sys
import json
from jsparse import parseJS, ParseError
from type import jsValToType

messagePatt = re.compile('QQQ ACTOR ([^ ]+) MESSAGE ([^ ]+) CONTENTS (.+)$')

def lookAtActors():
    sys.stdin.reconfigure(encoding='latin1')

    actors = {}

    for l in sys.stdin:
        mp = messagePatt.match(l)
        if not mp:
            continue
        actorName = mp.group(1)
        messageName = mp.group(2)
        contentsRaw = mp.group(3)
        contents = "???"
        try:
            contents = parseJS(contentsRaw)
        except ParseError as p:
            print(p, file=sys.stderr)
            print(f'  {contentsRaw}', file=sys.stderr)
            break

        # TODO Catch the exception.
        t = jsValToType(contents)

        currMessages = actors.setdefault(actorName, {})
        if messageName in currMessages:
            currType = currMessages[messageName]
            if t != currType:
                print(f"Type changed from {currType} to {t}")
        else:
            currMessages[messageName] = t

    for a, mm in actors.items():
        print(a)
        for m, t in mm.items():
            print(f"  {m}: {t}")

lookAtActors()
