# example of using dc6006l class control.


import src.dc6006l_class as ps
#import dc6006l_class as ps
import time

if __name__ == "__main__":

    power = ps.dc6006l_class()
    result = power.init("COM5")
    power.get_status()
    power.enable_state_reporting()
    power.output_enable()
    power.set_v_out2(10)

    power.output_disable()
    power.close()