from enum import Enum
import json
import broadlink
import logging
from helpers import async_learn
from typing import List, Union
import questionary


class MediaCommands(Enum):
    OFF = 'off'
    ON = 'on'
    PREVIOUS_CHANNEL = 'previousChannel'
    NEXT_CHANNEL = 'nextChannel'
    VOLUME_UP = 'volumeUp'
    VOLUME_DOWN = 'volumeDown'
    MUTE = 'mute'


class MediaDevice:
    def __init__(self, device: Union[broadlink.rm4pro, broadlink.rm4mini], manufacturer: str, supportedModels: List[str], logger: logging.Logger):
        self.device = device
        self.sources = self._promptMediaSources()
        self.logger = logger
        self.outputConfig = self._buildBaseOutputConfig(manufacturer, supportedModels)
        self.is_rf = False

    def _promptMediaSources(self):
        mediaSources = questionary.text('Enter Media Source names (comma separated)').ask()
        if ',' in mediaSources:
            mediaSources = mediaSources.split(',')
        else:
            mediaSources = [mediaSources]

        return mediaSources

    def _buildBaseOutputConfig(self, manufacturer: str, supportedModels: List[str],):
        # Build the base output config
        outputConfig = {}
        outputConfig['manufacturer'] = manufacturer
        outputConfig['supportedModels'] = supportedModels
        outputConfig['supportedController'] = 'Broadlink'
        outputConfig['commandsEncoding'] = 'Base64'
        outputConfig['commands'] = {}
        outputConfig['commands']['sources'] = {}

        # Build the base config for each Media Command
        for command in MediaCommands:
            outputConfig['commands'][command.value] = ""

        # Build the base config for each source
        for source in self.sources:
            outputConfig['commands']['sources'][source] = ""

        return outputConfig

    def _learnCommand(self, commandType: str):
        """Learn a command from the remote"""
        self.logger.debug(f'Learning {commandType.upper()} command')

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
                return self._learnCommand(commandType)
            return False

        self.logger.debug(f'Received command: {command}')
        print('\nCommand received.')
        
        # Only show command code in verbose mode (INFO level)
        if logging.getLogger().level <= logging.INFO:
            print(f'Command code: {command}')
            
        print('Press Enter to confirm, N to re-learn, or S to skip this command')
        choice = input().lower()

        if choice == 's':
            self.logger.debug(f'Skipping {commandType} command')
            return True
        elif choice == 'n':
            return self._learnCommand(commandType)
        else:
            self.outputConfig['commands'][commandType] = command
            self.logger.debug(f'Saved command {commandType}')
            print('Command saved successfully')
            return True

    def _writeCommandToConfig(self, command: str, key: str, nestedKey: str = None):
        if key and nestedKey:
            self.outputConfig['commands'][key][nestedKey] = command
        elif key:
            self.outputConfig['commands'][key] = command

    def learn(self, is_rf: bool = False):
        """Learn all commands for the media device"""
        self.is_rf = is_rf
        self.logger.debug('Starting media command learning process')
        print('\nYou will now be prompted to press buttons on your remote control.\n')

        # Learn the media commands
        for command in MediaCommands:
            if not self._learnCommand(command.value):
                self.logger.error(f'Failed to learn {command.value} command')
                return None
            self.logger.debug(f'Successfully learned {command.value} command')

        # Learn the sources
        for source in self.sources:
            if not self._learnCommand('sources'):
                self.logger.error(f'Failed to learn {source} command')
                return None
            self.logger.debug(f'Successfully learned {source} command')

        self.logger.debug('Successfully completed media command learning')
        self.logger.debug(f'Final config: {json.dumps(self.outputConfig, indent=2)}')
        return self.outputConfig
