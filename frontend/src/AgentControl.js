import { useState, useContext } from "react";
import {
  Typography,
  Box,
  Paper,
  TextField,
  Button,
  Tab,
  Tabs
} from "@mui/material";
import { URIContext } from "./App";
const AgentControl = ({agent, data, running, toggleRunning, objective, setObjective}) => {
  const baseURI = useContext(URIContext);
  const [chatHistory, setChatHistory] = useState([]);
  const [tabValue, setTabValue] = useState(0);
  const [instruction, setInstruction] = useState("");

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const InstructAgent = async (instruction) => {
    const response = (await (await fetch(`${baseURI}/api/instruct/${agent}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt: instruction,
      }),
    })).json()).response;

    setChatHistory((prevChatHistory) => [
      ...prevChatHistory,
      `You: ${instruction}`,
      `Agent: ${response}`,
    ]);
  };

  const handleKeyPress = async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleSendInstruction();
    }
  };

  const handleSendInstruction = async () => {
    await InstructAgent(instruction, agent);
    setInstruction("");
  };

  console.log(data);

  return (
    <>
      <Tabs value={tabValue} onChange={handleTabChange} sx={{mb: "0.5rem"}}>
        <Tab label="Objective Management" />
        <Tab label="Instruct Agent" />
      </Tabs>
      <Box sx={{display: "flex", flexDirection: "column", height: "100%"}}>
      {tabValue === 0 && (
        <>
          <TextField
            fullWidth
            label="Agent Objective"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            sx={{ mb: 2 }}
          />
          <Button

              variant="contained"
              color="primary"
              onClick={toggleRunning}
              fullWidth
            >
              {running?"Stop":"Start"} Task
            </Button>

        </>
      )}
      {tabValue === 1 && (
        <>
          <TextField
            fullWidth
            label="Enter Instruction for Agent"
            placeholder="Instruction..."
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
            Instruct Agent
          </Button>
        </>
      )}
      <Typography variant="h6" gutterBottom>
          {tabValue === 0?"Objective Work Log":"Instruction Chat History"}
        </Typography>
        <Paper
          elevation={3}
          sx={{ flexGrow: 1, padding: "0.5rem", overflowY: "auto" }}
        >
          {(tabValue===0?data:chatHistory).map((message, index) => (
            <pre key={index} style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              {message}
            </pre>
          ))}
        </Paper>

      </Box>
    </>
  );
};

export default AgentControl;