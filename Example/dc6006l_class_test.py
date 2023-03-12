# example of using dc6006l class control.


import src.dc6006l_class as ps
#import dc6006l_class as ps
import time

if __name__ == "__main__":

    power = ps.dc6006l_class()
    result = power.init("/dev/ttyUSB0")
    power.get_status()
    power.enable_state_reporting()
    power.output_disable()
    power.set_v_out(200/100)
    power.output_enable()
    for v in range(10000):
        time.sleep(1)
        state = power.get_state()
        print(f"State: {state}")
        if state != None:
            print(f"Current:{state[1]}, Voltage: {state[0]}")
            current = state[1]
            if current == 0:
                print(f"ps restart")
                power.output_disable()
                time.sleep(5)
                power.output_enable()

    power.output_disable()
    power.close()