#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Translating the pseudo-TypeScript for message actor types to the JSON output.

from ts_parse import parseActorDecls
import sys


# XXX Need to take a list of files on the command line.


def translateToJSON():
    sys.stdin.reconfigure(encoding='latin1')
