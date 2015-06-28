import time
import uart
import elm327
from obd import commands
from obd import sensors
from response import Response


class OBDScanner(object):
    """
        ELM327 OBD-II Scanner

        Information about OBD-II PIDs
        http://en.wikipedia.org/wiki/OBD-II_PIDs

        Additional details about EML327 OBD <-> RS232 found here:
        http://elmelectronics.com/DSheets/ELM327DS.pdf
    """

    def __init__(self, pb_str, baud=uart.DEFAULT_BAUDRATE, units=0):
        """
            Init params
            :param pb_str: port or bus number|name
            :param baud: it is the clock rate
            :param units: default units for system readings (0 - Europe, 1 - English)
        """
        self.pb_str = pb_str
        self.baud = baud
        self.uart_port = None
        self.elm_version = ""
        self.obd_protocol = ""
        self.units = units
        # Time to wait (in seconds) before attempting to receive data after an
        # OBD command has been issued
        self.receive_wait_time = 0.5
        self.success = "OK"
        self.sensor = None
        # it does prove that the connection with a vehicle is working
        self.__connected = False

    def connect(self):
        """
            Opens a connection to an ELM327 OBD-II Interface
            :return:
        """
        self.uart_port = uart.UART().connection(self.pb_str, baudrate=self.baud)

        if self.is_port():
            self.initialize()

    def is_port(self):
        """ Returns a boolean for whether a successful connection with port was made """
        return self.uart_port is not None

    def __enter__(self):
        """
            Sets up the OBDScanner to work as a ContextManager
            :return: this OBDScanner instance for use within the context
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def battery_voltage(self):
        """
            Reads the vehicle's battery voltage from a connected OBD-II Scanner
            :return: the battery voltage returned by the OBD-II Scanner
        """
        return self.send(elm327.BATTERY_VOLTAGE_COMMAND)

    def disconnect(self):
        """
            Disconnect from a connected OBD-II Scanner
            :return:
        """
        if self.is_port():
            self.reset()
            self.uart_port.close()
        self.__connected = None
        self.elm_version = ""

    def initialize(self):
        """
            Initialize the OBD-II Scanner state after connecting
            :return:
        """
        self.reset()
        if not self._check_response(self.echo_off()):
            # logging error
            raise Exception("ATE0 did not return success")
        if not self._check_response(self.send(elm327.SET_PROTOCOL_AUTO_COMMAND).raw_value):
            # logging error
            raise Exception("Set protocol command did not return success")

        self.obd_protocol = self.send(elm327.DESCRIBE_PROTOCOL_COMMAND).value
        self.sensor = sensors.Command(self.send, self.units)

        # checks connection with vehicle
        self.__connected = self.sensor.check_pids()

        if not self.__connected:
            raise Exception("Failed connection!")

    def receive(self):
        """
            Receive data from connected OBD-II Scanner
            :return: the data returned by the OBD-II Scanner
        """
        if self.is_port():
            retry_number = 0
            value = b''
            while True:
                data = self.uart_port.read(1)

                if data == b'>':
                    break

                # ignore incoming bytes that are of value 00 (NULL)
                if data == b'\x00':
                    continue

                if len(data) == 0:
                    if retry_number >= elm327.DEFAULT_RETRIES:
                        break
                    retry_number += 1
                    continue

                value += data

            if value:
                return Response(value)
        else:
            # logging warning
            raise Exception("Cannot read when unconnected")

        return Response()

    def reset(self):
        """
            Reset the OBD-II Scanner
            :return:
        """
        if self.is_port():
            self.send(elm327.RESET_COMMAND, 1)
            self.elm_version = self.receive()

    def send(self, data, delay=None):
        """
            Send data/command to the connected OBD-II Scanner
            :param data: the data/command to send to the connected OBD-II
            scanner
            :param delay: the delay between write and read, in sec
            :return the data returned by the OBD-II Scanner
        """
        if self.is_port():
            self._write(data)

        # Wait for data to become available
        if delay:
            time.sleep(delay)

        return self.receive()

    def vehicle_id_number(self):
        """
            Returns the vehicle's identification number (VIN)
            :return:
        """
        return self.send(commands.VEHICLE_ID_NUMBER_COMMAND)

    def clear_trouble_codes(self):
        """
            Uses OBD Mode 04 to clear trouble codes and the malfunction
            indicator lamp (MIL) / check engine light
            :return:
        """
        if not self._check_response(self.send(commands.CLEAR_TROUBLE_CODES_COMMAND)):
            # logging error
            print("Clear trouble codes did not return success")

    def echo_off(self):
        """
            Turns ECHO OFF for the OBD-II Scanner
            :return response data
        """
        return self.send(elm327.ECHO_OFF_COMMAND).raw_value

    def _check_response(self, data):
        """
            Checks the common command
        """
        return self.success in data

    def _write(self, data):
        """
            Send data/command to the connected OBD-II Scanner
            :param data: the data/command to send to the connected OBD-II
            scanner
            :return:
        """
        self.uart_port.flushOutput()
        self.uart_port.flushInput()
        self.uart_port.write(data + "\r")