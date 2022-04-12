# Copyright (C) 2022 The Rivet Team. All rights reserved.
# Use of this source code is governed by an MIT license
# that can be found in the LICENSE file.

import sys
from rivetc.compiler import Compiler


def main(args):
    Compiler(args)


if __name__ == "__main__":
    main(sys.argv[1:])
