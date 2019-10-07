import network
import socket
import ure
import time

wlan_ap = network.WLAN(network.AP_IF)
wlan_sta = network.WLAN(network.STA_IF)
connect_timeout = 3

class WifiManager:
    server_socket = None
    profiles = None
    ap_config = None
    client = None

    def __init__(self, profiles, ap_config):
        self.profiles = profiles
        self.ap_config = ap_config

    def connect(self):
        """return a working WLAN(STA_IF) instance or None"""

        now = time.time()

        while now + connect_timeout < time.time():
            if wlan_sta.isconnected():
                return wlan_sta
            time.sleep(0.5)

        connected = False

        try:
            if wlan_sta.isconnected():
                return wlan_sta

            # Search WiFis in range
            wlan_sta.active(True)
            networks = wlan_sta.scan()

            AUTHMODE = {0: "open", 1: "WEP", 2: "WPA-PSK", 3: "WPA2-PSK", 4: "WPA/WPA2-PSK"}

            for ssid, bssid, channel, rssi, authmode, hidden in sorted(networks, key=lambda x: x[3], reverse=True):
                ssid = ssid.decode('utf-8')
                encrypted = authmode > 0
                print("ssid: %s chan: %d rssi: %d authmode: %s" % (ssid, channel, rssi, AUTHMODE.get(authmode, '?')))
                if encrypted:
                    if ssid in self.profiles:
                        password = self.profiles[ssid]
                        connected = self.do_connect(ssid, password)
                    else:
                        print("skipping unknown encrypted network")
                # else:  # open
                #     connected = self.do_connect(ssid, None)
                if connected:
                    break

        except OSError as e:
            print("exception", str(e))

        # start web server for connection manager:
        # if not connected:
        #     connected = self.start()

        return wlan_sta if connected else None


    def do_connect(self, ssid, password):
        wlan_sta.active(True)

        if wlan_sta.isconnected():
            return None

        print('Trying to connect to %s...' % ssid)
        wlan_sta.connect(ssid, password)

        for retry in range(100):
            connected = wlan_sta.isconnected()
            if connected:
                break
            time.sleep(0.1)
            print('.', end='')
        if connected:
            print('\nConnected. Network config: ', wlan_sta.ifconfig())
        else:
            print('\nFailed. Not Connected to: ' + ssid)
        return connected


    def send_header(self, status_code=200, content_length=None ):
        self.client.sendall("HTTP/1.0 {} OK\r\n".format(status_code))
        self.client.sendall("Content-Type: text/html\r\n")
        
        if content_length is not None:
            self.client.sendall("Content-Length: {}\r\n".format(content_length))
        
        self.client.sendall("\r\n")


    def send_response(self, payload, status_code=200):
        content_length = len(payload)
        
        self.send_header(status_code, content_length)
        
        if content_length > 0:
            self.client.sendall(payload)
        
        self.client.close()


    def handle_root(self):
        wlan_sta.active(True)
        ssids = sorted(ssid.decode('utf-8') for ssid, *_ in wlan_sta.scan())

        self.send_header()

        self.client.sendall("""\
            <html>
                <h1 style="color: #5e9ca0; text-align: center;">
                    <span style="color: #ff0000;">
                        Setup device
                    </span>
                </h1>
                <form action="configure" method="post">
                    <table style="margin-left: auto; margin-right: auto;">
                        <tbody>
                            <tr>
                                <th>WiFi name:</th>
                                <td>
                                    <select name="ssid">
        """)
        while len(ssids):
            ssid = ssids.pop(0)
            self.client.sendall("""\
                                        <option value="{0}">{0}</option>
            """.format(ssid))
        
        self.client.sendall("""\
                                    </select>
                                </td>
                            </tr>
                            <tr>
                                <th>Password:</th>
                                <td><input name="password" type="password" /></td>
                            </tr>
                        </tbody>
                    </table>
                    <p style="text-align: center;">
                        <input type="submit" value="Submit" />
                    </p>
                </form>
            </html>
        """) # % dict(filename=CONFIG_FILE))
        
        self.client.close()


    def handle_configure(self, request):
        match = ure.search("ssid=([^&]*)&password=(.*)", request)

        if match is None:
            self.send_response("Parameters not found", status_code=400)
            return False
        # version 1.9 compatibility
        try:
            ssid = match.group(1).decode("utf-8").replace("%3F", "?").replace("%21", "!")
            password = match.group(2).decode("utf-8").replace("%3F", "?").replace("%21", "!")
        except Exception:
            ssid = match.group(1).replace("%3F", "?").replace("%21", "!")
            password = match.group(2).replace("%3F", "?").replace("%21", "!")

        if len(ssid) == 0:
            self.send_response("SSID must be provided", status_code=400)
            return False

        if self.do_connect(ssid, password):
            response = """\
                <html>
                    <center>
                        <br><br>
                        <h1 style="color: #5e9ca0; text-align: center;">
                            <span style="color: #ff0000;">
                                Successfully setup device!.
                            </span>
                        </h1>
                        <br><br>
                    </center>
                </html>
            """ #% dict(ssid=ssid)
            self.send_response(response)

            self.profiles[ssid] = password
            # write_config(config)

            time.sleep(5)

            wlan_ap.active(False)

            return True
        else:
            response = """\
                <html>
                    <center>
                        <h1 style="color: #5e9ca0; text-align: center;">
                            <span style="color: #ff0000;">
                                Could not connect to WiFi network %(ssid)s.
                            </span>
                        </h1>
                        <br><br>
                        <form>
                            <input type="button" value="Go back!" onclick="history.back()"></input>
                        </form>
                    </center>
                </html>
            """ % dict(ssid=ssid)
            
            self.send_response(response)
            
            return False


    def handle_not_found(self, url):
        self.send_response("Path not found: {}".format(url), status_code=404)


    def stop(self):
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None


    def start(self, port=80):
        addr = socket.getaddrinfo('0.0.0.0', port)[0][-1]

        self.stop()

        wlan_sta.active(True)
        wlan_ap.active(True)

        wlan_ap.config(**self.ap_config)

        self.server_socket = socket.socket()
        self.server_socket.bind(addr)
        self.server_socket.listen(1)

        print('Connect to WiFi ssid ' + self.ap_config['essid'] + ', default password: ' + self.ap_config['password'])
        print('and access the ESP via your favorite web browser at 192.168.4.1.')
        print('Listening on:', addr)

        while True:
            if wlan_sta.isconnected():
                return wlan_sta

            self.client, addr = self.server_socket.accept()
            
            print('client connected from', addr)

            try:
                self.client.settimeout(5.0)

                request = b""
                try:
                    while "\r\n\r\n" not in request:
                        request += self.client.recv(512)
                except OSError:
                    pass

                print("Request is: {}".format(request))

                if "HTTP" not in request:  # skip invalid requests
                    continue

                # version 1.9 compatibility
                try:
                    url = ure.search("(?:GET|POST) /(.*?)(?:\\?.*?)? HTTP", request).group(1).decode("utf-8").rstrip("/")
                except Exception:
                    url = ure.search("(?:GET|POST) /(.*?)(?:\\?.*?)? HTTP", request).group(1).rstrip("/")
                print("URL is {}".format(url))

                if url == "":
                    self.handle_root()
                elif url == "configure":
                    self.handle_configure(request)
                else:
                    self.handle_not_found(url)

            finally:
                self.client.close()
