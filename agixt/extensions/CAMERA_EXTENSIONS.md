# Camera Extensions for AGiXT

This document provides setup and usage instructions for the camera system extensions in AGiXT.

## Overview

Five camera system extensions have been added to AGiXT:

1. **Blink Extension** (`blink.py`) - Controls Blink camera systems
2. **Ring Extension** (`ring.py`) - Controls Ring camera and doorbell systems
3. **Hikvision Extension** (`hikvision.py`) - Controls Hikvision cameras and DVRs
4. **Axis Extension** (`axis.py`) - Controls Axis Communications cameras
5. **Vivotek Extension** (`vivotek.py`) - Controls Vivotek IP cameras

All extensions follow AGiXT's extension patterns and provide comprehensive camera control capabilities.

## Installation

### Dependencies

Install the required Python packages:

```bash
pip install blinkpy>=0.23.0 ring_doorbell>=0.9.13 hikvisionapi>=0.3.2 axis>=64 aiohttp
```

These dependencies have been added to `requirements.txt` and will be installed automatically.

### Configuration Options

All camera extensions support two configuration methods:

1. **Arguments** (Recommended): Pass credentials directly when initializing the extension
2. **Environment Variables**: Use as fallback when arguments are not provided

#### Configuration via Arguments

```python
# Example: Initialize Axis camera with arguments
axis_camera = axis_camera(
    host="192.168.1.101",
    username="root", 
    password="your_password",
    port=80  # optional
)

# Example: Initialize Hikvision camera with arguments
hikvision = hikvision(
    host="http://192.168.1.100",
    username="admin",
    password="your_password"
)
```

#### Configuration via Environment Variables (Fallback)

If arguments are not provided, the extensions will use environment variables:

##### Blink Extension

```bash
BLINK_USERNAME=your_blink_email@example.com
BLINK_PASSWORD=your_blink_password
```

##### Ring Extension

```bash
RING_USERNAME=your_ring_email@example.com
RING_PASSWORD=your_ring_password
RING_USER_AGENT=AGiXT-Ring-1.0  # Optional, defaults to "AGiXT-Ring-1.0"
```

##### Hikvision Extension

```bash
HIKVISION_HOST=http://192.168.1.100  # Camera/DVR IP address with protocol
HIKVISION_USERNAME=admin             # Username for authentication
HIKVISION_PASSWORD=your_password     # Password for authentication
```

##### Axis Extension

```bash
AXIS_HOST=192.168.1.101        # Camera IP address (no protocol)
AXIS_USERNAME=root             # Username for authentication
AXIS_PASSWORD=your_password    # Password for authentication
AXIS_PORT=80                   # Port number (optional, default: 80)
```

##### Vivotek Extension

```bash
VIVOTEK_HOST=192.168.1.102     # Camera IP address (no protocol)
VIVOTEK_USERNAME=root          # Username (usually 'root' for Vivotek)
VIVOTEK_PASSWORD=your_password # Password for authentication
VIVOTEK_PORT=80                # Port number (optional, default: 80)
```

## Blink Extension Features

### Blink Available Commands

1. **Arm Blink System** - Arms the security system or specific sync modules
2. **Disarm Blink System** - Disarms the security system or specific sync modules
3. **Capture Video Clip** - Takes a new picture/video from a specific camera
4. **Check Camera Status** - Gets detailed status of cameras including battery, signal strength
5. **Get Motion Alerts** - Retrieves recent motion detection events
6. **Get Camera List** - Lists all available cameras with basic information
7. **Download Recent Videos** - Downloads recent video clips from cameras
8. **Check System Status** - Gets overall system status including sync modules

### Blink Usage Examples

```python
# Arm all sync modules
result = await blink_extension.arm_system()

# Arm specific sync module
result = await blink_extension.arm_system("Front Yard")

# Check specific camera status
result = await blink_extension.check_camera_status("Front Door")

# Capture video from camera
result = await blink_extension.capture_video_clip("Driveway")

# Get recent motion alerts
result = await blink_extension.get_motion_alerts(limit=5)
```

### Blink Authentication Notes

- Uses username/password authentication
- Supports 2FA (requires manual implementation in production)
- Session management handles token refresh automatically
- Connection is established on first command use

## Ring Extension Features

### Ring Available Commands

1. **View Live Stream** - Gets live stream access information
2. **Access Recorded Video** - Retrieves URLs for recorded videos
3. **Adjust Device Settings** - Modifies device settings (volume, motion detection, lights)
4. **Check Motion Alerts** - Gets recent motion detection events
5. **Enable Motion Alerts** - Enables motion detection for devices
6. **Disable Motion Alerts** - Disables motion detection for devices
7. **Get Device List** - Lists all Ring devices (doorbells, cameras, chimes)
8. **Download Recent Videos** - Downloads recent recordings
9. **Get Device Health** - Shows device health information (WiFi, battery, etc.)
10. **Set Device Lights** - Controls lights on compatible devices
11. **Test Device Sound** - Tests chime sounds

### Ring Usage Examples

```python
# Get all devices
result = await ring_extension.get_device_list()

# Check motion alerts for specific device
result = await ring_extension.check_motion_alerts("Front Door", limit=10)

# Access recent recordings
result = await ring_extension.access_recorded_video("Front Door", limit=3)

# Adjust volume
result = await ring_extension.adjust_device_settings("Front Door", "volume", "8")

# Enable motion detection
result = await ring_extension.enable_motion_alerts("Driveway Camera")

# Control lights
result = await ring_extension.set_device_lights("Floodlight Cam", "on", duration=30)

# Download recent videos
result = await ring_extension.download_recent_videos("Front Door", count=5)
```

### Ring Authentication Notes

- Uses username/password authentication with 2FA support
- Implements token caching to minimize login frequency
- Automatic token refresh when expired
- Stores cached tokens in `{user_agent}.token.cache`

## Hikvision Extension Features

### Hikvision Environment Variables

Set the following environment variables:

```bash
HIKVISION_HOST=http://192.168.1.100  # Camera/DVR IP address with protocol
HIKVISION_USERNAME=admin             # Username for authentication
HIKVISION_PASSWORD=your_password     # Password for authentication
```

### Hikvision Available Commands

1. **Get Device Info** - Retrieves device information including model, firmware, and serial number
2. **Capture Image** - Takes a snapshot from specified channel with configurable quality
3. **Get Motion Detection Status** - Shows current motion detection configuration
4. **Set Motion Detection** - Configures motion detection settings and sensitivity
5. **Get Event Notifications** - Monitors for motion and other events in real-time
6. **Get Channel List** - Lists all available video input channels
7. **Get System Status** - Shows system uptime, CPU, and memory usage
8. **Get Recording Status** - Checks recording status for specified channel
9. **Start Recording** - Initiates manual recording (if supported by firmware)
10. **Stop Recording** - Stops manual recording (if supported by firmware)
11. **Get Storage Info** - Displays storage device information and capacity
12. **Reboot System** - Remotely reboots the camera/DVR system

### Hikvision Usage Examples

```python
# Get device information
result = await hikvision_extension.get_device_info()

# Capture high-quality image from channel 1
result = await hikvision_extension.capture_image(channel=1, quality="high")

# Enable motion detection with 80% sensitivity
result = await hikvision_extension.set_motion_detection(channel=1, enabled=True, sensitivity=80)

# Monitor for events for 30 seconds
result = await hikvision_extension.get_event_notifications(timeout=30)
```

## Axis Extension Features

### Axis Environment Variables

Set the following environment variables:

```bash
AXIS_HOST=192.168.1.101        # Camera IP address (no protocol)
AXIS_USERNAME=root             # Username for authentication
AXIS_PASSWORD=your_password    # Password for authentication
AXIS_PORT=80                   # Port number (optional, default: 80)
```

### Axis Available Commands

1. **Get Device Info** - Retrieves device information including brand, model, and firmware
2. **Get Live Stream URL** - Provides streaming URLs for different formats and resolutions
3. **Capture Image** - Takes a snapshot with configurable resolution and format
4. **Get Motion Detection Status** - Shows motion detection configuration
5. **Set Motion Detection** - Basic motion detection enable/disable
6. **Get Event Notifications** - Monitors for camera events
7. **Get PTZ Status** - Shows PTZ capabilities and current position
8. **Control PTZ** - Controls pan, tilt, and zoom movements
9. **Get Audio Settings** - Shows audio configuration and capabilities
10. **Set Audio Settings** - Configures audio settings and volume
11. **Get System Status** - Shows comprehensive system status
12. **Reboot Camera** - Remotely reboots the camera

### Axis Usage Examples

```python
# Get live stream URL for high-quality MJPEG
result = await axis_extension.get_live_stream_url(resolution="high", format="mjpeg")

# Capture medium resolution image
result = await axis_extension.capture_image(resolution="medium", format="jpeg")

# Control PTZ - pan left at 50% speed
result = await axis_extension.control_ptz(action="pan_left", speed=50)

# Set audio volume to 75%
result = await axis_extension.set_audio_settings(enabled=True, volume=75)
```

## Vivotek Extension Features

### Vivotek Environment Variables

Set the following environment variables:

```bash
VIVOTEK_HOST=192.168.1.102     # Camera IP address (no protocol)
VIVOTEK_USERNAME=root          # Username (usually 'root' for Vivotek)
VIVOTEK_PASSWORD=your_password # Password for authentication
VIVOTEK_PORT=80                # Port number (optional, default: 80)
```

### Vivotek Available Commands

1. **Get Device Info** - Retrieves device information including model, firmware, and network settings
2. **Get Live Stream URL** - Provides streaming URLs for MJPEG and RTSP formats
3. **Capture Image** - Takes a snapshot from specified stream
4. **Get Motion Detection Status** - Shows motion detection configuration
5. **Set Motion Detection** - Configures motion detection settings
6. **Get PTZ Status** - Shows PTZ capabilities and current position
7. **Control PTZ** - Controls pan, tilt, and zoom movements with speed control
8. **Get System Status** - Shows comprehensive system status and uptime
9. **Get Video Settings** - Shows current video configuration (resolution, quality, etc.)
10. **Set Video Settings** - Configures brightness, contrast, and saturation
11. **Get Audio Settings** - Shows audio configuration and capabilities
12. **Reboot Camera** - Prepares reboot command for the camera

### Vivotek Usage Examples

```python
# Get device information and network settings
result = await vivotek_extension.get_device_info()

# Get RTSP stream URL for H.264
result = await vivotek_extension.get_live_stream_url(stream=1, format="h264")

# Configure motion detection with 90% sensitivity
result = await vivotek_extension.set_motion_detection(enabled=True, sensitivity=90)

# Control PTZ - tilt up at 75% speed
result = await vivotek_extension.control_ptz(action="tilt_up", speed=75)

# Adjust video settings
result = await vivotek_extension.set_video_settings(brightness=60, contrast=55, saturation=50)
```

## Advanced Configuration

### Authentication Methods

- **Hikvision**: Uses HTTP digest authentication through hikvisionapi library
- **Axis**: Uses basic authentication with session management
- **Vivotek**: Uses HTTP basic authentication with direct API calls

### Streaming Protocols

- **Hikvision**: MJPEG, H.264, H.265 via RTSP and HTTP
- **Axis**: MJPEG, H.264, H.265 via VAPIX API
- **Vivotek**: MJPEG via HTTP, H.264 via RTSP

### Event Monitoring

- **Hikvision**: Real-time event stream with configurable timeout
- **Axis**: Event monitoring through Axis event manager
- **Vivotek**: Manual polling of motion detection status

## Security Considerations

### Network Security

- Use HTTPS where supported (Hikvision with proper certificates)
- Implement firewall rules to restrict camera access
- Use VPN for remote access to camera networks
- Change default passwords immediately

### Credential Management

- Store credentials in environment variables only
- Never hardcode credentials in scripts
- Use strong, unique passwords for each camera
- Enable 2FA where supported by camera firmware

### API Rate Limiting

- Implement delays between rapid successive calls
- Monitor camera CPU usage during heavy API usage
- Use appropriate timeout values for network requests
- Cache frequently accessed information when possible

## Error Handling

Both extensions implement comprehensive error handling:

### Connection Errors

- Automatic retry with exponential backoff
- Graceful degradation when services unavailable
- Clear error messages for troubleshooting

### Authentication Errors

- Token refresh attempts
- Clear authentication failure messages
- Guidance for credential issues

### Device Errors

- Per-device error isolation
- Fallback to available devices
- Detailed error logging

## File Structure

```text
AGiXT/agixt/extensions/
├── blink.py           # Blink camera extension
├── ring.py            # Ring camera extension
├── hikvision.py       # Hikvision camera extension
├── axis.py            # Axis camera extension
├── vivotek.py         # Vivotek camera extension
└── README.md          # This documentation (extension pattern guide)

requirements.txt       # Updated with new dependencies
```

## Configuration Examples

### Basic AGiXT Agent Configuration

When creating an AGiXT agent, ensure the extensions are available:

```json
{
    "settings": {
        "extensions": ["blink", "ring", "hikvision", "axis", "vivotek"],
        "BLINK_USERNAME": "your_email@example.com",
        "BLINK_PASSWORD": "your_password",
        "RING_USERNAME": "your_email@example.com", 
        "RING_PASSWORD": "your_password",
        "HIKVISION_HOST": "http://192.168.1.100",
        "HIKVISION_USERNAME": "admin",
        "HIKVISION_PASSWORD": "your_password",
        "AXIS_HOST": "192.168.1.101",
        "AXIS_USERNAME": "root",
        "AXIS_PASSWORD": "your_password",
        "VIVOTEK_HOST": "192.168.1.102",
        "VIVOTEK_USERNAME": "root",
        "VIVOTEK_PASSWORD": "your_password"
    }
}
```

### Environment File Configuration

```bash
# Blink Configuration
BLINK_USERNAME=your_blink_email@example.com
BLINK_PASSWORD=your_secure_password

# Ring Configuration  
RING_USERNAME=your_ring_email@example.com
RING_PASSWORD=your_secure_password
RING_USER_AGENT=AGiXT-Ring-1.0

# Hikvision Configuration
HIKVISION_HOST=http://192.168.1.100
HIKVISION_USERNAME=admin
HIKVISION_PASSWORD=your_secure_password

# Axis Configuration
AXIS_HOST=192.168.1.101
AXIS_USERNAME=root
AXIS_PASSWORD=your_secure_password
AXIS_PORT=80

# Vivotek Configuration
VIVOTEK_HOST=192.168.1.102
VIVOTEK_USERNAME=root
VIVOTEK_PASSWORD=your_secure_password
VIVOTEK_PORT=80
```

## Troubleshooting

### Common Issues

1. **Import Errors**

   - Ensure `blinkpy` and `ring_doorbell` packages are installed
   - Check Python environment and package versions

2. **Authentication Failures**

   - Verify credentials are correct
   - Check if 2FA is enabled on accounts
   - Ensure accounts have camera access

3. **Device Not Found Errors**

   - Use `Get Device List` commands to see available devices
   - Check device names match exactly (case-sensitive)
   - Ensure devices are online and connected

4. **Token Cache Issues**

   - Delete cached token files to force re-authentication
   - Check file permissions for cache directory

5. **Connection Problems**

   - **Hikvision**: Verify HTTP/HTTPS protocol in HIKVISION_HOST
   - **Axis**: Check if port 80/443 is accessible
   - **Vivotek**: Ensure camera web interface is enabled

6. **Feature Limitations**

   - **PTZ Control**: Only available on PTZ-capable cameras
   - **Recording Control**: Depends on camera firmware version
   - **Event Monitoring**: May require specific firmware features
   - **Audio Features**: Limited to cameras with audio support

### Error Messages

#### "Failed to connect"

1. Check network connectivity to camera
2. Verify IP address and port settings
3. Ensure camera web interface is accessible
4. Check firewall rules

#### "Authentication failed"

1. Verify credentials in environment variables
2. Check if user account is active
3. Ensure user has API access permissions
4. Try accessing camera web interface manually

#### "Command not supported"

1. Check camera firmware version
2. Verify feature is available on camera model
3. Consult camera documentation for API limitations
4. Try alternative commands or methods

### Debug Logging

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed information about:

- HTTP requests and responses
- Authentication attempts
- API call timings
- Error details and stack traces

## Future Enhancements

### Planned Features

1. **Enhanced 2FA Support**

   - Web-based 2FA prompt integration
   - Stored authentication token management
   - Multi-user authentication support

2. **Advanced Video Features**

   - Live stream integration
   - Video analysis and motion detection
   - Automated video archival

3. **Smart Notifications**

   - Intelligent motion filtering
   - Person/package detection integration
   - Custom alert rules

4. **Integration Features**

   - Home automation integration
   - Geofencing support
   - Scheduled arming/disarming

### Contributing

To contribute improvements:

1. Follow AGiXT extension patterns from `extensions/README.md`
2. Implement comprehensive error handling
3. Add unit tests for new features
4. Update documentation
5. Test with real devices when possible

## Support

For issues and support:

1. Check extension logs for error details
2. Verify API credentials and device connectivity
3. Consult official API documentation:

   - [Blink API](https://github.com/fronzbot/blinkpy)
   - [Ring API](https://github.com/python-ring-doorbell/python-ring-doorbell)
   - [Hikvision API](https://github.com/SecurityInMotion/hikvisionapi)
   - [Axis API](https://developer.axis.com/)
   - [Vivotek API](https://www.vivotek.com/)

4. Report bugs with full error logs and configuration details

---

These extensions provide powerful camera control capabilities while following AGiXT's security and architectural patterns. They serve as examples of how to integrate complex authentication workflows and device management into the AGiXT ecosystem.
