#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Translate the pseudo-TypeScript for JS actor types to the JSON encoding.

import argparse

from actor_decls import ActorDecls
from ts_parse import ActorDeclsParser


def parseFiles(filenames):
    parser = ActorDeclsParser()
    actorDecls = ActorDecls()

    for filename in filenames:
        with open(filename, "r", encoding="utf8") as f:
            newDecls = parser.parse(f.read(), filename)
            actorDecls.addActors(newDecls)

    return actorDecls


def translateFiles(files, output):
    decls = parseFiles(files)
    if decls is None:
        return

    decls.writeJSONToFile(output)


# XXX For use by our current moz.build shim.
def translateFile(output, file):
    translateFiles([file], output)


def parseArgs():
    parser = argparse.ArgumentParser(
        description="Translate multiple files containing TypeScript-style JS actor "
        + "message types into a single JSON encoded file for use by Firefox"
    )
    parser.add_argument(
        "files",
        type=str,
        metavar="IN_FILE",
        nargs="+",
        help="TypeScript-style source file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        metavar="OUT_FILE",
        required=True,
        help="File location for the JSON output.",
    )
    return parser.parse_args()


def main():
    args = parseArgs()
    with open(args.output, "w", encoding="utf8") as f:
        translateFiles(args.files, f)


if __name__ == "__main__":
    main()
