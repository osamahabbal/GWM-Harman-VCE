import argparse
import json
import re

#
# Project code property: 'ro.vehicle.config.AAA'
#
kProjectCodeProperty = 'AAA'

#
# Calculates CRC8
# @param[in] data: Binary data without CRC byte
# @return CRC value
#
def calcCrc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc ^= 0x8380
            crc *= 2
    return (crc >> 8) & 0xFFFFFF

#
# Reads binary files
# @param[in] path: File path
#
def readConfig(path: str) -> bytearray:
    with open(path, 'rb') as cfg:
        return bytearray(cfg.read())
    
#
# Writes binary files
# @param[in] path: File path
# @param[in] data: Binary data
#
def writeConfig(path: str, data: bytes):
    with open(path, 'wb') as cfg:
        cfg.write(data)

#
# Reads JSON in UTF-8 encoding
# @param[in] path: File path
#
def readMap(path: str):
    with open(path, 'r', encoding = 'utf-8') as map:
        return json.load(map)
    
#
# Extracts position table from JSON
# @param[in] map: JSON config
#
def getPositionTable(map) -> str:
    return map['ro.vehicle.config']

#
# Config entry position
#
class Position:
    byte_idx = 0
    high_bit = 0
    low_bit = 0

    def _isValidBitPos(self, pos: int) -> bool:
        return 0 <= pos <= 7

    #
    # @param[in] pos: Position string in format "[byte_idx][high_bit:low_bit]"
    #
    def __init__(self, pos: str):
        match = re.match(r'\[(\d+)\]\[(\d+):(\d+)\]', pos)
        if not match:
            raise ValueError(f'Invalid position format: {pos}')
        
        byte_idx, high_bit, low_bit = map(int, match.groups())
        if not self._isValidBitPos(high_bit):
            raise OverflowError(f'High bit {high_bit} should be in range [0...7]')

        if not self._isValidBitPos(low_bit):
            raise OverflowError(f'Low bit {low_bit} should be in range [0...7]')
        
        if low_bit > high_bit:
            raise OverflowError(f'Low bit {low_bit} should be less than high bit {high_bit}')
        
        self.byte_idx = byte_idx
        self.high_bit = high_bit
        self.low_bit = low_bit
#
# Reads bits at a given position
# @param[in] data: Configuration bytes
# @return Little-endian bitstring 
#
def readBits(data: bytes, pos: Position) -> str:
    bitstr = format(data[pos.byte_idx], '08b')
    return bitstr[8 - pos.high_bit - 1:8 - pos.low_bit]

#
# Writes bits at a given position
# @param[in] data: Configuration bytes
# @param[in] pos: Position
# @param[in] value: Little-endian bitstring
#
def writeBits(data: bytearray, pos: Position, value: str) -> None:
    value_len = len(value)
    expected_len = pos.high_bit - pos.low_bit + 1
    if value_len != expected_len:
        raise OverflowError(f'Bistring length {value_len} is not equal to expected {expected_len}')
    
    bitlist = list(format(data[pos.byte_idx], '08b'))
    bitlist[8 - pos.high_bit - 1:8 - pos.low_bit] = list(value)
    data[pos.byte_idx] = int(''.join(bitlist), 2)

#
# Writes number at a given position
# @remark Value is converted to a bit string of required length (padded with leading zeros)
# @param[in] data: Configuration bytes
# @param[in] pos: Position
# @param[in] value: Number
#
def writeNumber(data: bytearray, pos: Position, value: int) -> None:
    bitstr = format(value, 'b')
    actual_len = len(bitstr)
    expected_len = pos.high_bit - pos.low_bit + 1

    if actual_len > expected_len:
        raise OverflowError(f'Value {value} is too large')
    
    if actual_len < expected_len:
        bitstr = '0' * (expected_len - actual_len) + bitstr 
    
    writeBits(data, pos, bitstr)

#
# Validates config size and project code against map
# @param[in] data: Configuration bytes
# @param[in] map: JSON config
#
def validateConfig(data: bytes, map) -> None:
    data_len = len(data)
    if data_len == 0 or data_len != map['size']:
        raise ValueError(f'Config size should be {data_len}')
    
    table = getPositionTable(map)
    project_code = int(readBits(data, Position(table['AAA'])), 2)
    if not project_code in map['project_code']:
        raise ValueError(f'Unsupported project code {project_code}')
    
    for property, pos in table.items():
        position = Position(pos)
        if position.byte_idx >= data_len - 1:  # Last byte is CRC
            raise OverflowError(f'Property {property} has invalid index {position.byte_idx}')
        
#
# Property name and value
#
class Property:
    name = ''
    bitstr = ''
    number = 0

    def _splitProps(self, sep: str, props: str):
        split = props.split(sep)
        if len(split) < 2:
            return None
        return split
    
    def _extractBistr(self, s: str) -> str:
        if len(s) == 0 or not all(c in '01' for c in s):
            raise ValueError(f'Bitstring {s} should contain only 0 and 1')
        return s
    
    def _extractNumber(self, s: str) -> int:
        n = int(s, 0)         # Select base automatically
        if n < 0 or n > 255:  # Should fit in a byte
            raise ValueError(f'Number {n} should be positive and less than 255')
        return n

    def __init__(self, props: str):
        split = self._splitProps(':', props)
        if not split is None:
            self.name = split[0]
            self.bitstr = self._extractBistr(split[1])
            return
        
        split = self._splitProps('=', props)
        if not split is None:
            self.name = split[0]
            self.number = self._extractNumber(split[1])
            return

        raise ValueError(f'Argument {props} should be in format PROPERTY:BITSTRING or PROPERTY=DECVALUE or PROPERTY=HEXVALUE')

#
# Does processing
#
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--map', dest = 'map', type = str, default = 'map.json', help = 'path to JSON file with mapping of properties to config bits')
    parser.add_argument('--src', dest = 'src', type = str, default = 'VehicleConfig.bin', help = 'path to source config binary file')
    parser.add_argument('--dst', dest = 'dst', type = str, default = 'NewVehicleConfig.bin', help = 'path to destination config binary file')
    parser.add_argument('props', metavar = 'PROPERTY:BITSTRING', type = str, nargs = '+', help = 'property:bitstring pairs')
    args = parser.parse_args()
   
    print(f'Read property map from {args.map}')
    map = readMap(args.map)

    print(f'Read config from {args.src}')
    data = readConfig(args.src)
    validateConfig(data, map)
    updated = False

    for property in [Property(p) for p in args.props]:
        name = property.name
        if name == kProjectCodeProperty:
            raise ValueError(f'Project code change is not supported')

        position = getPositionTable(map).get(name)
        if position is None:
            raise KeyError(f"Property '{name}' not found in map")
        
        if len(property.bitstr) > 0:
            writeBits(data, Position(position), property.bitstr)
        else:
            writeNumber(data, Position(position), property.number)
        updated = True

    if updated:
        print(f'Save updated config to {args.dst}')
        data[-1] = calcCrc8(data[:-1])
        writeConfig(args.dst, data)

#
# Launches main
#
if __name__ == "__main__":
    main()






