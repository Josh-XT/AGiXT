import { useState } from "react";
import {
  Tab,
  Tabs
} from "@mui/material";
import ChainSteps from "./ChainSteps";
import { useTheme } from "@mui/material/styles";
export default function ChainPanel() {
  const [tab, setTab] = useState(0);

  const handleTabChange = (event, newTab) => {
    setTab(newTab);
  };
  const theme = useTheme();
  const tabs = [
    <ChainSteps key="step" />,
  ];
  return (
    <>
      <Tabs value={tab} onChange={handleTabChange} TabIndicatorProps={{ style: { background: theme.palette.mode == "dark"?"#FFF":"#000" } }} sx={{ mb: "0.5rem" }} textColor={theme.palette.mode == "dark"?"white":"black"}>
        <Tab label="Configure Chain Steps" />
      </Tabs>
      {tabs[tab]}
    </>
  );
};
