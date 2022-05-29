"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2019 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""
import abc

import numpy as np

from .utilities import cart2sph, normalize


class Primitive(abc.ABC):
    __slots__ = ()

    def __repr__(self):
        klass = "{}.{}".format(self.__class__.__module__, self.__class__.__name__)
        attributes = " ".join(
            "{}={}".format(k, v.__repr__()) for k, v in self.__dict__.items()
        )
        return "<{klass} at {id}: {attributes}>".format(
            klass=klass, id=id(self), attributes=attributes
        )

    def __str__(self):
        def to_str(obj, float_fmt="{:f}") -> str:
            if isinstance(obj, float) or isinstance(obj, int):
                return float_fmt.format(obj)
            if isinstance(obj, np.ndarray):
                if obj.dtype != np.object:
                    return ", ".join(float_fmt.format(x) for x in obj)
            return str(obj)

        klass = self.__class__.__name__
        attributes = " - ".join(
            "{}: {}".format(k, to_str(v)) for k, v in self.__dict__.items()
        )
        return "{klass} -> {attributes}".format(klass=klass, attributes=attributes)


class Line(Primitive):
    __slots__ = ("origin", "direction", "dim")

    def __init__(self, origin, direction):
        self.origin = np.asarray(origin)
        self.direction = normalize(np.asarray(direction))
        self.dim = self.origin.shape[0]


class Circle(Primitive):
    __slots__ = ("center", "normal", "radius")

    def __init__(self, center=[0.0, 0.0, 0.0], normal=[0.0, 0.0, -1.0], radius=0.0):
        self.center = np.asarray(center, dtype=float)
        self.normal = np.asarray(normal, dtype=float)
        self.radius = radius

    def spherical_representation(self):
        phi, theta = cart2sph(self.normal)
        return phi, theta, self.radius

    def is_null(self):
        return self.radius <= 0.0

    @staticmethod
    def null() -> "Circle":
        return Circle(radius=0.0)


class Ellipse(Primitive):
    __slots__ = ("center", "major_radius", "minor_radius", "angle")

    def __init__(self, center, minor_radius, major_radius, angle):
        self.center = center
        self.major_radius = major_radius
        self.minor_radius = minor_radius
        self.angle = angle

        if self.minor_radius > self.major_radius:
            current_minor_radius = self.minor_radius
            self.minor_radius = self.major_radius
            self.major_radius = current_minor_radius
            self.angle = self.angle + np.pi / 2

    def circumference(self):
        a = self.minor_radius
        b = self.major_radius
        return np.pi * (3.0 * (a + b) - np.sqrt((3.0 * a + b) * (a + 3.0 * b)))

    def area(self):
        return np.pi * self.minor_radius * self.major_radius

    def circularity(self):
        return self.minor_radius / self.major_radius

    def parameters(self):
        return (
            self.center[0],
            self.center[1],
            self.minor_radius,
            self.major_radius,
            self.angle,
        )


class Sphere(Primitive):
    __slots__ = ("center", "radius")

    def __init__(self, center, radius):
        self.center = center
        self.radius = radius

    def __bool__(self):
        return self.radius > 0


class Conicoid(Primitive):
    """
    Coefficients of the general equation (implicit form) of a cone, given its vertex and base (ellipse/conic).
    Formulae follow equations (1)-(3) of:
    Safaee-Rad, R. et al.: "Three-Dimensional Location Estimation of Circular Features for Machine Vision",
    IEEE Transactions on Robotics and Automation, Vol.8(5), 1992, pp624-640.
    """

    __slots__ = tuple("ABCFGHUVWD")

    def __init__(self, conic, vertex):
        alpha = vertex[0]
        beta = vertex[1]
        gamma = vertex[2]
        self.A = (gamma ** 2) * conic.A
        self.B = (gamma ** 2) * conic.C
        self.C = (
            conic.A * (alpha ** 2)
            + conic.B * alpha * beta
            + conic.C * (beta ** 2)
            + conic.D * alpha
            + conic.E * beta
            + conic.F
        )
        self.F = -gamma * (conic.C * beta + conic.B / 2 * alpha + conic.E / 2)
        self.G = -gamma * (conic.B / 2 * beta + conic.A * alpha + conic.D / 2)
        self.H = (gamma ** 2) * conic.B / 2
        self.U = (gamma ** 2) * conic.D / 2
        self.V = (gamma ** 2) * conic.E / 2
        self.W = -gamma * (conic.E / 2 * beta + conic.D / 2 * alpha + conic.F)
        self.D = (gamma ** 2) * conic.F


class Conic(Primitive):
    """
    Coefficients A-F of the general equation (implicit form) of a conic
    Ax² + Bxy + Cy² + Dx + Ey + F = 0
    calculated from 5 ellipse parameters, see https://en.wikipedia.org/wiki/Ellipse#General_ellipse
    """

    __slots__ = tuple("ABCDEF")

    def __init__(self, *args):
        if len(args) == 1:
            ellipse = args[0]
            ax = np.cos(ellipse.angle)
            ay = np.sin(ellipse.angle)
            a2 = ellipse.major_radius ** 2
            b2 = ellipse.minor_radius ** 2

            self.A = a2 * ay * ay + b2 * ax * ax
            self.B = 2.0 * (b2 - a2) * ax * ay
            self.C = a2 * ax * ax + b2 * ay * ay
            self.D = -2.0 * self.A * ellipse.center[0] - self.B * ellipse.center[1]
            self.E = -self.B * ellipse.center[0] - 2.0 * self.C * ellipse.center[1]
            self.F = (
                self.A * ellipse.center[0] * ellipse.center[0]
                + self.B * ellipse.center[0] * ellipse.center[1]
                + self.C * ellipse.center[1] * ellipse.center[1]
                - a2 * b2
            )

        if len(args) == 6:
            self.A, self.B, self.C, self.D, self.E, self.F = args

    def discriminant(self):
        return self.B ** 2 - 4 * self.A * self.C
