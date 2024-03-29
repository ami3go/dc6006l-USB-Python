# Power supply link: http://www.fnirsi.cn/productinfo/556155.html
# Library was created by sniffing serial connunication with logic analyzer.
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE
#
# Author GitHub: ami3go
#        email: alexandr.chasnyk@gmail.com
#
#

import serial.tools.list_ports
import serial
import time

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def range_check(val, min, max, val_name):
    if val > max:
        print(f"Wrong {val_name}: {val}. Max output should be less then {max} V")
        val = max
    if val < min:
        print(f"Wrong {val_name}: {val}. Should be >= {min}")
        val = min
    return val


class dc6006l_class:
    def __init__(self):
        self.ser = None

    def init(self, com_port):
        com_port_list = [comport.device for comport in serial.tools.list_ports.comports()]
        if com_port not in com_port_list:
            print("COM port connected")
            print("Please ensure that USB is connected")
            print(f"Please check COM port Number. Currently it is {com_port} ")
            print(f'Founded COM ports:{com_port_list}')
            return False
        else:
            self.ser = serial.Serial(
                port=com_port,
                baudrate=115200,
                timeout=0.1
            )
            if not self.ser.isOpen():
                self.ser.open()
            # tmp = self.ser.isOpen()
            # print("is open:", tmp)
            # return_value = self.get_status()
            return True

    def close(self):
        self.ser.close()
        self.ser = None

    def send(self, cmd_str):
        self.ser.reset_output_buffer()
        time.sleep(0.1)
        txt = f'{cmd_str}\r\n'
        self.ser.write(txt.encode())

    def query(self, n_bytes, cmd_str=None):
        if cmd_str != None:
            self.ser.reset_output_buffer()
            txt = f'{cmd_str}\r\n'
            self.ser.reset_input_buffer()
            self.ser.write(txt.encode())
            time.sleep(0.15)
        read_back = self.ser.read(n_bytes).decode()
        return read_back

    def set_v_out(self, voltage):
        voltage = range_check(voltage, 0, 60, "voltage")
        val = int(round((voltage * 100),1))
        txt = f'V{str(val).zfill(4)}'
        n_bytes = 10
        read_back = self.query(n_bytes, txt)
        #print(read_back)
        if len(read_back) == 10 and read_back[4] == "A" and read_back[9] == "A":
            z = read_back.split("A")
            v_out = int(z[0]) / 100
            i_out = int(z[1]) / 1000
            if voltage == v_out:
                # print(f" V: {v_out} I: {i_out}, OK")
                return True
            else:
                if abs(v_out - voltage) > 0.1:
                    print("Something wrong while setting voltage. Set and read back value mismatch")
                    print(f" Vset: {voltage} Vget: {v_out}, Iget: {i_out}")
                    return False
                else:
                    return True


    def set_i_out(self, current):
        current = range_check(current, 0, 6, "current")
        current = round(current, 5)
        val = int(current * 1000)
        txt = f'I{str(val).zfill(4)}'
        n_bytes = 10
        read_back = self.query(n_bytes, txt)
        if len(read_back) == 10:
            z = read_back.split("A")
            v_out = int(z[0]) / 100
            i_out = int(z[1]) / 1000
            if current == i_out:
                # print(f" V: {v_out} I: {i_out}, OK")
                return True
            else:
                print("Something wrong while setting current. Set and read back value mismatch")
                print(f" Iset: {current} Vget: {v_out}, Iget: {i_out}, val: {val}, txt: {txt}")
                return False


    def __output_enable_p(self):
        array_state = None
        self.send("N")
        state = self.get_state()
        return state["Output"] # return off_on variable of array_status

    def output_enable(self):
        j = 0
        while (j < 4):
            j += 1
            if (self.__output_enable_p() == 1):
                return True
            else:
                time.sleep(0.3)

    def __output_disable_p(self):
        self.ser.reset_output_buffer()
        self.ser.write("F\r\n".encode())
        array_state = self.get_state()
        return array_state  # return off_on variable of array_status

    def output_disable(self):
        j = 0
        while (j < 4):
            j += 1
            state = self.__output_disable_p()
            # print(state)
            if state != None:
                if state["Output"] == 0:
                    return True
            else:
                time.sleep(0.3)
        return False

    def get_status(self, var_name="none"):
        replay_len = 66
        self.disable_state_reporting()
        time.sleep(0.1)
        self.enable_state_reporting()
        txt = self.query(replay_len, None)
        # i=0
        # while i < 4:
        #     i = i + 1
        #     txt = self.query(replay_len, None)
        #     print(f"i:{i} get state: {txt}")
        #     if txt == "":
        #         # self.ser.reset_input_buffer()
        #         time.sleep(0.05)
        #     else:
        #         # ret_val = None
        #         if len(txt) == replay_len:
        #             if ((txt[4] == "A") and
        #                     (txt[9] == "A") and (txt[14] == "A") and
        #                     (txt[16] == "A") and (txt[20] == "A") and
        #                     (txt[22] == "A")):
        #                 print(txt)
        #                 z = txt.split("A")
        #                 v_out = int(z[0]) / 100
        #                 i_out = int(z[1]) / 1000
        #                 p_out = int(z[2]) / 100
        #                 p1 = int(z[3])
        #                 temp = int(z[4])
        #                 cv_cc = int(z[5])
        #                 error = int(z[6])
        #                 off_on = int(z[7])
        #                 status["Vout"] = v_out
        #                 status["Iout"] = i_out
        #                 status["Pout"] = p_out
        #                 status["P1"] = p1
        #                 status["Temp"] = temp
        #                 status["CV_CC"] = cv_cc
        #                 status["Error"] = error
        #                 status["Output"] = off_on
        #                 ret_val = [v_out, i_out, p_out, p1, temp, cv_cc, error, off_on]
        #                 # return ret_val
        #                 return  status
        #                 break
        # return None


        if txt.find("KB") != -1:
            self.disable_state_reporting()
            time.sleep(0.5)
            self.enable_state_reporting()
            time.sleep(0.1)
            txt = self.query(66, None)

        if txt.find("KB") == -1:
            print(f"Get_status. Wrong replay on COM: {txt}")
            print("Please check the COM port number")
            # self.ser.close()
            return False
        else:
            # print(f"get_status: {txt}")
            txt = txt.replace("KB","0",1)

            z = txt.split('A')
            # print(f"get_status: {z}")
            # decode first replay string.
            # there is no input voltage ??
            v_out = int(z[0]) / 100
            i_out = int(z[1]) / 1000
            p_out = int(z[2]) / 100
            p1 = int(z[3])
            temp = int(z[4])
            cv_cc = int(z[5])
            limit_error = int(z[6])
            on_off = int(z[7])
            v_set = int(z[8]) / 100
            i_set = int(z[9]) / 1000
            v_lim = int(z[10]) / 100
            i_lim = int(z[11]) / 1000
            p_lim = int(z[12]) / 100
            tout_en = int(z[13])
            tout_hh = int(z[14])
            tout_mm = int(z[15])
            tout_ss = int(z[16])



            # v_out = int(txt[2:6]) / 100
            # i_out = int(txt[7:11]) / 1000
            # p_out = int(txt[13:16]) / 100
            # p1 = int(txt[17:18])
            # temp = int(txt[19:22])
            # cv_cc = int(txt[23:24])
            # limit_error = int(txt[25:26])
            # on_off = int(txt[27:28])
            # v_set = int(txt[29:33]) / 100
            # i_set = int(txt[34:38]) / 1000
            # v_lim = int(txt[39:43]) / 100
            # i_lim = int(txt[44:48]) / 1000
            # p_lim = int(txt[49:54]) / 100
            # tout_en = int(txt[55:56])
            # tout_hh = int(txt[57:59])
            # tout_mm = int(txt[60:62])
            # tout_ss = int(txt[63:65])
            status = {
                "v_out": v_out,
                "i_out": i_out,
                "p_out": p_out,
                "temp": temp,
                "cv_cc": cv_cc,
                "limit_error": limit_error,
                "on_off": on_off,
                "v_set": v_set,
                "i_set": i_set,
                "v_lim": v_lim,
                "i_lim": i_lim,
                "p_lim": p_lim,
                "timeout_en": tout_en,
                "timeout_hh": tout_hh,
                "timeout_mm": tout_mm,
                "timeout_ss": tout_ss
            }
            if var_name == "none":
                return status
            else:
                return status[var_name]

    def set_volt_protect(self, voltage):
        if voltage > 61:
            print(f"Wrong voltage: {voltage} V. Max output should be less then 61 V")
            voltage = 61
        if voltage < 0.2:
            print(f"Wrong voltage: {voltage} V. Should be >= 0.2")
            voltage = 0.2
        val = int(voltage * 100)
        txt = f'B{str(val).zfill(4)}\r\n'
        # print for debug
        # print(txt)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(txt.encode())
        read_back = self.ser.read(27).decode()
        if len(read_back) == 27:
            v_lim = int(txt[0:4]) / 100
            i_lim = int(txt[5:9]) / 1000
            p_lim = int(txt[10:14]) / 100
            if voltage == v_out:
                # print(f" V: {v_out} I: {i_out}, OK")
                return True
            else:
                print("Something wrong while setting voltage. Set and read back value mismatch")
                return False

    def set_current_protect(self, current):
        current = range_check(current, 0, 6, "current")
        val = int(current * 1000)
        txt = f'D{str(val).zfill(4)}\r\n'
        # print for debug
        # print(txt)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(txt.encode())
        read_back = self.ser.read(27).decode()
        if len(read_back) == 27:
            v_lim = int(txt[0:4]) / 100
            i_lim = int(txt[5:9]) / 1000
            p_lim = int(txt[10:14]) / 100
            if voltage == v_out:
                # print(f" V: {v_out} I: {i_out}, OK")
                return True
            else:
                print("Something wrong while setting voltage. Set and read back value mismatch")
                return False

    def enable_state_reporting(self):
        self.send("Q")

    def disable_state_reporting(self):
        self.send("W")

    def get_state(self):
        ostate = {}
        ret_val = None
        replay_len = 27
        i = 0
        while i < 5:
            i = i + 1
            txt = self.query(replay_len, None)
            # print(f"i:{i} get state: {txt}")
            if txt == "":
                # self.ser.reset_input_buffer()
                time.sleep(0.05)
            else:
                #ret_val = None
                if len(txt) == replay_len:
                    if ((txt[4] == "A") and
                            (txt[9] == "A") and (txt[14] == "A") and
                            (txt[16] == "A") and (txt[20] == "A") and
                            (txt[22] == "A")):
                        # print(txt)
                        z = txt.split("A")
                        v_out = int(z[0]) / 100
                        i_out = int(z[1]) / 1000
                        p_out = int(z[2]) / 100
                        p1 = int(z[3])
                        temp = int(z[4])
                        cv_cc = int(z[5])
                        error = int(z[6])
                        off_on = int(z[7])
                        ostate["Vout"] = v_out
                        ostate["Iout"] = i_out
                        ostate["Pout"] = p_out
                        ostate["P1"] = p1
                        ostate["Temp"] = temp
                        ostate["CV_CC"] = cv_cc
                        ostate["Error"] = error
                        ostate["Output"] = off_on

                        # ret_val = [v_out, i_out, p_out, p1, temp, cv_cc, error, off_on]
                        ret_val = ostate
                        break
        return ret_val
