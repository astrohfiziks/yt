"""
Import the components of the volume rendering extension

Author: Matthew Turk <matthewturk@gmail.com>
Affiliation: KIPAC/SLAC/Stanford
Homepage: http://yt.enzotools.org/
License:
  Copyright (C) 2009 Matthew Turk.  All Rights Reserved.

  This file is part of yt.

  yt is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import numpy as na
from yt.funcs import *
import h5py

from VolumeIntegrator import PartitionedGrid

def partition_grid(start_grid, field, log_field = True, threshold = None):
    if threshold is not None:
        if start_grid[field].max() < threshold[0] or \
           start_grid[field].min() > threshold[1]: return None
    to_cut_up = start_grid.get_vertex_centered_data(field, smoothed=True).astype('float64')

    if log_field: to_cut_up = na.log10(to_cut_up)
    assert(na.any(na.isnan(to_cut_up)) == False)

    if len(start_grid.Children) == 0:
        pg = PartitionedGrid(
                to_cut_up.copy(),
                na.array(start_grid.LeftEdge, dtype='float64'),
                na.array(start_grid.RightEdge, dtype='float64'),
                na.array(start_grid.ActiveDimensions, dtype='int64'))
        return [pg]

    x_vert = [0, start_grid.ActiveDimensions[0]]
    y_vert = [0, start_grid.ActiveDimensions[1]]
    z_vert = [0, start_grid.ActiveDimensions[2]]

    for grid in start_grid.Children:
        gi = start_grid.get_global_startindex()
        si = grid.get_global_startindex()/2 - gi
        ei = si + grid.ActiveDimensions/2 
        x_vert += [si[0], ei[0]]
        y_vert += [si[1], ei[1]]
        z_vert += [si[2], ei[2]]

    # Now we sort by our vertices, in axis order

    x_vert.sort()
    y_vert.sort()
    z_vert.sort()

    return [g for g in _partition(start_grid, to_cut_up, x_vert, y_vert, z_vert)]

def _partition(grid, data, x_vert, y_vert, z_vert):
    grids = []
    cim = grid.child_index_mask
    for xs, xe in zip(x_vert[:-1], x_vert[1:]):
        for ys, ye in zip(y_vert[:-1], y_vert[1:]):
            for zs, ze in zip(z_vert[:-1], z_vert[1:]):
                sl = (slice(xs, xe), slice(ys, ye), slice(zs, ze))
                dd = cim[sl]
                if dd.size == 0: continue
                uniq = na.unique(dd)
                if uniq.size > 1: continue
                if uniq[0] > -1: continue
                data = data[xs:xe+1,ys:ye+1,zs:ze+1].copy()
                dims = na.array(dd.shape, dtype='int64')
                start_index = na.array([xs,ys,zs], dtype='int64')
                left_edge = grid.LeftEdge + start_index * grid.dds
                right_edge = left_edge + dims * grid.dds
                yield PartitionedGrid(
                    data, left_edge, right_edge, dims)

def partition_all_grids(grid_list, field = "Density",
                        threshold = (-1e300, 1e300), eval_func = None):
    new_grids = []
    pbar = get_pbar("Partitioning ", len(grid_list))
    if eval_func is None: eval_func = lambda a: True
    for i, g in enumerate(grid_list):
        if not eval_func(g): continue
        pbar.update(i)
        to_add = partition_grid(g, field, True, threshold)
        if to_add is not None: new_grids += to_add
    pbar.finish()
    return na.array(new_grids, dtype='object')

def export_partitioned_grids(grid_list, fn):
    f = h5py.File(fn, "w")
    pbar = get_pbar("Writing Grids", len(grid_list))
    nelem = sum((grid.my_data.size for grid in grid_list))
    ngrids = len(grid_list)
    group = f.create_group("/PGrids")
    left_edge = na.concatenate([[grid.LeftEdge,] for grid in grid_list])
    f.create_dataset("/PGrids/LeftEdges", data=left_edge); del left_edge
    right_edge = na.concatenate([[grid.RightEdge,] for grid in grid_list])
    f.create_dataset("/PGrids/RightEdges", data=right_edge); del right_edge
    dims = na.concatenate([[grid.my_data.shape[:],] for grid in grid_list])
    f.create_dataset("/PGrids/Dims", data=dims); del dims
    data = na.concatenate([grid.my_data.ravel() for grid in grid_list])
    f.create_dataset("/PGrids/Data", data=data); del data
    f.close()
    pbar.finish()

def import_partitioned_grids(fn):
    f = h5py.File(fn, "r")
    n_groups = len(f.listnames())
    grid_list = []
    dims = f["/PGrids/Dims"][:]
    left_edges = f["/PGrids/LeftEdges"][:]
    right_edges = f["/PGrids/RightEdges"][:]
    data = f["/PGrids/Data"][:]
    pbar = get_pbar("Reading Grids", dims.shape[0])
    curpos = 0
    for i in xrange(dims.shape[0]):
        gd = dims[i,:]
        gle, gre = left_edges[i,:], right_edges[i,:]
        gdata = data[curpos:curpos+gd.prod()].reshape(gd)
        # Vertex -> Grid, so we -1 from dims in this
        grid_list.append(PartitionedGrid(gdata, gle, gre, gd - 1))
        curpos += gd.prod()
        pbar.update(i)
    pbar.finish()
    f.close()
    return na.array(grid_list, dtype='object')