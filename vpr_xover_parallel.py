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


def get_modifier(placement, seed=1):
    modifier_xml_string = '''<AnnealingModifier seed="%d">
                <SwapConfig>
                    <AnnealSwapHandler fixed_pins="true" />
                </SwapConfig>
            </AnnealingModifier>''' % seed

    modifier_xml = vpr_ext.load_xml_string(modifier_xml_string)
    modifier_config = vpr_ext.select_single_node(modifier_xml, '//AnnealingModifier').node()
    modifier = vpr_ext.AnnealingModifier(placement, modifier_config)
    return modifier


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
    vpr_args = ['./vpr', args.netlist_file, args.arch_file] + ('placed.out '\
            'routed.out -place_only -fast -nodisp -place_algorithm '\
            'bounding_box -seed %d' % args.seed).split(' ')

    print vpr_args
    
    #Parallelize this loop
    
    def apply_modifier(vpr_args, io_grid, seed=0):
        with Silence():
            vpr_context = VPRContext(vpr_args)

            placement = vpr_context.get_random_placement()
            placement.set_io(io_grid)
            calc = BBCalculator.create(placement)
            initial_cost = calc.compute_cost()
            modifier = get_modifier(placement, seed=seed)
            new_placement = modifier.get_placement()
        return new_placement.get_io_grid(), new_placement.get_grid()

    def apply_combination(vpr_args, io_grid, grid1, grid2, seed=None):
        with Silence():
            vpr_context = VPRContext(vpr_args)
            p1 = vpr_context.get_random_placement()
        p1.set_io(io_grid)
        p1.set_grid(grid1)
        p2 = p1.copy()
        p2.set_grid(grid2)

        c = ConstrainedSwapPlacementCombination(p1, p2)
        best_grid, min_id, costs = c.swaps_min_placement(seed=None)
        return best_grid, min_id, costs

    pool = Pool(processes=args.process_count)
    pool2 = Pool(processes=args.process_count)

    with Silence():
        vpr_context = VPRContext(vpr_args)
    placement = vpr_context.get_random_placement()
    io_grid = placement.get_io_grid() 

    modifier_start = datetime.now()
    modifier_results = [pool.apply_async(apply_modifier, (vpr_args,
            io_grid, i)) for i in range(args.run_count)]

    # Wait for all modifier jobs to complete
    pool.close()
    pool.join()
    modifier_end = datetime.now()
    modifier_seconds = (modifier_end - modifier_start).total_seconds()
    print 'Starting placement generation/improvement completed in %.2f seconds'\
            ' (%.2fs/placement) [%d placements]' % (modifier_seconds,
                    (modifier_seconds / args.run_count), args.run_count)

    combine_results = []

    combine_start = datetime.now()
    # This will a xover for each two-way pairing of resultant placements from
    # the previous stage.  Note that multiple combinations are being done per
    # pair, each starting with a different seed.
    placement_count = len(modifier_results)
    combinations = itertools.combinations(range(placement_count), 2)
    combinations_count =  placement_count * (placement_count - 1) / 2
    for seed in range(4):
        for i, j in combinations:
            grid1 = modifier_results[i].get()[1]
            grid2 = modifier_results[j].get()[1]
            result = pool2.apply_async(apply_combination, (vpr_args, io_grid,
                    grid1, grid2), dict(seed=seed))
            combine_results.append(result)

    # Wait for all combination jobs to complete
    pool2.close()
    pool2.join()
    combine_end = datetime.now()
    combine_seconds = (combine_end - combine_start).total_seconds()
    print 'Placement pair combinations completed in %.2f seconds'\
            ' (%.2fs/combination) [%d combinations]' % (combine_seconds,
                    (combine_seconds / combinations_count), combinations_count)

    results = [dict(zip(['best_grid', 'min_id', 'costs'], r.get())) for r in combine_results]

    if args.output_dir:
        # Dump results to a file
        args.output_dir.joinpath('results.out').pickle_dump(results)

        # Example to show loading results out of the file again
        loaded_results = args.output_dir.joinpath('results.out').pickle_load()

    # Plot an example costs array (from a single combination pair) using
    # matplotlib.
    plt.plot(range(len(results[0]['costs'])), results[0]['costs'])
    plt.savefig('test.pdf')
