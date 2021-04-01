# dc6006l_control
 ## A python lib to control power supply FNIRSI dc6006l via front usb connector
 Power supply link: http://www.fnirsi.cn/productinfo/556155.html
 
 Unfortunatelly FNIRSI did not share any information on how to work with serial connunication. 
 Library was created by sniffing serial connunication with logic analyzer. 
 
 **When you repost or share any information form this page please attach reference to this page**
 ## Command list: 
**[cmd]+CR+LF** general command format
 
**V0100** - {mV*10}set 1 V (V1000 set 10V)
 
**I0500** - {mA}set  0500mA current limit

**B0500** - {mV*10} set voltage protection to 5V

**D0500** - {mA}set  0500mA voltage protection

**E0200** - {W/10} 20W power protection

**H01** - [hours] time protection

**M20** -  {min} time protection

**S20** - {sec} time protection

**X** - enable time protection

**Y** - disable time protection

**N** - Output ON

**F** - Output off
 
