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

    def _learnCommand(self, command_type: str):
        """Learn a command from the remote"""
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
            return self._writeCommandToConfig(command, command_type)
        else:
            return self._learnCommand(command_type)

    def _writeCommandToConfig(self, command: str, key: str, nestedKey: str = None):
        if key and nestedKey:
            self.outputConfig['commands'][key][nestedKey] = command
        elif key:
            self.outputConfig['commands'][key] = command

    def learn(self, is_rf: bool = False):
        """Learn all commands for the media device"""
        self.is_rf = is_rf
        # Learn the media commands
        for command in MediaCommands:
            self._learnCommand(command.value)

        # Learn the sources
        for source in self.sources:
            self._learnCommand('sources')
            self.logger.debug(json.dumps(self.outputConfig, indent=4))

        return self.outputConfig
