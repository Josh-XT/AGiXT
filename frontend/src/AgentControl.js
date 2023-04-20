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
import { URIContext } from "./App";
const AgentControls = ({agent, data, toggleRunning}) => {
  const baseURI = useContext(URIContext);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshInteval, setRefreshInterval] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [tabValue, setTabValue] = useState(0);
  const [objective, setObjective] = useState("");
  const [instruction, setInstruction] = useState("");

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const InstructAgent = async (instruction) => {
    const response = await fetch(`${baseURI}/api/instruct/${agent}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt: instruction,
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
      <Tabs value={tabValue} onChange={handleTabChange} sx={{mb: "1rem"}}>
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
          {refreshInteval ? (
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