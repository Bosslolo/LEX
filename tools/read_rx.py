import serial
import time

s = serial.Serial("COM5", 115200, timeout=0.4)
time.sleep(0.2)
s.dtr = False
s.rts = True
time.sleep(0.08)
s.rts = False
s.dtr = True
end = time.time() + 6
while time.time() < end:
    line = s.readline().decode("utf-8", "ignore").strip()
    if line:
        print(line)
s.close()
