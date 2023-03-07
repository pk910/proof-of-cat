from utime import sleep, sleep_ms, ticks_ms
import utime as time
from sys import exit
import json
import random
import network
import uasyncio
import ubinascii
from wifi_connect import WiFiConnect
from web_server import Nanoweb
from entropy_lib import MAX_SIZE, TARGET_ENTROPY, add_entropy, measure_entropy
from components import init_rgb_led, init_i2c, init_battery, init_gyro, get_data
from machine import RTC, deepsleep, wake_reason, DEEPSLEEP, reset

DEBUG = False
LED_INTENSITY = 75
LED_LOW_INTENSITY = 5

MOVEMENT_ACCELERATION = 0.1
MOVEMENT_GYRODIFF = 0.5

print(f"MAX_SIZE: {MAX_SIZE}")
print(f"TARGET_ENTROPY: {TARGET_ENTROPY}")
print("-"*30)

led = init_rgb_led()
i2c = init_i2c()
mpu = init_gyro(i2c)
battery = init_battery(i2c)
rtc = RTC()
naw = Nanoweb()
wlan = network.WLAN(network.STA_IF)
wlan.active(False)
entropy_str = ""
last_gyro_data = (0, 0, 0)
idle_time = 0


def do_deepsleep(time):
    # persist state
    rtc.memory(f"{entropy_str}\n{last_gyro_data[0]}|{last_gyro_data[1]}|{last_gyro_data[2]}\n{idle_time}")
    
    led.show_led((0,0,0))
    sleep_ms(50)
    
    deepsleep(time)
    
def awake_deepsleep():
    global entropy_str, last_gyro_data, idle_time
    rtc_data = rtc.memory().decode("utf-8").split("\n")
    if len(rtc_data) != 3:
        return
    entropy_str = rtc_data[0]
    
    gyro_data = rtc_data[1].split("|")
    last_gyro_data = (float(gyro_data[0]), float(gyro_data[1]), float(gyro_data[2]))
    
    idle_time = int(rtc_data[2])
    
    print (f"restored state:")
    print (f"  entropy length: {len(entropy_str)}")
    print (f"  gyro data: {last_gyro_data[0]}, {last_gyro_data[1]}, {last_gyro_data[2]}")
    print (f"  idle time: {idle_time} ms")

def get_uptime():
    uptime_s = int(time.ticks_ms() / 1000)
    uptime_h = int(uptime_s / 3600)
    uptime_m = int(uptime_s / 60)
    uptime_m = uptime_m % 60
    uptime_s = uptime_s % 60
    return ('{:02d}h {:02d}m {:02d}z'.format(uptime_h, uptime_m, uptime_s))

def check_entropy():
    if len(entropy_str) > MAX_SIZE and measure_entropy(entropy_str) > TARGET_ENTROPY:
        return True
    return False

def check_movement(data):
    global last_gyro_data
    acceleration = (abs(data[3]), abs(data[4]), abs(data[5]))
    gyro_diff = (abs(data[0] - last_gyro_data[0]), abs(data[1] - last_gyro_data[1]), abs(data[2] - last_gyro_data[2]))
    #print("diff: ",gyro_diff[0],gyro_diff[1],gyro_diff[2], acceleration[0], acceleration[1], acceleration[2])
    
    # check acceleration > MOVEMENT_ACCELERATION
    if acceleration[0] > MOVEMENT_ACCELERATION or acceleration[1] > MOVEMENT_ACCELERATION or acceleration[2] > MOVEMENT_ACCELERATION:
        return True
    # check gyro difference > MOVEMENT_GYRODIFF
    if gyro_diff[0] > MOVEMENT_GYRODIFF or gyro_diff[1] > MOVEMENT_GYRODIFF or gyro_diff[2] > MOVEMENT_GYRODIFF:
        return True
    
    return False

def await_movement():
    global last_gyro_data, idle_time
    
    led.show_led((0,LED_LOW_INTENSITY,0))
    while True:
        data = get_data(mpu)
        if check_movement(data):
            break
        print("°",end="") # print ° for non-movement sensor poll
        
        last_gyro_data = (data[0], data[1], data[2])
        
        if idle_time > 330000: # no movements for 5:30 min ((5*60 + 30) * 1000)
            idle_time += 10000
            do_deepsleep(10000) # deep sleep the next 10 secs
            # deepsleep - execution stopped
        if idle_time > 90000: # no movements for 1:30 min ((1*60 + 30) * 1000)
            idle_time += 5000
            do_deepsleep(5000) # deep sleep the next 5 secs
            # deepsleep - execution stopped
        
        if idle_time > 30000: # no movements for 30 sec  (30 * 1000)
            idle_time += 1000
            sleep_ms(1000)
        else:
            idle_time += 500
            sleep_ms(500)
    
    led.show_led((0,LED_INTENSITY,0))
    idle_time = 0
    return data

def rng():
    global entropy_str, last_gyro_data, idle_time
    
    led.show_led((0,LED_INTENSITY,0))
    i=0
    
    if not check_entropy():
        while True:
            sample_period = int(random.uniform(500, 1100)) 
            sleep_ms(sample_period)
            data = get_data(mpu)
            if not check_movement(data):
                print("°",end="") # print ° for non-movement sensor poll
                led.show_led((0,LED_LOW_INTENSITY,0))
                idle_time += sample_period
                if idle_time > 5000:
                    data = await_movement()
            else:
                print(".",end="") # print . for valid sensor poll
                led.show_led((0,LED_INTENSITY,0))
                idle_time = 0
            last_gyro_data = (data[0], data[1], data[2])
            
            entropy_str = add_entropy(mpu, entropy_str, data)
            i+=1
            if i % 10 == 0:
                print("")
                print("Current entropy: {} bits".format(measure_entropy(entropy_str)))
                print("Current lenght:", len(entropy_str))
            if check_entropy():
                break
        print("")
    else:
        for i in range(4):
            sample_period = int(random.uniform(100, 400))
            sleep_ms(sample_period)
            data = get_data(mpu)
            entropy_str = add_entropy(mpu, entropy_str, data)
        print("Current entropy: {} bits".format(measure_entropy(entropy_str)))
        print("Current lenght:", len(entropy_str))
    return entropy_str

def connect_wifi():
    if not wlan.isconnected():
        print("Connecting wifi")
        try:
            net = WiFiConnect(retries=20)
            wc = net.connect()
            sleep(2)
            ip_addr = net.ifconfig()[0]
            if ip_addr == "0.0.0.0":
                led.show_led((LED_INTENSITY,0,0))
                print("The wifi doesn't seem not be connected corretly, please check your settings and run the program again.")
                return False
            else:
                print("IP address:",ip_addr)
                led.show_led((0,LED_INTENSITY,0))
                return True
        except:
            print("The wifi did not connect, please check your settings and run the program again.")
            led.show_led((LED_INTENSITY,0,0))
            return False


# init code
wake_reason = wake_reason()
if wake_reason == DEEPSLEEP:
    print ("Resume Catropy")
    led.show_led((LED_LOW_INTENSITY,LED_LOW_INTENSITY,0))
    sleep_ms(50)
    led.show_led((LED_LOW_INTENSITY,0,0))
    
    # restore persisted state
    awake_deepsleep()
    
    # check movement or go back to deepsleep
    await_movement()
else:
    print("Starting Catropy")
    
    # blink to indicate startup :)
    for i in range(10):
        led.show_led((LED_INTENSITY,0,0))
        sleep_ms(100)
        led.show_led((0,LED_INTENSITY,0))
        sleep_ms(100)
    
    led.show_led((LED_LOW_INTENSITY,0,0))

#print(f"Battery Status: VCELL: {battery.vcell}, SOC: {battery.soc}, CRATE: {battery.crate}")
print("Starting randomness generation")
rng()
print("Initial entropy gathered, starting API")

@naw.route("/status")
async def status(request):
    await request.write("HTTP/1.1 200 OK\r\n")
    await request.write("Content-Type: application/json\r\n\r\n")
    uptime_str = get_uptime()
    shannon=measure_entropy(entropy_str)
    bits = len(entropy_str) * 4
    await request.write(json.dumps({
        "uptime": uptime_str,
        "Shannon entropy": shannon,
        "lenght": bits}))

@naw.route("/")
def entropy(request):
    await request.write("HTTP/1.1 200 OK\r\n\r\n")
    random = ubinascii.b2a_base64(rng())
    await request.write(json.dumps({
        "": random}))

@naw.route("/reboot")
def entropy(request):
    await request.write("HTTP/1.1 200 OK\r\n\r\n")
    await request.write("reboot")
    sleep_ms(1000)
    reset()
    
@naw.route("/battery")
async def status(request):
    await request.write("HTTP/1.1 200 OK\r\n")
    await request.write("Content-Type: application/json\r\n\r\n")
    
    await request.write(json.dumps({
        "vcell": battery.vcell,
        "crate": battery.crate,
        "soc": battery.soc}))

loop = uasyncio.get_event_loop()
if DEBUG:
    print("Starting webserver")

led.show_led((0,0,LED_LOW_INTENSITY))
wlan.active(True)
while True:
    
    if connect_wifi():
        break
    elif wlan.isconnected():
        wlan.disconnect()
    
    sleep(2)
    led.show_led((LED_INTENSITY,0,LED_INTENSITY))
    sleep_ms(100)
    print("Retry WiFi connect")

print("Start webserver")
led.show_led((0,0,LED_INTENSITY))
loop.create_task(naw.run())
loop.run_forever()
