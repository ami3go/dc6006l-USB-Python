# DC6006L control library

 ## A python library for controling affordable power supply FNIRSI DC6006L via front usb connector
 Power supply link: http://www.fnirsi.cn/productinfo/556155.html
 

 Unfortunately FNIRSI did not share any information on how to work with serial connunication. 
 Library was created by sniffing serial communication with logic analyzer. 
 
 
 !Warning:
 Firmware for PS is immature. 
 Bug identified so far:
 
 
 13.04.2021
 - incorrect voltage set. for example, you sent 0.7V while power supply could sent 7V or 70 V =)
   !Please use over-voltage protection when working power supply and usb interface.!
 
 ## Dependency:
 
      import serial
      import time
      import serial.tools.list_ports

 **When you repost or share any information form this page please attach reference to this page**
 
  ## Function list:
 
**.init(com_port)** - initialization for power supply  

**.close()** - close serial port.

**.set_v_out(voltage)** - setting voltage 

**.set_v_out_retry(voltage)** - setting voltage, waiting for replay to confirm, if not retry to set same value

**.set_i_out(current)** - setting current 

**.set_i_out_retry(current)** - setting current, waiting for replay to confirm, if not retry to set same value

**.output_enable()**

**.output_disable()**

**.get_status(var_name)** - if var_name = none or empty, a list of all variable would be returned. 
                          - if var_name = "specific_name" -  only specific var value vould be returned 
         
                "v_out": v_out,
                "i_out": i_out,
                "p_out": p_out,
                "temp":  temp,
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
                
**.set_volt_protect(voltage)**

**.enable_state_reporting()**

**.get_state()** - ret_val = [v_out,i_out,p_out,p1,temp,cv_cc,error,off_on]


Full command lis












