#!/usr/bin/env python
import numpy as np

from path import path

from pyvpr import VPRContext, BBCalculator, PlaceResult
from pyvpr.generators.hmetis import HMetisGenerator
from pyvpr.geometry import Point
#from pyvpr.placement_dialog import PlacementDialog


def get_block_colour(dims, coords):
    x_dim, y_dim = dims
    x, y = coords
    x_ratio = x / x_dim
    y_ratio = y / y_dim

    red = 0.5 * x_ratio + 0.5 * y_ratio
    green = y_ratio
    blue = x_ratio
    return (red, green, blue)


def get_modifier(placement):
    modifier_xml_string = '''<AnnealingModifier>
                <SwapConfig>
                    <AnnealSwapHandler fixed_pins="true" />
                </SwapConfig>
            </AnnealingModifier>'''

    modifier_xml = load_xml_string(modifier_xml_string)
    modifier_config = select_single_node(modifier_xml, '//AnnealingModifier').node()
    modifier = AnnealingModifier(placement, modifier_config)
    return modifier


def get_tile_annealer(placement):
    modifier_xml_string = '''
        <TileAnnealerModifier size="8" log_file="tile_annealer_log.csv" >
            <!--
            <ScheduleConfig> <AnnealingSchedule start_iter_count="20" max_rlim="20" /> </ScheduleConfig>
            -->
        </TileAnnealerModifier>'''
    modifier_xml = load_xml_string(modifier_xml_string)
    modifier_config = select_single_node(modifier_xml, '//TileAnnealerModifier').node()
    modifier = TileAnnealerModifier(placement, modifier_config)
    return modifier


def get_cuda_eq_annealer(placement):
    modifier_xml_string = '''
        <CUDAEqAnnealerModifier size="8" skip_rate="0.9" iteration_ratio="0.4" log_file="cuda_annealer_log.csv">
            <ScheduleConfig> <AnnealingSchedule start_iter_count="50" max_rlim="20" /> </ScheduleConfig>
        </CUDAEqAnnealerModifier>
    '''
    modifier_xml = load_xml_string(modifier_xml_string)
    modifier_config = select_single_node(modifier_xml, '//CUDAEqAnnealerModifier').node()
    modifier = TileAnnealerModifier(placement, modifier_config)
    return modifier


def test_grid(placement):
    grid = placement.get_grid()
    placement.set_grid(grid)
    grid2 = placement.get_grid()
    assert((grid == grid2).all())


def test_modifier(placement):
    modifier = get_modifier(placement)
    new_placement = modifier.get_placement()


def test_all(placement):
    test_grid(placement)
    test_modifier(placement)


def get_block_colour_map(placement):
    grid = placement.get_grid()
    dims = placement.dims
    block_colour_map = dict()
    for x in range(dims.x):
        for y in range(dims.y):
            if grid[x, y] >= 0:
                block_colour_map[grid[x, y]] = get_block_colour(dims, Point(x, y))
    block_colour_map[-1] = (1, 0, 0)
    return block_colour_map


def get_colour_map(block_colour_map, placement):
    grid = placement.get_grid()
    dims = placement.dims
    colour_map = dict()
    for x in range(dims.x):
        for y in range(dims.y):
            colour_map[(x, y)] = block_colour_map[grid[x, y]]
    return colour_map


def _parse_args(argv):
    """Parses arguments, returns ``(options, args)``."""
    from argparse import ArgumentParser

    parser = ArgumentParser(description="""\
Run VPR equivalent through Python bindings.""",
                            epilog="""\
(C) 2012  Christian Fobel, licensed under the terms of GPL2.""",
                           )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--start_random',
                    action='store_true', dest='start_random',
                    help='Start with random placement (same as VPR).')
    group.add_argument('--start_hmetis',
                    action='store_true', dest='start_hmetis',
                    help='Start with a placement constructed using hHMetis.')
    group.add_argument('--start_hmetis_greedy',
                    action='store_true', dest='start_hmetis_greedy',
                    help='Start with a placement constructed using hHMetis (greedy).')
    parser.add_argument('-o', '--output_dir',
                    dest='output_dir', default=None, type=path,
                    help='Directory to write output placements to '\
                            '(default=%(default)s).')
    parser.add_argument('-c', '--run_count',
                    dest='run_count', default=1, type=int,
                    help='Number of passes to run (default=%(default)s).')
    args = parser.parse_args(argv)

    assert(args.run_count > 0)
    
    return args


if __name__ == '__main__':
    import sys

    if '--' not in sys.argv:
        raise ValueError, 'Must provide -- followed by VPR arguments.'
    delimit_index = sys.argv.index('--')
    py_args = sys.argv[1:delimit_index]
    vpr_args = sys.argv[:1] + sys.argv[delimit_index + 1:]
    args = _parse_args(py_args)

    vpr_context = VPRContext(vpr_args)
    if args.start_random:
        placement = vpr_context.get_random_placement()
    elif args.start_hmetis:
        print 'Using HMetisGenerator'
        hmetis_gen = HMetisGenerator(vpr_context)
        placement = hmetis_gen.get_placement()
    else: # args.start_hmetis_greedy
        print 'Using HMetisGenerator greedy'
        hmetis_gen = HMetisGenerator(vpr_context)
        placement = hmetis_gen.get_greedy_placement()
    results = []
    for i in range(args.run_count):
        seed = np.random.randint(0, 99999999)
        results.append(vpr_context.run(placement,
                modifier_attrs={'seed': str(seed)},
                output_dir=args.output_dir))
    results.sort(key=lambda x: x.bb_cost)

    print ''
    for r in results:
        print r
    print ''

    fields = ['bb_cost', 'runtime']
    result_grid = np.array([[getattr(r, f) for f in fields] for r in results], dtype=np.float)
    formats = dict(bb_cost='%.2f', runtime='%.4g seconds')
    benchmark_name = path(r.config.netlist_file).namebase
    for i, f in enumerate(fields):
        data = result_grid[:, i]
        fmt = formats.get(f, '%s')
        print '{%s} [%s,%s] field=%s mean=%s stddev=%s min=%s max=%s' % (
                benchmark_name,
                r.config.modifier_name,
                [r.config.modifier_attrs for r in results],
                f, fmt % np.mean(data),
                fmt % np.std(data),
                fmt % np.min(data),
                fmt % np.max(data))
