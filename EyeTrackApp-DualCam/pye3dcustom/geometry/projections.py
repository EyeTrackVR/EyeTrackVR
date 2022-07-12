"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2019 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""
import logging
import warnings

import numpy as np

from .intersections import intersect_sphere_multiple_lines
from .primitives import Circle, Conic, Conicoid, Ellipse, Line
from .utilities import normalize
from ..cpp.projections import unproject_ellipse

logger = logging.getLogger(__name__)


def unproject_edges_to_sphere(
    edges, focal_length, sphere_center, sphere_radius, width=640, height=480
):
    n_edges = edges.shape[0]

    directions = edges - np.asarray([width / 2.0, height / 2.0])
    directions = np.hstack((directions, focal_length * np.ones((n_edges, 1))))
    directions = directions / np.linalg.norm(directions, axis=1, keepdims=1)

    origins = np.zeros((n_edges, 3))

    edges_on_sphere, idxs = intersect_sphere_multiple_lines(
        sphere_center, sphere_radius, origins, directions
    )

    return edges_on_sphere, idxs


def project_point_into_image_plane(point, focal_length):
    scale = focal_length / point[2]
    point_projected = scale * np.asarray(point)
    return point_projected[:2]


def project_line_into_image_plane(line, focal_length):
    p1 = line.origin
    p2 = line.origin + line.direction

    p1_projected = project_point_into_image_plane(p1, focal_length)
    p2_projected = project_point_into_image_plane(p2, focal_length)

    return Line(p1_projected, p2_projected - p1_projected)


def project_circle_into_image_plane(
    circle, focal_length, transform=True, width=0, height=0
):
    c = circle.center
    n = circle.normal
    r = circle.radius
    f = focal_length

    cn = np.dot(c, n)
    c2r2 = np.dot(c, c) - r ** 2
    ABC = cn ** 2 - 2.0 * cn * (c * n) + c2r2 * (n ** 2)
    F = 2.0 * (c2r2 * n[1] * n[2] - cn * (n[1] * c[2] + n[2] * c[1]))
    G = 2.0 * (c2r2 * n[2] * n[0] - cn * (n[2] * c[0] + n[0] * c[2]))
    H = 2.0 * (c2r2 * n[0] * n[1] - cn * (n[0] * c[1] + n[1] * c[0]))
    conic = Conic(ABC[0], H, ABC[1], G * f, F * f, ABC[2] * f ** 2)

    disc_ = conic.discriminant()

    if disc_ < 0:

        A, B, C, D, E, F = conic.A, conic.B, conic.C, conic.D, conic.E, conic.F
        center_x = (2 * C * D - B * E) / disc_
        center_y = (2 * A * E - B * D) / disc_
        temp_ = 2 * (A * E ** 2 + C * D ** 2 - B * D * E + disc_ * F)
        minor_axis = (
            -np.sqrt(np.abs(temp_ * (A + C - np.sqrt((A - C) ** 2 + B ** 2)))) / disc_
        )  # Todo: Absolute value???
        major_axis = (
            -np.sqrt(np.abs(temp_ * (A + C + np.sqrt((A - C) ** 2 + B ** 2)))) / disc_
        )

        if B == 0 and A < C:
            angle = 0
        elif B == 0 and A >= C:
            angle = np.pi / 2.0
        else:
            angle = np.arctan((C - A - np.sqrt((A - C) ** 2 + B ** 2)) / B)

        # TO BE CONSISTENT WITH PUPIL
        if transform:
            center_x = center_x + width / 2.0
            center_y = center_y + height / 2.0
            minor_axis, major_axis = 2.0 * minor_axis, 2.0 * major_axis
            angle = angle * 180.0 / np.pi + 90.0

        return Ellipse(np.asarray([center_x, center_y]), minor_axis, major_axis, angle)

    else:

        return False


def project_sphere_into_image_plane(
    sphere, focal_length, transform=True, width=0, height=0
):
    scale = focal_length / sphere.center[2]

    projected_sphere_center = scale * sphere.center
    projected_radius = scale * sphere.radius

    if transform:
        projected_sphere_center[0] += width / 2.0
        projected_sphere_center[1] += height / 2
        projected_radius *= 2.0

    return Ellipse(projected_sphere_center[:2], projected_radius, projected_radius, 0.0)
