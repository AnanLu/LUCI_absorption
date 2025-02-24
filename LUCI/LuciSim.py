"""
Suite of simulations tools in LUCI
"""

import numpy as np
from LUCI.LuciFunctions import Gaussian, Sinc, SincGauss
from os import path
import ppxf.sps_util as lib
from urllib import request
ppxf_dir = path.dirname(path.realpath(lib.__file__))

class Spectrum:

    def __init__(self, lines, fit_function, ampls, velocity, broadening, filter_, resolution, snr, redshift=0.0):
        """
        Initialize mock spectrum by creating the spectrum and adding noise

        Args:
            lines: List of lines to model (e.x. ['Halpha'])
            fit_function: Function used to model lines  (options: 'sinc', 'gaussian', 'sincgauss')
            ampls: List of amplitudes for emission lines
            velocity: List of velocities of emission lines; if not a list, then all velocities are set equal
            broadening: List of broadening of emissino lines; ditto above
            filter: SITELLE Filter (e.x. 'SN3')
            resolution: Spectral resolution
            snr: Signal to noise ratio
            redshift of object (default 0.0)

        """

        self.line_dict = {'Halpha': 656.280, 'NII6583': 658.341, 'NII6548': 654.803,
                      'SII6716': 671.647, 'SII6731': 673.085, 'OII3726': 372.603,
                      'OII3729': 372.882, 'OIII4959': 495.891, 'OIII5007': 500.684,
                      'Hbeta': 486.133}
        self.available_functions = ['gaussian', 'sinc', 'sincgauss']
        # Initialize (default SN3 values)
        #self.delta_x = 2943  # step size in nanometers
        #self.n_steps = 289  # Number of steps (default R~5000)
        #self.order = 8  # Folding order
        self.theta = 11.96  # Interferometer angle in degrees
        self.zpd_index  = 0  # Zero Path Difference
        self.lines = lines
        self.line_num = len(lines)  # Number of  lines to fit
        self.fit_function = fit_function
        self.ampls = ampls
        if not isinstance(velocity, list):
            # List not passed -- set all velocities equal
            self.velocity = [velocity for i in range(len(lines))]
        if not isinstance(broadening, list):
            # List not passed -- set all broadening equal
            self.broadening = [broadening for i in range(len(lines))]
        self.filter = filter_
        if self.filter == 'SN3':
            self.delta_x = 2943
            self.order = 8
        elif self.filter == 'SN2':
            self.delta_x = 1680
            self.order = 6
        elif self.filter == 'SN1':
            self.delta_x = 1647
            self.order = 8
        elif self.filter == 'C1':
            self.delta_x = 570
            self.order = 2
        elif self.filter == 'C2':
            self.delta_x = 1680
            self.order = 5
        elif self.filter == 'C3':
            self.delta_x = 1778
            self.order = 6
        elif self.filter == 'C4':
            self.delta_x = 5272
            self.order = 12
        else:
            print('We only support C1, C2, C3, C4, SN1, SN2, and SN3 at this time.')
            print('Terminating the program')
            exit()
        self.resolution = resolution
        self.redshift = redshift
        # Calculate number of steps from resolution
        self.n_steps = 0
        self.steps_from_resolution()
        self.snr = snr  # Set signal-to-noise ratio
        self.calc_sinc_width()
        # Checks
        self.check_lines()
        self.check_fitting_model()


    def steps_from_resolution(self):
        """
        Calculate the number of steps given the resolution, delta_x, and order.
        This is taken from Martin's Thesis.
        """
        temp = (self.order + 0.5) / (2 * self.delta_x)
        self.n_steps = int(np.ceil(1.20671 * self.resolution / (2 * temp * self.delta_x)))  # The constant comes from the sinc function)

    def calc_sinc_width(self):
        """
        Calculate sinc width of the sincgauss function

        """
        MPD = np.cos(np.deg2rad(self.theta))*self.delta_x*(self.n_steps-self.zpd_index)/1e7
        self.sinc_width = 1/(2*MPD)

    def gaussian_model(self, channel, amp, pos, sigma):
        """
        Function to initiate the correct number of models to fit

        Args:
            channel: Wavelength Axis in cm-1
            amp: Amplitude of the line
            pos: Position of the line
            sigma: Sigma of the line

        Return:
            Value of function given input parameters

        """
        f1 =  Gaussian().evaluate(channel, [amp, pos, sigma], 1)  # The last argument is 1 since we add one line at a time
        return f1


    def sinc_model(self, channel, amp, pos, sigma):
        """
        Function to initiate the correct number of models to fit

        Args:
            channel: Wavelength Axis in cm-1
            amp: Amplitude of the line
            pos: Position of the line
            sigma: Sigma of the line

        Return:
            Value of function given input parameters

        """
        f1 = Sinc().evaluate(channel, [amp, pos, sigma], 1, self.sinc_width)
        return f1


    def sincgauss_model(self, channel, amp, pos, sigma):
        """
        Function to initiate the correct number of models to fit

        Args:
            channel: Wavelength Axis in cm-1
            amp: Amplitude of the line
            pos: Position of the line
            sigma: Sigma of the line

        Return:
            Value of function given input parameters

        """
        f1 = SincGauss().evaluate(channel, [amp, pos, sigma], 1, self.sinc_width)
        return np.real(f1)

    def create_spectrum(self):
        """
        Create a mock spectrum given the lines of interest, the fitting function, the
        amplitudes of the lines, the kinematics of the lines, and the interferometer parameters.
        The interferometer parameters (step, n_steps, order & theta) will be used to construct the x-axis.
        We add noise given the snr value provided by sampling from a normal distribution with a sigma=1.


        """

        # Calculate correction factor
        corr = 1/np.cos(np.deg2rad(self.theta))
        # Construct x axis in units of cm-1
        x_min = self.order/(2*self.delta_x) * corr * 1e7
        x_max = (self.order+1)/(2*self.delta_x) * corr * 1e7
        step_ = x_max - x_min
        axis = np.array([x_min+j*step_/self.n_steps for j in range(self.n_steps)])
        # Initiate spectrum
        spectrum = np.zeros_like(axis)  # Set continuum of about 2
        # Create emission lines
        for line_ct, line in enumerate(self.lines):
            line_lambda_cm = (1e7 / self.line_dict[line])/(1+self.redshift)  # Convert from nm to cm-1
            vel_ = self.velocity[line_ct]  # Get velocity
            broad_ = self.broadening[line_ct]  # Get broadening
            amp_ = self.ampls[line_ct]  # Get amplitude
            # Calculate position of line given velocity & match to closest point on axis
            line_pos = (vel_/3e5)*line_lambda_cm + line_lambda_cm
            min_ind = np.argmin(np.abs(axis - line_pos))
            line_pos = axis[min_ind]
            # Calculate sigma given broadening
            sigma = (broad_*line_pos)/(3e5*corr)#/(2.*np.sqrt(2. * np.log(2.)))
            # Create spectrum
            if self.fit_function == 'gaussian':
                spectrum += self.gaussian_model(axis, amp_, line_pos, sigma)
            elif self.fit_function == 'sinc':
                spectrum += self.sinc_model(axis, amp_, line_pos, sigma)
            elif self.fit_function == 'sincgauss':
                self.calc_sinc_width()
                spectrum += self.sincgauss_model(axis, amp_, line_pos, sigma)
            else:
                print('An incorrect fit function was entered. Please use either gaussian, sinc, or sincgauss.')
            #print(np.max(spectrum))
        # We now add noise with our predefined SNR
        spectrum += np.max(spectrum)*np.random.normal(0.0,1/self.snr,spectrum.shape)
        return axis, spectrum

    

    def check_lines(self):
        """
        This function checks to see that the lines provided are in the available options
        Return:
        Nothing if the user provides appropriate lines
        Else it will throw an error

        """
        if set(self.lines).issubset(self.line_dict):
            pass
        else:
            raise Exception('Please submit a line name in the available list: \n {}'.format(self.line_dict.keys()))

    def check_fitting_model(self):
        """
        This function checks to see that the model provided is in the available options
        Return:
        Nothing if the user provides an appropriate fitting model
        Else it will throw an error

        """
        if self.fit_function in self.available_functions:
            pass
        else:
            print(self.fit_function)
            raise Exception(
                'Please submit a fitting function name in the available list: \n {}'.format(self.available_functions))

def abs_template(resolution, filter, age=1, metal=-0.2):
    """
    Function to calculate the stellar component based off ppxf Miles models

    Args:
        resolution:
        filter:
        age:
        metal:
    Return:
        wavenumber:
        amplitude:

    Written by Anan Lu
    """
    # Calculate velocity scale
    velscale = 3 * 10 ** 5 / resolution / 2
    # Make age list and metal list for Miles
    agelist = np.logspace(np.log10(0.0613), np.log10(15.8489), 25)
    metallist = [-0.4, -0.71, -1.31, -1.71, 0, 0.22]
    metallist = np.array(metallist)
    # Get the age closest to the age provided
    age_idx = np.abs(agelist - age).argmin()
    metal_idx = np.abs(metallist - metal).argmin()
    # Load in miles star templates
    #ppxf_dir = path.dirname(path.realpath(lib.__file__))
    #pathname = ppxf_dir + '/miles_models/Eun1.30*.fits'
    ppxf_dir = path.dirname(path.realpath(lib.__file__))
    sps_name = 'emiles'
    basename = f"spectra_{sps_name}_9.0.npz"
    filename = path.join(ppxf_dir, 'sps_models', basename)
    if not path.isfile(filename):
        url = "https://raw.githubusercontent.com/micappe/ppxf_data/main/" + basename
        request.urlretrieve(url, filename)
    miles = lib.sps_lib(filename, velscale, norm_range=[5070, 5950])
    stars_templates, lam_temp = miles.templates, miles.lam_temp
    # Initialize output variables
    wavenumber = 0
    amplitude = [0]
    # Calculate for SN3
    if filter == 'SN3':
        #x_sn3 = np.where((lam_temp >= 6430) & (lam_temp <= 6790))
        x_sn3 = np.where((lam_temp >= 6400) & (lam_temp <= 6870))
        lambda_sn3 = lam_temp[x_sn3]
        amplitude = stars_templates[x_sn3, age_idx, metal_idx]
        wavenumber = 10 ** 8 / lambda_sn3
    # Calculate for SN2
    if filter == 'SN2':
        x_sn2 = np.where((lam_temp >= 4770) & (lam_temp <= 5100))
        lambda_sn2 = lam_temp[x_sn2]
        amplitude = stars_templates[x_sn2, age_idx, metal_idx]
        wavenumber = 10 ** 8 / lambda_sn2

    return wavenumber, amplitude[0]