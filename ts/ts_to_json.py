#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Translate the pseudo-TypeScript for JS actor types to the JSON encoding.

import argparse
import sys
from ts_parse import ActorDeclsParser
from actor_decls import ActorDecls, ActorError


def parseFiles(filenames):
    parser = ActorDeclsParser()
    actorDecls = ActorDecls()

    for filename in filenames:
        with open(filename, 'r', encoding='utf8') as f:
            try:
                newDecls = parser.parse(f.read(), filename)
                actorDecls.addActors(newDecls)
            except ActorError as e:
                print(e, file=sys.stderr)
                return None

    return actorDecls

def parseArgs():
    parser = argparse.ArgumentParser(description=
      "Translate multiple files containing TypeScript-style JS actor " +
      "message types into a single JSON encoded file for use by Firefox")
    parser.add_argument("files", type=str, metavar="IN_FILE", nargs="+",
                        help="TypeScript-style source file.")
    parser.add_argument("--output", "-o", type=str, metavar="OUT_FILE",
                        required=True,
                        help="File location for the JSON output.")
    return parser.parse_args()

def main():
    args = parseArgs()
    decls = parseFiles(args.files)
    if decls is None:
        return

    with open(args.output, 'w', encoding='utf8') as f:
        decls.writeJSONToFile(f)


if __name__ == "__main__":
    main()
