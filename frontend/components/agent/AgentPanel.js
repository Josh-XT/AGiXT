import { useState } from "react";
import {
  Tab,
  Tabs
} from "@mui/material";
import AgentChat from "./AgentChat";
import AgentObjective from "./AgentObjective";
import AgentInstruct from "./AgentInstruct";
export default function AgentPanel () {
  const [tab, setTab] = useState(0);

  const handleTabChange = (event, newTab) => {
    setTab(newTab);
  };

  const tabs = [
    <AgentChat />,
    <AgentInstruct />,
    <AgentObjective />
  ];
  return (
    <>
      <Tabs value={tab} onChange={handleTabChange} sx={{mb: "0.5rem"}}>
        <Tab label="Chat With Agent" />
        <Tab label="Instruct Agent" />
        <Tab label="Provide Agent With Objective" />
      </Tabs>
        {tabs[tab]}
    </>
  );
};
