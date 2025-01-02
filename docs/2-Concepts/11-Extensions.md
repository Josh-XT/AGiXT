# AGiXT Extensions

AGiXT extensions are modular components that provide additional capabilities to AI agents through a "bolt-on" architecture. This approach allows for seamless integration of new functionalities without modifying the core system.

## Authentication & Context Management

### User Context

Extensions receive several key pieces of context during initialization:

```python
def __init__(self, **kwargs):
    # AGiXT SDK initialized with user's JWT
    self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else AGiXTSDK(
        base_uri=getenv("AGIXT_URI"),
        api_key=kwargs["api_key"] if "api_key" in kwargs else "",
    )
    
    # User's AGiXT JWT for authentication
    self.api_key = kwargs["api_key"] if "api_key" in kwargs else ""
    
    # Agent and conversation context
    self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
    self.conversation_name = kwargs["conversation_name"] if "conversation_name" in kwargs else ""
    self.conversation_id = kwargs["conversation_id"] if "conversation_id" in kwargs else None
    
    # Working directory for file operations
    self.WORKING_DIRECTORY = kwargs["conversation_directory"] if "conversation_directory" in kwargs else os.path.join(os.getcwd(), "WORKSPACE")
    
    # Extension-specific settings from agent configuration
    self.settings = kwargs  # Contains any additional extension-specific settings
```

## AGiXT SDK Integration

Extensions can leverage the AGiXT SDK ([PyPI](https://pypi.org/project/agixtsdk) | [GitHub](https://github.com/AGiXT/python-sdk)) to interact with core AGiXT functionality. The SDK is automatically injected via `self.ApiClient` and initialized with the user's context.

### Common SDK Operations

```python
# Prompt the agent for analysis or reasoning
response = self.ApiClient.prompt_agent(
    agent_name=self.agent_name,
    prompt_name="Think About It",
    prompt_args={
        "user_input": query,
        "conversation_name": self.conversation_name,
        # Control flags for safe command execution
        "disable_commands": True,    # Prevent recursive command execution
        "log_user_input": False,     # Skip logging internal queries
        "log_output": False,         # Skip logging internal responses
        "browse_links": False,       # Disable link browsing
        "websearch": False,          # Disable web searches
        "analyze_user_input": False, # Skip automatic data analysis
        "tts": False,               # Disable text-to-speech
    }
)

# Store information in agent's memory
self.ApiClient.learn_text(
    agent_name=self.agent_name,
    user_input=input,
    text=data_to_correlate,
    collection_number=self.conversation_id
)

# Run a predefined chain
result = self.ApiClient.run_chain(
    chain_name="Process Data",
    agent_name=self.agent_name,
    user_input=data,
    chain_args={
        "conversation_name": self.conversation_name
    }
)

# Log a subactivity in the conversation
# A `\n` will separate what is shown to the user (a brief description of what is happening) and more detailed information
# It is important to log subactivities during workflows in commands to keep the user informed about the agent's progress.
self.ApiClient.new_conversation_message(
    role=self.agent_name,
    message=f"[SUBACTIVITY] Creating user account.\nThe user on {url} was created successfully.\nNew user name: {new_user_name}\nPassword: {new_password}",
    conversation_name=self.conversation_name
)
```

### Control Flag Usage Patterns

1. **Inside Commands**

   ```python
   # When executing inside a command, disable recursive features
   response = self.ApiClient.prompt_agent(
       agent_name=self.agent_name,
       prompt_name="Analyze Data",
       prompt_args={
           "user_input": data,
           "disable_commands": True,  # Prevent recursion
           "log_user_input": False,   # Keep logs clean
           "log_output": False,
           "websearch": False,
           "analyze_user_input": False,
       }
   )
   ```

2. **Chain Execution**

   ```python
   # When running chains, you might want to enable certain features
   result = self.ApiClient.run_chain(
       chain_name="Research Task",
       agent_name=self.agent_name,
       user_input=query,
       chain_args={
           "conversation_name": self.conversation_name,
           "websearch": True,      # Enable research capabilities
           "browse_links": True,   # Allow link exploration
           "log_output": True,     # Track chain output
       }
   )
   ```

3. **Data Processing**

   ```python
   # When processing data internally
   analysis = self.ApiClient.prompt_agent(
       agent_name=self.agent_name,
       prompt_name="Process Data",
       prompt_args={
           "user_input": data,
           "analyze_user_input": True,   # Enable data analysis
           "disable_commands": True,     # No commands needed
           "log_user_input": False,      # Internal processing
           "log_output": False,
       }
   )
   ```

### Important SDK Patterns

1. **Context Preservation**
   - Always pass through `self.agent_name` and `self.conversation_name`
   - Use `self.conversation_id` for memory operations
   - Maintain activity tracking with subactivity messages
   - Control flags preserve execution context

2. **Memory Management**
   - Use collection numbers for organizing different types of memories
   - Collection 0: Long-term agent memories
   - Collection 2/3: Positive/negative feedback
   - Custom collections: Extension-specific data

3. **Chain Integration**
   - Extensions can run existing chains
   - Pass relevant context through chain_args
   - Enable/disable features based on chain purpose
   - Consider resource implications when enabling features

4. **Conversation Logging**
   - Log significant operations as subactivities
   - Use consistent activity ID formatting
   - Help maintain conversation context
   - Control logging verbosity with flags

5. **Resource Management**
   - Use control flags to prevent unnecessary operations
   - Disable resource-intensive features when not needed
   - Prevent recursive command execution
   - Maintain clean conversation logs

The SDK provides a comprehensive interface to AGiXT's capabilities, allowing extensions to leverage the full power of the platform while maintaining proper context and security boundaries. Proper use of control flags ensures efficient resource usage and prevents potential issues like recursive command execution or cluttered conversation logs.

### Important Considerations

1. Always use `self.ApiClient` for AGiXT API operations to maintain user context, it is automatically injected into `kwargs`.
2. Use `self.api_key` (user's JWT) for any operations requiring authentication, this is reserved specifically for AGiXT API calls. If using a different API, prepend the `api_key` variable name with the extension name, such as `OURA_API_KEY`.
3. Respect the working directory boundaries for file operations, the agent should not work outside of `self.WORKING_DIRECTORY` at any time. This will contain file operations to the specific conversation.
4. Access extension-specific settings through `kwargs`. These settings are automatically injected and can be used to configure extension behavior.
5. Maintain conversation context for continuity
6. The agent settings are automatically injected into kwargs, `super().__init__(**kwargs)` is not necessary.
7. Log subactivities to provide context and traceability throughout the command executions if there is a workflow that involves multiple steps. This will keep the user informed about the agent's progress as it executes the commands.

### Extension Configuration and Command Availability

The `__init__` method of your extension defines what configuration is required for the extension's commands to become available to agents:

```python
def __init__(self, OURA_API_KEY: str = "", **kwargs):
    """
    Initialize the Oura extension.
    
    Args:
        OURA_API_KEY (str): API key for Oura Ring access
        **kwargs: Additional agent settings
    """
    self.base_uri = "https://api.ouraring.com"
    self.session = requests.Session()
    self.session.headers.update({"Authorization": f"Bearer {OURA_API_KEY}"})
    self.commands = {
        "Get Oura Ring Data": self.get_oura_data,
    } if OURA_API_KEY else {}  # Commands only available with API key
```

Key points about initialization:

- Parameters in `__init__` (except kwargs) become required "agent settings"
- If an extension requires API keys or credentials, declare them as init parameters
- Extensions without init parameters are always available for enabling
- Commands become available only when required settings are provided
- Users must configure these settings in their agent configuration before commands become available

Example agent settings flow:

1. Extension with no init parameters:
   - Commands are immediately available for enabling
   - No configuration required

2. Extension requiring API key (like Oura):
   - Commands are hidden until API key is configured
   - Users see extension listed as available but requiring configuration
   - Once API key is added to agent settings, commands become available
   - The API key is automatically injected via kwargs when extension is used

## Core Extensions Overview

### AGiXT Actions Extension

Provides high-level orchestration and coordination capabilities across other extensions.

**Key Capabilities:**

- Task scheduling and follow-ups
- Deep analysis and reasoning
- Python code execution in sandboxed environment
- Chain generation and management
- OpenAPI extension generation

**Example Use Cases:**

- Complex workflow automation
- Multi-step task execution
- System integration
- Code generation and execution

### Long-term Memory Extension

Implements persistent knowledge storage and retrieval capabilities for AI agents.

**Key Capabilities:**

- Memory database creation and management
- Structured information storage
- Natural language memory retrieval
- Memory correlation and tagging

**Example Use Cases:**

- Knowledge persistence across conversations
- Learning from past interactions
- Information organization and retrieval
- Context maintenance

### GitHub Extension

Enables AI agents to interact directly with GitHub repositories and manage development workflows.

**Key Capabilities:**

- Repository management (cloning, creating, reading contents)
- Issue tracking and management
- Pull request creation and review
- Code modification and improvement
- Branch management
- Automated code fixes and improvements

**Example Use Cases:**

- Automated code reviews
- Issue resolution and PR creation
- Repository maintenance
- Code base improvements
- Documentation updates

### Microsoft 365 Extension

Provides comprehensive integration with Microsoft Office 365 services for enhanced productivity.

**Key Capabilities:**

- Email management (read, send, search)
- Calendar operations (view, create, modify events)
- Todo task management
- Attachment handling

**Example Use Cases:**

- Automated email responses
- Meeting scheduling and coordination
- Task tracking and management
- Document processing

### Google Workspace Extension

Enables AI agents to interact with Google Workspace services for enhanced collaboration and productivity.

**Key Capabilities:**

- Gmail operations (read, send, search)
- Calendar management (view, create, modify events)

**Example Use Cases:**

- Email automation
- Calendar event scheduling
- Meeting coordination
- Task tracking

### Oura Ring Extension

Interfaces with the Oura API to access health and wellness data.

**Key Capabilities:**

- Biometric data retrieval
- Sleep analysis
- Activity tracking
- Wellness metrics

**Example Use Cases:**

- Health data analysis
- Sleep pattern monitoring
- Activity tracking
- Wellness reporting

## Creating New Extensions

### Extension Structure

```python
from Extensions import Extensions

class your_extension(Extensions):
    """
    The Extension Name extension provides [core functionality description].
    
    This extension allows AI agents to:
    - [Key capability 1]
    - [Key capability 2]
    - [Key capability 3]
    
    The extension requires [any prerequisites or configuration].
    AI agents should use this when they need to [usage guidance].
    """
    
    def __init__(self, **kwargs):
        self.commands = {
            "Command Name": self.command_method,
            # Additional commands...
        }
        # Initialize any extension-specific attributes
        self.settings = kwargs
        
    async def command_method(self, arg1: str, arg2: int) -> str:
        """
        Detailed description of what the command does and when it should be used.
        
        This command is particularly useful for:
        - [Use case 1]
        - [Use case 2]
        - [Use case 3]
        
        The AI should use this command when:
        - [Condition 1]
        - [Condition 2]
        
        Args:
            arg1 (str): Description of argument
            arg2 (int): Description of argument
            
        Returns:
            str: Description of return value
            
        Example Usage:
            <execute>
            <name>Command Name</name>
            <arg1>example value</arg1>
            <arg2>123</arg2>
            </execute>
        """
        # Command implementation
```

### Docstring Design

Docstrings are crucial for AGiXT extensions as they serve as the primary guidance for AI agents to understand when and how to use commands. Well-designed docstrings should include:

#### Extension Class Docstring

```python
"""
The Extension Name extension provides [core functionality description].

This extension allows AI agents to:
- [Key capability 1]
- [Key capability 2]
- [Key capability 3]

The extension requires [any prerequisites or configuration].
AI agents should use this when they need to [usage guidance].
"""
```

#### Command Method Docstrings

```python
"""
Detailed description of what the command does and when it should be used.

This command is particularly useful for:
- [Use case 1]
- [Use case 2]
- [Use case 3]

The AI should use this command when:
- [Condition 1]
- [Condition 2]

Args:
    arg1 (str): Description of argument
    arg2 (int): Description of argument
    
Returns:
    str: Description of return value
    
Example Usage:
    <execute>
    <name>Command Name</name>
    <arg1>example value</arg1>
    <arg2>123</arg2>
    </execute>
"""
```

### Key Docstring Principles

1. **Clarity of Purpose**: Clearly state what the extension/command does
2. **Usage Guidance**: Explain when AI agents should use this functionality
3. **Prerequisites**: List any required configuration or setup
4. **Examples**: Provide concrete usage examples
5. **Limitations**: Note any important constraints or limitations
6. **Error Cases**: Document how errors are handled
7. **Context Hints**: Include keywords that help AIs understand relevant contexts

### Interaction Patterns

1. **Command Execution Flow**
   - Commands are discovered and loaded dynamically from extensions
   - AI agents analyze docstrings to determine appropriate command usage
   - Commands are executed through formatted XML tags
   - Results are captured and can influence further actions
   - Multiple commands can be chained together

2. **Context Management**
   - Extensions can access conversation and agent context
   - Working directories are managed per conversation
   - File operations are sandboxed to specific directories
   - Resource cleanup is handled automatically

3. **State Handling**
   - Extensions maintain their own state
   - Configuration is passed through kwargs
   - Credentials and tokens are managed securely
   - Retry logic handles transient failures

4. **Response Processing**
   - Commands return structured output
   - Outputs can be processed before user display
   - Results can trigger additional commands
   - Error states are captured and handled

### Best Practices

1. **Clean Interface Design**
   - Provide intuitive command names
   - Use clear method signatures with type hints
   - Include comprehensive docstrings
   - Handle errors gracefully

2. **State Management**
   - Initialize required attributes in `__init__`
   - Handle authentication and connections properly
   - Manage resources efficiently
   - Implement proper cleanup

3. **Error Handling**
   - Implement retry logic for transient failures
   - Provide clear error messages
   - Log errors appropriately
   - Gracefully degrade functionality when possible

4. **Data Transformation**
   - Convert between API formats and AI-friendly formats
   - Handle different data types appropriately
   - Format output for readability
   - Validate input/output data

5. **Documentation**
   - Document command purposes and usage
   - Provide example use cases
   - Include parameter descriptions
   - Document any required configuration

### Extension Integration Patterns

### Security Considerations

1. **API Key Management**
   - Store credentials securely
   - Use environment variables
   - Implement proper access controls
   - Rotate credentials regularly

2. **Code Execution**
   - Use sandboxed environments (e.g., Docker)
   - Implement resource limits
   - Validate input code
   - Monitor execution

3. **Data Privacy**
   - Handle sensitive data appropriately
   - Implement proper access controls
   - Follow data protection regulations
   - Secure data transmission

## Extension Examples

### Basic Extension Template

```python
class example_extension(Extensions):
    """
    The Example Extension provides a template for creating new extensions.
    """
    def __init__(self, EXAMPLE_API_KEY: str = "", **kwargs):
        self.example_api_key = EXAMPLE_API_KEY  # Extension-specific API key
        self.client = None
        self.commands = {
            "Do Something": self.do_something,
        }
    
    async def do_something(self, input: str) -> str:
        """
        Do something with the input.
        
        Args:
            input (str): The input to process
            
        Returns:
            str: The processed result
        """
        try:
            # Command implementation
            return result
        except Exception as e:
            logging.error(f"Error in do_something: {str(e)}")
            return f"Error: {str(e)}"
```

## Best Practices for Extension Commands

1. **Command Naming**
   - Use clear, descriptive names
   - Follow consistent naming conventions
   - Indicate command purpose
   - Use natural language when possible

2. **Parameter Design**
   - Use appropriate data types
   - Provide default values when sensible
   - Use clear parameter names
   - Document parameter constraints

3. **Return Values**
   - Return consistent data types
   - Provide informative responses
   - Handle errors gracefully
   - Include operation status

4. **Documentation**
   - Describe command purpose
   - Document parameters
   - Provide usage examples
   - Include error conditions
