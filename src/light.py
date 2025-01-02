from enum import Enum
import json
import broadlink
import logging
from typing import List, Union
from helpers import async_learn
import questionary


class LightOperationModes(Enum):
    OFF = 'off'
    ON = 'on'
    BRIGHTEN = 'brighten'
    DIM = 'dim'


class LightColorModes(Enum):
    WHITE = 'white'
    BLUE = 'blue'
    YELLOW = 'yellow'


class LightDevice:
    def __init__(self, device: Union[broadlink.rm4pro, broadlink.rm4mini], manufacturer: str, supportedModels: List[str], logger: logging.Logger):
        self.device = device
        self.logger = logger
        self.outputConfig = self._buildBaseOutputConfig(manufacturer, supportedModels)

    def _buildBaseOutputConfig(self, manufacturer: str, supportedModels: List[str]):
        # Build the base output config
        outputConfig = {}
        outputConfig['manufacturer'] = manufacturer
        outputConfig['supportedModels'] = supportedModels
        outputConfig['supportedController'] = 'Broadlink'
        outputConfig['commandsEncoding'] = 'Base64'
        outputConfig['commands'] = {}

        # Add operation modes
        for mode in LightOperationModes:
            outputConfig['commands'][mode.value] = ""

        # Add color modes
        outputConfig['commands']['colors'] = {}
        for color in LightColorModes:
            outputConfig['commands']['colors'][color.value] = ""

        return outputConfig

    def _learnCommand(self, command_type: str, command_name: str = None):
        """Learn a command from the remote"""
        if command_name:
            print(f'\nLearning {command_type.upper()} {command_name.upper()} - Point remote at device and press button')
        else:
            print(f'\nLearning {command_type.upper()} - Point remote at device and press button')

        # Get the current frequency if it was set during device initialization
        frequency = None
        if hasattr(self.device, 'frequency'):
            frequency = self.device.frequency

        command = async_learn(self.device, is_rf=self.is_rf, frequency=frequency)
        if command is None:
            return False

        choice = input(f'Press Enter or Y to confirm or N to relearn - {command}\n')

        if choice.lower() == 'y' or choice == '':
            return self._writeCommandToConfig(command, command_type, command_name)
        else:
            return self._learnCommand(command_type, command_name)

    def _writeCommandToConfig(self, command: str, command_type: str, command_name: str = None):
        """Write a learned command to the config"""
        if command_type == 'colors':
            self.outputConfig['commands']['colors'][command_name] = command
        else:
            self.outputConfig['commands'][command_type] = command
        return True

    def learn(self, is_rf: bool = False):
        """Learn all commands for the light device"""
        self.is_rf = is_rf
        print('\nYou will now be prompted to press buttons on your remote control.\n')

        # Learn basic operation commands
        for mode in LightOperationModes:
            if not self._learnCommand(mode.value):
                return None

        # Learn color commands
        for color in LightColorModes:
            if not self._learnCommand('colors', color.value):
                return None

        return self.outputConfig
