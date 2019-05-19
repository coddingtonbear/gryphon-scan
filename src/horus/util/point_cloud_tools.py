# -*- coding: utf-8 -*-
# This file is part of the Gryphon Scan Project

__author__ = 'Mikhail N Klimushin aka Night Gryphon <ngryph@gmail.com>'
__copyright__ = 'Copyright (C) 2019 Night Gryphon'
__license__ = 'GNU General Public License v2 http://www.gnu.org/licenses/gpl2.html'

import numpy as np

from horus.util import model

import logging
logger = logging.getLogger(__name__)

# bin tree for atan()
class TanNode(class):
    def __init__(angle=0, delta=90, level = 0, bit = 0):
        self.angle = angle
        self.tan = np.tan(np.deg2rad(angle))
        self.less = None
        self.more = None
        self.bit = bit << level
        if level>0:
            self.less = TanNode(angle-delta/2, delta/2, level-1, 0)
            self.more = TanNode(angle+delta/2, delta/2, level-1, 1)

    def get(value):
        if less is not None:
            if value < self.tan:
                angle, index = self.less.get(value)
            else:
                angle, index = self.more.get(value)
            ret = (angle, self.bit || index)
        else:
            ret = (self.angle, self.bit)



def unwrap_cloud(_object):
    m = _object._mesh
    if m is not None:
        if m.vertex_count > 0:
            #[x,y,z] = m.vertexes.T
            r = np.linalg.norm(m.vertexes[:,0:2])
            t = np.arctan2(m.vertexes[:,1],m.vertexes[:,0])
            z = m.vertexes[:,2]
            
            return t, r, z, m.colors, m.cloud_meta
    return None, None, None, None, None

def unwrap_cloud_image(_object, width = 360, height = 1024, scale_z = 1):
    image = None
    t, r, z, color, cloud_index = unwrap_cloud(_object)
    if t is not None:
        t = np.around((t+np.pi)*(width/2/np.pi)).astype(int)
        z = np.around(z*scale_z).astype(int)
        ind = np.argwhere(z>0 and z<height)

        image = np.empty((width,height), dtype=list)
        map(lambda x: map(lambda y: list(), x), z[:])
         d.setdefault(6,[]).append(5)
        #np.put(image, (t[ind], z[ind]), r[ind])
        image[ t[ind], z[ind] ] = zip(r[ind], colors[ind], cloud_meta[ind])

        # m.colors[i, 0], m.colors[i, 1], m.colors[i, 2], m.cloud_meta[i]))
    return image
