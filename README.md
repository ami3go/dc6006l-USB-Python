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

**N** - output ON

**F** - output off
 
**Q** - start reporting
**W** - close reporting

When you send "Q" it starts periodic message from power supply
**periodic message:**

0199A 0700A 0139A 0A 029A 0A 0A 1A - on 
0000A 0000A 0000A 0A 029A 0A 0A 0A - off
0000A 0000A 0000A 0A 029A 0A 2A 0A - short Circuit 
0058A 0098A 0005A 0A 028A 1A 0A 1A - current limit ON ()
Periodic mesage format 
0199A 0700A 0139A 0A 029A 0A 0A 1A
[voltage,{V/100}: 1.99]A [ampere{A/1000}:0.700]A [watt{W/10}:1.39W]A [unknown] 0A [temp:029deg] [CC/CV=0]0A [error type]0A [on/0ff:1]A
**Error type:**
0 - OK - non errors
1 - OV - Over voltage protection
2-  OC - over current protection
3 - OT - over time protection

CC/CV - sourse type mode:
CC - constant current mode [CC/CV = 0]
CV - constant voltage mode [CC/CV = 1]



