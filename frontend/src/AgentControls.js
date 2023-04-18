import React, { useState, useEffect } from "react";
import {
  Typography,
  Box,
  Paper,
  TextField,
  Button,
  Tab,
  Tabs,
} from "@mui/material";
import AgentCommandsList from "./AgentCommandsList";

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

  const run = async () => {
    // Set the objective
    const setObjResponse = await fetch(`${baseURI}/api/set_objective`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ objective }),
    });
  
    const setObjData = await setObjResponse.json();
    setChatHistory((prevChatHistory) => [
      ...prevChatHistory,
      `Setting Objective: ${objective}`,
      `Endpoint Response: ${JSON.stringify(setObjData)}`,
    ]);
  
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
        `Endpoint Response: ${JSON.stringify(data)}`, // Add this line to log the endpoint response
      ]);
  
      await new Promise((resolve) => setTimeout(resolve, 1000)); // Sleep for 1 second
    }
  };
  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const InstructAgent = async (instruction) => {
    // Call the Instruct API endpoint with the given instruction
    const response = await fetch(`${baseURI}/api/instruct/${selectedAgent}/true`, {
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
    // Update the chat history with the instruction and the response
    setChatHistory((prevChatHistory) => [
      ...prevChatHistory,
      `You: ${instruction}`,
      `Agent: ${output}`,
    ]);
  };

  const handleKeyPress = async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      await InstructAgent(instruction);
      setInstruction("");
    }
  };

  const handleSendInstruction = async () => {
    await InstructAgent(instruction);
    setInstruction("");
  };

  return (
    <>
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
          <Button
            variant="contained"
            color="primary"
            onClick={() => run(selectedAgent)}
            fullWidth
          >
            Start Task
          </Button>
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
      <AgentCommandsList
        commands={commands}
        tabValue={tabValue}
        setObjective={setObjective}
        setInstruction={setInstruction}
        objective={objective}
        instruction={instruction}
      />
      <AgentCommandsList
        commands={commands}
        tabValue={tabValue}
        setObjective={setObjective}
        setInstruction={setInstruction}
      />
    </>
  );
};

export default AgentControls;