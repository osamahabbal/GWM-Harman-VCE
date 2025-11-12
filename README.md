# GWM Vehicle Config Editor
## Description
Simple tool to edit `/data/vendor/vehicle/info/VehicleConfig.bin` in HUT to enable advanced features without an OBD2 scanner like ThinkDiag.
Use `adb root` to access configuration file.
## Requirements
Python 3.2 or newer.
## Usage
```
vce [--map <path-to-map-file>] [--src <path-to-source-config-file|VehicleConfig.bin>] [--dst <path-to-source-config-file|NewVehicleConfig.bin>] property1:value1...propertyN:valueN
```
