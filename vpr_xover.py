#!/usr/bin/env python
from collections import deque, namedtuple
from multiprocessing import Process, cpu_count, Pool
import math
import itertools

from path import path
import numpy as np

from pyvpr import VPRContext, BBCalculator, PlaceResult, vpr_ext,\
        ConstrainedSwapPlacementCombination


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
    
    #Paralleize this loop
    
    def apply_modifier(vpr_args, io_grid, seed=0):
        vpr_context = VPRContext(vpr_args)

        placement = vpr_context.get_random_placement()
        placement.set_io(io_grid)
        calc = BBCalculator.create(placement)
        initial_cost = calc.compute_cost()
        modifier = get_modifier(placement, seed=seed)
        new_placement = modifier.get_placement()
        return new_placement.get_io_grid(), new_placement.get_grid()

    def apply_combination(vpr_args, io_grid, grid1, grid2, seed=None):
        vpr_context = VPRContext(vpr_args)
        p1 = vpr_context.get_random_placement()
        p1.set_io(io_grid)
        p1.set_grid(grid1)
        p2 = p1.copy()
        p2.set_grid(grid2)

        c = ConstrainedSwapPlacementCombination(p1, p2)
        best_grid, min_id, costs = c.swaps_min_placement(seed=None)
        return best_grid, min_id, costs

    pool = Pool(processes=cpu_count())
    pool2 = Pool(processes=cpu_count())

    vpr_context = VPRContext(vpr_args)
    placement = vpr_context.get_random_placement()
    io_grid = placement.get_io_grid() 

    modifier_results = [pool.apply_async(apply_modifier, (vpr_args,
            io_grid, i)) for i in range(args.run_count)]

    pool.close()
    pool.join()

    combine_results = []

    for seed in range(4):
        for i, j in itertools.combinations(range(len(modifier_results)), 2):
            grid1 = modifier_results[i].get()[1]
            grid2 = modifier_results[j].get()[1]
            result = pool2.apply_async(apply_combination, (vpr_args, io_grid,
                    grid1, grid2), dict(seed=seed))
            combine_results.append(result)

    pool2.close()
    pool2.join()

    results = [dict(zip(['best_grid', 'min_id', 'costs'], r.get())) for r in combine_results]

    path('results.out').pickle_dump(results)
    loaded_results = path('results.out').pickle_load()
