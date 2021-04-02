

import sys
#need this string to be able import the lib from /src folder
#otherwise put  dc6006l_class.py at root of your project
sys.path.append('../src')
import dc6006l_class as ps
import time

if __name__ == "__main__":

    power = ps.dc6006l_class()
    result = power.init("COM5")
    power.get_status()
    power.output_enable()
    power.set_v_out(13.55)
    for v in range(10000):
        time.sleep(1)
        state = power.get_state()
        print(f"Current:{state[1]}, Voltage: {state[0]}")
        current = state[1]
        if current == 0:
            print(f"ps restart")
            power.output_disable()
            time.sleep(5)
            power.output_enable()

    power.output_disable()
    power.close()