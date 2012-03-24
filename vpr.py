#!/usr/bin/env python
from path import path
import numpy as np

from pyvpr import VPRContext, BBCalculator, PlaceResult, vpr_ext


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


def test_grid(placement):
    grid = placement.get_grid()
    placement.set_grid(grid)
    grid2 = placement.get_grid()
    assert((grid == grid2).all())


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
    vpr_context = VPRContext(vpr_args)
    new_placements = []

    placement = vpr_context.get_random_placement()
    calc = BBCalculator.create(placement)
    initial_cost = calc.compute_cost()
    for i in range(args.run_count):
        modifier = get_modifier(placement, seed=i)
        new_placement = modifier.get_placement()
        new_placements.append(new_placement)

    final_costs = []
    for p in new_placements:
        calc = BBCalculator.create(p)
        final_costs.append(calc.compute_cost())

    np_final_costs = np.array(final_costs)
    print 'Initial cost: %s' % initial_cost
    print 'Final costs: %s' % np_final_costs
    print 'Mean cost: %s' % np.mean(np_final_costs)
    print 'Stddev cost: %s' % np.std(np_final_costs)

    # Save final placements to the specified output directory
    if args.output_dir:
        for i, p in enumerate(new_placements):
            output_filename = path('%s-seed%d-run%dof%d-placed.out'\
                    % (args.netlist_file.namebase, args.seed, i + 1,
                            args.run_count))
            output_path = args.output_dir / output_filename
            output_path.write_bytes(str(p))
