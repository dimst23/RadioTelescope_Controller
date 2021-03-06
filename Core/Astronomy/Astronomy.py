import os
import math
import time
import datetime
import logging
import ephem
import numpy as np
from PyQt5 import QtCore
from pyorbital import tlefile
from astropy.coordinates import SkyCoord, EarthLocation, FK5
from astropy.time import Time
from skyfield.api import load


RAD_TO_DEG = 57.2957795131  # Radians to degrees conversion factor
SEC_TO_DAY = 1.1574074e-5  # How many days a second has

# TODO add them to a file to be easily changed
MOTOR_RA_STEPS_PER_DEGREE = 43200.0 / 15.0  # 43200 is in steps per hour of right ascension
MOTOR_DEC_STEPS_PER_DEGREE = 10000.0  # Steps per degree
MAX_STEP_FREQUENCY = 200.0  # Maximum stepping frequency of the motors in Hz


class Calculations(QtCore.QObject):
    """
    The Calculations class contains methods which perform the necessary astronomical conversions. Apart from coordinate
    conversion, there are methods to calculate the transit time of an object and also create a map of scanning points.

    Todo:
        Replace deprecated PyEphem with astropy and skyfield
    """
    def __init__(self, cfg_data, parent=None):
        """
        Calculations class constructor to initialize the required variables. Also the logger object is created.

        Todo:
            Remove super if it is not required

        Args:
            cfg_data: The XML parser object
            parent: Parent class, if any
        """
        super(Calculations, self).__init__(parent)
        self.logger = logging.getLogger(__name__)  # Create the logger for the file
        self.cfg_data = cfg_data

        lat_lon = cfg_data.get_lat_lon()  # Get the latitude and longitude
        self.location = EarthLocation(lat=lat_lon[0], lon=lat_lon[1])  # Astropy location object
        self.observer = ephem.Observer()  # Create the observer object
        self.observer.lat, self.observer.lon = lat_lon[0], lat_lon[1]  # Provide the observer's location
        self.observer.elevation = float(cfg_data.get_altitude())  # Set the location's altitude in meters

    def hour_angle(self, object_ra: float, object_dec: float, date=None):
        """
        Converts the provided right ascension (RA) of an object to its corresponding hour angle (HA), based on the
        provided date.

        Args:
            date: Desired date for the calculation of the hour angle
            object_ra (float): The right ascension of the object in J2000
            object_dec (float): Object's declination in J2000

        Todo:
            Check the reason that the the values for the HA differ by almost 2 minutes from the real ones

        Todo:
            Also add a solid documentation for the whole file, explaining in detail the parsed arguments

        Todo:
            Update the docstring of this function because there is a major change.

        Returns:
            float: Calculated hour angle
        """
        if date is None:
            date = self.current_time()
        else:
            if len(date) == 3:
                day = int(date[2])
                hour = (date[2] - day) * 24
                minute = (hour - int(hour)) * 60
                second = int(minute - int(minute)) * 60
                date = (date[0], date[1], day, int(hour), int(minute), second)

        object_coordinates = SkyCoord(ra=str(object_ra), dec=str(object_dec), unit='deg')
        equinox_time = Time(datetime.datetime(*date), scale='utc', location=self.location, format='datetime')
        ra_jnow = object_coordinates.transform_to(FK5(equinox=equinox_time)).ra

        # Get the local sidereal time
        time_scale = load.timescale()
        utc_time = time_scale.utc(*date)
        local_sidereal_time = utc_time.gast * 15 + self.location.lon.degree

        return round(local_sidereal_time - ra_jnow.degree, 6)  # Return the calculated hour angle

    def hour_angle_to_ra(self, object_ha: float, object_dec: float, date=None):
        """
        Convert the provided object's hour angle to its corresponding right ascension. This method assumes that ephem is
        properly calibrated. Also the date is assumed to be now.

        Todo:
            Check what happens in every case and if the conversion of degrees is needed

        Args:
            object_ha (float): Hour angle of the desired object
            object_dec (float): Declination of the object
            date (tuple): The desired date

        Returns:
            The current right ascension of the object in J2000
        """
        # Get the local sidereal time
        if date is None:
            date = self.current_time()  # Get the current time and date as needed
        else:
            if len(date) == 3:
                day = int(date[2])
                hour = (date[2] - day)*24
                minute = (hour - int(hour))*60
                second = int(minute - int(minute))*60
                date = (date[0], date[1], day, int(hour), int(minute), second)

        # Calculate the desired right ascension
        time_scale = load.timescale()
        utc_time = time_scale.utc(*date)
        local_sidereal_time = utc_time.gast * 15 + self.location.lon.degree
        calculated_ra = local_sidereal_time - object_ha  # Calculate the right ascension in JNOW

        # Calculate the right ascension of the provided object in J2000
        equinox_time = Time(datetime.datetime(*date), scale='utc', location=self.location, format='datetime')
        object_coordinates = SkyCoord(ra=str(calculated_ra), dec=str(object_dec), unit='deg',
                                      frame=FK5, equinox=equinox_time)
        ra_j2000 = object_coordinates.transform_to(FK5(equinox='J2000.0')).ra

        return round(ra_j2000.degree, 6)

    @staticmethod
    def current_time(decimal_day=False, dummy_time=None):
        """
        Get the current GMT time without daylight saving.

        Todo:
            Determine if this function is required

        Returns:
            tuple: A tuple containing the current year, month and decimal day
        """
        if dummy_time is not None:
            return dummy_time

        gmt = time.gmtime()  # Get the current time
        if decimal_day:
            decimal_day = float(gmt.tm_mday) + float(gmt.tm_hour)/24.0 + float(gmt.tm_min)/(24.0*60.0) + \
                          float(gmt.tm_sec)/(24.0*60.0*60.0)
            return gmt.tm_year, gmt.tm_mon, decimal_day
        return gmt.tm_year, gmt.tm_mon, gmt.tm_mday, gmt.tm_hour, gmt.tm_min, gmt.tm_sec

    def transit(self, obj_ra: float, obj_dec: float, stp_to_home_ra: int, stp_to_home_dec: int, transit_time: int):
        """
        Calculates the hour angle of the provided object, at the specified position provided by the step number.
        The final hour angle is calculated for a stationary object. We add the maximum time taken by any motor
        to go at the desired position, to the current time and then the hour angle at the latter position is calculated.
        Home position of the dish is considered to be 0h hour angle and 0 degrees declination.

        Args:
            obj_ra (float): Objects right ascension in degrees
            obj_dec (float): Objects declination in degrees
            stp_to_home_ra (int): Number of steps away from home position for the right ascension motor
            stp_to_home_dec (int): Number of steps away from home for the declination motor
            transit_time (int): Time to transit position, provided in seconds

        Returns:
            A list containing the hour angle at the target location and the declination of the object
        """
        # TODO may be needed to add some "safety" seconds
        cur_time = self.current_time()  # Get the current time in tuple
        cur_ha = self.hour_angle(obj_ra, obj_dec, cur_time)  # Get the current object hour angle
        step_distance_ra = abs(stp_to_home_ra + cur_ha * MOTOR_RA_STEPS_PER_DEGREE)
        step_distance_dec = abs(stp_to_home_dec + obj_dec * MOTOR_DEC_STEPS_PER_DEGREE)
        print(step_distance_ra, step_distance_dec)

        max_distance = max(step_distance_ra, step_distance_dec)  # Calculate the maximum distance, to calculate max time
        max_move_time = max_distance / MAX_STEP_FREQUENCY  # Maximum time required for any motor, calculated in seconds
        target_time = (cur_time[0], cur_time[1], cur_time[2] + (max_move_time + transit_time) * SEC_TO_DAY)
        target_ha = self.hour_angle(obj_ra, obj_dec, target_time)  # Calculate the hour angle at the target location

        return [target_ha, obj_dec]

    def transit_planetary(self, objec, stp_to_home_ra: int, stp_to_home_dec: int, transit_time: int):
        """
        Calculate object's position when the dish arrives at position.
        This function calculates the coordinates of the requested object, taking into account the delay of the dish
        until it moves to the desired position. This is the same as the transit function, but here the transit is
        calculated for a planetary object.

        Args:
            objec: pyephem object type, which is the object of interest (e.g. ephem.Jupiter())
            stp_to_home_ra (int): Number of steps from home position for the right ascension motor
            stp_to_home_dec (int): Number of steps from home position for the declination motor
            transit_time (int): Time to transit position, provided in seconds

        Returns:
            A list containing the object's coordinates at the antenna's requested position
        """
        if objec == "Sun":
            objec = ephem.Sun()  # Select the Sun object #noqa pylint: disable=no-member
        elif objec == "Jupiter":
            objec = ephem.Jupiter()  # Select Jupiter as object
        elif objec == "Mars":
            objec = ephem.Mars()  # Select Mars as the object
        elif objec == "Venus":
            objec = ephem.Venus()  # Select Venus as the object
        elif objec == "Moon":
            objec = ephem.Moon()  # Select moon as the object

        cur_time = self.current_time()  # Get the current time in tuple
        date = "%.0f/%.0f/%.6f" % (cur_time[0], cur_time[1], cur_time[2])  # Get the current date
        objec.compute(cur_time, epoch=date)  # Compute the object's coordinates

        # Get the current coordinates for the planetary body
        obj_ra = float(objec.a_ra) * RAD_TO_DEG
        obj_dec = float(objec.a_dec) * RAD_TO_DEG

        cur_ha = self.hour_angle(obj_ra, obj_dec, cur_time)  # Get the current object hour angle
        step_distance_ra = abs(stp_to_home_ra + cur_ha * MOTOR_RA_STEPS_PER_DEGREE)
        step_distance_dec = abs(stp_to_home_dec + obj_dec * MOTOR_DEC_STEPS_PER_DEGREE)

        max_distance = max(step_distance_ra, step_distance_dec)  # Calculate the maximum distance, to calculate max time
        max_move_time = max_distance / MAX_STEP_FREQUENCY  # Maximum time required for any motor, calculated in seconds
        target_time = (cur_time[0], cur_time[1], cur_time[2] + (max_move_time + transit_time) * SEC_TO_DAY)

        # Recalculate the coordinates for the new time
        objec.compute(cur_time, epoch=date)
        obj_ra = float(objec.a_ra) * RAD_TO_DEG
        obj_dec = float(objec.a_dec) * RAD_TO_DEG
        target_ha = self.hour_angle(obj_ra, obj_dec, target_time)  # Calculate the hour angle at the target location

        return [target_ha, obj_dec]

    def tracking_planetary(self, objec, stp_to_home_ra: int, stp_to_home_dec: int):
        """
        Calculate the rate of change for the coordinates of different planetary bodies. The main calculations performed
        are the same as the transit functions. Knowing the rate of change allows for real time corrections of motor
        position.

        Args:
            objec: pyephem object type, which is the object of interest (e.g. ephem.Jupiter())
            stp_to_home_ra (int): Number of steps from home position for the right ascension motor
            stp_to_home_dec (int): Number of steps from home position for the declination motor

        Returns:
            list: Contains the object's coordinates on transit and the rate of change for the coordinates
        """
        sum_ra = sum_dec = 0.0  # Variable to hold the sum for averaging
        prev_ra = prev_dec = 0.0  # Initialize the variables
        count = 0  # Counting variable used in the loop and averaging
        transit_coords = self.transit_planetary(objec, stp_to_home_ra, stp_to_home_dec, 0)  # Calculate transit first

        # Get the right object
        if objec == "Sun":
            objec = ephem.Sun()  # Select the Sun object
        elif objec == "Jupiter":
            objec = ephem.Jupiter()  # Select Jupiter as object
        elif objec == "Mars":
            objec = ephem.Mars()  # Select Mars as the object
        elif objec == "Venus":
            objec = ephem.Venus()  # Select Venus as the object
        elif objec == "Moon":
            objec = ephem.Moon()  # Select moon as the object

        cur_time = self.current_time()  # Get the current time in tuple
        epoch_date = "%.0f/%.0f/%.6f" % (cur_time[0], cur_time[1], cur_time[2])  # Get the current date
        comp_date = epoch_date  # Set the dates to equal at first

        # Iterate for 24 hours to get enough points
        for count in range(0, 24):
            objec.compute(comp_date, epoch=epoch_date)
            cur_ra = float(objec.a_ra)
            cur_dec = float(objec.a_dec)

            if count > 0:
                sum_ra += (cur_ra - prev_ra)
                sum_dec += (cur_dec - prev_dec)
            prev_ra = cur_ra
            prev_dec = cur_dec
            comp_date = "%.0f/%.0f/%.6f" % (cur_time[0], cur_time[1], cur_time[2] + 0.04166666667)  # One hour increment

        roc_ra = ((sum_ra/count) * RAD_TO_DEG) / 3600.0  # Return degrees per second for the RA
        roc_dec = ((sum_dec/count) * RAD_TO_DEG) / 3600.0  # Return degrees per second for the DEC

        return [transit_coords[0], transit_coords[1], roc_ra, roc_dec]

    def scanning_map_generator(self, points: tuple, step_size: tuple, direction: str):
        """
        Generate a sky map of points to be scanned. Each points corresponds to the sky point at the time when the
        antenna passes through.

        Args:
            points (tuple): Initial box points at four corners. Coordinate system and epoch should be included
            step_size (tuple): Stepping size for each axis (a tuple)
            direction (str): Direction of scanning with respect to the first point

        Returns:
            list: Map points in celestial coordinates
        """
        epoch = points[5]  # Get the epoch provided
        coord_system = points[4]  # Get the coordinate system of the provided coordinates

        direct = direction.split(": ")[1]  # Get the direction string
        second_axis = False
        if direct == "R-Down":
            initial_point = points[0]
            second_point = points[1]
            third_point = points[2]
            # fourth_point = points[3]
        elif direct == "R-Up":
            initial_point = points[3]
            second_point = points[2]
            third_point = points[1]
            # fourth_point = points[0]
        elif direct == "L-Down":
            initial_point = points[1]
            second_point = points[0]
            third_point = points[3]
            # fourth_point = points[2]
        elif direct == "L-Up":
            initial_point = points[2]
            second_point = points[3]
            third_point = points[0]
            # fourth_point = points[1]
        elif direct == "Up-R":
            initial_point = points[3]
            second_point = points[0]
            third_point = points[1]
            # fourth_point = points[2]
            second_axis = True
        elif direct == "Up-L":
            initial_point = points[2]
            second_point = points[1]
            third_point = points[0]
            # fourth_point = points[3]
            second_axis = True
        elif direct == "Down-R":
            initial_point = points[0]
            second_point = points[3]
            third_point = points[2]
            # fourth_point = points[1]
            second_axis = True
        elif direct == "Down-L":
            initial_point = points[1]
            second_point = points[2]
            third_point = points[3]
            # fourth_point = points[0]
            second_axis = True
        # TODO implement a fix to include the last box without overlap
        num_boxes_x = math.floor(abs(second_point[0] - initial_point[0])/step_size[0])
        num_boxes_y = math.floor(abs(second_point[1] - third_point[1])/step_size[1])

        # Generate the point map in the Equatorial coordinate system
        x_point = initial_point[0]  # Get the first coordinate before the loop
        y_point = initial_point[1]
        raw_points = ((x_point, y_point), )
        transformed = self.coordinate_transform((x_point, y_point,), (coord_system, epoch,))
        map_points = ((round(transformed[0], 6), round(transformed[1], 6)),)

        if not second_axis:
            if second_point[0] - initial_point[0] < 0:
                fill_reverse = False  # Indicate reverse direction filling of the tuple with points (inverse logic)
            else:
                fill_reverse = True

            for i in range(0, int(num_boxes_y)):
                if i != 0:
                    y_point -= step_size[1]  # Don't deduct the step on the first point
                fill_reverse = not fill_reverse  # Negate the direction of point filling

                for j in range(0, int(num_boxes_x)):
                    if not (j == 0 and i != 0):
                        if fill_reverse is True:
                            x_point -= step_size[0]
                        else:
                            x_point += step_size[0]
                    raw_points += ((round(x_point, 6), round(y_point, 6)),)

                    transformed = self.coordinate_transform((x_point, y_point,), (coord_system, epoch,))
                    map_points += ((round(transformed[0], 6), round(transformed[1], 6)),)
        else:
            if second_point[1] - initial_point[1] < 0:
                fill_reverse = False  # Indicate reverse direction filling of the tuple with points (inverse logic)
            else:
                fill_reverse = True

            for i in range(0, int(num_boxes_x)):
                if i != 0:
                    x_point -= step_size[0]  # Don't deduct the step on the first point
                fill_reverse = not fill_reverse  # Negate the direction of point filling

                for j in range(0, int(num_boxes_y)):
                    if not (j == 0 and i != 0):
                        if fill_reverse is True:
                            y_point -= step_size[1]
                        else:
                            y_point += step_size[1]
                    raw_points += ((round(x_point, 6), round(y_point, 6)),)

                    transformed = self.coordinate_transform((x_point, y_point,), (coord_system, epoch,))
                    map_points += ((round(transformed[0], 6), round(transformed[1], 6)),)
        # TODO Remove print statement
        print("Raw points:")
        print(raw_points)
        print("Mapped points")
        print(map_points)

        return [map_points, raw_points]

    def scanning_point_calculator(self, map_points: tuple, init_steps: tuple, step_size: tuple,
                                  int_time=0.0, objec=None):
        """
        Generate the scanning map in HA and DEC, providing the integration and the initial steps.

        Args:
            map_points: Map points generated from the `scanning_map_generator`
            init_steps: Initial steps from home in RA and DEC axis
            step_size: Motor step size
            int_time: Integration time for the signal reception
            objec: Planetary object passing. Default is none.

        Returns:
            list: The calculated position of the points for scanning
        """
        if objec is None:
            first_point = self.transit(map_points[0][0], map_points[0][1], init_steps[0], init_steps[1], 0)
            roc_ra = roc_dec = 0  # Not rate of change for the non-planetary bodies
        else:
            first_point = self.tracking_planetary(objec, init_steps[0], init_steps[1])  # Get also the rate of change
            roc_ra = first_point[2]  # Get the rate of change for RA as returned from the tracking calculation
            roc_dec = first_point[3]  # Get the rate of change for DEC as returned from the tracking calculation
        calc_points = "%f_%f" % (first_point[0], first_point[1])

        # Initialize the variable with the initial steps from home
        step_incr_dec = init_steps[1]
        step_incr_ra = init_steps[0]
        for i in range(1, len(map_points)):  # Exclude first point
            try:
                if map_points[i][1] != map_points[i + 1][1]:
                    step_incr_dec += step_size[1] * MOTOR_DEC_STEPS_PER_DEGREE
                if map_points[i][0] != map_points[i + 1][0]:
                    step_incr_ra += step_size[0] * MOTOR_RA_STEPS_PER_DEGREE
            except IndexError:
                pass
            step_incr = (step_incr_ra, step_incr_dec, )

            if int(int_time * 60.0) != 0:
                tr_time = int(int_time * 60.0)
            else:
                tr_time = 0

            # Account for planetary object coordinates
            # TODO Test how the planetary selection is functioning
            if objec is None:
                transit_point = self.transit(map_points[i][0], map_points[i][1], step_incr[0], step_incr[1], tr_time)
            else:
                transit_point = self.transit_planetary(objec, step_incr[0], step_incr[1], tr_time)
            calc_points += "_%f_%f" % (transit_point[0], transit_point[1])  # Save the points as a string

        return [calc_points, (roc_ra, roc_dec, )]

    def coordinate_transform(self, coordinates: tuple, system_and_date: tuple):
        """
        Transform coordinates from other systems to celestial coordinates

        Args:
            coordinates (tuple):
            system_and_date (tuple):

        Returns:
        """
        position = np.radians(coordinates)  # Convert coordinates from degrees to radians
        if system_and_date[1] == "Now":
            epoch = self.current_time()  # Get the current time and date as the epoch
        else:
            epoch = system_and_date[1]
        self.observer.date = epoch

        if system_and_date[0] == "Horizontal":
            converted_ra, converted_dec = np.degrees(self.observer.radec_of(position[1], position[0]))
        elif system_and_date[0] == "Galactic":
            galactic_posit = ephem.Galactic(position[1], position[0], epoch=epoch)
            converted_ra, converted_dec = np.degrees(galactic_posit.to_radec())  # Convert from Galactic
        elif system_and_date[0] == "Ecliptic":
            ecliptic_position = ephem.Ecliptic(position[1], position[0], epoch=epoch)
            converted_ra, converted_dec = np.degrees(ecliptic_position.to_radec())  # Convert from Ecliptic coordinates
        else:
            converted_ra, converted_dec = coordinates

        return converted_ra, converted_dec  # Return the coordinate tuple

    def geo_sat_position(self, satellite: str):
        """


        Args:
            satellite (str): Name of the satellite

        Returns:
            np.array: Array containing the ra and dec of the satellite
        """
        # TODO improve the function
        try:
            # Get the filename
            url = self.cfg_data.get_tle_url()  # Get the URL from the settings file
            file_dir = os.path.abspath("TLE/" + url.split("/")[-1])  # Directory for the saved file

            tle_data = tlefile.read(satellite, file_dir)

            sat = ephem.readtle(tle_data.platform, tle_data.line1, tle_data.line2)
            self.observer.date = self.current_time()
            sat.compute(self.observer)

            c_time = self.current_time()  # Get the current time
            ha_sat = np.round(self.hour_angle(math.degrees(sat.ra), math.degrees(sat.dec), c_time), 4)  # Get the hour
            # angle of the satellite

            return np.array([np.round(np.degrees((sat.alt, sat.az,)), 4),
                             np.round((ha_sat, np.degrees(sat.dec),), 4)]).tolist()
        except KeyError:
            self.logger.exception("No satellite found. See traceback.")
