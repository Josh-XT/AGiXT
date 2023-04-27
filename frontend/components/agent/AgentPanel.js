import { useState } from "react";
import {
  Tab,
  Tabs
} from "@mui/material";
import AgentChat from "./AgentChat";
import AgentObjective from "./AgentObjective";
import AgentInstruct from "./AgentInstruct";
import AgentAdmin from "./AgentAdmin";
import { useTheme } from "@mui/material/styles";
export default function AgentPanel() {
  const [tab, setTab] = useState(0);

  const handleTabChange = (event, newTab) => {
    setTab(newTab);
  };
  const theme = useTheme();
  const tabs = [
    <AgentChat key="chat" />,
    <AgentInstruct key="instruct" />,
    <AgentObjective key="objective" />,
    <AgentAdmin key="admin" />
  ];
  return (
    <>
      <Tabs value={tab} onChange={handleTabChange} TabIndicatorProps={{ style: { background: theme.palette.mode == "dark"?"#FFF":"#000" } }} sx={{ mb: "0.5rem" }} textColor={theme.palette.mode == "dark"?"white":"black"}>
        <Tab label="Chat With Agent" />
        <Tab label="Instruct Agent" />
        <Tab label="Set Agent Objective" />
        <Tab label="Administrate Agent" />
      </Tabs>
      {tabs[tab]}
    </>
  );
};
