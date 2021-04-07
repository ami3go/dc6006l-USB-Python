# example of using dc6006l class control.


import src.dc6006l_class as ps
#import dc6006l_class as ps
import time

if __name__ == "__main__":

    power = ps.dc6006l_class()
    result = power.init("COM4")
    power.get_status()
    power.enable_state_reporting()
    power.output_disable()
    power.set_v_out(0.01)
    power.output_enable()

    vout = 0.00
    voltage_step = 0.05
    Vout_high = 5
    Nreps = 10
    on_pulse_width = 1
    off_pulse_width = 1
    power.set_v_out(Vout_high)
    for x in range(0, Nreps):
        power.output_enable()
        time.sleep(on_pulse_width)
        print(f"Vout: {vout} State: {power.get_state()}")

        power.output_disable()
        time.sleep(off_pulse_width)
        print(f"Vout: {vout} State: {power.get_state()}")


    power.output_disable()
    power.close()