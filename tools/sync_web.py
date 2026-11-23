#!/usr/bin/env python3
"""Copy the shared optimizer.js into web/. The calculator repo is its one source.

    python tools/sync_web.py                 # copy from ../cutcalculator
    python tools/sync_web.py --from PATH     # copy from another checkout
    python tools/sync_web.py --check         # exit 1 if web/ differs from the checkout
"""
import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ['optimizer.js']
DEST = os.path.join(ROOT, 'web')
SOURCE = os.path.join(os.path.dirname(ROOT), 'cutcalculator')


def stale(source=SOURCE):
    return [f for f in FILES if not os.path.exists(os.path.join(DEST, f))
            or not filecmp.cmp(os.path.join(source, f), os.path.join(DEST, f), shallow=False)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='source', default=SOURCE)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if not all(os.path.isfile(os.path.join(args.source, f)) for f in FILES):
        sys.exit(f'{args.source} is not a cutcalculator checkout')
    if args.check:
        bad = stale(args.source)
        if bad:
            sys.exit('web/ is out of date: ' + ', '.join(bad) + '. Run python tools/sync_web.py')
        print('web/ matches ' + args.source)
        return
    os.makedirs(DEST, exist_ok=True)
    for f in FILES:
        shutil.copyfile(os.path.join(args.source, f), os.path.join(DEST, f))
    print('copied ' + ', '.join(FILES) + ' from ' + args.source)


if __name__ == '__main__':
    main()
