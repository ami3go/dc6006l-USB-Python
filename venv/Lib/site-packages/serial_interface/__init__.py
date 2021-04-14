'''
This Python package (serial_interface) creates a class named SerialInterface,
which inherits from serial.Serial and adds methods to it, like auto
discovery of available serial ports in Linux, Windows, and Mac OS X. The
SerialInterface class can be used by itself, but it is mostly intended to
be a base class for other serial port devices with higher level
functions. SerialInterfaces creates a list of SerialInterface
instances from all available serial ports.
'''
from .serial_interface import SerialInterface, SerialInterfaces, find_serial_interface_ports, find_serial_interface_port, WriteFrequencyError, WriteError, ReadError, __version__
