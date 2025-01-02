from enum import Enum, IntEnum
import base64
import codecs
import time
import broadlink
from broadlink.exceptions import ReadError, StorageError
import logging


class DeviceType(Enum):
    CLIMATE = 1
    MEDIA = 2
    FAN = 3
    LIGHT = 4


class LogLevel(IntEnum):
    ERROR = 3
    WARNING = 4
    INFO = 6
    DEBUG = 7


def async_learn(device: broadlink.Device, is_rf=False, frequency=None, log_level=None):
    logger = logging.getLogger(__name__)
    
    if is_rf:
        # Re-authenticate device to ensure fresh control key
        try:
            logger.info('Re-authenticating device')
            device.auth()
        except Exception as e:
            logger.error(f'Failed to re-authenticate device: {str(e)}')
            return None
            
        try:
            # Cancel any previous RF learning state
            device.cancel_rf_sweep()
            logger.info('Canceling any previous RF learning state')
            device.cancel_sweep_frequency()
            time.sleep(1)  # Give device time to process cancel command
        except Exception as e:
            logger.error(f'Error canceling previous state: {str(e)}')
            # Don't return here, try to continue
            
        # Set the frequency if provided
        if frequency:
            device.frequency = frequency
        
        # Start frequency detection if no frequency provided
        if not frequency:
            logger.info('=== Starting frequency detection ===')
            logger.info('Press and HOLD the button on your remote...')
            try:
                device.sweep_frequency()
                logger.info('Successfully started frequency sweep')
                
                # Wait for frequency detection
                start = time.time()
                while time.time() - start < 20:  # 20 second timeout
                    time.sleep(1)
                    locked, detected_freq = device.check_frequency()
                    if locked:
                        frequency = detected_freq
                        logger.info(f'Successfully detected frequency: {frequency} MHz')
                        logger.info('You can now release the button')
                        break
                else:
                    logger.error('Failed to detect frequency')
                    return None
                    
                # Give user time to release button
                time.sleep(2)
                
            except Exception as e:
                logger.error(f'Error during frequency detection: {str(e)}')
                return None
        
        # Now start RF learning
        logger.info('=== Starting RF learning mode ===')
        logger.info('Press the button on your remote (short press)...')
        try:
            # Re-auth before starting RF learning
            device.auth()
            
            # Start RF learning with the frequency
            logger.info(f'Starting RF learning with frequency: {frequency} MHz')
            device.find_rf_packet(frequency)
            logger.info('Successfully started RF learning mode')
            
        except Exception as e:
            logger.error(f'Failed to start RF learning: {str(e)}')
            return None
            
        # Listen for RF packet
        start = time.time()
        TIMEOUT = 20  # Timeout in seconds
        last_check = 0  # Track when we last checked for data
        
        while time.time() - start < TIMEOUT:
            current_time = time.time()
            # Only check every 100ms to prevent flooding the device
            if current_time - last_check >= 0.1:
                try:
                    device.auth()
                    data = device.check_data()
                    if data:
                        logger.info('Successfully received RF data')
                        return ''.join(format(x, '02x') for x in data)
                except Exception as e:
                    # Only log non-storage-full errors
                    if "storage is full" not in str(e):
                        logger.error(f'Error checking data: {str(e)}')
                last_check = current_time
            else:
                # Sleep a small amount to prevent CPU spinning
                time.sleep(0.01)
            
        logger.warning(f'Learning timed out after {time.time() - start:.1f} seconds')
        return None
    else:
        # Re-authenticate device to ensure fresh control key
        try:
            logger.info('Re-authenticating device')
            device.auth()
        except Exception as e:
            logger.error(f'Failed to re-authenticate device: {str(e)}')
            return None
            
        device.enter_learning()
        start = time.time()
        while time.time() - start < 20:  # 20 second timeout
            time.sleep(1)
            try:
                data = device.check_data()
                if data:
                    logger.info('Successfully received IR data')
                    # Format the data properly for SmartIR
                    data = ''.join(format(x, '02x') for x in bytearray(data))
                    decode_hex = codecs.getdecoder("hex_codec")
                    return base64.b64encode(decode_hex(data)[0]).decode('utf-8')
            except (ReadError, StorageError) as e:
                if "storage is full" in str(e):
                    pass  # Ignore storage full errors completely
                else:
                    logger.error(f'Error checking data: {str(e)}')
                continue
    
    logger.error('Learning timed out')
    return None


def validateNumber(value):
    if value.isdigit():
        return True
    else:
        return "Please enter a valid number."
