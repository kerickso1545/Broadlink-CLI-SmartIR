from enum import Enum
import json
import broadlink
import logging
from helpers import async_learn
from typing import List, Union
import questionary


class FanOperationModes(Enum):
    OFF = 'off'
    ON = 'on'
    REVERSE = 'reverse'


class FanSpeedModes(Enum):
    LEVEL1 = 'level1'
    LEVEL2 = 'level2'
    LEVEL3 = 'level3'
    LEVEL4 = 'level4'
    LEVEL5 = 'level5'
    LEVEL6 = 'level6'


class FanTimerModes(Enum):
    TIMER_1H = 'timer_1h'
    TIMER_2H = 'timer_2h'
    TIMER_4H = 'timer_4h'
    TIMER_8H = 'timer_8h'


class FanDevice:
    def __init__(self, device: Union[broadlink.rm4pro, broadlink.rm4mini], manufacturer: str, supportedModels: List[str], logger: logging.Logger):
        self.device = device
        self.fanModes = [mode.value for mode in FanSpeedModes]  # All speed modes
        self.timerModes = self._promptTimerModes()
        self.logger = logger
        self.outputConfig = self._buildBaseOutputConfig(manufacturer, supportedModels)

    def _promptTimerModes(self):
        print("\nSelect which timer modes your remote supports:")
        print("Navigation:")
        print("- UP/DOWN arrows to move between options")
        print("- SPACE to select/unselect the current option")
        print("- ENTER to confirm ALL selections when done")
        print("\nMake sure to select ALL timer modes before pressing ENTER\n")
        
        selectedTimerModes = questionary.checkbox(
            'Timer Modes',
            choices=[
                questionary.Choice('1 Hour Timer', value='timer_1h'),
                questionary.Choice('2 Hour Timer', value='timer_2h'),
                questionary.Choice('4 Hour Timer', value='timer_4h'),
                questionary.Choice('8 Hour Timer', value='timer_8h')
            ],
            validate=lambda x: len(x) > 0 or "Please select at least one timer mode or press Ctrl+C to cancel"
        ).ask()

        # Confirm selections
        if selectedTimerModes:
            print("\nYou selected these timer modes:")
            for mode in selectedTimerModes:
                hours = mode.split('_')[1].replace('h', '')
                print(f"- {hours} Hour Timer")
            
            confirm = questionary.confirm("Is this correct? (y/n)").ask()
            if not confirm:
                print("\nLet's try selecting the timer modes again...")
                return self._promptTimerModes()

        return selectedTimerModes

    def _buildBaseOutputConfig(self, manufacturer: str, supportedModels: List[str]):
        # Build the base output config
        outputConfig = {}
        outputConfig['manufacturer'] = manufacturer
        outputConfig['supportedModels'] = supportedModels
        outputConfig['supportedController'] = 'Broadlink'
        outputConfig['commandsEncoding'] = 'Base64'
        outputConfig['speed'] = self.fanModes
        outputConfig['timer'] = self.timerModes
        outputConfig['commands'] = {}

        # Add base commands section
        outputConfig['commands']['off'] = None
        outputConfig['commands']['on'] = None
        outputConfig['commands']['reverse'] = None
        
        # Add speed commands
        for fanMode in self.fanModes:
            outputConfig['commands'][fanMode] = None
            
        # Add timer commands
        for timerMode in self.timerModes:
            outputConfig['commands'][timerMode] = None

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

    def learn(self, is_rf: bool = False):
        """Learn all commands for the fan"""
        self.is_rf = is_rf
        self.logger.debug('Starting fan command learning process')
        print('\nYou will now be prompted to press buttons on your remote control.\n')

        # Calculate total commands
        total_commands = 3 + len(self.fanModes) + len(self.timerModes)  # OFF + ON + REVERSE + speeds + timers
        command_count = 1
        
        # Learn basic commands
        commands_to_learn = [
            ('off', 'OFF'),
            ('on', 'ON'),
            ('reverse', 'REVERSE')
        ]
        
        for command_id, command_name in commands_to_learn:
            print(f'\n=== Learning {command_name} ({command_count}/{total_commands}) ===')
            result = self._learnCommand(command_id)
            if result == 'skip':
                self.logger.info(f'Skipped {command_name} command')
            elif result:
                self.logger.debug(f'Successfully learned {command_name} command')
            command_count += 1
        
        # Learn speed commands
        for fanMode in self.fanModes:
            print(f'\n=== Learning SPEED {fanMode.upper()} ({command_count}/{total_commands}) ===')
            result = self._learnCommand(fanMode)
            if result == 'skip':
                self.logger.info(f'Skipped {fanMode} command')
            elif result:
                self.logger.debug(f'Successfully learned {fanMode} command')
            command_count += 1
            
        # Learn timer commands
        for timerMode in self.timerModes:
            # Convert timer_1h to "1 HOUR TIMER" for display
            hours = timerMode.split('_')[1].replace('h', '')
            timer_name = f'{hours} HOUR TIMER'
            print(f'\n=== Learning {timer_name} ({command_count}/{total_commands}) ===')
            result = self._learnCommand(timerMode)
            if result == 'skip':
                self.logger.info(f'Skipped {timer_name} command')
            elif result:
                self.logger.debug(f'Successfully learned {timer_name} command')
            command_count += 1

        self.logger.debug('Successfully completed fan command learning')
        self.logger.debug(f'Final config: {json.dumps(self.outputConfig, indent=2)}')
        return self.outputConfig
