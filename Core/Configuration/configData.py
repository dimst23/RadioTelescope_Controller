import xml.etree.ElementTree as etree
import logging


class confData(object):
    # Class constructor
    def __init__(self, filename):
        self.filename = filename  # Create a variable with the given filename
        self.log = logging.getLogger(__name__)  # Create the logger for this module
        try:
            self.tree = etree.parse(self.filename)  # Try to parse the given file
            self.root = self.tree.getroot()  # Get the root from the XML file
        except Exception:
            self.log.exception("There is an issue with the XML settings file. See traceback below.")

    def parse(self):
        try:
            self.tree = etree.parse(self.filename)  # Try to parse the given file
            self.root = self.tree.getroot()  # Get the root from the XML file
        except Exception:
            self.log.exception("There is an issue with the XML settings file. See traceback below.")

    def getConfig(self, child, subchild):
        children = list(self.root.find(child))
        for item in children:
            if item.tag == subchild:
                return item.text
            else:
                continue

    def setConfig(self, element, child, value):
        elm = self.root.find(element)  # Get the required element from the tree
        children = list(elm)  # List the children of the element
        for item in children:
            if item.tag == child:
                item.text = value
                self.tree.write(self.filename)
                break
            else:
                continue

    def getMapsSelect(self):
        return self.root.find("location").get("gmaps")

    def setMapsSelect(self, stat):
        self.root.find("location").set("gmaps", stat)
        self.tree.write(self.filename)

    def getServRemote(self, element):
        return self.root.find(element).get("remote")

    def setServRemote(self, element, status):
        self.root.find(element).set("remote", status)
        self.tree.write(self.filename)

    def getLatLon(self):
        lat = self.getConfig("location", "latitude")
        lon = self.getConfig("location", "longitude")
        return [lat, lon]

    def setLatLon(self, location):
        self.setConfig("location", "latitude", str(location[0]))
        self.setConfig("location", "longitude", str(location[1]))

    def getAltitude(self):
        return self.getConfig("location", "altitude")

    def setAltitude(self, altitude):
        self.setConfig("location", "altitude", str(altitude))

    # TCP client data
    def getHost(self):
        return self.getConfig("TCP", "host")

    def setHost(self, host):
        self.setConfig("TCP", "host", host)

    def getPort(self):
        return self.getConfig("TCP", "port")

    def setPort(self, port):
        self.setConfig("TCP", "port", str(port))

    def getTCPAutoConnStatus(self):
        return self.root.find("TCP").get("autoconnect")

    def TCPAutoConnEnable(self):
        self.root.find("TCP").set("autoconnect", "yes")
        self.tree.write(self.filename)

    def TCPAutoConnDisable(self):
        self.root.find("TCP").set("autoconnect", "no")
        self.tree.write(self.filename)

    # TCP Stellarium server data
    def getStellHost(self):
        return self.getConfig("TCPStell", "host")

    def setStellHost(self, host):
        self.setConfig("TCPStell", "host", host)

    def getStellPort(self):
        return self.getConfig("TCPStell", "port")

    def setStellPort(self, port):
        self.setConfig("TCPStell", "port", str(port))

    def getTCPStellAutoConnStatus(self):
        return self.root.find("TCPStell").get("autoconnect")

    def TCPStellAutoConnEnable(self):
        self.root.find("TCPStell").set("autoconnect", "yes")
        self.tree.write(self.filename)

    def TCPStellAutoConnDisable(self):
        self.root.find("TCPStell").set("autoconnect", "no")
        self.tree.write(self.filename)

    # TCP RPi server data (Auto-connection is dependant on the client)
    def getRPiHost(self):
        return self.getConfig("TCPRPiServ", "host")

    def setRPiHost(self, host):
        self.setConfig("TCPRPiServ", "host", host)

    def getRPiPort(self):
        return self.getConfig("TCPRPiServ", "port")

    def setRPiPort(self, port):
        self.setConfig("TCPRPiServ", "port", str(port))

    # Get the currently saved object
    def getObject(self):
        stat_obj = self.root.find("object").get("stationary")
        if stat_obj == "no":
            return [self.getConfig("object", "name"), -1]
        else:
            name = self.getConfig("object", "name")
            ra = self.getConfig("object", "RA")
            dec = self.getConfig("object", "DEC")
            return [name, ra, dec]

    def setObject(self, name, ra=-1, dec=-1):
        if (ra == -1) or (dec == -1):
            self.root.find("object").set("stationary", "no")
            self.setConfig("object", "name", name)
            self.setConfig("object", "RA", str(-1))
            self.setConfig("object", "DEC", str(-1))
        else:
            self.root.find("object").set("stationary", "yes")
            self.setConfig("object", "name", name)
            self.setConfig("object", "RA", str(ra))
            self.setConfig("object", "DEC", str(dec))
    
    def getHomeSteps(self):
        ra = self.root.find("Steps").get("ra_to_home")
        dec = self.root.find("Steps").get("dec_to_home")
        return [ra, dec]

    def setHomeSteps(self, ra, dec):
        self.root.find("Steps").set("ra_to_home", str(ra))
        self.root.find("Steps").set("dec_to_home", str(dec))
        self.tree.write(self.filename)

    def getTLEURL(self):
        url = self.getConfig("TLE", "url")
        return url

    def setTLEURL(self, url: str):
        self.setConfig("TLE", "url", url)

    def getTLEautoUpdate(self):
        return self.root.find("TLE").get("autoupdate")

    def setTLEautoUpdate(self, status: bool):
        if status is True:
            val = "yes"
        else:
            val = "no"
        self.root.find("TLE").set("autoupdate", val)

    def getTLEupdateInterval(self):
        return self.getConfig("TLE", "updt_interval")

    def setTLEupdateInterval(self, interval):
        self.setConfig("TLE", "updt_interval", str(interval))

    def getAllConfiguration(self):
        loc = list(self.root.find("location"))
        tcp = list(self.root.find("TCP"))
        data = []
        for loc_item in loc:
            data.append(loc_item.text)
        for tcp_item in tcp:
            data.append(tcp_item.text)
        return data
