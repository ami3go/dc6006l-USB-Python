from __future__ import print_function, division
import serial
import os
import time
from timeit import default_timer as timer
import platform
import atexit
import operator
import threading


try:
    from pkg_resources import get_distribution, DistributionNotFound
    _dist = get_distribution('serial_interface')
    # Normalize case for Windows systems
    dist_loc = os.path.normcase(_dist.location)
    here = os.path.normcase(__file__)
    if not here.startswith(os.path.join(dist_loc, 'serial_interface')):
        # not installed, but there is another version that *is*
        raise DistributionNotFound
except (ImportError,DistributionNotFound):
    __version__ = None
else:
    __version__ = _dist.version

DEBUG = False

class WriteFrequencyError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)

class WriteError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)

class ReadError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)

class SerialInterface(serial.Serial):
    '''
    SerialInterface inherits from serial.Serial and adds methods to it,
    like auto discovery of available serial ports in Linux, Windows, and
    Mac OS X.

    Example Usage:

    dev = SerialInterface() # Might automatically find device if one available
    # if it is not found automatically, specify port directly
    dev = SerialInterface(port='/dev/ttyUSB0') # Linux
    dev = SerialInterface(port='/dev/tty.usbmodem262471') # Mac OS X
    dev = SerialInterface(port='COM3') # Windows
    dev.get_device_info()
    '''
    _TIMEOUT = 0.05
    _WRITE_TIMEOUT = 0.05
    _WRITE_READ_DELAY = 0.001
    _WRITE_WRITE_DELAY = 0.005
    _OPEN_CHARS = "([{"
    _CLOSE_CHARS = ")]}"

    def __init__(self, *args, **kwargs):
        try:
            self.debug = kwargs.pop('debug')
        except KeyError:
            self.debug = DEBUG
        try_ports = None
        if 'try_ports' in kwargs:
            try_ports = kwargs.pop('try_ports')
        try:
            self._write_read_delay = kwargs.pop('write_read_delay')
        except KeyError:
            self._write_read_delay = self._WRITE_READ_DELAY
        try:
            self._write_write_delay = kwargs.pop('write_write_delay')
        except KeyError:
            self._write_write_delay = self._WRITE_WRITE_DELAY
        try:
            self.device_name = kwargs.pop('device_name')
        except KeyError:
            self.device_name = ''

        if ('port' not in kwargs) or (kwargs['port'] is None):
            kwargs.update({'port': find_serial_interface_port(try_ports=try_ports,debug=self.debug)})
        if 'timeout' not in kwargs:
            kwargs.update({'timeout': self._TIMEOUT})
        if 'write_timeout' not in kwargs:
            kwargs.update({'write_timeout': self._WRITE_TIMEOUT})

        super(SerialInterface,self).__init__(*args,**kwargs)
        atexit.register(self._exit_serial_interface)

        # save write_data so it can be used for debugging
        self._write_data = None
        # save bytes_written so it can be used for debugging
        self._bytes_written = None
        # save read_data so it can be used for debugging
        self._read_data = None

        self._time_write_prev = timer()
        self._lock = threading.Lock()

    def _exit_serial_interface(self):
        '''
        Close the serial connection to provide some clean up.
        '''
        self.close()

    def _debug_print(self, *args):
        '''
        Prints debug info if self.debug == True.
        '''
        if self.debug:
            print(*args)

    def write_check_freq(self,write_data,delay_write=False,lock_=True):
        '''
        Use instead of self.write when you want to ensure that
        serial write commands do not happen too
        frequently. delay_write=True waits and then writes the serial
        data, delay_write=False raises WriteFrequencyError
        Exception if time between method calls is too short. Might
        remove delay_write option if it turns out to be
        unnecessary.
        '''
        time_now = timer()
        time_since_write_prev = time_now - self._time_write_prev
        if time_since_write_prev < self._write_write_delay:
            delay_time_needed = self._write_write_delay - time_since_write_prev
            if delay_write:
                time.sleep(delay_time_needed)
            else:
                raise WriteFrequencyError("Time between writes needs to be > {0}s".format(self._write_write_delay))
        bytes_written = 0
        if lock_:
            bytes_written = self._write_check_freq_locked(write_data,delay_write)
        else:
            bytes_written = self._write_check_freq_unlocked(write_data)
        self._debug_print('write_data:', write_data)
        self._debug_print('bytes_written:', bytes_written)
        return bytes_written

    def _write_check_freq_locked(self,write_data,blocking=True):
        bytes_written = 0
        lock_acquired = self._lock.acquire(blocking)
        if not lock_acquired:
            raise WriteFrequencyError("Time between writes needs to be larger.")
        try:
            bytes_written = self._write_check_freq_unlocked(write_data)
        finally:
            self._lock.release()

        return bytes_written

    def _write_check_freq_unlocked(self,write_data):
        self._write_data = None
        self._bytes_written = 0
        try:
            try:
                self._write_data = write_data.encode()
                self._bytes_written = self.write(write_data.encode())
            except (UnicodeDecodeError):
                self._write_data = write_data
                self._bytes_written = self.write(write_data)
            if self._bytes_written > 0:
                self._time_write_prev = timer()
        except (serial.SerialTimeoutException):
            self._write_data = None
            self._bytes_written = 0
        return self._bytes_written

    def write_read(self,write_data,use_readline=True,check_write_freq=False,max_read_attempts=100,delay_write=True,match_chars=False,size=None):
        '''
        A simple self.write followed by a self.readline with a
        delay set by write_read_delay when use_readline=True and
        check_write_freq=False. Setting check_write_freq=True ensures
        the write frequency is not too fast for the serial device to
        handle. Setting use_readline=False reads all data
        characters that are available instead of looking for the end
        of line character or timing out.

        max_read_attempts opens the possibility to read from the device again
        if the device did not have the data ready after the first read
        '''

        read_data = None
        lock_acquired = self._lock.acquire(delay_write)
        if not lock_acquired:
            raise WriteFrequencyError("Time between writes needs to be larger.")
        try:
            self._write_data = None
            self._bytes_written = 0
            if check_write_freq:
                self._bytes_written = self.write_check_freq(write_data,delay_write=delay_write,lock_=False)
            else:
                try:
                    self._write_data = write_data.encode()
                    self._bytes_written = self.write(write_data.encode())
                except (UnicodeDecodeError):
                    self._write_data = write_data
                    self._bytes_written = self.write(write_data)
            if self._bytes_written > 0:
                time.sleep(self._write_read_delay)
                read_data = self._read_with_retry(use_readline,max_read_attempts,match_chars,size)
                self._debug_print('read_data:', read_data)
            else:
                self._write_data = None
                raise WriteError("No bytes written.")
        finally:
            self._lock.release()
        return read_data

    def _read_with_retry(self,use_readline,max_read_attempts,match_chars,size):
        '''
        Reads data from the device.  If there is no data, try
        reading again.
        '''
        i = 0
        while i < max_read_attempts:
            i += 1
            read_data = self._read(use_readline,match_chars,size)
            if read_data:
                return read_data

            self._debug_print('no read_data -- retrying')
        if not read_data:
            raise ReadError("No read_data received.")
        else:
            return read_data

    def _read(self,use_readline,match_chars,size):
        '''
        Reads data from the device
        '''
        self._read_data = None
        if size is not None:
            self._read_data = self.read(size)
        elif match_chars:
            self._read_data = self._read_until_matching()
        elif use_readline:
            self._read_data = self.readline()
        else:
            chars_waiting = self.in_waiting
            self._debug_print('chars_waiting:', chars_waiting)
            self._read_data = self.read(chars_waiting)

        return self._read_data

    def _read_until_matching(self):
        open_char_count = 0
        close_char_count = 0
        line = bytearray()
        time_now = timer()
        time_prev = time_now
        while ((open_char_count == 0) or (close_char_count == 0) or (open_char_count != close_char_count)) and ((time_now-time_prev) <= self._TIMEOUT):
            c = self.read(1)
            time_now = timer()
            if c:
                if c in self._OPEN_CHARS:
                    open_char_count += 1
                elif c in self._CLOSE_CHARS:
                    close_char_count += 1
                line += c
                time_prev = time_now
        return bytes(line)

    def get_device_info(self):
        '''
        Returns device name and serial port.
        '''
        serial_interface_info = {'device_name' : self.device_name,
                                 'port' : self.port,
        }
        return serial_interface_info

    def check_write_freq(self,write_period_desired,write_data,delay_write=False):
        cycle_count = 100
        time_start = timer()
        time_prev = timer()
        for cycle_n in range(cycle_count):
            self.write_check_freq(write_data,delay_write)
            sleep_duration = write_period_desired - (timer() - time_prev)
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            time_prev = timer()
        time_stop = timer()
        write_period_actual = (time_stop - time_start)/cycle_count
        print('desired write period: {0}, actual write period: {1}'.format(write_period_desired,write_period_actual))

    def check_write_read_freq(self,write_period_desired,write_data,use_readline=True,check_write_freq=False,max_read_attempts=100,delay_write=True,match_chars=False):
        cycle_count = 100
        time_start = timer()
        time_prev = timer()
        read_data = ''
        for cycle_n in range(cycle_count):
            read_data = self.write_read(write_data,use_readline,check_write_freq,max_read_attempts,delay_write,match_chars)
            sleep_duration = write_period_desired - (timer() - time_prev)
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            time_prev = timer()
        time_stop = timer()
        write_period_actual = (time_stop - time_start)/cycle_count
        print('desired write read period: {0}, actual write read period: {1}'.format(write_period_desired,write_period_actual))
        print('read_data: {0}'.format(read_data))

# device_names example:
# [{'port':'/dev/ttyACM0',
#   'device_name':'port0'},
#  {'port':'/dev/ttyACM1',
#   'device_name':'port1'}]
class SerialInterfaces(list):
    '''
    SerialInterfaces inherits from list and automatically populates it
    with SerialInterfaces on all available serial ports.

    Example Usage:

    devs = SerialInterfaces()  # Might automatically find all available devices
    # if they are not found automatically, specify ports to use
    devs = SerialInterfaces(use_ports=['/dev/ttyUSB0','/dev/ttyUSB1']) # Linux
    devs = SerialInterfaces(use_ports=['/dev/tty.usbmodem262471','/dev/tty.usbmodem262472']) # Mac OS X
    devs = SerialInterfaces(use_ports=['COM3','COM4']) # Windows
    devs.get_devices_info()
    devs.sort_by_port()
    dev = devs[0]
    dev.get_device_info()
    '''

    def __init__(self,*args,**kwargs):
        debug = DEBUG
        if 'debug' in kwargs:
            debug = kwargs['debug']
        use_ports = None
        if 'use_ports' in kwargs:
            use_ports = kwargs.pop('use_ports')
        try_ports = None
        if 'try_ports' in kwargs:
            try_ports = kwargs.pop('try_ports')
        device_names = []
        if 'device_names' in kwargs:
            device_names = kwargs.pop('device_names')

        if use_ports is not None:
            serial_interface_ports = use_ports
        else:
            serial_interface_ports = find_serial_interface_ports(try_ports=try_ports,debug=debug)
        for port in serial_interface_ports:
            kwargs.update({'port': port})
            self.append_device(*args,**kwargs)

        self._update_device_names(device_names)

    def _update_device_names(self,device_names):
        for name_dict in device_names:
            device_name = name_dict.pop('device_name')
            for device_index in range(len(self)):
                dev = self[device_index]
                match = True
                for key in list(name_dict.keys()):
                    if name_dict[key] != getattr(dev,key):
                        match = False
                if match:
                    dev.device_name = str(device_name)

    def append_device(self,*args,**kwargs):
        '''
        Appends another SerialInterface.
        '''
        self.append(SerialInterface(*args,**kwargs))

    def get_devices_info(self):
        '''
        Get info for each SerialInterface.
        '''
        serial_interfaces_info = []
        for dev in self:
            serial_interfaces_info.append(dev.get_device_info())
        return serial_interfaces_info

    def sort_by_port(self,*args,**kwargs):
        '''
        Sort SerialInterfaces by port.
        '''
        kwargs['key'] = operator.attrgetter('port')
        self.sort(**kwargs)

    def get_by_port(self,port):
        '''
        Return a SerialInterface by port.
        '''
        for device_index in range(len(self)):
            dev = self[device_index]
            if dev.port == port:
                return dev

    def sort_by_device_name(self,*args,**kwargs):
        '''
        Sort SerialInterfaces by device names.
        '''
        kwargs['key'] = operator.attrgetter('device_name','port')
        self.sort(**kwargs)

    def get_by_device_name(self,device_name):
        '''
        Return a SerialInterface by its device name.
        '''
        dev_list = []
        for device_index in range(len(self)):
            dev = self[device_index]
            if dev.device_name == device_name:
                dev_list.append(dev)
        if len(dev_list) == 1:
            return dev_list[0]
        elif 1 < len(dev_list):
            return dev_list


# ----------------------------------------------------------------------------

def find_serial_interface_ports(try_ports=None, debug=DEBUG):
    '''
    Returns a list of all available serial ports.
    Linux: /dev/ttyUSB* or /dev/ttyACM* or /dev/*arduino*
    Mac OS X: /dev/tty.* or /dev/cu.*
    Windows: COM*
    '''
    serial_interface_ports = []
    os_type = platform.system()
    if os_type == 'Linux':
        serial_interface_ports = os.listdir('{0}dev'.format(os.path.sep))
        serial_interface_ports = [x for x in serial_interface_ports if 'ttyUSB' in x or 'ttyACM' in x or 'arduino' in x]
        serial_interface_ports = ['{0}dev{0}{1}'.format(os.path.sep,x) for x in serial_interface_ports]
    elif os_type == 'Windows':
        try:
            import winreg
        except ImportError:
            import _winreg as winreg
        import itertools

        path = 'HARDWARE\\DEVICEMAP\\SERIALCOMM'
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        except WindowsError:
            key = None

        if key is not None:
            for i in itertools.count():
                try:
                    val = winreg.EnumValue(key, i)
                    # Only return USBSER devices
                    if 'USBSER' in val[0]:
                        serial_interface_ports.append(str(val[1]))
                except EnvironmentError:
                    break
    elif os_type == 'Darwin':
        serial_interface_ports = os.listdir('{0}dev'.format(os.path.sep))
        serial_interface_ports = [x for x in serial_interface_ports if 'tty.' in x or 'cu.' in x]
        serial_interface_ports = ['{0}dev{0}{1}'.format(os.path.sep,x) for x in serial_interface_ports]

    if try_ports is not None:
        serial_interface_ports = list(set(try_ports) & set(serial_interface_ports))

    serial_interface_ports.sort()
    return serial_interface_ports

def find_serial_interface_port(try_ports=None, debug=DEBUG):
    '''
    Returns a serial port if one is available.
    '''
    serial_interface_ports = find_serial_interface_ports(try_ports)
    if len(serial_interface_ports) == 1:
        return serial_interface_ports[0]
    elif len(serial_interface_ports) == 0:
        raise RuntimeError('Could not find any serial devices. Check connections and permissions.')
    else:
        raise RuntimeError('Found more than one serial device. Specify port.\n' + str(serial_interface_ports))
