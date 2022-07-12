"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2019 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""
import numpy as np


def intersect_line_line(p11, p12, p21, p22, internal=False):
    x1, y1 = p11
    x2, y2 = p12
    x3, y3 = p21
    x4, y4 = p22

    if ((x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)) != 0:
        Px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / (
            (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        )
        Py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / (
            (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        )
        if internal:
            if x1 != x2:
                lam = (Px - x2) / (x1 - x2)
            else:
                lam = (Py - y2) / (y1 - y2)
            if 0 <= lam <= 1:
                return [True, Px, Py]
            else:
                return [False]
        else:
            return [True, Px, Py]
    else:
        return [False]


def intersect_sphere_multiple_lines(sphere_center, radius, points, directions):
    # Note: Directions need to be normalized!
    intermediate = np.einsum("ij,ij->i", directions, points - sphere_center)
    discriminant = (
        intermediate ** 2 - np.sum((points - sphere_center) ** 2, axis=1) + radius ** 2
    )
    idx = discriminant > 0
    sqr = np.sqrt(discriminant[idx])
    d1 = -intermediate[idx] + sqr
    d2 = -intermediate[idx] - sqr
    d_final = np.expand_dims(np.minimum(d1, d2), axis=1)
    intersections_on_sphere = points[idx] + d_final * directions[idx]

    return intersections_on_sphere, idx


def intersect_sphere_line(sphere_center, radius, point, direction):
    temp = np.dot(direction, point - sphere_center)
    discriminant = temp ** 2 - np.linalg.norm(point - sphere_center) ** 2 + radius ** 2
    if discriminant >= 0.0:
        sqr = np.sqrt(discriminant)
        d1 = -temp + sqr
        d2 = -temp - sqr
        return [True, d1, d2]
    else:
        return [False, 0.0, 0.0]


def intersect_plane_line(p_plane, n_plane, p_line, l_line, radius=-1):
    if np.dot(n_plane, l_line) == 0 or np.dot(p_plane - p_line, n_plane) == 0:
        return [False]
    else:
        d = np.dot(p_plane - p_line, n_plane) / np.dot(l_line, n_plane)
        p_intersect = p_line + d * l_line
        if radius > 0:
            if np.linalg.norm(p_plane - p_intersect) <= radius[0]:
                return [True, p_intersect[0], p_intersect[1], p_intersect[2]]
            else:
                return [False, 0.0, 0.0, 0.0]
        else:
            return [True, p_intersect[0], p_intersect[1], p_intersect[2]]


def nearest_point_on_sphere_to_line(center, radius, origin, direction):
    intersection = intersect_sphere_line(center, radius, origin, direction)
    if intersection[0]:
        d = np.min(intersection[1:])
        return origin + d * direction
    else:
        temp = np.dot(direction, center - origin)
        origin_prime = origin + temp * direction
        direction_prime = center - origin_prime
        direction_prime /= np.linalg.norm(direction_prime)
        success, d1, d2 = intersect_sphere_line(
            center, radius, origin_prime, direction_prime
        )
        if success:
            d = min(d1, d2)
            return origin_prime + d * direction_prime
        else:
            np.zeros(3)


def nearest_intersection_points(p1, p2, p3, p4):
    """Calculates the two nearest points, and their distance to each other on
    two lines defined by (p1,p2) respectively (p3,p4)
    """

    def mag(p):
        return np.sqrt(p.dot(p))

    def normalise(p1, p2):
        p = p2 - p1
        m = mag(p)
        if m == 0:
            return [0.0, 0.0, 0.0]
        else:
            return p / m

    d1 = normalise(p1, p2)
    d2 = normalise(p3, p4)

    diff = p1 - p3
    a01 = -d1.dot(d2)
    b0 = diff.dot(d1)

    if np.abs(a01) < 1.0:

        # Lines are not parallel.
        det = 1.0 - a01 * a01
        b1 = -diff.dot(d2)
        s0 = (a01 * b1 - b0) / det
        s1 = (a01 * b0 - b1) / det

    else:

        # Lines are parallel, select any pair of closest points.
        s0 = -b0
        s1 = 0

    closestPoint1 = p1 + s0 * d1
    closestPoint2 = p3 + s1 * d2
    dist = mag(closestPoint2 - closestPoint1)

    return closestPoint1, closestPoint2, dist


def nearest_intersection_lines(lines):
    dim = len(lines[0].origin)

    R = np.zeros((dim, dim))
    q = np.zeros(dim)

    for line in lines:
        v = np.reshape(line.direction, (dim, 1))
        A = np.eye(dim) - v @ v.T
        R += A
        q += A @ line.origin

    return np.linalg.pinv(R) @ q
