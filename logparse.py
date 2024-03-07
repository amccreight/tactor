#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Analyze JS actor logging.

import re
import sys
import json

messagePatt = re.compile('QQQ ACTOR ([^ ]+) MESSAGE ([^ ]+) CONTENTS (.+)$')

def lookAtActors():
    sys.stdin.reconfigure(encoding='latin1')

    for l in sys.stdin:
        mp = messagePatt.match(l)
        if not mp:
            continue
        actorName = mp.group(1)
        messageName = mp.group(2)
        contentsRaw = mp.group(3)
        contents = "???"
        if contentsRaw == "(void 0)":
            contents = "VOID!!!"
        elif contentsRaw == "null":
            contents = "NULL!!!"
        elif contentsRaw[0] == "(" and contentsRaw[-1] == ")":
            # XXX This isn't JSON because the property names aren't strings.
            contents = contentsRaw[1:-1]

        print(f'Actor: {actorName}; Message: {messageName}; Contents: {contents}')

lookAtActors()
