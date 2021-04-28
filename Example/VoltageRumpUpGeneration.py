# example of using dc6006l class control.


import src.dc6006l_class as ps
#import dc6006l_class as ps
import time

if __name__ == "__main__":

    power = ps.dc6006l_class()
    result = power.init("COM5")
    power.get_status()
    power.enable_state_reporting()
    power.disable_state_reporting()
    power.enable_state_reporting()
    power.output_disable()
    power.set_v_out(0.01)
    power.output_enable()

    vout = 0.00
    voltage_step = 0.1
    Vout_high = 6
    Vout_low = 3
    vout = Vout_low
    Nreps = 10
    step_delay = 0.5
    for x in range(0,Nreps ):
        for v in range(round((Vout_high-Vout_low)/voltage_step)):
            power.set_v_out(vout)
            power.set_i_out(vout/100 +0.5)
            time.sleep(step_delay)
            state = power.get_state()
            print(f"Vout: {vout} State: {state}")
            vout = round((vout + voltage_step),3)# function round should be used beca
        for v in range(round((Vout_high-Vout_low)/voltage_step)):
            power.set_v_out(vout)
            power.set_i_out(vout / 100 + 0.5 )
            time.sleep(step_delay)
            state = power.get_state()
            print(f"Vout: {vout} State: {state}")
            vout = round((vout - voltage_step), 3)

    power.output_disable()
    power.close()