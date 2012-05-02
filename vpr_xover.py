#!/usr/bin/env python
from __future__ import division
from collections import deque, namedtuple
from multiprocessing import Process, cpu_count, Pool
import math
import itertools
from datetime import datetime

from path import path
import numpy as np
import matplotlib
matplotlib.use('PDF')
import matplotlib.pyplot as plt


from pyvpr import VPRContext, BBCalculator, PlaceResult, vpr_ext,\
        ConstrainedSwapPlacementCombination
from silence import Silence


def _parse_args():
    """Parses arguments, returns ``(options, args)``."""
    from argparse import ArgumentParser

    parser = ArgumentParser(description="""\
Run VPR equivalent through Python bindings.""",
                            epilog="""\
(C) 2012  Christian Fobel, licensed under the terms of GPL2.""",
                           )
    parser.add_argument('-o', '--output_dir',
                    dest='output_dir', default=None, type=path,
                    help='Directory to write output placements to '\
                            '(default=%(default)s).')
    parser.add_argument('-c', '--run_count',
                    dest='run_count', default=1, type=int,
                    help='Number of passes to run (default=%(default)s).')
    parser.add_argument('--processes',
                    dest='process_count', default=cpu_count(), type=int,
                    help='Number of processes to dispatch (default=%(default)s).')
    parser.add_argument('-s', '--seed', default=1, type=int,
                    help='Random seed (default=%(default)s).')
    parser.add_argument(nargs=1, dest='netlist_file')
    parser.add_argument(nargs=1, dest='arch_file')
    args = parser.parse_args()

    if args.output_dir:
        args.output_dir = path(args.output_dir)
        args.output_dir.makedirs_p()
    args.netlist_file = path(args.netlist_file[0])
    args.arch_file = path(args.arch_file[0])
    assert(args.run_count > 0)
    
    return args


if __name__ == '__main__':
    import sys

    args = _parse_args()

    vpr_context = VPRContext.annealer_context(args.netlist_file,
            args.arch_file, args.seed)

    # Note that each repeated call to get_random_placement() will return a
    # unique placement.
    placement1 = vpr_context.get_random_placement()
    placement2 = vpr_context.get_random_placement()

    # Since we currently do not process I/O placement in the anneal, for our
    # comparison between placements, we want to start all placements with the
    # same I/O positions.  Therefore, we will use the positions from placement1
    # to apply to placement2.
    placement2.set_io(placement1.get_io_grid())

    c = ConstrainedSwapPlacementCombination(placement1, placement2)

    # Perform all swaps between placement1 and placement2, recording the fitness
    # of each placement along the way.  Note that the 'seed' parameter below may
    # be used to generate different orderings of swaps between placement1 and
    # placement2.
    best_grid, min_id, costs = c.swaps_min_placement(seed=None)
