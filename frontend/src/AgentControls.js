import React, { useState, useEffect } from "react";
import {
  Typography,
  Box,
  Paper,
  TextField,
  Button,
  Switch,
  FormGroup,
  FormControlLabel,
  Tab,
  Tabs,
} from "@mui/material";

const AgentControls = ({ darkMode, handleToggleDarkMode, selectedAgent }) => {
  const [objective, setObjective] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [tabValue, setTabValue] = useState(0);
  const [baseURI, setBaseURI] = useState("");

  async function getBaseURI() {
    try {
      const response = await fetch("http://127.0.0.1:5000");
      if (response.ok) {
        return "http://127.0.0.1:5000";
      }
    } catch (error) {
      console.warn("Local endpoint not accessible:", error);
    }
    return "";
  }

  useEffect(() => {
    async function setURI() {
      setBaseURI(await getBaseURI());
    }
    setURI();
  }, []);

  const run = async () => {
    // Set the objective
    await fetch(`${baseURI}/api/set_objective`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ objective }),
    });
  
    while (true) {
      // Execute the next task
      const response = await fetch(`${baseURI}/api/execute_next_task`);
      const data = await response.json();
  
      if (!data.task || !data.result) {
        setChatHistory((prevChatHistory) => [
          ...prevChatHistory,
          '*****ALL TASKS COMPLETE*****',
        ]);
        break;
      }
  
      setChatHistory((prevChatHistory) => [
        ...prevChatHistory,
        `*****TASK LIST*****\n${data.task_list.map((task, index) => `${index + 1}. ${task.task_name}`).join('\n')}`,
        `*****NEXT TASK*****\n${data.task.task_id}: ${data.task.task_name}`,
        `*****RESULT*****\n${data.result}`,
      ]);    
  
      await new Promise((resolve) => setTimeout(resolve, 1000)); // Sleep for 1 second
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const InstructAgent = async (instruction) => {
    // Call the Instruct API endpoint with the given instruction
    const response = await fetch(`${baseURI}/api/instruct`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt: instruction,
        data: {
          agent_name: selectedAgent,
          commands_enabled: true,
        },
      }),
    });
    
    const data = await response.json();
    const output = data.response;
    // Update the chat history with the instruction and the response
    setChatHistory((prevChatHistory) => [
      ...prevChatHistory,
      `You: ${instruction}`,
      `Agent: ${output}`,
    ]);
  };

  const InstructionInput = (props) => {
    const [instruction, setInstruction] = useState("");

    const handleInstructionChange = (event) => {
      setInstruction(event.target.value);
    };

    const handleKeyPress = async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await InstructAgent(instruction);
        setInstruction("");
      }
    };

    return (
      <TextField
        {...props}
        value={instruction}
        onChange={handleInstructionChange}
        onKeyPress={handleKeyPress}
      />
    );
  };

  const handleSendInstruction = async () => {
    const instructionInput = document.getElementById("instructionInput");
    await InstructAgent(instructionInput.value);
    instructionInput.value = "";
  };

  return (
    <>
      <FormGroup>
        <FormControlLabel
          control={
            <Switch checked={darkMode} onChange={handleToggleDarkMode} />
          }
          label="Toggle Dark Mode"
        />
      </FormGroup>
      <Tabs value={tabValue} onChange={handleTabChange}>
        <Tab label="Task Manager" />
        <Tab label="Instruct" />
      </Tabs>
      {tabValue === 0 && (
        <>
          <TextField
            fullWidth
            label="Enter Objective"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            sx={{ mb: 2 }}
          />
          <Button variant="contained" color="primary" onClick={run} fullWidth>
            Start Task
          </Button>
        </>
      )}
      {tabValue === 1 && (
        <>
          <InstructionInput
            fullWidth
            label="Enter Instruction"
            placeholder="Type instruction"
            id="instructionInput"
            sx={{ mb: 2 }}
          />
          <Button
            variant="contained"
            color="primary"
            onClick={handleSendInstruction}
            fullWidth
          >
            Send Instruction
          </Button>
        </>
      )}
      <Box mt={2} p={2} bgcolor="background.paper" borderRadius={1}>
        <Typography variant="h6" gutterBottom>
          Chat History
        </Typography>
        <Paper
          elevation={3}
          style={{ padding: "16px", maxHeight: "300px", overflowY: "auto" }}
        >
          {chatHistory.map((message, index) => (
            <Typography key={index} gutterBottom>
              {message}
            </Typography>
          ))}
        </Paper>
      </Box>
    </>
  );
};

export default AgentControls;