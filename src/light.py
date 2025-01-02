from enum import Enum
import json
import broadlink
import logging
from helpers import async_learn
from typing import List, Union
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

        self.logger.debug(f"Built base config: {json.dumps(outputConfig, indent=2)}")
        return outputConfig

    def _learnCommand(self, command_type: str, command_name: str = None):
        """Learn a command from the remote"""
        if command_name:
            self.logger.debug(f'Learning {command_type.upper()} {command_name.upper()}')
        else:
            self.logger.debug(f'Learning {command_type.upper()}')

        print('\nPoint remote at device and press button')

        # Get the current frequency if it was set during device initialization
        frequency = None
        if hasattr(self.device, 'frequency'):
            frequency = self.device.frequency
            self.logger.debug(f'Using frequency: {frequency} MHz')

        command = async_learn(self.device, is_rf=self.is_rf, frequency=frequency)
        if command is None:
            self.logger.warning('Learning failed or timed out')
            print("\nLearning failed or timed out. Try again? (Y/n)")
            choice = input().lower()
            if choice != 'n':
                return self._learnCommand(command_type, command_name)
            return False

        self.logger.debug(f'Received command: {command}')
        print('\nCommand received.')
        
        # Only show command code in verbose mode (INFO level)
        if logging.getLogger().level <= logging.INFO:
            print(f'Command code: {command}')
            
        print('Press Enter to confirm, N to re-learn, or S to skip this command')
        choice = input().lower()

        if choice == 's':
            self.logger.debug(f'Skipping {command_type} command')
            return True
        elif choice == 'n':
            return self._learnCommand(command_type, command_name)
        else:
            result = self._writeCommandToConfig(command, command_type, command_name)
            if result:
                print('Command saved successfully')
            return result

    def _writeCommandToConfig(self, command: str, command_type: str, command_name: str = None):
        """Write a learned command to the config"""
        if command_type == 'colors':
            self.outputConfig['commands']['colors'][command_name] = command
            self.logger.debug(f'Saved color command {command_name}')
        else:
            self.outputConfig['commands'][command_type] = command
            self.logger.debug(f'Saved command {command_type}')
        return True

    def learn(self, is_rf: bool = False):
        """Learn all commands for the light device"""
        self.is_rf = is_rf
        self.logger.debug('Starting light command learning process')
        print('\nYou will now be prompted to press buttons on your remote control.\n')

        # Learn basic operation commands
        for mode in LightOperationModes:
            if not self._learnCommand(mode.value):
                self.logger.error(f'Failed to learn {mode.value} command')
                return None
            self.logger.debug(f'Successfully learned {mode.value} command')

        # Learn color commands
        for color in LightColorModes:
            if not self._learnCommand('colors', color.value):
                self.logger.error(f'Failed to learn color {color.value}')
                return None
            self.logger.debug(f'Successfully learned color {color.value}')

        self.logger.debug('Successfully completed light command learning')
        self.logger.debug(f'Final config: {json.dumps(self.outputConfig, indent=2)}')
        return self.outputConfig
