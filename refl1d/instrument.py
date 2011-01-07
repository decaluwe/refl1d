# This program is in the public domain
# Author: Paul Kienzle
r"""
Reflectometry instrument definitions.

An instrument definition contains all the information necessary to compute
the resolution for a measurement.  See :mod:`resolution` for details.

Usage
=====

:mod:`refl1d.instrument` (this module) defines two instrument types:
:class:`Monochromatic` and :class:`Pulsed`. These represent
generic scanning and time of flight instruments, respectively.

To perform a simulation or load a data set, a measurement geometry must
be defined.  In the following example, we set up the geometry for the
AND/R instrument, with the wavelength and wavelength dispersion
predetermined by the choice of monochromator settings, and with the
angular divergence defined for the particular measurement using slits
of 0.1 mm below 0.5\ |degrees| and opening slits above 0.5\ |degrees|
starting at 0.2 mm and maintaining a fixed $\Delta \theta / \theta$.  We
use this geometry to compute the measurement resolution $Q, \Delta Q$.

    >>> from numpy import linspace
    >>> from refl1d.instrument import Monochromatic
    >>> from refl1d.resolution import dTdL2dQ
    >>> geometry = Monochromatic(
    ...    instrument="AND/R", radiation="neutron",
    ...    wavelength=5.0042, dLoL=0.009, d_s1=230+1856, d_s2=230,
    ...    Tlo=0.5, slits_at_Tlo=0.2, slits_below=0.1)
    >>> T,dT,L,dL = geometry.resolution(T=linspace(0,5,51))
    >>> Q,dQ = dTdL2dQ(T=T,dT=dT,L=L,dL=dL)

More commonly, though, the instrument would be used to generate a
measurement probe for use in modeling or to read in a previously
measured data set:

    >>> simulation_probe = geometry.probe(T=linspace(0,5,51))
    >>> measured_probe = geometry.load('blg117.refl')

For magnetic systems a polarized beam probe is needed::

    >>> probe = geometry.magnetic_probe(T=numpy.arange(0,5,100))

When loading or simulating a data set, any of the instrument parameters
and measurement geometry information can be specified, replacing the
defaults within the instrument.  For example, to include sample broadening
effects in the resolution::

    >>> probe1 = geometry.load('blg117.refl', sample_broadening=0.1)

Properties of the instrument can be displayed, both for the generic
instrument (which defines slit distances and wavelength in this case)
or for the specific measurement (which adds detail about the slit
opening as a function of angle)::

    >>> from refl1d.ncnrdata import ANDR
    >>> print ANDR.defaults()
    >>>
    >>> print geometry.defaults()

Defining Instruments
====================

Standard instruments can be defined for each facility.  This saves the users
having to remember details of the instrument geometry.

For example, the above one-off example could be formalized using::

    from refl1d.instrument import Monochromatic
    class ANDR(Monochromatic):
        instrument = "AND/R"
        radiation = "neutron"
        wavelength = 5.0042   # Angstroms
        dLoL = 0.009          # FWHM
        d_s1 = 230.0 + 1856.0 # mm
        d_s2 = 230.0          # mm

This instrument definition can then be used to define the measurement
geometry:

    >>> geometry = ANDR(Tlo=0.5, slits_at_Tlo=0.2, slits_below=0.1)
    >>> T,dT,L,dL = geometry.resolution(T=linspace(0,5,51))
    >>> Q,dQ = dTdL2dQ(T=T,dT=dT,L=L,dL=dL)

GUI Usage
=========

Graphical user interfaces follow different usage patterns from scripts.
Here the emphasis will be on selecting a data set to process, displaying
its default metadata and allowing the user to override it.

File loading should follow the pattern established in reflectometry
reduction, with an extension registry and a fallback scheme whereby
files can be checked in a predefined order.  If the file cannot be
loaded, then the next loader is tried.  This should be extended with
the concept of a magic signature such as those used by graphics and
sound file applications: read the first block and run it through
the signature check before trying to load it.  For unrecognized
extensions, all loaders can be tried.

The file loader should return an instrument instance with metadata
initialized from the file header.  This metadata can be displayed
to the user along with a plot of the data and the resolution.  When
metadata values are changed, the resolution can be recomputed and the
display updated.  When the data set is accepted, the final resolution
calculation can be performed.
"""
from __future__ import division

# TODO: the resolution calculator should not be responsible for loading
# the data; maybe do it as a mixin?

import numpy
#from numpy import pi, inf, sqrt, log, degrees, radians, cos, sin, tan
from resolution import TL2Q, QL2T, dTdL2dQ, dQdT2dLoL, FWHM2sigma, sigma2FWHM
from resolution import bins, binwidths, binedges
from resolution import slit_widths, divergence
from probe import make_probe, PolarizedNeutronProbe


class Monochromatic(object):
    """
    Instrument representation for scanning reflectometers.

    :Parameters:
        *instrument* : string
            name of the instrument
        *radiation* : string | xray or neutron
            source radiation type
        *d_s1*, *d_s2* : float | mm
            distance from sample to pre-sample slits 1 and 2; post-sample
            slits are ignored
        *wavelength* : float | Angstrom
            wavelength of the instrument
        *dLoL* : float
            constant relative wavelength dispersion; wavelength range and
            dispersion together determine the bins
        *slits* : float OR (float,float) | mm
            fixed slits
        *slits_at_Tlo* : float OR (float,float) | mm
            slit 1 and slit 2 openings at Tlo; this can be a scalar if both
            slits are open by the same amount, otherwise it is a pair (s1,s2).
        *slits_at_Qlo* : float OR (float,float) | mm
            equivalent to slits_at_Tlo, for instruments that are controlled by
            Q rather than theta
        *Tlo*, *Thi* : float | degrees
            range of opening slits, or inf if slits are fixed.
        *Qlo*, *Qhi* : float | inv Angstroms
            range of opening slits when instrument is controlled by Q.
        *slits_below*, *slits_above* : float OR (float,float) | mm
            slit 1 and slit 2 openings below Tlo and above Thi; again, these
            can be scalar if slit 1 and slit 2 are the same, otherwise they
            are each a pair (s1,s2).  Below and above default to the values of
            the slits at Tlo and Thi respectively.
        *sample_width* : float | mm
            width of sample; at low angle with tiny samples, stray neutrons
            miss the sample and are not reflected onto the detector, so the
            sample itself acts as a slit, therefore the width of the sample
            may be needed to compute the resolution correctly
        *sample_broadening* : float | degrees FWHM
            amount of angular divergence (+) or focusing (-) introduced by
            the sample; this is caused by sample warp, and may be read off
            of the rocking curve by subtracting (s1+s2)/2/(d_s1-d_s2) from
            the FWHM width of the rocking curve
    """
    instrument = "monochromatic"
    radiation = "unknown"
    # Required attributes
    wavelength = None
    dLoL = None
    d_s1 = None
    d_s2 = None
    # Optional attributes
    Tlo= 90  # Use 90 for fixed slits; this is effectively inf
    Thi= 90
    fixed_slits = None
    slits_at_Tlo = None    # Slit openings at Tlo, and default for slits_below
    slits_below = None     # Slit openings below Tlo, or fixed slits if Tlo=90
    slits_above = None
    sample_width = 1e10    # Large but finite value
    sample_broadening = 0

    def __init__(self, **kw):
        self._translate_Q_to_theta(kw)
        for k,v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                raise TypeError("unexpected keyword argument '%s'"%k)

    def probe(self, **kw):
        """
        Return a probe for use in simulation.

        :Parameters:
            *Q* : [float] | Angstroms
                Q values to be measured.
            *T* : [float] | degrees
                Angles to be measured.

        Additional keyword parameters

        :Returns:
            *probe* : Probe
                Measurement probe with complete resolution information.  The
                probe will not have any data.

        If both *Q* and *T* are specified then *Q* takes precedents.

        You can override instrument parameters using key=value.  In
        particular, settings for *slits_at_Tlo*, *Tlo*, *Thi*,
        *slits_below*, and *slits_above* are used to define the
        angular divergence.
        """
        self._translate_Q_to_theta(kw)
        T,dT,L,dL = self.resolution(**kw)
        T = kw.pop('T')
        return make_probe(T=T,dT=dT,L=L,dL=dL,
                          radiation=self.radiation, **kw)

    def magnetic_probe(self, Tguide=270, shared_beam=True, **kw):
        """
        Simulate a polarized measurement probe.

        Returns a probe with Q, angle, wavelength and the associated
        uncertainties, but not any data.

        Guide field angle *Tguide* can be specified, as well as keyword
        arguments for the geometry of the probe cross sections such as
        *slits_at_Tlo*, *Tlo*, *Thi*, *slits_below*, and *slits_above*
        to define the angular divergence.
        """
        probes = [self.probe(**kw) for _ in range(4)]
        probe = PolarizedNeutronProbe(probes, Tguide=Tguide)
        if shared_beam:
            probe.shared_beam()  # Share the beam parameters by default
        return probe

    def simulate(self, sample, uncertainty=0.01, **kw):
        """
        Simulate a run with a particular sample.

        :Parameters:
            *sample* : Stack
                Model of the sample.
            *uncertainty* = 0.01 : float
                Relative uncertainty in the measurement.

        Additional :meth:`probe` keyword parameters are required to define
        the set of angles to be measured

        :Returns:
            *experiment* : Experiment
                Sample + probe with simulated data.

        The relative uncertainty is used to calculate the number of incident
        beam intensity for the measurement as follows::

            >>> I = (100 Q)^4 / s^2

        """
        from .experiment import Experiment
        probe = self.probe(**kw)
        M = Experiment(probe=probe, sample=sample)
        _, Rth = M.reflectivity()
        dR = uncertainty*M.fresnel()
        R = Rth + numpy.random.randn(*Rth.shape)*dR
        probe.data = R,dR

        return M

    def resolution(self, **kw):
        """
        Calculate resolution at each angle.

        :Return:
            *T*, *dT* : [float] | degrees
                Angles and angular divergence.
            *L*, *dL* : [float] | Angstroms
                Wavelengths and wavelength dispersion.
        """
        self._translate_Q_to_theta(kw)
        if 'T' not in kw:
            raise TypeError("resolution requires slits and either T or Q")

        L = kw.get('L',kw.get('wavelength',self.wavelength))
        dLoL = kw.get('dLoL',self.dLoL)
        if L is None:
            raise TypeError("Need wavelength L to compute resolution")
        if dLoL is None:
            raise TypeError("Need wavelength dispersion dLoL to compute resolution")

        T = kw['T']
        if 'slits' not in kw:
            kw['slits'] = self.calc_slits(**kw)
        dT = self.calc_dT(**kw)

        return T,dT,L,dLoL*L

    def calc_slits(self, **kw):
        """
        Determines slit openings from measurement pattern.

        If slits are fixed simply return the same slits for every angle,
        otherwise use an opening range [Tlo,Thi] and the value of the
        slits at the start of the opening to define the slits.  Slits
        below Tlo and above Thi can be specified separately.

        *T* OR *Q*       incident angle or Q
        *Tlo*, *Thi*     angle range over which slits are opening
        *slits_at_Tlo*   openings at the start of the range, or fixed opening
        *slits_below*, *slits_above*   openings below and above the range

        Use fixed_slits is available, otherwise use opening slits.
        """
        self._translate_Q_to_theta(kw)
        if 'T' not in kw:
            raise TypeError("calc_slits requires angle T=... or Q=...")
        T = kw['T']
        Tlo = kw.get('Tlo',self.Tlo)
        Thi = kw.get('Thi',self.Thi)
        fixed_slits = kw.get('fixed_slits',self.fixed_slits)
        if fixed_slits is not None:
            slits_at_Tlo = slits_below = slits_above = fixed_slits
            Tlo = 90
        else:
            slits_at_Tlo = kw.get('slits_at_Tlo',self.slits_at_Tlo)
            slits_below = kw.get('slits_below',self.slits_below)
            slits_above = kw.get('slits_above',self.slits_above)

        # Otherwise we are using opening slits
        if Tlo is None or slits_at_Tlo is None:
            raise TypeError("Resolution calculation requires Tlo and slits_at_Tlo")
        slits = slit_widths(T=T, slits_at_Tlo=slits_at_Tlo,
                            Tlo=Tlo, Thi=Thi,
                            slits_below=slits_below,
                            slits_above=slits_above)
        return slits

    def calc_dT(self, **kw):
        """
        Compute the angular divergence for given slits and angles

        :Parameters:
            *T* OR *Q* : [float] | degrees OR |1/A|
                measurement angles
            *slits* : float OR (float,float) | mm
                total slit opening from edge to edge, not beam center to edge
            *d_s1*, *d_s2* : float | mm
                distance from sample to slit 1 and slit 2
            *sample_width* : float | mm
                size of sample
            *sample_broadening* : float | degrees FWHM
                resolution changes from sample warp

        :Returns:
            *dT* : [float] | degrees FWHM
                angular divergence

        *sample_broadening* can be estimated from W, the full width at half
        maximum of a rocking curve measured in degrees:

            sample_broadening = W - degrees( 0.5*(s1+s2) / (d1-d2))

        """
        self._translate_Q_to_theta(kw)
        if 'T' not in kw or 'slits' not in kw:
            raise TypeError("calc_dT requires slits and either T or Q")
        slits = kw['slits']
        T = kw['T']
        d_s1 = kw.get('d_s1',self.d_s1)
        d_s2 = kw.get('d_s2',self.d_s2)
        if d_s1 is None or d_s2 is None:
            raise TypeError("Need slit distances d_s1, d_s2 to compute resolution")
        sample_width = kw.get('sample_width',self.sample_width)
        sample_broadening = kw.get('sample_broadening',self.sample_broadening)
        dT = divergence(T=T, slits=slits, distance=(d_s1,d_s2),
                        sample_width=sample_width,
                        sample_broadening=sample_broadening)

        return dT

    def _translate_Q_to_theta(self, kw):
        """
        Rewrite keyword arguments with Q values translated to theta values.
        """
        # Grab wavelength first so we can translate Qlo/Qhi to Tlo/Thi no
        # matter what order the keywords appear.
        wavelength = kw.get('wavelength',self.wavelength)
        if "Q" in kw:
            kw["T"] = QL2T(kw.pop("Q"), wavelength)
        if "Qlo" in kw:
            kw["Tlo"] = QL2T(kw.pop("Qlo"), wavelength)
        if "Qhi" in kw:
            kw["Thi"] = QL2T(kw.pop("Qhi"), wavelength)
        if "slits_at_Qlo" in kw:
            kw["slits_at_Tlo"] = kw.pop("slits_at_Qlo")

    def __str__(self):
        msg = """\
== Instrument %(name)s ==
radiation = %(radiation)s at %(L)g Angstrom with %(dLpercent)g%% resolution
slit distances = %(d_s1)g mm and %(d_s2)g mm
fixed region below %(Tlo)g and above %(Thi)g degrees
slit openings at Tlo are %(slits_at_Tlo)s mm
sample width = %(sample_width)g mm
sample broadening = %(sample_broadening)g degrees
""" % dict(name=self.instrument, L=self.wavelength, dLpercent=self.dLoL*100,
           d_s1=self.d_s1, d_s2=self.d_s2,
           sample_width=self.sample_width,
           sample_broadening=self.sample_broadening,
           Tlo=self.Tlo, Thi=self.Thi,
           slits_at_Tlo=str(self.slits_at_Tlo), radiation=self.radiation,
           )
        return msg

    @classmethod
    def defaults(cls):
        """
        Return default instrument properties as a printable string.
        """
        msg = """\
== Instrument class %(name)s ==
radiation = %(radiation)s at %(L)g Angstrom with %(dLpercent)g%% resolution
slit distances = %(d_s1)g mm and %(d_s2)g mm
""" % dict(name=cls.instrument, L=cls.wavelength, dLpercent=cls.dLoL*100,
           d_s1=cls.d_s1, d_s2=cls.d_s2,
           radiation=cls.radiation,
           )
        return msg

class Pulsed(object):
    """
    Instrument representation for pulsed reflectometers.

    :Parameters:
        *instrument* : string
            name of the instrument
        *radiation* : string | xray, neutron
            source radiation type
        *T* : float | degrees
            sample angle
        *slits* : float OR (float,float) | mm
            slit 1 and slit 2 openings
        *d_s1*, *d_s2* : float | mm
            distance from sample to pre-sample slits 1 and 2; post-sample
            slits are ignored
        *wavelength* : (float,float) | Angstrom
            wavelength range for the measurement
        *dLoL* : float
            constant relative wavelength dispersion; wavelength range and
            dispersion together determine the bins
        *sample_width* : float | mm
            width of sample; at low angle with tiny samples, stray neutrons
            miss the sample and are not reflected onto the detector, so the
            sample itself acts as a slit, therefore the width of the sample
            may be needed to compute the resolution correctly
        *sample_broadening* : float | degrees FWHM
            amount of angular divergence (+) or focusing (-) introduced by
            the sample; this is caused by sample warp, and may be read off
            of the rocking curve by subtracting 0.5*(s1+s2)/(d_s1-d_s2) from
            the FWHM width of the rocking curve
    """
    instrument = "pulsed"
    radiation = "neutron" # unless someone knows how to do TOF Xray...
    # Required attributes
    d_s1 = None
    d_s2 = None
    slits = None
    T = None
    wavelength = None
    dLoL = None # usually 0.02 for 2% FWHM
    # Optional attributes
    sample_width = 1e10
    sample_broadening = 0

    def __init__(self, **kw):
        for k,v in kw.items():
            if not hasattr(self, k):
                raise TypeError("unexpected keyword argument '%s'"%k)
            setattr(self, k, v)

    def probe(self, **kw):
        """
        Simulate a measurement probe.

        Returns a probe with Q, angle, wavelength and the associated
        uncertainties, but not any data.

        You can override instrument parameters using key=value.
        In particular, slit settings *slits* and *T* define
        the angular divergence and *dLoL* defines the wavelength
        resolution.
        """
        low,high = kw.get('wavelength',self.wavelength)
        dLoL = kw.get('dLoL',self.dLoL)
        T = kw.pop('T',self.T)
        L = bins(low,high,dLoL)
        dL = binwidths(L)
        T,dT,L,dL = self.resolution(L=L, dL=dL, T=T, **kw)
        return make_probe(T=T,dT=dT,L=L,dL=dL,
                          radiation=self.radiation, **kw)

    def magnetic_probe(self, Tguide=270, shared_beam=True, **kw):
        """
        Simulate a polarized measurement probe.

        Returns a probe with Q, angle, wavelength and the associated
        uncertainties, but not any data.

        Guide field angle *Tguide* can be specified, as well as keyword
        arguments for the geometry of the probe cross sections such as
        slit settings *slits* and *T* to define the angular divergence
        and *dLoL* to define the wavelength resolution.
        """
        probes = [self.probe(**kw) for _ in range(4)]
        probe = PolarizedNeutronProbe(probes, Tguide=Tguide)
        if shared_beam:
            probe.shared_beam()  # Share the beam parameters by default
        return probe

    def simulate(self, sample, uncertainty=0.01, **kw):
        """
        Simulate a run with a particular sample.

        :Parameters:
            *sample* : Stack
                Reflectometry model
            *T* : [float] | degrees
                List of angles to be measured, such as [0.15,0.4,1,2].
            *slits* : [float] or [(float,float)] | mm
                Slit settings for each angle. Default is 0.2*T
            *uncertainty* = 0.01 : float or [float]
                Incident intensity is set so that the worst dF/F is better
                than *uncertainty*, where F is the idealized Fresnel
                reflectivity of the sample.
            *dLoL* = 0.02: float
                Wavelength resolution
            *normalize* = True : boolean
                Whether to normalize the intensities
            *theta_offset* = 0 : float | degrees
                Sample alignment error
            *background* = 0 : float
                Background counts per incident neutron (background is
                assumed to be independent of measurement geometry).
            *back_reflectivity* = False : boolean
                Whether beam travels through incident medium
                or through substrate.
            *back_absorption* = 1 : float
                Absorption factor for beam traveling through substrate.
                Only needed for back reflectivity measurements.
        """
        from reflectometry.reduction.rebin import rebin
        from .experiment import Experiment
        from .resolution import binedges
        from .probe import ProbeSet
        T = kw.pop('T', self.T)
        slits = kw.pop('slits', self.slits)
        if slits is None: slits = [0.2*Ti for Ti in T]

        dLoL = kw.pop('dLoL', self.dLoL)
        normalize = kw.pop('normalize', True)
        theta_offset = kw.pop('theta_offset', 0)
        background = kw.pop('background', 0)
        back_reflectivity = kw.pop('back_reflectivity', False)
        back_absorption = kw.pop('back_absorption', 1)

        # Compute reflectivity with resolution and added noise
        probes = []
        for Ti,Si in zip(T,slits):
            probe = self.probe(T=Ti, slits=Si, dLoL=dLoL)
            probe.back_reflectivity = back_reflectivity
            probe.theta_offset.value = theta_offset
            probe.back_absorption.value = back_absorption
            M = Experiment(probe=probe, sample=sample)
            # Note: probe.L is reversed because L is sorted by increasing
            # Q in probe.
            I = rebin(binedges(self.feather[0]),self.feather[1],
                      binedges(probe.L[::-1]))[::-1]
            Ci = max(1./(uncertainty**2 * I * M.fresnel()))
            Icounts = Ci*I

            _, Rth = M.reflectivity()
            Rcounts = numpy.random.poisson(Rth*Icounts)
            if background > 0:
                Rcounts += numpy.random.poisson(Icounts*background,
                                                size=Rcounts.shape)
            # Set intensity/background _after_ calculating the theory function
            # since we don't want the theory function altered by them.
            probe.background.value = background
            # Correct for the feather.  This has to be done otherwise we
            # won't see the correct reflectivity.  Even if corrected for
            # the feather, though, we haven't necessarily corrected for
            # the overall number of counts in the measurement.
            # Z = X/Y
            # var Z = (var X / X**2 + var Y / Y**2) * Z**2
            #       = (1/X + 1/Y) * (X/Y)**2
            #       = (Y + X) * X/Y**3
            R = Rcounts/Icounts
            dR = numpy.sqrt((Icounts + Rcounts)*Rcounts/Icounts**3)

            if not normalize:
                #Ci = 1./max(R)
                R, dR = R*Ci, dR*Ci
                probe.background.value *= Ci
                probe.intensity.value = Ci

            probe.data = R,dR
            probes.append(probe)

        return Experiment(sample=sample, probe=ProbeSet(probes))

    def resolution(self, L, dL, **kw):
        """
        Return the resolution of the measurement.  Needs *T*, *L*, *dL*
        specified as keywords.
        """
        T = kw.pop('T', self.T)
        slits = kw.pop('slits', self.slits)
        dT = self.calc_dT(T,slits,**kw)

        # Compute the FWHM angular divergence in radians
        # Return the resolution
        return T,dT,L,dL

    def calc_dT(self, T, slits, **kw):
        d_s1 = kw.get('d_s1',self.d_s1)
        d_s2 = kw.get('d_s2',self.d_s2)
        sample_width = kw.get('sample_width',self.sample_width)
        sample_broadening = kw.get('sample_broadening',self.sample_broadening)
        dT = divergence(T=T, slits=slits, distance=(d_s1,d_s2),
                        sample_width=sample_width,
                        sample_broadening=sample_broadening)

        return dT

    def __str__(self):
        msg = """\
== Instrument %(name)s ==
radiation = %(radiation)s in %(L_min)g to %(L_max)g Angstrom with %(dLpercent)g%% resolution
slit distances = %(d_s1)g mm and %(d_s2)g mm
slit openings = %(slits)s mm
sample width = %(sample_width)g mm
sample broadening = %(sample_broadening)g degrees FWHM
""" % dict(name=self.instrument,
           L_min=self.wavelength[0], L_max=self.wavelength[1],
           dLpercent=self.dLoL*100,
           d_s1=self.d_s1, d_s2=self.d_s2, slits = str(self.slits),
           sample_width=self.sample_width,
           sample_broadening=self.sample_broadening,
           radiation=self.radiation,
           )
        return msg

    @classmethod
    def defaults(cls):
        """
        Return default instrument properties as a printable string.
        """
        msg = """\
== Instrument class %(name)s ==
radiation = %(radiation)s in %(L_min)g to %(L_max)g Angstrom with %(dLpercent)g%% resolution
slit distances = %(d_s1)g mm and %(d_s2)g mm
""" % dict(name=cls.instrument,
           L_min=cls.wavelength[0], L_max=cls.wavelength[1],
           dLpercent=cls.dLoL*100,
           d_s1=cls.d_s1, d_s2=cls.d_s2,
           radiation=cls.radiation,
           )
        return msg

_ = '''
class GenericMonochromatic(Monochromatic):
    def load(self, filename, **kw):
        """
        Load the data, returning the associated probe.  This probe will
        contain Q, angle, wavelength, measured reflectivity and the
        associated uncertainties.

        You can override instrument parameters using key=value.  In
        particular, slit settings *slits_at_Tlo*, *Tlo*, *Thi*,
        and *slits_below*, and *slits_above* are used to define the
        angular divergence.

        .. Note::
             This function ignores any resolution information stored in
             the file, such as dQ, dT or dL columns, and instead uses the
             defined instrument parameters to calculate the resolution.

        """
        # Load the data
        data = numpy.loadtxt(filename).T
        if data.shape[0] == 2:
            Q,R = data
            dR = None
        elif data.shape[0] == 3:
            Q,R,dR = data
        elif data.shape[0] == 4:
            Q,dQ,R,dR = data
        elif data.shape[0] == 5:
            Q,dQ,R,dR,L = data
        if "Q" not in kw: kw["Q"] = Q
        T,dT,L,dL = self.resolution(**kw)
        kw.update(dict(T=T,dT=dT,L=L,dL=dL,data=(R,dR),
                       radiation=self.radiation))
        return make_probe(**kw)

class GenericPulsed(Pulsed):
    def load(self, filename, **kw):
        """
        Load the data, returning the associated probe.  This probe will
        contain Q, angle, wavelength, measured reflectivity and the
        associated uncertainties.

        You can override instrument parameters using key=value.
        In particular, slit settings *slits* and *T* define the
        angular divergence.
        """
        # Load the data
        data = numpy.loadtxt(filename).T
        Q,dQ,R,dR,L = data
        dL = binwidths(L)
        T = kw.pop('T',QL2T(Q,L))
        T,dT,L,dL = self.resolution(L=L, dL=dL, T=T, **kw)
        return make_probe(T=T,dT=dT,L=L,dL=dL,data=(R,dR),
                          radiation=self.radiation, **kw)
'''