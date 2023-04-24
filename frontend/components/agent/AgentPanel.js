import { useState } from "react";
import {
  Tab,
  Tabs
} from "@mui/material";
import AgentChat from "./AgentChat";
import AgentObjective from "./AgentObjective";
import AgentInstruct from "./AgentInstruct";
import AgentAdmin from "./AgentAdmin";
export default function AgentPanel() {
  const [tab, setTab] = useState(0);

  const handleTabChange = (event, newTab) => {
    setTab(newTab);
  };

  const tabs = [
    <AgentChat key="chat" />,
    <AgentInstruct key="instruct" />,
    <AgentAdmin key="admin" />
  ];
  return (
    <>
      <Tabs value={tab} onChange={handleTabChange} sx={{ mb: "0.5rem" }}>
        <Tab label="Chat With Agent" />
        <Tab label="Instruct Agent" />
        <Tab label="Administrate Agent" />
      </Tabs>
      {tabs[tab]}
    </>
  );
};
