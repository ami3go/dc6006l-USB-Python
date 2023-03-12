# example of using dc6006l class control.


import src.dc6006l_class as ps
#import dc6006l_class as ps
import time





if __name__ == "__main__":
    #variables
    Vout_high = 5  # voltage of high level, here 5V
    Nreps = 10
    on_pulse_width = 0.5  # time in second
    off_pulse_width = 0.8  # time in seconds



    power = ps.dc6006l_class()
    # result = power.init("COM4")
    result = power.init('/dev/ttyUSB0')  # linux variant
    power.get_status()
    power.enable_state_reporting()
    power.output_disable()
    power.set_v_out(Vout_high)
    power.output_enable()



    power.set_v_out(Vout_high)
    for x in range(0, Nreps):
        power.output_enable()
        time.sleep(on_pulse_width)
        print(f" OnTime:{on_pulse_width} s, State: {power.get_state()}")

        power.output_disable()
        time.sleep(off_pulse_width)
        print(f"OffTime:{off_pulse_width} s, State: {power.get_state()}")


    power.output_disable()
    power.close()