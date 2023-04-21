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
import AgentChat from "./AgentChat";
import AgentObjective from "./AgentObjective";
export default function AgentPanel () {
  const [chatHistory, setChatHistory] = useState([]);
  const [tab, setTab] = useState(0);
  const [instruction, setInstruction] = useState("");

  const handleTabChange = (event, newTab) => {
    setTab(newTab);
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

  const tabs = [
    <AgentChat />,
    <AgentObjective />
  ];
  return (
    <>
      <Tabs value={tab} onChange={handleTabChange} sx={{mb: "0.5rem"}}>
        <Tab label="Chat With Agent" />
        <Tab label="Provide Agent With Objective" />
      </Tabs>
        {tabs[tab]}
    </>
  );
};
