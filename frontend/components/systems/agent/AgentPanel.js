import { useState } from "react";
import {
  Tab,
  Tabs
} from "@mui/material";
import { useRouter } from "next/router";
import AgentChat from "./tabs/AgentChat";
import AgentInstruct from "./tabs/AgentInstruct";
import AgentAdmin from "./tabs/AgentAdmin";
import AgentTask from "./tabs/AgentTask";
import AgentConfigure from "./tabs/AgentConfigure";
import { useTheme } from "@mui/material/styles";
export default function AgentPanel() {
  const router = useRouter();
  console.log(router.query.config);
  const [tab, setTab] = useState(router.query.config=="true"?3:0);
  const handleTabChange = (event, newTab) => {
    setTab(newTab);
  };
  const theme = useTheme();
  const tabs = [
    <AgentChat key="chat" />,
    <AgentInstruct key="instruct" />,
    <AgentTask key="task" />,
    <AgentConfigure key="admin" />,
    <AgentAdmin key="admin" />
  ];
  return (
    <>
      <Tabs value={tab} onChange={handleTabChange} TabIndicatorProps={{ style: { background: theme.palette.mode == "dark"?"#FFF":"#000" } }} sx={{ mb: "0.5rem" }} textColor={theme.palette.mode == "dark"?"white":"black"}>
        <Tab label="Chat With Agent" />
        <Tab label="Instruct Agent" />
        <Tab label="Task Agent" />
        <Tab label="Configure Agent" />
        <Tab label="Administrate Agent" />
      </Tabs>
      {tabs[tab]}
    </>
  );
};
