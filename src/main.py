import argparse
import os
import json
import logging
import broadlink
import questionary
from typing import List, Optional
from helpers import DeviceType
from climate import ClimateDevice
from fan import FanDevice
from media import MediaDevice
from light import LightDevice
import time

def setupLogging(args):
    """Configure logging based on command line arguments"""
    if args.debug:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def getLogger(log_level):
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    # Set up file handler
    file_handler = logging.FileHandler('logs/debug.log')
    file_handler.setLevel(logging.DEBUG)
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Enable debug logging for broadlink library specifically
    broadlink_logger = logging.getLogger('broadlink')
    broadlink_logger.setLevel(logging.DEBUG)
    
    return logging.getLogger(__name__)


def scanDevices(frequency=None, device_type=None, host=None, mac=None):
    logger = logging.getLogger(__name__)
    devices = []
    logger.debug('=== Starting device scan ===')
    logger.debug(f'Manual device type specified: {hex(device_type) if device_type else None}')
    
    if device_type and host and mac:
        logger.debug(f'Using direct device connection - type: {device_type}, host: {host}, mac: {mac}')
        try:
            mac = bytearray.fromhex(mac)
            device = broadlink.gendevice(device_type, (host, broadlink.DEFAULT_PORT), mac)
            device.auth()
            devices = [device]
            if logger.getEffectiveLevel() <= logging.INFO:  # Show in verbose mode
                print('\nFound device:')
                print(f'  MAC Address : {":".join(format(x, "02x") for x in device.mac)}')
                print(f'  IP Address  : {device.host[0]}')
                print(f'  Device Type : 0x{device.devtype:x}')
            logger.debug(f'Connected to device:')
            logger.debug(f'  - Type: {type(device).__name__}')
            logger.debug(f'  - Model: {device.model}')
            logger.debug(f'  - Device Type (hex): 0x{device.devtype:x}')
            logger.debug(f'  - Host: {device.host[0]}')
            logger.debug(f'  - MAC: {device.mac.hex()}')
        except Exception as e:
            logger.error(f'Failed to connect to device: {str(e)}')
            print(f'Failed to connect to device: {str(e)}')
            exit()
    else:
        print('Scanning for devices...\n')
        for device in broadlink.xdiscover():
            if logger.getEffectiveLevel() <= logging.INFO:  # Show in verbose mode
                print('\nFound device:')
                print(f'  MAC Address : {":".join(format(x, "02x") for x in device.mac)}')
                print(f'  IP Address  : {device.host[0]}')
                print(f'  Device Type : 0x{device.devtype:x}')
            logger.debug(f'Found device via auto-discovery:')
            logger.debug(f'  - Type: {type(device).__name__}')
            logger.debug(f'  - Model: {device.model}')
            logger.debug(f'  - Device Type (hex): 0x{device.devtype:x}')
            logger.debug(f'  - Host: {device.host[0]}')
            logger.debug(f'  - MAC: {device.mac.hex()}')
            logger.debug(f'  - Available methods: {[method for method in dir(device) if not method.startswith("_")]}')
            devices.append(device)

    if len(devices) == 0:
        logger.debug('No devices found during scan')
        print('No devices found')
        exit()

    return devices


def showAndSelectDevice(devices: List[broadlink.Device]) -> broadlink.Device:
    # Build hashmap of deviceIp to device
    deviceIpToDevice = {}
    deviceHosts = []
    for device in devices:
        deviceIpToDevice[device.host[0]] = device
        deviceHosts.append(device.host[0])

    selectedDeviceIp = questionary.select('Select Device', choices=deviceHosts).ask()

    # Fetch the device from the hashmap
    device = deviceIpToDevice[selectedDeviceIp]

    # Currently only support RM4 Pro + RM4 Mini
    if 'rm4' not in device.model.lower():
        print(f'Invalid Device - {device.model} is not supported')
        exit()

    # No need to re-auth since we already authenticated in scanDevices
    logger = logging.getLogger(__name__)
    logger.debug(f'Selected device: {device.model}')
    return device


def selectDeviceType() -> DeviceType:
    selectedDeviceType = questionary.select(
        'Select Device Type',
        choices=[deviceType.name for deviceType in DeviceType]
    ).ask()
    logger = logging.getLogger(__name__)
    logger.debug(f'Selected device type: {selectedDeviceType}')
    return selectedDeviceType


def selectSignalType() -> bool:
    signalType = questionary.select(
        'Select Signal Type',
        choices=['RF', 'IR']
    ).ask()
    logger = logging.getLogger(__name__)
    logger.debug(f'Selected signal type: {signalType}')
    return signalType == 'RF'


def promptManufacturer():
    manufacturer = questionary.text('Enter Manufacturer').ask()
    logger = logging.getLogger(__name__)
    logger.debug(f'Entered manufacturer: {manufacturer}')
    return manufacturer


def promptSupportedModels():
    supportedModels = questionary.text('Enter Supported Models Number / Names (comma separated)').ask()
    if ',' in supportedModels:
        supportedModels = supportedModels.split(',')
    else:
        supportedModels = [supportedModels]

    logger = logging.getLogger(__name__)
    logger.debug(f'Entered supported models: {supportedModels}')
    return supportedModels


def promptFrequency():
    frequency = questionary.text(
        'Enter RF frequency in MHz (optional, leave empty for default)',
        validate=lambda text: True if text == '' or (text.replace('.', '', 1).isdigit() and len(text.split('.')[1]) <= 2 if '.' in text else True) else 'Please enter a valid number with at most 2 decimal places'
    ).ask()
    logger = logging.getLogger(__name__)
    logger.debug(f'Entered frequency: {frequency}')
    return frequency


def saveConfig(config: dict, deviceType: str, manufacturer: str):
    """Save the config to a JSON file"""
    # Create the out folder if it doesn't exist
    if not os.path.exists('./out'):
        os.makedirs('./out')
    
    # Save the config with timestamp
    fileName = f'./out/{deviceType}-{manufacturer}-{int(time.time())}.json'
    with open(fileName, 'w') as f:
        json.dump(config, f, indent=4)
    print(f'\nSuccessfully created {fileName}')


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Broadlink CLI Tool")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    # Setup logging
    logger = setupLogging(args)
    logger.debug("Starting Broadlink CLI Tool")

    # Add device specification options
    device_type = questionary.text(
        'Enter device type in hex (e.g., 0x649b) or leave empty for auto-discovery',
        validate=lambda text: True if text == '' or text.startswith('0x') else 'Please enter a hex value starting with 0x'
    ).ask()
    
    host = questionary.text(
        'Enter device IP address (leave empty for auto-discovery)'
    ).ask()
    
    mac = questionary.text(
        'Enter device MAC address without colons (leave empty for auto-discovery)'
    ).ask()

    # First just scan for devices without setting frequency
    devices = scanDevices(
        None,  # Don't set frequency yet
        int(device_type, 16) if device_type else None,
        host if host else None,
        mac if mac else None
    )

    # Select the device if multiple found
    device = None
    if len(devices) > 1:
        device = showAndSelectDevice(devices)
    else:
        device = devices[0]

    # Select signal type (RF or IR)
    is_rf = selectSignalType()
    logger.debug(f"Selected {'RF' if is_rf else 'IR'} signal type")

    # Get frequency if RF
    freq = None
    if is_rf:
        freq = promptFrequency()
        if freq:
            freq_float = float(freq)
            device.frequency = freq_float
            logger.debug(f'Set frequency to {freq_float} MHz')
    
    # Select device type
    deviceType = selectDeviceType()
    logger.debug(f"Selected device type: {deviceType}")
    
    manufacturer = promptManufacturer()
    supportedModels = promptSupportedModels()

    # Call the appropriate device class to learn
    logger.debug(f"Initializing {deviceType} device handler")
    outputConfig = None
    
    if deviceType == DeviceType.CLIMATE.name:
        climate = ClimateDevice(device, manufacturer, supportedModels, logger)
        outputConfig = climate.learn(is_rf)

    if deviceType == DeviceType.FAN.name:
        fan = FanDevice(device, manufacturer, supportedModels, logger)
        outputConfig = fan.learn(is_rf)

    if deviceType == DeviceType.MEDIA.name:
        media = MediaDevice(device, manufacturer, supportedModels, logger)
        outputConfig = media.learn(is_rf)

    if deviceType == DeviceType.LIGHT.name:
        light = LightDevice(device, manufacturer, supportedModels, logger)
        outputConfig = light.learn(is_rf)

    if outputConfig:
        saveConfig(outputConfig, deviceType, manufacturer)
    else:
        logger.error("Failed to learn commands")


main()
