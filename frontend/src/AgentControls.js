import React, { useState, useEffect } from "react";
import {
  Typography,
  Box,
  Paper,
  TextField,
  Button,
  Tab,
  Tabs,
  CircularProgress,
} from "@mui/material";

const AgentControls = ({
  darkMode,
  handleToggleDarkMode,
  selectedAgent,
  setChatHistory,
  chatHistory,
  commands,
  tabValue,
  setTabValue,
  objective,
  setObjective,
  instruction,
  setInstruction,
}) => {
  const [baseURI, setBaseURI] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isTaskRunning, setIsTaskRunning] = useState(false);

  async function getBaseURI() {
    try {
      const response = await fetch("http://127.0.0.1:5000/api/docs");
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

  useEffect(() => {
    const getOutput = async () => {
      if (isTaskRunning) {
        setIsLoading(true);
        const response = await fetch(`${baseURI}/api/task/output/${selectedAgent}`);
        const data = await response.json();
        console.log(data)
        if (data.output && data.output.length > 0) {
          setChatHistory((prevChatHistory) => [
            ...prevChatHistory,
            ...data.output.map((output) => `Output: ${output}`),
          ]);
        }
  
        setIsLoading(false);
        setTimeout(getOutput, 2000);
      }
    };
  
    getOutput();
    return () => clearTimeout(getOutput);
  }, [isTaskRunning, baseURI, setChatHistory, chatHistory, selectedAgent]);

  const startTask = async () => {
    setIsTaskRunning(true);
    await fetch(`${baseURI}/api/task/start/${selectedAgent}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ objective: objective }),
    });
  };

  const stopTask = async () => {
    setIsTaskRunning(false);
    await fetch(`${baseURI}/api/task/stop/${selectedAgent}`, { method: "POST" });
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const InstructAgent = async (instruction, agent_name) => {
    const response = await fetch(`${baseURI}/api/instruct`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt: instruction,
        agent_name: agent_name,
      }),
    });

    const data = await response.json();
    const output = data.response;
    setChatHistory((prevChatHistory) => [
      ...prevChatHistory,
      `You: ${instruction}`,
      `Agent: ${output}`,
    ]);
  };

  const handleKeyPress = async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await InstructAgent(instruction, selectedAgent);
      setInstruction("");
    }
  };

  const handleSendInstruction = async () => {
    await InstructAgent(instruction, selectedAgent);
    setInstruction("");
  };

  return (
    <>
      {isLoading && (
        <Box display="flex" justifyContent="center" mt={2}>
          <CircularProgress />
        </Box>
      )}
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
          {isTaskRunning ? (
            <Button
              variant="contained"
              color="secondary"
              onClick={stopTask}
              fullWidth
            >
              Stop Task
            </Button>
          ) : (
            <Button
              variant="contained"
              color="primary"
              onClick={startTask}
              fullWidth
            >
              Start Task
            </Button>
          )}
        </>
      )}
      {tabValue === 1 && (
        <>
          <TextField
            fullWidth
            label="Enter Instruction"
            placeholder="Type instruction"
            id="instructionInput"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyPress={handleKeyPress}
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
            <pre key={index} style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              {message}
            </pre>
          ))}
        </Paper>
      </Box>
    </>
  );
};

export default AgentControls;