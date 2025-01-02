from enum import Enum
import json
import broadlink
import logging
from helpers import async_learn, validateNumber
from typing import List, Union
import questionary


class ClimateOperationModes(Enum):
    OFF = 'off'
    COOL = 'cool'
    HEAT = 'heat'
    HEAT_COOL = 'heat_cool'
    FAN = 'fan_only'
    DRY = 'dry'


class ClimateFanModes(Enum):
    AUTO = 'auto'
    LEVEL1 = 'level1'
    LEVEL2 = 'level2'
    LEVEL3 = 'level3'
    LEVEL4 = 'level4'
    LEVEL5 = 'level5'
    LEVEL6 = 'level6'
    LEVEL7 = 'level7'
    LEVEL8 = 'level8'
    LEVEL9 = 'level9'
    LEVEL10 = 'level10'


class ClimateDevice:
    def __init__(self, device: Union[broadlink.rm4pro, broadlink.rm4mini], manufacturer: str, supportedModels: List[str], logger: logging.Logger):
        self.device = device
        self.tempMin = self._promptTemperature('Minimum')
        self.tempMax = self._promptTemperature('Maximum')
        self.precision = self._promptPrecision()
        self.operationModes = self._promptOperationModes()
        self.fanModes = self._promptFanModes()
        self.logger = logger

        # Grab our temps with precision, and trim the ending .0's
        tempWithPrecision = [self.tempMin + self.precision * i for i in range(int((self.tempMax - self.tempMin) / self.precision) + 1)]
        self.temps = [int(x) if x.is_integer() else x for x in tempWithPrecision]

        self.outputConfig = self._buildBaseOutputConfig(manufacturer, supportedModels)

    def _promptTemperature(self, minOrMax: str):
        temperature = questionary.text(f'Enter the {minOrMax} Temperature', validate=validateNumber).ask()
        return int(temperature)

    def _promptPrecision(self):
        precision = questionary.select('Select Precision (Default is 1.0)', choices=['1.0', '0.5']).ask()
        return float(precision)

    def _promptOperationModes(self):
        # Remove OFF from the list of operation modes, its required below
        operationModes = [operationMode.value for operationMode in ClimateOperationModes if operationMode != ClimateOperationModes.OFF]

        selectedOperationModes = questionary.checkbox(
            'Select Operation Modes',
            choices=operationModes
        ).ask()

        return selectedOperationModes

    def _promptFanModes(self):
        selectedFanModes = questionary.checkbox(
            'Select Fan Modes (Number of speeds supported)',
            choices=[fanMode.value for fanMode in ClimateFanModes]
        ).ask()

        return selectedFanModes

    def _buildBaseOutputConfig(self, manufacturer: str, supportedModels: List[str],):
        # Build the base output config
        outputConfig = {}
        outputConfig['manufacturer'] = manufacturer
        outputConfig['supportedModels'] = supportedModels
        outputConfig['supportedController'] = 'Broadlink'
        outputConfig['commandsEncoding'] = 'Base64'
        outputConfig['minTemperature'] = self.tempMin
        outputConfig['maxTemperature'] = self.tempMax
        outputConfig['precision'] = self.precision
        outputConfig['operationModes'] = self.operationModes
        outputConfig['fanModes'] = self.fanModes
        outputConfig['commands'] = {}

        # Build the base config for each operation mode
        for operationMode in self.operationModes:
            outputConfig['commands'][operationMode] = {}
            for fanMode in self.fanModes:
                outputConfig['commands'][operationMode][fanMode] = {}
                for temp in self.temps:
                    outputConfig['commands'][operationMode][fanMode][str(temp)] = ''

        return outputConfig

    def _learnCommand(self, operationMode: str, fanMode: str, temp: int):
        """Learn a command from the remote"""
        self.logger.debug(f'Learning {operationMode.upper()} mode, {fanMode.upper()} fan, {temp}° temp')

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
                return self._learnCommand(operationMode, fanMode, temp)
            return False

        self.logger.debug(f'Received command: {command}')
        print('\nCommand received.')
        
        # Only show command code in verbose mode (INFO level)
        if logging.getLogger().level <= logging.INFO:
            print(f'Command code: {command}')
            
        print('Press Enter to confirm, N to re-learn, or S to skip this command')
        choice = input().lower()

        if choice == 's':
            self.logger.debug(f'Skipping {operationMode} command')
            return True
        elif choice == 'n':
            return self._learnCommand(operationMode, fanMode, temp)
        else:
            self.outputConfig['commands'][operationMode][fanMode][str(temp)] = command
            self.logger.debug(f'Saved command {operationMode}')
            print('Command saved successfully')
            return True

    def _learnOffCommand(self):
        """Learn the OFF command from the remote"""
        self.logger.debug(f'Learning OFF command')

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
                return self._learnOffCommand()
            return False

        self.logger.debug(f'Received command: {command}')
        print('\nCommand received.')
        
        # Only show command code in verbose mode (INFO level)
        if logging.getLogger().level <= logging.INFO:
            print(f'Command code: {command}')
            
        print('Press Enter to confirm, N to re-learn, or S to skip this command')
        choice = input().lower()

        if choice == 's':
            self.logger.debug(f'Skipping OFF command')
            return True
        elif choice == 'n':
            return self._learnOffCommand()
        else:
            self.outputConfig['commands']['off'] = command
            self.logger.debug(f'Saved command OFF')
            print('Command saved successfully')
            return True

    def learn(self, is_rf: bool = False):
        """Learn all commands for the climate device"""
        self.is_rf = is_rf
        self.logger.debug('Starting climate command learning process')
        print('\nYou will now be prompted to press buttons on your remote control.\n')

        # Learn the OFF Command
        if not self._learnOffCommand():
            self.logger.error('Failed to learn OFF command')
            return None
        self.logger.debug('Successfully learned OFF command')

        # Learn each temperature at each fanMode and operationMode
        for operationMode in ClimateOperationModes:
            if operationMode == ClimateOperationModes.OFF:
                continue

            for fanMode in ClimateFanModes:
                for temp in self.temps:
                    if not self._learnCommand(operationMode.value.lower(), fanMode.value.lower(), temp):
                        self.logger.error(f'Failed to learn {operationMode.value} mode, {fanMode.value} fan, {temp}° temp')
                        return None
                    self.logger.debug(f'Successfully learned {operationMode.value} mode, {fanMode.value} fan, {temp}° temp')

        self.logger.debug('Successfully completed climate command learning')
        self.logger.debug(f'Final config: {json.dumps(self.outputConfig, indent=2)}')
        return self.outputConfig
