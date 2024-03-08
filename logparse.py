#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Analyze JS actor logging.

import re
import sys
import json
from jsparse import parseJS, ParseError


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

        currMessages = actors.setdefault(actorName, {})
        currContents = currMessages.setdefault(messageName, [])
        currContents.append(contents)

    print(actors)

lookAtActors()
